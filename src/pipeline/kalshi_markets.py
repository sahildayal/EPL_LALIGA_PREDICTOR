"""
Normalises Kalshi soccer markets into the shape the edge engine expects.

Series tickers are matched EXACTLY, never by prefix. `KXLALIGA2*` is LaLiga 2 —
the Spanish second division — so a prefix match on `KXLALIGA` silently pulls in
fixtures we have neither ratings nor sharp lines for, and we would price them
against La Liga fair values. Verified live against /trade-api/v2/series.
"""
import re

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


def parse_teams(market: dict) -> tuple:
    """Extracts (home, away) canonical names, or (None, None) if unresolvable."""
    for field in ("title", "event_title", "rules_primary"):
        text = market.get(field) or ""
        m = re.search(r"([A-Za-z .'&-]+?)\s+(?:vs\.?|at|@)\s+([A-Za-z .'&-]+)", text)
        if not m:
            continue
        try:
            return canonical(m.group(1).strip()), canonical(m.group(2).strip())
        except UnknownTeam:
            continue
    return None, None


def _selection_1x2(market: dict, home: str, away: str):
    sub = (market.get("yes_sub_title") or market.get("subtitle") or market.get("title") or "").lower()
    if "draw" in sub or "tie" in sub:
        return "draw"
    try:
        if canonical(sub.replace("win", "").strip()) == home:
            return "home"
        if canonical(sub.replace("win", "").strip()) == away:
            return "away"
    except UnknownTeam:
        pass
    if home.split()[0] in sub:
        return "home"
    if away.split()[0] in sub:
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
