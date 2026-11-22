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
  * it counts as FILLED only if Kalshi's public trade tape shows a trade on our
    side of the contract at a price STRICTLY BELOW L between posting and
    kickoff (agreed 2026-11-22). Someone selling below our bid means our order,
    resting at a better price, would have been matched first, whatever our
    queue position. Trades AT L are ignored: others may have been ahead of us.
    That makes E's fill rate a lower bound, never an overstatement;
  * a filled order becomes an ordinary bet at price L and settles like any
    other; an unfilled one is refunded and excluded from every metric.

Fills are judged at settle time, after kickoff, from the tape, so they cost no
Odds API credits. Fees: Kalshi's maker coefficient is 0.0175 (a quarter of the
0.07 taker rate) on series listed with maker fees, which includes every *GAME
series; it is applied to every market here, which overstates E's cost on the
totals/BTTS series that charge makers nothing. Like every other arm, realised
P&L does not deduct fees; the estimate is recorded on each bet.
"""
import math
from datetime import datetime, timezone

from src.market.edge import build_opportunities
from src.market.fees import maker_fee_as_fraction_of_payout
from src.market.grading import Bet, is_no_side

MIN_EDGE = 0.02
FLAT_FRACTION = 0.01
MAX_ORDERS = 12
MIN_PRICE, MAX_PRICE = 0.05, 0.95          # same price bounds as filter_bettable


def _floor_cent(x: float) -> float:
    return math.floor(x * 100.0 + 1e-9) / 100.0


def limit_price(fair: float, bid, ask: float):
    """The price E would rest at, or None when no price both clears the bar and rests."""
    # The highest price that still clears the bar after the maker fee. The fee
    # depends on the price, so step down a cent at a time from the naive cap.
    cap = _floor_cent(fair - MIN_EDGE)
    while cap >= MIN_PRICE and fair - cap - maker_fee_as_fraction_of_payout(cap) < MIN_EDGE:
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
        if not o.ticker:
            continue
        price = limit_price(o.fair_prob, o.bid, o.ask)
        if price is None:
            continue
        edge = o.fair_prob - price - maker_fee_as_fraction_of_payout(price)
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
            "fair_prob": o.fair_prob, "net_edge": round(edge, 5),
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


def first_fill(order: dict, trades: list):
    """
    The first trade that proves the order filled, or None.

    `trades` are Kalshi trade-tape rows. Our contract's price is the YES price
    for a YES order and the NO price for a NO order. Only trades after posting
    and before kickoff count, and only STRICTLY below the limit.
    """
    side_key = "no_price_dollars" if is_no_side(order["selection"]) else "yes_price_dollars"
    posted, kickoff = _ts(order.get("posted_utc")), _ts(order.get("kickoff"))
    hits = []
    for t in trades:
        when = _ts(t.get("created_time"))
        try:
            px = float(t.get(side_key))
        except (TypeError, ValueError):
            continue
        if when is None or posted is None or kickoff is None:
            continue
        if posted <= when < kickoff and px < float(order["limit"]) - 1e-9:
            hits.append((when, px))
    return min(hits) if hits else None


def resolve_orders(book: dict, fetch_trades, now: datetime = None) -> dict:
    """
    Turns every order whose fixture has kicked off into a bet or a refund.

    `fetch_trades(ticker, min_ts, max_ts)` returns the tape for one market. An
    order whose tape cannot be read stays open and is reported, never guessed.
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
        hit = first_fill(order, trades)
        resolved = dict(order, resolved_utc=now.isoformat())
        if hit:
            bet = Bet(market=order["market"], selection=order["selection"],
                      home=order["home"], away=order["away"], stake=order["stake"],
                      price=order["limit"], line=order.get("line"),
                      league=order.get("league"), kickoff=order.get("kickoff"),
                      fair_prob=order.get("fair_prob"),
                      closing_price=order.get("closing_price"),
                      quoted_ask=order.get("quoted_ask"),
                      fill_contracts=order.get("contracts")).to_dict()
            bet.update(placed_utc=order["posted_utc"], filled_utc=hit[0].isoformat(),
                       fill_through_price=hit[1], order_type="maker",
                       closing_bid=order.get("closing_bid"),
                       maker_fee_est=round(maker_fee_as_fraction_of_payout(order["limit"])
                                           * order["contracts"], 4))
            book["active_bets"].append(bet)
            resolved["status"] = "FILLED"
            out["filled"].append(resolved)
        else:
            book["bankroll"] = round(book["bankroll"] + order["stake"], 2)
            resolved["status"] = "UNFILLED"
            out["unfilled"].append(resolved)
        book.setdefault("order_history", []).append(resolved)
    book["active_orders"] = still
    return out
