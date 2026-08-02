"""
Sharp reference lines from The Odds API (https://the-odds-api.com).

This is the anchor of the 2026/27 strategy. A benchmark over 1,250 real EPL
matches showed no model configuration beating de-vigged Bet365 (0.9512 log loss
vs 0.9564 for the best model), so we do not try to out-predict the market. We
treat a de-vigged sharp consensus as fair value and bet only where Kalshi's
price diverges from it by more than the fee.

Free tier is 500 requests/month. A matchweek needs ~4 (two leagues x two market
groups), so the budget is comfortable — but responses are cached hard anyway,
and remaining quota is surfaced on every call so we notice before running dry.
"""
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from src.data import cache

load_dotenv()

BASE_URL = "https://api.the-odds-api.com/v4"
LEAGUES = {"epl": "soccer_epl", "laliga": "soccer_spain_la_liga"}

# Pinnacle is the sharpest widely-available book and is the preferred reference.
# The others form the consensus fallback when Pinnacle has not posted a line.
SHARP_BOOKS = ["pinnacle", "betfair_sb_uk", "smarkets", "matchbook"]

CACHE_TTL_SECONDS = 3600 * 2      # lines move; two hours is a sane pre-match window


class OddsUnavailable(RuntimeError):
    """
    Raised when sharp odds cannot be retrieved.

    Never fall back to invented prices. Without a reference line there is no
    divergence to measure, and the correct action is to skip the bet.
    """


def _api_key() -> str:
    key = os.getenv("ODDS_API_KEY")
    if not key:
        raise OddsUnavailable(
            "ODDS_API_KEY is not set. Add it to .env locally and to the repository "
            "secrets for the GitHub Actions matchweek job."
        )
    return key


def _request(path: str, params: dict) -> tuple:
    """Returns (payload, quota_remaining). Raises OddsUnavailable on any failure."""
    params = {**params, "apiKey": _api_key()}
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=25)
    except Exception as exc:
        raise OddsUnavailable(f"Odds API request failed: {exc}") from exc

    remaining = resp.headers.get("x-requests-remaining")
    if resp.status_code == 401:
        raise OddsUnavailable("Odds API rejected the key (401). Check ODDS_API_KEY.")
    if resp.status_code == 429:
        raise OddsUnavailable(f"Odds API quota exhausted (429). Remaining: {remaining}")
    if resp.status_code != 200:
        raise OddsUnavailable(f"Odds API returned {resp.status_code}: {resp.text[:200]}")

    try:
        remaining = int(remaining) if remaining is not None else None
    except ValueError:
        remaining = None
    return resp.json(), remaining


# --- De-vigging --------------------------------------------------------------

def devig_multiplicative(odds: dict) -> dict:
    """
    Proportional de-vig: p_i = (1/o_i) / sum(1/o_j).

    Simple and standard, but it distributes the margin evenly across outcomes,
    which systematically overprices longshots (the favourite-longshot bias).
    """
    inv = {k: 1.0 / v for k, v in odds.items() if v and v > 1.0}
    if len(inv) < 2:
        raise OddsUnavailable(f"Need at least two valid prices to de-vig, got {odds}")
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()}


def devig_shin(odds: dict, max_iter: int = 100, tol: float = 1e-10) -> dict:
    """
    Shin (1993) de-vig, which models the margin as compensation for insider
    trading rather than a flat tax. It shades favourites up and longshots down
    relative to the proportional method and is generally better calibrated,
    which matters because we bet on the difference between this and Kalshi.

    Solves for the insider proportion z, then
        p_i = (sqrt(z^2 + 4(1-z) * pi_i^2 / B) - z) / (2(1-z))
    where pi_i are the raw implied probabilities and B their sum.
    """
    inv = {k: 1.0 / v for k, v in odds.items() if v and v > 1.0}
    if len(inv) < 2:
        raise OddsUnavailable(f"Need at least two valid prices to de-vig, got {odds}")

    n = len(inv)
    booksum = sum(inv.values())               # B = sum of raw inverse odds
    if booksum <= 1.0:                        # no margin (or arbitrage): nothing to strip
        return {k: v / booksum for k, v in inv.items()}
    if n == 2:
        # Shin is degenerate for two outcomes (the z solver divides by n-2), and
        # for a two-way book it collapses to the proportional result anyway.
        return devig_multiplicative(odds)

    def p_of(x, z):
        return ((z * z + 4.0 * (1.0 - z) * x * x / booksum) ** 0.5 - z) / (2.0 * (1.0 - z))

    # Solve sum_i p_i(z) = 1. Rearranged, that is
    #   sum_i sqrt(z^2 + 4(1-z) x_i^2 / B) = 2 + (n-2) z
    z = 0.0
    for _ in range(max_iter):
        s = sum((z * z + 4.0 * (1.0 - z) * x * x / booksum) ** 0.5 for x in inv.values())
        z_new = min(0.5, max(0.0, (s - 2.0) / (n - 2)))
        if abs(z_new - z) < tol:
            z = z_new
            break
        z = z_new

    probs = {k: p_of(x, z) for k, x in inv.items()}
    total = sum(probs.values())
    return {k: v / total for k, v in probs.items()}      # renormalise away solver drift


def devig(odds: dict, method: str = "shin") -> dict:
    if method == "shin":
        return devig_shin(odds)
    if method == "multiplicative":
        return devig_multiplicative(odds)
    raise ValueError(f"Unknown de-vig method {method!r}")


# --- Fetching ----------------------------------------------------------------

def _consensus_odds(bookmakers: list, market_key: str) -> tuple:
    """
    Returns (odds_dict, source). Prefers the sharpest available book; falls back
    to the median across all books, which is more robust than the mean to a
    single stale or erroneous line.
    """
    by_book = {}
    for b in bookmakers:
        for m in b.get("markets", []):
            if m.get("key") != market_key:
                continue
            outcomes = {}
            for o in m.get("outcomes", []):
                name = o.get("name")
                point = o.get("point")
                label = f"{name} {point}" if point is not None else name
                outcomes[label] = float(o.get("price", 0) or 0)
            if outcomes:
                by_book[b["key"]] = outcomes

    if not by_book:
        raise OddsUnavailable(f"No bookmaker posted market {market_key!r}")

    for sharp in SHARP_BOOKS:
        if sharp in by_book:
            return by_book[sharp], sharp

    labels = set().union(*(set(o) for o in by_book.values()))
    median_odds = {}
    for label in labels:
        vals = sorted(o[label] for o in by_book.values() if label in o and o[label] > 1.0)
        if vals:
            mid = len(vals) // 2
            median_odds[label] = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
    return median_odds, f"consensus_median_n{len(by_book)}"


def fetch_fair_prices(league: str, markets: str = "h2h", force: bool = False) -> dict:
    """
    Returns fair (de-vigged) probabilities per fixture for one league:

        {"fetched_utc": ..., "quota_remaining": int|None, "fixtures": [
            {"home", "away", "commence_time", "source", "fair": {...}, "raw": {...}}
        ]}

    Raises OddsUnavailable rather than returning partial or invented prices.
    """
    if league not in LEAGUES:
        raise ValueError(f"Unknown league {league!r}; expected one of {sorted(LEAGUES)}")

    cache_key = {"league": league, "markets": markets}
    if not force:
        cached = cache.get("odds_api_fair", cache_key)
        if cached:
            return cached

    payload, remaining = _request(
        f"/sports/{LEAGUES[league]}/odds",
        {"regions": "uk,eu,us", "markets": markets, "oddsFormat": "decimal"},
    )

    fixtures = []
    for ev in payload:
        books = ev.get("bookmakers", [])
        if not books:
            continue
        entry = {
            "home": ev.get("home_team"),
            "away": ev.get("away_team"),
            "commence_time": ev.get("commence_time"),
            "fair": {},
            "raw": {},
            "source": {},
        }
        for market_key in markets.split(","):
            try:
                odds, source = _consensus_odds(books, market_key)
                entry["raw"][market_key] = odds
                entry["fair"][market_key] = devig(odds)
                entry["source"][market_key] = source
            except OddsUnavailable:
                continue          # this market simply is not posted yet
        if entry["fair"]:
            fixtures.append(entry)

    result = {
        "league": league,
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "quota_remaining": remaining,
        "fixtures": fixtures,
    }
    cache.set("odds_api_fair", cache_key, result, ttl_seconds=CACHE_TTL_SECONDS)
    return result


def quota_remaining() -> int:
    """Cheap quota probe against the free /sports endpoint (does not count against usage)."""
    _, remaining = _request("/sports/", {})
    return remaining
