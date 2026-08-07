"""
The four season arms.

Each differs from the flagship in exactly one variable, so May's result is
interpretable rather than merely interesting:

    A  divergence + quarter-Kelly     flagship
    B  divergence + flat 1%           A/B isolates the staking rule
    C  model-only  + quarter-Kelly    A/C isolates the edge source
    D  parlay / SGP                   does the parlay arm clear its own vig?

Arm C is expected to lose. Walk-forward CV found no model beating the market in
any of 32 fold-league combinations, and the market/model blend weight converged
to zero. C is funded anyway because a control that loses is what makes A and B
interpretable — without it, "divergence works" and "we got lucky" look identical.
"""
from dataclasses import dataclass

from src.market import ledger
from src.market.edge import (
    SOURCE_MODEL, build_opportunities, filter_bettable, deduplicate_by_fixture,
)
from src.market.grading import Bet
from src.market.parlay_arm import (
    MIN_LEGS, Parlay, enumerate_parlays, legs_from_opportunities, select_parlays,
)
from src.market.staking import quarter_kelly, flat_stake

# Legs need only be priceable and mildly positive, not independently bettable.
# Arm D exists to test the parlay structure, not to re-test arm A's selections.
PARLAY_LEG_MIN_EDGE = 0.005

ARM_A = "A_divergence_kelly"
ARM_B = "B_divergence_flat"
ARM_C = "C_model_kelly"
ARM_D = "D_parlay"


@dataclass(frozen=True)
class ArmConfig:
    key: str
    label: str
    fair_source: str              # 'sharp' | 'model' — which estimate is fair value
    staking: str                  # 'kelly' | 'flat'
    min_edge: float
    cap: float = 0.03
    flat_fraction: float = 0.01


ARM_CONFIGS = {
    ARM_A: ArmConfig(ARM_A, "Divergence + quarter-Kelly",
                     fair_source="sharp", staking="kelly", min_edge=0.02),
    ARM_B: ArmConfig(ARM_B, "Divergence + flat 1%",
                     fair_source="sharp", staking="flat", min_edge=0.02),
    # Arm C prices the SAME markets off the model rather than the sharp line.
    #
    # An earlier version selected opportunities where no sharp line existed,
    # which was wrong: every market in scope (1X2, totals, BTTS) always has a
    # sharp line, so arm C would have placed zero bets all season and the control
    # would have silently produced no data.
    #
    # It also carries a wider threshold. The model is measurably worse than the
    # market, so a 2-point "edge" against a sharp price is far more likely to be
    # model error than opportunity.
    ARM_C: ArmConfig(ARM_C, "Model-only + quarter-Kelly",
                     fair_source="model", staking="kelly", min_edge=0.04),
    # Arm D's threshold is 5% and is NOT to be lowered to make it bet more.
    #
    # A dry run over five fixtures with an unusually generous 5-6c per-leg
    # divergence produced zero qualifying parlays: once the same-game
    # correlation is priced into the ask as well as the probability (see
    # parlay_arm.price_parlay), Kalshi's per-leg fee eats the compounded edge.
    # Real divergences run nearer 1-4c, so this arm may bet rarely or never.
    #
    # That is the answer, not a malfunction. "The parlay structure essentially
    # never clears its own compounded vig" is exactly what arm D was funded to
    # find out. Tuning the threshold downward until the arm starts betting would
    # replace that finding with one about the threshold.
    ARM_D: ArmConfig(ARM_D, "Parlay / SGP",
                     fair_source="sharp", staking="kelly", min_edge=0.05),
}


def _to_bet(opp, stake: float, league=None) -> Bet:
    return Bet(
        market=opp.market, selection=opp.selection,
        home=opp.home, away=opp.away,
        stake=stake, price=opp.ask, line=opp.line,
        league=league or opp.league, kickoff=opp.kickoff,
        model_prob=opp.model_prob, fair_prob=opp.fair_prob,
    )


def plan_arm(arm: str, kalshi_markets: list, fair_by_fixture: dict,
             model_probs: dict = None, state: dict = None,
             max_bets: int = 12, score_matrices: dict = None) -> list:
    """
    Produces this matchweek's staking plan for one arm. Does not write anything.

    Returns a list of {opportunity, stake_plan, bet} for bets that clear the
    arm's threshold, capped at max_bets to bound concurrent exposure. Arm D
    returns {parlay, stake_plan} instead — see plan_parlay_arm.
    """
    cfg = ARM_CONFIGS[arm]
    state = state or ledger.load_state()
    if arm == ARM_D:
        return plan_parlay_arm(kalshi_markets, fair_by_fixture,
                               score_matrices=score_matrices, state=state)
    book = state["arms"][arm]
    bankroll = book["bankroll"]
    starting = book["starting_bankroll"]

    if cfg.fair_source == "model":
        # Price everything off the model by withholding the sharp line entirely,
        # so arm C answers "what if we trusted the model?" on the same fixtures
        # arm A sees — rather than only on fixtures arm A ignores.
        opps = build_opportunities(kalshi_markets, {}, model_probs,
                                   allow_model_priced=True)
    else:
        opps = build_opportunities(kalshi_markets, fair_by_fixture, model_probs,
                                   allow_model_priced=False)

    opps = deduplicate_by_fixture(filter_bettable(opps, min_edge=cfg.min_edge))

    # Never stake a fixture+market this arm already holds.
    #
    # deduplicate_by_fixture only looks within a single run. Re-running a failed
    # Friday job, or any overlap between weekly windows, would otherwise place a
    # second bet on the same outcome and silently double the per-fixture cap the
    # staking rules are supposed to enforce.
    held = {(b.get("home"), b.get("away"), b.get("market"))
            for b in book.get("active_bets", [])}
    opps = [o for o in opps if (o.home, o.away, o.market) not in held]

    plans, running = [], bankroll
    for opp in opps[:max_bets]:
        if cfg.staking == "kelly":
            sp = quarter_kelly(opp.fair_prob, opp.ask, running,
                               cap=cfg.cap, min_edge=cfg.min_edge)
        else:
            sp = flat_stake(opp.fair_prob, opp.ask, running, starting,
                            fraction=cfg.flat_fraction, min_edge=cfg.min_edge)
        if not sp.should_bet:
            continue
        # Reserve against the running bankroll so a matchweek cannot commit the
        # same dollar twice across several bets.
        running = round(running - sp.stake, 2)
        plans.append({"opportunity": opp, "stake_plan": sp,
                      "bet": _to_bet(opp, sp.stake)})
        if running <= 0:
            break
    return plans


def plan_parlay_arm(kalshi_markets: list, fair_by_fixture: dict,
                    score_matrices: dict = None, state: dict = None,
                    max_parlays: int = 3) -> list:
    """
    Arm D's plan: a few non-overlapping multi-leg wagers.

    Legs are drawn from the same sharp-anchored opportunities arm A sees, but at
    a LOWER bar than arm A's betting threshold. That is deliberate: requiring
    each leg to be independently bettable would make arm D a near-duplicate of
    arm A's selections, and the season's question is whether the parlay
    STRUCTURE clears its own compounded vig — not whether arm A's picks do.

    Staking is flat, not Kelly. Kelly is superlinearly sensitive to an overstated
    probability, and a parlay's probability is a product of three estimates each
    carrying its own error, so Kelly sizing here would size confidently off the
    least reliable number in the system.
    """
    cfg = ARM_CONFIGS[ARM_D]
    state = state or ledger.load_state()
    book = state["arms"][ARM_D]
    bankroll, starting = book["bankroll"], book["starting_bankroll"]

    opps = filter_bettable(
        build_opportunities(kalshi_markets, fair_by_fixture, allow_model_priced=False),
        min_edge=PARLAY_LEG_MIN_EDGE)
    legs = legs_from_opportunities(opps)
    if len(legs) < MIN_LEGS:
        return []

    # Same rule as the single-bet arms: never re-stake a leg this arm already
    # holds inside an open parlay, or the true exposure to that outcome doubles.
    held = {(l.get("home"), l.get("away"), l.get("market"), l.get("selection"))
            for p in book.get("active_parlays", []) for l in p.get("legs", [])}
    legs = [l for l in legs
            if (l.home, l.away, l.market, l.selection) not in held]

    priced = enumerate_parlays(legs, score_matrices, min_edge=cfg.min_edge)
    chosen = select_parlays(priced, max_parlays=max_parlays)

    plans, running = [], bankroll
    for p in chosen:
        stake = round(starting * cfg.flat_fraction, 2)
        if stake <= 0 or stake > running:
            break
        running = round(running - stake, 2)
        parlay = Parlay(
            legs=p["legs"], stake=stake, fair_prob=p["fair_prob"], ask=p["ask"],
            net_edge=p["net_edge"], is_sgp=p["is_sgp"],
            joint_method=p["joint_method"],
            notes=[f"fee {p['fee_frac']:.4f} of payout across {len(p['legs'])} legs",
                   f"penalty {p['penalty']:.4f} (synthetic ask"
                   + (" + SGP correlation)" if p["is_sgp"] else ")")],
        )
        plans.append({"parlay": parlay, "stake_plan": None, "pricing": p})
    return plans


def place_arm(arm: str, plans: list, state: dict = None) -> dict:
    """Commits a plan to the ledger. Insufficient bankroll stops the arm, never reloads it."""
    owns = state is None
    state = state or ledger.load_state()
    placed, skipped = [], []
    for p in plans:
        try:
            if "parlay" in p:
                placed.append(ledger.place_parlay(arm, p["parlay"], state=state))
            else:
                placed.append(ledger.place_bet(arm, p["bet"], state=state))
        except ledger.InsufficientBankroll as exc:
            skipped.append({"bet": p.get("bet") or p.get("parlay"), "reason": str(exc)})
            break
    if owns:
        ledger.save_state(state)
    return {"arm": arm, "placed": placed, "skipped": skipped}


def plan_all(kalshi_markets: list, fair_by_fixture: dict,
             model_probs: dict = None, state: dict = None,
             score_matrices: dict = None) -> dict:
    """Plans every arm against one shared snapshot of prices and fair values."""
    state = state or ledger.load_state()
    return {
        arm: plan_arm(arm, kalshi_markets, fair_by_fixture, model_probs,
                      state=state, score_matrices=score_matrices)
        for arm in (ARM_A, ARM_B, ARM_C, ARM_D)
    }
