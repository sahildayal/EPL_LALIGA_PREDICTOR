"""
Per-league match dataset built from football-data.co.uk, with point-in-time features.

Two defects in the old pipeline motivate this module:

1. **Train/serve skew.** Training rows carried real season-to-date tables while
   `get_match_features` fabricated them at inference (`htgs = avg_goals * 10`,
   `htp = form * 30`). The model was scored on a distribution it never saw live.

2. **Dead features.** Twelve of the thirty-one features were 99.8% NaN in
   training and median-imputed to a constant, so the model learned nothing from
   them — but they varied at inference, injecting pure noise.

The fix is structural, not cosmetic: `FeatureBuilder` is the *only* way features
are ever produced. Training replays history through it match by match; serving
replays the same history and then asks for the next fixture. There is no second
code path that could drift.

Point-in-time correctness is guaranteed by ordering: `features_for()` reads only
state accumulated from strictly earlier matches, and `update()` is called after.
"""
import io
import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from src.data.canonical_teams import canonical, UnknownTeam, TEAMS

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
LEAGUE_CODES = {"epl": "E0", "laliga": "SP1"}

DATA_DIR = Path(__file__).parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "football_data"
PROCESSED_DIR = DATA_DIR / "processed"

FIRST_SEASON = 2000          # football-data has E0 from 1993 and SP1 from 1995,
                             # but 2000+ keeps the two leagues aligned.


def current_season_start(today=None) -> int:
    """
    Calendar year the in-progress season began in. July is the cutover.

    Both leagues start in August and finish in May, so a fixture in March 2027
    belongs to the season that began in 2026.
    """
    from datetime import datetime, timezone
    today = today or datetime.now(timezone.utc).date()
    return today.year if today.month >= 7 else today.year - 1


# Derived, not pinned. A hardcoded end year would train the model on history up
# to last season and never on the season it is actually betting on — which for a
# season explicitly run as a learning layer defeats the point.
LAST_SEASON = current_season_start()

FORM_WINDOW = 5


def season_codes(first: int = FIRST_SEASON, last: int = LAST_SEASON) -> list:
    """2000 -> '0001', 2025 -> '2526'."""
    return [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(first, last + 1)]


class DatasetUnavailable(RuntimeError):
    """Raised when source data cannot be obtained. Never substitute invented matches."""


# --- Download ---------------------------------------------------------------

def _read_csv_tolerant(text: str) -> pd.DataFrame:
    """
    Reads a football-data CSV that may be ragged.

    Several files gain extra columns partway through the season, so rows are
    wider than the header and the C parser aborts. We pad the header rather than
    passing on_bad_lines='skip': dropping real matches to make a parser happy is
    exactly the kind of silent data loss this rebuild exists to remove.
    """
    try:
        return pd.read_csv(io.StringIO(text))
    except pd.errors.ParserError:
        pass

    import csv as _csv
    rows = list(_csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise DatasetUnavailable("CSV contained no usable rows")

    header, body = rows[0], rows[1:]
    width = max([len(header)] + [len(r) for r in body])
    header = header + [f"_extra_{i}" for i in range(len(header), width)]
    header = [h if h.strip() else f"_blank_{i}" for i, h in enumerate(header)]
    body = [r + [""] * (width - len(r)) for r in body]

    df = pd.DataFrame(body, columns=header)
    return df.apply(lambda s: pd.to_numeric(s, errors="ignore"))


def download_season(league: str, season: str, refresh: bool = False) -> pd.DataFrame:
    """Downloads one league-season, caching the raw CSV on disk."""
    if league not in LEAGUE_CODES:
        raise ValueError(f"Unknown league {league!r}; expected one of {sorted(LEAGUE_CODES)}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{LEAGUE_CODES[league]}_{season}.csv"

    if path.exists() and not refresh:
        return _read_csv_tolerant(path.read_text(encoding="latin-1"))

    url = BASE_URL.format(season=season, code=LEAGUE_CODES[league])
    try:
        resp = requests.get(url, timeout=40)
        resp.raise_for_status()
    except Exception as exc:
        raise DatasetUnavailable(f"Could not download {url}: {exc}") from exc

    path.write_bytes(resp.content)
    return _read_csv_tolerant(resp.content.decode("latin-1"))


def _first_available(row: pd.Series, candidates: list):
    for c in candidates:
        if c in row.index:
            v = row[c]
            if pd.notna(v) and float(v) > 1.0:
                return float(v)
    return np.nan


def load_matches(leagues=("epl", "laliga"), first: int = FIRST_SEASON,
                 last: int = LAST_SEASON, refresh: bool = False) -> pd.DataFrame:
    """
    Returns one tidy frame of every match, canonical team names, harmonised odds.

    Odds preference is Pinnacle > Bet365 > market average, because Pinnacle is
    the sharpest of the three and the whole strategy is anchored on sharp prices.
    """
    frames = []
    for league in leagues:
        for season in season_codes(first, last):
            try:
                # A finished season's file never changes again, so the on-disk
                # cache is authoritative for history. The CURRENT season's file
                # gains rows every week, so it is always re-fetched — serving it
                # from cache is how the model would quietly stop seeing the
                # results it is meant to be learning from.
                is_current = season == season_codes(LAST_SEASON, LAST_SEASON)[0]
                raw = download_season(league, season, refresh=refresh or is_current)
            except DatasetUnavailable:
                continue
            raw = raw[raw["HomeTeam"].notna() & raw["AwayTeam"].notna()].copy()
            if raw.empty:
                continue

            out = pd.DataFrame()
            out["date"] = pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce")
            out["league"] = league
            out["season"] = season
            out["home"] = raw["HomeTeam"].map(lambda n: canonical(n, strict=False))
            out["away"] = raw["AwayTeam"].map(lambda n: canonical(n, strict=False))
            out["home_goals"] = pd.to_numeric(raw["FTHG"], errors="coerce")
            out["away_goals"] = pd.to_numeric(raw["FTAG"], errors="coerce")

            for src, dst in [("HS", "home_shots"), ("AS", "away_shots"),
                             ("HST", "home_sot"), ("AST", "away_sot"),
                             ("HC", "home_corners"), ("AC", "away_corners")]:
                out[dst] = pd.to_numeric(raw[src], errors="coerce") if src in raw.columns else np.nan

            out["odds_h"] = raw.apply(lambda r: _first_available(r, ["PSH", "PSCH", "B365H", "AvgH", "BbAvH"]), axis=1)
            out["odds_d"] = raw.apply(lambda r: _first_available(r, ["PSD", "PSCD", "B365D", "AvgD", "BbAvD"]), axis=1)
            out["odds_a"] = raw.apply(lambda r: _first_available(r, ["PSA", "PSCA", "B365A", "AvgA", "BbAvA"]), axis=1)
            out["odds_over25"] = raw.apply(lambda r: _first_available(r, ["Avg>2.5", "B365>2.5", "BbAv>2.5"]), axis=1)
            out["odds_under25"] = raw.apply(lambda r: _first_available(r, ["Avg<2.5", "B365<2.5", "BbAv<2.5"]), axis=1)

            frames.append(out)

    if not frames:
        raise DatasetUnavailable("No seasons could be loaded.")

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["date", "home_goals", "away_goals"])
    df = df[df["home"] != df["away"]]

    unknown = sorted(set(df["home"]) | set(df["away"]) - set(TEAMS))
    unknown = [t for t in unknown if t not in TEAMS]
    if unknown:
        print(f"Warning: {len(unknown)} unregistered team names in dataset: {unknown[:10]}")

    df["result"] = np.where(df.home_goals > df.away_goals, "H",
                     np.where(df.home_goals < df.away_goals, "A", "D"))
    df["total_goals"] = df.home_goals + df.away_goals
    df["btts"] = ((df.home_goals >= 1) & (df.away_goals >= 1)).astype(int)
    return df.sort_values(["date", "league", "home"]).reset_index(drop=True)


# --- Point-in-time features --------------------------------------------------

@dataclass
class TeamState:
    """Rolling record for one team. Season counters reset at each new season."""
    season: str = ""
    played: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    home_played: int = 0
    home_goals_for: int = 0
    home_goals_against: int = 0
    away_played: int = 0
    away_goals_for: int = 0
    away_goals_against: int = 0
    shots_for: float = 0.0
    shots_against: float = 0.0
    sot_for: float = 0.0
    sot_against: float = 0.0
    goals_for_stat: float = 0.0        # goals in matches where shot data exists,
    goals_against_stat: float = 0.0    # so conversion rates use a consistent base
    corners_for: float = 0.0
    corners_against: float = 0.0
    stat_matches: int = 0
    form_points: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    form_gf: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    form_ga: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    last_date: pd.Timestamp = None

    def roll_season(self, season: str):
        if season != self.season:
            keep_form = (self.form_points, self.form_gf, self.form_ga, self.last_date)
            self.__init__(season=season)          # season counters reset
            # Form and rest carry across the break; they describe the team, not the table.
            self.form_points, self.form_gf, self.form_ga, self.last_date = keep_form


class FeatureBuilder:
    """
    The single source of match features, used identically at train and serve time.

    Usage is strictly: features_for(...) BEFORE update(...) for each match in
    chronological order. That ordering is what makes the features point-in-time.
    """

    def __init__(self):
        self.states = {}

    def _state(self, team: str, season: str) -> TeamState:
        st = self.states.setdefault(team, TeamState(season=season))
        st.roll_season(season)
        return st

    @staticmethod
    def _per_game(total, n, default):
        return float(total) / n if n > 0 else default

    def features_for(self, home: str, away: str, season: str, date) -> dict:
        """Features from state accumulated strictly before this match."""
        date = pd.Timestamp(date)
        h, a = self._state(home, season), self._state(away, season)

        def side(st, prefix, is_home):
            played = st.played
            gf_pg = self._per_game(st.goals_for, played, 1.35)
            ga_pg = self._per_game(st.goals_against, played, 1.35)
            hp = st.home_played if is_home else st.away_played
            hgf = st.home_goals_for if is_home else st.away_goals_for
            hga = st.home_goals_against if is_home else st.away_goals_against
            rest = (date - st.last_date).days if st.last_date is not None else 7
            return {
                f"{prefix}_played": played,
                f"{prefix}_gf_pg": gf_pg,
                f"{prefix}_ga_pg": ga_pg,
                f"{prefix}_gd_pg": gf_pg - ga_pg,
                f"{prefix}_ppg": self._per_game(st.points, played, 1.35),
                f"{prefix}_venue_gf_pg": self._per_game(hgf, hp, gf_pg),
                f"{prefix}_venue_ga_pg": self._per_game(hga, hp, ga_pg),
                f"{prefix}_form_ppg": (sum(st.form_points) / len(st.form_points)) if st.form_points else 1.35,
                f"{prefix}_form_gf": (sum(st.form_gf) / len(st.form_gf)) if st.form_gf else 1.35,
                f"{prefix}_form_ga": (sum(st.form_ga) / len(st.form_ga)) if st.form_ga else 1.35,
                f"{prefix}_shots_pg": self._per_game(st.shots_for, st.stat_matches, 12.0),
                f"{prefix}_shots_against_pg": self._per_game(st.shots_against, st.stat_matches, 12.0),
                f"{prefix}_sot_pg": self._per_game(st.sot_for, st.stat_matches, 4.5),
                f"{prefix}_sot_against_pg": self._per_game(st.sot_against, st.stat_matches, 4.5),
                f"{prefix}_corners_pg": self._per_game(st.corners_for, st.stat_matches, 5.0),
                f"{prefix}_corners_against_pg": self._per_game(st.corners_against, st.stat_matches, 5.0),
                # Shot-quality proxies, standing in for xG. Every free xG feed
                # (Understat, FBref, fotmob) is now blocked, but shots and shots
                # on target are present in the football-data files for all 26
                # seasons and come from the source we already validate against.
                f"{prefix}_shot_accuracy": self._per_game(st.sot_for, st.shots_for, 0.36),
                f"{prefix}_conversion": self._per_game(st.goals_for_stat, st.sot_for, 0.30),
                f"{prefix}_save_rate": 1.0 - self._per_game(st.goals_against_stat, st.sot_against, 0.30),
                f"{prefix}_rest_days": float(min(max(rest, 0), 30)),
            }

        feats = {}
        feats.update(side(h, "h", True))
        feats.update(side(a, "a", False))
        feats["gd_pg_diff"] = feats["h_gd_pg"] - feats["a_gd_pg"]
        feats["ppg_diff"] = feats["h_ppg"] - feats["a_ppg"]
        feats["form_ppg_diff"] = feats["h_form_ppg"] - feats["a_form_ppg"]
        feats["rest_diff"] = feats["h_rest_days"] - feats["a_rest_days"]
        # Early-season flag: the staking rule should be more cautious while the
        # season-to-date table is still mostly prior rather than evidence.
        feats["min_played"] = float(min(feats["h_played"], feats["a_played"]))
        return feats

    def update(self, home: str, away: str, season: str, date,
               home_goals: int, away_goals: int, stats: dict = None):
        """Advances state. Must be called only after features_for for this match."""
        date = pd.Timestamp(date)
        h, a = self._state(home, season), self._state(away, season)
        stats = stats or {}

        hp = 3 if home_goals > away_goals else (1 if home_goals == away_goals else 0)
        ap = 3 if away_goals > home_goals else (1 if home_goals == away_goals else 0)

        for st, gf, ga, pts, is_home in ((h, home_goals, away_goals, hp, True),
                                         (a, away_goals, home_goals, ap, False)):
            st.played += 1
            st.goals_for += int(gf)
            st.goals_against += int(ga)
            st.points += pts
            st.form_points.append(pts)
            st.form_gf.append(int(gf))
            st.form_ga.append(int(ga))
            st.last_date = date
            if is_home:
                st.home_played += 1
                st.home_goals_for += int(gf)
                st.home_goals_against += int(ga)
            else:
                st.away_played += 1
                st.away_goals_for += int(gf)
                st.away_goals_against += int(ga)

        shots = stats.get("home_shots"), stats.get("away_shots")
        if all(pd.notna(x) for x in shots):
            h_sot = float(stats.get("home_sot") or 0.0)
            a_sot = float(stats.get("away_sot") or 0.0)
            h_cor = float(stats.get("home_corners") or 0.0)
            a_cor = float(stats.get("away_corners") or 0.0)

            h.shots_for += float(shots[0]); h.shots_against += float(shots[1])
            a.shots_for += float(shots[1]); a.shots_against += float(shots[0])
            h.sot_for += h_sot; h.sot_against += a_sot
            a.sot_for += a_sot; a.sot_against += h_sot
            h.corners_for += h_cor; h.corners_against += a_cor
            a.corners_for += a_cor; a.corners_against += h_cor
            # Goal counters restricted to stat-bearing matches, so conversion and
            # save rates divide comparable numerators and denominators.
            h.goals_for_stat += int(home_goals); h.goals_against_stat += int(away_goals)
            a.goals_for_stat += int(away_goals); a.goals_against_stat += int(home_goals)
            h.stat_matches += 1
            a.stat_matches += 1


FEATURE_COLUMNS = None      # populated on first build


def build_training_matrix(matches: pd.DataFrame) -> pd.DataFrame:
    """
    Walks matches in chronological order, emitting point-in-time features.

    Each league keeps its own builder: a club's table position means nothing
    across leagues, and mixing them is how the old dataset ended up fitting
    international sides and Premier League clubs in one namespace.
    """
    global FEATURE_COLUMNS
    matches = matches.sort_values("date").reset_index(drop=True)
    builders = {}
    rows = []

    for m in matches.itertuples(index=False):
        fb = builders.setdefault(m.league, FeatureBuilder())
        feats = fb.features_for(m.home, m.away, m.season, m.date)
        rows.append(feats)
        fb.update(
            m.home, m.away, m.season, m.date, m.home_goals, m.away_goals,
            {"home_shots": m.home_shots, "away_shots": m.away_shots,
             "home_sot": m.home_sot, "away_sot": m.away_sot,
             "home_corners": m.home_corners, "away_corners": m.away_corners},
        )

    feat_df = pd.DataFrame(rows)
    FEATURE_COLUMNS = list(feat_df.columns)
    return pd.concat([matches.reset_index(drop=True), feat_df], axis=1)


def build_and_save(leagues=("epl", "laliga"), first: int = FIRST_SEASON,
                   last: int = LAST_SEASON, refresh: bool = False) -> pd.DataFrame:
    """Builds the full dataset and writes it per-league plus combined."""
    matches = load_matches(leagues, first, last, refresh=refresh)
    full = build_training_matrix(matches)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    full.to_csv(PROCESSED_DIR / "matches.csv", index=False)
    for league in leagues:
        sub = full[full.league == league]
        sub.to_csv(PROCESSED_DIR / f"matches_{league}.csv", index=False)
    return full


if __name__ == "__main__":
    # Entry point for the Friday job. The dataset is derived data — 23 MB
    # rebuilt from football-data.co.uk in a couple of minutes — so it is not
    # committed to the repo, and CI regenerates it before staking.
    df = build_and_save()
    print(f"{len(df)} matches across {df.league.nunique()} leagues, "
          f"{df.season.nunique()} seasons, latest {df.date.max().date()}")
