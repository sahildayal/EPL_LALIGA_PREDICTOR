"""
Normalises Kalshi soccer markets into the shape the edge engine expects.

Series tickers are matched EXACTLY, never by prefix. `KXLALIGA2*` is LaLiga 2 —
the Spanish second division — so a prefix match on `KXLALIGA` silently pulls in
fixtures we have neither ratings nor sharp lines for, and we would price them
against La Liga fair values. Verified live against /trade-api/v2/series.
"""
import re
from typing import Optional

from src.data.canonical_teams import canonical, UnknownTeam
from src.market.grading import MARKET_1X2, MARKET_TOTALS, MARKET_BTTS

# Exact series tickers, per league and market. Confirmed present 2026-08-02.
SERIES = {
    "epl": {
        MARKET_1X2: "KXEPLGAME",
        MARKET_TOTALS: "KXEPLTOTAL",
        MARKET_BTTS: "KXEPLBTTS",
    },
    "laliga": {
        MARKET_1X2: "KXLALIGAGAME",
        MARKET_TOTALS: "KXLALIGATOTAL",
        MARKET_BTTS: "KXLALIGABTTS",
    },
}

# Deliberately excluded: second division, halves, spreads, corners, props.
EXCLUDED_PREFIXES = ("KXLALIGA2", "KXEPL1H", "KXEPL2H", "KXLALIGA1H", "KXLALIGA2H")


def all_series_tickers() -> list:
    return [t for league in SERIES.values() for t in league.values()]


def series_lookup() -> dict:
    return {t: (lg, m) for lg, mkts in SERIES.items() for m, t in mkts.items()}


def is_excluded(ticker: str) -> bool:
    return any(ticker.startswith(p) for p in EXCLUDED_PREFIXES)


def _price(market: dict, side: str = "yes"):
    """
    Ask price in dollars. We buy, so the ASK is what we pay — using the last
    trade or the midpoint would overstate every edge by half the spread.
    """
    for key in (f"{side}_ask_dollars", f"{side}_ask"):
        v = market.get(key)
        if v is None:
            continue
        v = float(v)
        return v / 100.0 if v > 1.0 else v      # some endpoints report cents
    return None


def _resolve_trailing(text: str):
    """
    Resolves a team name that may carry trailing title words, or None.

    Kalshi titles read "Arsenal vs Coventry Winner?", so a regex capturing the
    away side also swallows "Winner". Candidates are tried LONGEST FIRST and the
    first hit wins, which is what makes this safe: "Manchester United Winner"
    resolves at "Manchester United" and never reaches the bare "Manchester",
    where it could match a different club.
    """
    parts = text.split()
    for k in range(len(parts), 0, -1):
        try:
            return canonical(" ".join(parts[:k]))
        except UnknownTeam:
            continue
    return None


def parse_teams(market: dict) -> tuple:
    """
    Extracts (home, away) canonical names, or (None, None) if unresolvable.

    Regression: the capture group for the away side is greedy over ordinary
    letters, so Kalshi's "Arsenal vs Coventry Winner?" yielded "Coventry Winner",
    which is not a club. canonical() raised, every field fell through, and EVERY
    1X2 market on the exchange was silently dropped — the pipeline reported
    "Kalshi listed no in-scope markets" and placed nothing, which is
    indistinguishable from the season not having started yet.
    """
    for field in ("title", "event_title", "rules_primary"):
        text = market.get(field) or ""
        m = re.search(r"([A-Za-z .'&-]+?)\s+(?:vs\.?|at|@)\s+([A-Za-z .'&-]+)", text)
        if not m:
            continue
        home = _resolve_trailing(m.group(1).strip())
        away = _resolve_trailing(m.group(2).strip())
        if home and away and home != away:
            return home, away
    return None, None


def _selection_1x2(market: dict, home: str, away: str):
    """
    Which side this contract pays on, or None if it cannot be determined safely.

    Kalshi lists 1X2 as three separate binary markets sharing one title, and the
    side lives ONLY in yes_sub_title ("Arsenal" / "Coventry" / "Tie"). The title
    is therefore useless here — it names both clubs, so matching against it would
    resolve all three contracts of a fixture to the same side.

    Two prior heuristics are deliberately gone. `sub.replace("win", "")` stripped
    the substring anywhere it appeared, mangling any club containing those
    letters. Worse, a fallback matched on the first word of a club's name: for
    "Real Betis vs Real Sociedad" both sides begin "Real", so a contract on the
    away team resolved to "home" and would have staked real conviction on the
    wrong club. Returning None costs one skipped market; guessing costs money.
    """
    sub = (market.get("yes_sub_title") or market.get("subtitle") or "").strip()
    if not sub:
        return None
    low = sub.lower()
    if low in ("tie", "draw") or low.startswith(("tie ", "draw ")):
        return "draw"

    # Trailing "Win"/"Winner" is a title word, not part of the club's name.
    cleaned = re.sub(r"\s+(win|winner)$", "", sub, flags=re.IGNORECASE).strip()
    team = _resolve_trailing(cleaned)
    if team == home:
        return "home"
    if team == away:
        return "away"
    return None


def _line(market: dict):
    for field in ("yes_sub_title", "subtitle", "title", "ticker"):
        text = str(market.get(field) or "")
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def ask_ladder(orderbook: dict) -> list:
    """
    What it costs to BUY YES, cheapest first, as [(price, contracts)].

    Kalshi's book is quoted from both sides: buying YES at price p means matching
    a resting NO order at (1 - p). So the YES ask ladder is derived from the NO
    side, not the YES side — reading `yes_dollars` here would give the resting
    BIDS, i.e. what someone would pay us, which is the wrong side of the spread
    and would make every bet look cheaper than it is.
    """
    book = orderbook.get("orderbook_fp") or orderbook.get("orderbook") or orderbook
    levels = []
    for px, size in (book.get("no_dollars") or []):
        try:
            levels.append((round(1.0 - float(px), 4), float(size)))
        except (TypeError, ValueError):
            continue
    return sorted(levels)


def vwap_fill(ladder: list, budget: float) -> Optional[dict]:
    """
    Walks the book spending `budget` dollars. Returns the fill, or None if the
    book cannot absorb it.

    The quoted ask is only the price of the FIRST contract. A live example: arm C
    wanted 979 contracts of Elche at the quoted $0.30, but only 490 rested there;
    the true fill walked to ~$0.3105. Recording $0.30 would have put a price in
    the ledger that could never have been obtained, and overstated the edge by
    roughly a cent — half the entire 2% edge budget.

    Returning None on a book too thin to fill is deliberate: a partial fill is a
    different bet from the one the staking rule sized, and quietly shrinking the
    stake would override Kelly without saying so.
    """
    if budget <= 0 or not ladder:
        return None
    spent, contracts = 0.0, 0.0
    for price, size in ladder:
        if price <= 0:
            continue
        remaining = budget - spent
        if remaining <= 1e-9:
            break
        affordable = remaining / price
        take = min(size, affordable)
        spent += take * price
        contracts += take
        if take < size:
            break
    if contracts <= 0 or spent <= 0:
        return None
    if spent < budget - 0.01:            # book exhausted before the budget
        return None
    return {"vwap": round(spent / contracts, 6),
            "contracts": round(contracts, 4),
            "spent": round(spent, 4)}


def normalise(raw_markets: list) -> list:
    """
    Converts raw Kalshi market dicts into edge-engine rows.

    Anything we cannot confidently parse is dropped rather than guessed — a
    mis-parsed selection would stake money on the wrong side of a real fixture.
    """
    lookup = series_lookup()
    out = []

    for m in raw_markets:
        ticker = m.get("ticker") or ""
        if is_excluded(ticker):
            continue
        series = m.get("series_ticker") or ticker.split("-")[0]
        if series not in lookup:
            continue
        league, market_type = lookup[series]

        if (m.get("status") or "").lower() not in ("open", "active", ""):
            continue

        home, away = parse_teams(m)
        if not home or not away:
            continue

        ask = _price(m, "yes")
        if ask is None:
            continue

        row = {"home": home, "away": away, "league": league, "market": market_type,
               "ticker": ticker, "ask": ask,
               "kickoff": m.get("occurrence_datetime") or m.get("close_time")}

        if market_type == MARKET_1X2:
            sel = _selection_1x2(m, home, away)
            if not sel:
                continue
            out.append({**row, "selection": sel})

        elif market_type == MARKET_TOTALS:
            line = _line(m)
            if line is None:
                continue
            out.append({**row, "selection": "over", "line": line})
            no_ask = _price(m, "no")
            if no_ask is not None:
                out.append({**row, "selection": "under", "line": line, "ask": no_ask})

        elif market_type == MARKET_BTTS:
            out.append({**row, "selection": "yes"})
            no_ask = _price(m, "no")
            if no_ask is not None:
                out.append({**row, "selection": "no", "ask": no_ask})

    return out
