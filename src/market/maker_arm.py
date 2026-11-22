"""
Arm E: rest a limit order below fair value instead of paying the ask.

Arms A and B buy at the ask, and the ask is where the edge goes: across 1,356
priced markets the median Kalshi ask sat 2-4c worse than the de-vigged sharp
line. Bürgi, Deng & Whelan ("Makers and Takers", CEPR DP20631) find Kalshi
takers lose ~32% on average against ~10% for makers. Arm E tests whether
POSTING the price, rather than taking it, turns the same sharp-anchored view
into positive CLV.

E differs from B in exactly one variable. Same sharp fair value, same 2% net
bar, same flat 1% of the starting bankroll; only the execution changes:

  * the order rests at L = min(best bid + 1c, fair - maker fee - 2c), floored
    to the cent, and only if L is strictly below the ask (otherwise it would
    cross the spread and be a taker trade);
  * it lives until kickoff, holding its stake as collateral, as a real resting
    order would;
  * it fills only from trades on our side of the contract at a price STRICTLY
    BELOW L between posting and kickoff (agreed 2026-11-22), and only for as
    many contracts as those trades add up to. Someone dealing below our bid
    means our order, resting at a better price, would have been matched first,
    whatever our queue position, but only for the size that traded. Trades AT
    L are ignored (others may have been ahead of us), as are block trades and
    trades in the last FILL_CUTOFF before the estimated kickoff;
  * a filled order becomes an ordinary bet at price L and settles like any
    other; a partial fill becomes a smaller bet and refunds the rest; an
    unfilled order is refunded and excluded from every metric.

CLV caveat: a bet's closing_price is the closing ASK, and E enters at or below
the bid, so E's ask-based CLV builds in about half the spread. Compare E with
B on clv_mid_pts (against the closing midpoint) only; the dashboard marks E's
ask-based CLV as not comparable.

Fills are judged at settle time, after kickoff, from the tape, so they cost no
Odds API credits. Fees: Kalshi's maker coefficient is 0.0175 (a quarter of the
0.07 taker rate) on series listed with maker fees, which includes every *GAME
series; it is applied to every market here, which overstates E's cost on the
totals/BTTS series that charge makers nothing. Like every other arm, realised
P&L does not deduct fees; the estimate is recorded on each bet.
"""
import math
from datetime import datetime, timedelta, timezone

from src.market.edge import build_opportunities
from src.market.fees import maker_fee_as_fraction_of_payout
from src.market.grading import Bet, is_no_side

MIN_EDGE = 0.02
FLAT_FRACTION = 0.01
MAX_ORDERS = 12
MIN_PRICE, MAX_PRICE = 0.05, 0.95          # same price bounds as filter_bettable

#: Trades in the last minutes before the ESTIMATED kickoff do not count. Kickoff
#: is derived from Kalshi's resolution time (kalshi_markets.kickoff_from); if
#: that estimate ever runs late, in-play trades on a position that has just gone
#: bad would otherwise read as fills — the most adverse trades there are.
FILL_CUTOFF = timedelta(minutes=10)

#: A partial fill smaller than this is treated as no fill and refunded.
MIN_FILL_DOLLARS = 1.0


def _floor_cent(x: float) -> float:
    return math.floor(x * 100.0 + 1e-9) / 100.0


def limit_price(fair: float, bid, ask: float, penalty: float = 0.0):
    """
    The price E would rest at, or None when no price both clears the bar and rests.

    `penalty` is the opportunity's derivation penalty (edge.DERIVATION_PENALTY
    for BTTS solved from 1X2 + totals), so E clears exactly the bar arm B does.
    It was missing until review: E then rested BTTS orders B would refuse.
    """
    # The highest price that still clears the bar after the maker fee. The fee
    # depends on the price, so step down a cent at a time from the naive cap.
    cap = _floor_cent(fair - penalty - MIN_EDGE)
    while (cap >= MIN_PRICE
           and fair - cap - penalty - maker_fee_as_fraction_of_payout(cap) < MIN_EDGE):
        cap = round(cap - 0.01, 2)
    price = cap if not bid else min(cap, _floor_cent(bid + 0.01))
    if price < MIN_PRICE or price > MAX_PRICE or price >= ask - 1e-9:
        return None
    return round(price, 2)


def plan_orders(kalshi_markets: list, fair_by_fixture: dict, book: dict) -> list:
    """This run's orders for arm E: [{order: dict}]. Writes nothing."""
    opps = build_opportunities(kalshi_markets, fair_by_fixture, allow_model_priced=False)
    candidates = []
    for o in opps:
        # No ticker: no tape to judge a fill by. No kickoff: no end to the
        # order's life, so it would hold its stake forever.
        if not o.ticker or not _ts(o.kickoff):
            continue
        price = limit_price(o.fair_prob, o.bid, o.ask, o.derivation_penalty)
        if price is None:
            continue
        edge = (o.fair_prob - price - o.derivation_penalty
                - maker_fee_as_fraction_of_payout(price))
        candidates.append((edge, price, o))

    # One order per fixture and market, keeping the best edge, and never a
    # market this arm already holds as an order or as a filled bet.
    held = {(r.get("home"), r.get("away"), r.get("market"))
            for r in book.get("active_bets", []) + book.get("active_orders", [])}
    best = {}
    for edge, price, o in sorted(candidates, key=lambda c: c[0], reverse=True):
        key = (o.home, o.away, o.market)
        if key in held:
            continue
        best.setdefault(key, (edge, price, o))

    stake = round(book["starting_bankroll"] * FLAT_FRACTION, 2)
    plans, running = [], book["bankroll"]
    now = datetime.now(timezone.utc).isoformat()
    for edge, price, o in sorted(best.values(), key=lambda c: c[0], reverse=True)[:MAX_ORDERS]:
        if stake > running:
            break
        running = round(running - stake, 2)
        plans.append({"order": {
            "market": o.market, "selection": o.selection, "home": o.home, "away": o.away,
            "line": o.line, "league": o.league, "kickoff": o.kickoff, "ticker": o.ticker,
            "stake": stake, "limit": price, "contracts": round(stake / price, 4),
            "fair_prob": o.fair_prob, "fair_source": o.fair_source,
            "net_edge": round(edge, 5),
            "quoted_bid": o.bid, "quoted_ask": o.ask, "planned_utc": now,
            "label": Bet(market=o.market, selection=o.selection, home=o.home, away=o.away,
                         stake=stake, price=price, line=o.line).label,
        }})
    return plans


def _ts(raw):
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def fill_from_tape(order: dict, trades: list):
    """
    How much of the order the tape proves filled: (first_fill_time, contracts), or None.

    Only trades on OUR side of the contract (the YES price for a YES order, the
    NO price for a NO order), STRICTLY below the limit, after posting and more
    than FILL_CUTOFF before kickoff, count. Their sizes are summed: a trade
    through our price proves our resting order was matched for at most the
    contracts that traded, not for all of it. Review found one 0.63-contract
    print being booked as a full 370-contract fill. Block trades are excluded;
    they are negotiated off the book and prove nothing about it.
    """
    side_key = "no_price_dollars" if is_no_side(order["selection"]) else "yes_price_dollars"
    posted, kickoff = _ts(order.get("posted_utc")), _ts(order.get("kickoff"))
    if posted is None or kickoff is None:
        return None
    end = kickoff - FILL_CUTOFF
    first, size = None, 0.0
    for t in trades:
        if t.get("is_block_trade"):
            continue
        when = _ts(t.get("created_time"))
        try:
            px = float(t.get(side_key))
            n = float(t.get("count_fp") or t.get("count") or 0)
        except (TypeError, ValueError):
            continue
        if when is None or not (posted <= when < end) or px >= float(order["limit"]) - 1e-9:
            continue
        size += n
        first = when if first is None else min(first, when)
    if first is None or size <= 0:
        return None
    return first, min(size, float(order["contracts"]))


def resolve_orders(book: dict, fetch_trades, now: datetime = None) -> dict:
    """
    Turns every order whose fixture has kicked off into a bet, a partial bet, or a refund.

    `fetch_trades(ticker, min_ts, max_ts)` returns the tape for one market. An
    order whose tape cannot be read stays open and is reported, never guessed.
    A partial fill becomes a bet for the filled contracts and refunds the rest.
    Returns {"filled": [...], "unfilled": [...], "errors": [...]}.
    """
    now = now or datetime.now(timezone.utc)
    out = {"filled": [], "unfilled": [], "errors": []}
    still = []
    for order in book.get("active_orders", []):
        ko = _ts(order.get("kickoff"))
        if ko is None or now < ko:
            still.append(order)
            continue
        try:
            trades = fetch_trades(order["ticker"], _ts(order["posted_utc"]), ko)
        except Exception as exc:                                  # noqa: BLE001
            out["errors"].append(f"{order.get('label')}: {type(exc).__name__}: {exc}")
            still.append(order)
            continue
        fill = fill_from_tape(order, trades)
        limit = float(order["limit"])
        filled_stake = round(fill[1] * limit, 2) if fill else 0.0
        resolved = dict(order, resolved_utc=now.isoformat())
        if fill and filled_stake >= MIN_FILL_DOLLARS:
            contracts = round(fill[1], 4)
            bet = Bet(market=order["market"], selection=order["selection"],
                      home=order["home"], away=order["away"], stake=filled_stake,
                      price=limit, line=order.get("line"),
                      league=order.get("league"), kickoff=order.get("kickoff"),
                      fair_prob=order.get("fair_prob"),
                      closing_price=order.get("closing_price"),
                      quoted_ask=order.get("quoted_ask"),
                      fill_contracts=contracts).to_dict()
            bet.update(placed_utc=order["posted_utc"], filled_utc=fill[0].isoformat(),
                       order_type="maker", order_contracts=order["contracts"],
                       closing_bid=order.get("closing_bid"),
                       maker_fee_est=round(maker_fee_as_fraction_of_payout(limit)
                                           * contracts, 4))
            book["active_bets"].append(bet)
            # Refund whatever the tape did not prove filled.
            refund = round(float(order["stake"]) - filled_stake, 2)
            if refund > 0:
                book["bankroll"] = round(book["bankroll"] + refund, 2)
            resolved.update(status="FILLED" if refund <= 0 else "PARTIAL",
                            filled_contracts=contracts, filled_stake=filled_stake)
            out["filled"].append(resolved)
        else:
            book["bankroll"] = round(book["bankroll"] + float(order["stake"]), 2)
            resolved["status"] = "UNFILLED"
            out["unfilled"].append(resolved)
        book.setdefault("order_history", []).append(resolved)
    book["active_orders"] = still
    return out
