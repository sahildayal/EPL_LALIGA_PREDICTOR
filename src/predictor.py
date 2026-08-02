"""
LEGACY — exploratory predictor. NOT on the betting path.

This is the pre-rebuild multi-model ensemble, kept because it is useful for
ad-hoc "who wins A vs B?" questions from the CLI. Nothing here sizes, prices or
grades a bet.

**Its output must never reach the ledger.** The weekly automation
(`src/pipeline/matchweek.py`) does not import this module at all. Bets are
priced off the de-vigged sharp consensus in `src/market/edge.py`, and the only
model on that path is `src/models/dixon_coles.py`, used for arm C — a funded
control that is expected to lose.

That is an empirical finding, not a style preference. Walk-forward CV over 16
seasons in two leagues found no standalone model beating the market in any of
32 fold-league combinations, and a market/model blend weight fitted
walk-forward converged to ZERO model weight in both leagues. Reading a
confident-looking number out of this file and treating it as an edge is the
specific mistake that evidence rules out.

Some paths here still assume international football (national-team Elo,
confederation-era helpers) and are only as correct as the World Cup work that
produced them.
"""
import math
import numpy as np
import pandas as pd
from src.data.scrapers import fbref, news, fixtures, elo_db
from src.data.preprocessor import get_match_features
from src.models.statistical import DixonColesModel, EloModel
from src.models.dixon_coles_decay import DixonColesRegressor
from src.data.team_mapping import normalize_team_name
from src.models.machine_learning import (
    LogisticRegressionModel, SVMModel, GDAModel,
    RandomForestModel, XGBoostModel, NeuralNetworkModel
)

import json
from pathlib import Path

# Default ELO model initialized with our ratings seed
ELO_PREDICTOR = EloModel()
ELO_FILE_PATH = Path(__file__).parent.parent / "data" / "processed" / "elo_ratings.json"

def load_elo():
    """
    Populates ELO_PREDICTOR with live club ratings from ClubElo, plus national
    ratings for legacy international fixtures.

    Ordering matters. The previous implementation loaded elo_ratings.json (which
    holds only national teams) and returned early, leaving the club table
    unreachable — so every EPL/La Liga club fell through to the 1700 default and
    Elo emitted an identical prediction for every club fixture.

    ClubElo is the source of truth for clubs and is refreshed daily. We do not
    persist our own club Elo drift: ClubElo already updates continuously and is
    better calibrated than a hand-rolled K-factor loop.
    """
    loaded_clubs = 0

    # 1. Live club ratings (cached 24h by the scraper).
    try:
        from src.data.scrapers import club_elo
        club_ratings = club_elo.get_club_ratings()
        for t, elo in club_ratings.items():
            ELO_PREDICTOR.set(t, elo)
        loaded_clubs = len(club_ratings)
        _persist_club_snapshot(club_ratings)
    except Exception as exc:
        print(f"Warning: live ClubElo unavailable ({exc}). Falling back to last saved snapshot.")
        loaded_clubs = _load_club_snapshot()

    # 2. National teams occupy a different Elo scale; only used by legacy
    #    international fixtures, and never blended with club ratings.
    for t, elo in elo_db.NATIONAL_TEAM_ELO.items():
        if t not in ELO_PREDICTOR.ratings:
            ELO_PREDICTOR.set(t, elo)

    if loaded_clubs == 0:
        print(
            "Warning: no club Elo ratings loaded. Club predictions will fall back "
            "to the default rating and will not discriminate between teams."
        )


CLUB_ELO_SNAPSHOT_PATH = Path(__file__).parent.parent / "data" / "processed" / "club_elo_snapshot.json"


def _persist_club_snapshot(ratings: dict):
    """Saves the last good ClubElo pull so an API outage degrades gracefully."""
    try:
        CLUB_ELO_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CLUB_ELO_SNAPSHOT_PATH, "w") as f:
            json.dump(ratings, f, indent=2)
    except Exception:
        pass


def _load_club_snapshot() -> int:
    """Loads the last good ClubElo pull. Returns the number of clubs loaded."""
    if not CLUB_ELO_SNAPSHOT_PATH.exists():
        return 0
    try:
        with open(CLUB_ELO_SNAPSHOT_PATH, "r") as f:
            ratings = json.load(f)
        for t, elo in ratings.items():
            ELO_PREDICTOR.set(t, elo)
        return len(ratings)
    except Exception:
        return 0


def has_elo(team: str) -> bool:
    """True if we hold a real rating for this team rather than the default."""
    return normalize_team_name(team) in ELO_PREDICTOR.ratings

def save_elo():
    """
    Deprecated. Club ratings are owned by ClubElo and refreshed daily via
    _persist_club_snapshot(); persisting our own drift here would mix the club
    and national Elo scales into one file and be silently discarded on reload.
    Retained only so any external caller fails loudly rather than silently
    writing a file nothing reads.
    """
    raise NotImplementedError(
        "save_elo() is deprecated: club Elo is sourced from ClubElo and cached "
        "in club_elo_snapshot.json. See docs/superpowers/specs/2026-08-01-season-rebuild-design.md"
    )

# Load ratings
load_elo()


def get_fitted_dixon_coles() -> DixonColesRegressor:
    """
    Retrieves or fits the time-decayed Dixon-Coles regressor.
    Caches parameters in the SQLite database to avoid fitting on every prediction.
    """
    from src.data import cache
    master_csv_path = Path(__file__).parent.parent / "data" / "processed" / "master_dataset.csv"
    
    mtime = 0.0
    size = 0
    if master_csv_path.exists():
        stat = master_csv_path.stat()
        mtime = stat.st_mtime
        size = stat.st_size
    cache_key = f"dixon_coles_params_{mtime}_{size}"
    
    cached_data = cache.get("dixon_coles_model", {"key": cache_key})
    reg = DixonColesRegressor(xi=0.0019)
    
    if cached_data:
        reg.teams = cached_data["teams"]
        reg.team_indices = {t: idx for idx, t in enumerate(reg.teams)}
        reg.params = {
            "alphas": np.array(cached_data["alphas"]),
            "betas": np.array(cached_data["betas"]),
            "gamma": cached_data["gamma"],
            "rho": cached_data["rho"]
        }
        return reg
        
    if master_csv_path.exists():
        try:
            df = pd.read_csv(master_csv_path)
            if not df.empty:
                df = df.rename(columns={
                    "HomeTeam": "home_team",
                    "AwayTeam": "away_team",
                    "FTHG": "home_goals",
                    "FTAG": "away_goals"
                })
                df["Date"] = pd.to_datetime(df["Date"])
                ref_date = pd.Timestamp.now()
                df["days_ago"] = (ref_date - df["Date"]).dt.days
                
                reg.fit(df)
                
                cache_payload = {
                    "teams": reg.teams,
                    "alphas": reg.params["alphas"].tolist(),
                    "betas": reg.params["betas"].tolist(),
                    "gamma": float(reg.params["gamma"]),
                    "rho": float(reg.params["rho"])
                }
                cache.set("dixon_coles_model", {"key": cache_key}, cache_payload, ttl_seconds=3600 * 24)
                return reg
        except Exception:
            pass
            
    reg.fit(pd.DataFrame())
    return reg


class PredictionResult:
    def __init__(self, home: str, away: str, probabilities: dict, model_breakdown: dict, sentiment: float, elo_diff: float, progression_probabilities: dict = None):
        self.home = home
        self.away = away
        self.probabilities = probabilities  # {"home_win", "draw", "away_win"}
        self.model_breakdown = model_breakdown
        self.sentiment = sentiment
        self.elo_diff = elo_diff
        self.progression_probabilities = progression_probabilities or {"home_advances": 0.50, "away_advances": 0.50}


def predict_match(home_team: str, away_team: str, kalshi_probs: dict = None, neutral: bool = False, league: str = None) -> PredictionResult:
    """
    Orchestrates the 8 models to predict a single match for EPL, La Liga, or UCL.
    Blends ELO + Dixon-Coles + 6 ML models.
    """
    from src.data.team_mapping import get_match_league
    detected_league = get_match_league(home_team, away_team, league)
    
    home_lower = normalize_team_name(home_team)
    away_lower = normalize_team_name(away_team)
    
    # 1. Fetch team ELOs
    h_elo = ELO_PREDICTOR.get(home_lower)
    a_elo = ELO_PREDICTOR.get(away_lower)
    
    # Calculate rating difference
    home_adv_pts = 0.0 if neutral else (50.0 if detected_league == "ucl" else 65.0)
    elo_diff = round((h_elo + home_adv_pts) - a_elo, 1)
    
    # 2. Dixon-Coles statistical prediction
    dc_reg = get_fitted_dixon_coles()
    p_h, p_d, p_a = dc_reg.predict_match_probs(home_lower, away_lower)
    dc_prob = {
        "home_win": round(p_h, 4),
        "draw": round(p_d, 4),
        "away_win": round(p_a, 4)
    }
    
    # Calibrated ELO probability prediction
    temp_elo_predictor = EloModel()
    temp_elo_predictor.set(home_lower, h_elo)
    temp_elo_predictor.set(away_lower, a_elo)
    elo_prob = temp_elo_predictor.predict(home_lower, away_lower, home_advantage=(0 if neutral else home_adv_pts))
    
    # 3. Load & Run the 6 ML models
    ml_probs = []
    ml_models = [
        LogisticRegressionModel(),
        SVMModel(),
        GDAModel(),
        RandomForestModel(),
        XGBoostModel(),
        NeuralNetworkModel()
    ]
    
    features = get_match_features(home_lower, away_lower, kalshi_probs)
    
    ml_breakdown = {
        "Dixon-Coles": dc_prob,
        "ELO": elo_prob
    }
    
    for model in ml_models:
        if model.load():
            try:
                p = model.predict_proba(features)[0]
                prob_dict = {
                    "home_win": float(p[0]),
                    "draw": float(p[1]),
                    "away_win": float(p[2])
                }
                ml_probs.append(prob_dict)
                ml_breakdown[model.model_name] = prob_dict
            except Exception:
                pass
                
    # 4. Blend probabilities (30% ELO, 30% Dixon-Coles, 40% ML Ensemble)
    final_home = 0.30 * elo_prob["home_win"] + 0.30 * dc_prob["home_win"]
    final_draw = 0.30 * elo_prob["draw"] + 0.30 * dc_prob["draw"]
    final_away = 0.30 * elo_prob["away_win"] + 0.30 * dc_prob["away_win"]
    
    if ml_probs:
        avg_ml_home = float(np.mean([p["home_win"] for p in ml_probs]))
        avg_ml_draw = float(np.mean([p["draw"] for p in ml_probs]))
        avg_ml_away = float(np.mean([p["away_win"] for p in ml_probs]))
        
        final_home = 0.60 * final_home + 0.40 * avg_ml_home
        final_draw = 0.60 * final_draw + 0.40 * avg_ml_draw
        final_away = 0.60 * final_away + 0.40 * avg_ml_away
        
    # Re-normalize
    total = final_home + final_draw + final_away
    blended = {
        "home_win": round(final_home / total, 4),
        "draw": round(final_draw / total, 4),
        "away_win": round(final_away / total, 4)
    }
    
    # News Sentiment
    h_news = news.get_sentiment(home_lower)
    a_news = news.get_sentiment(away_lower)
    sentiment_diff = h_news.get("score", 0.0) - a_news.get("score", 0.0)
    
    # Goalkeeper penalty save rate profiles for elite club GKs
    gk_rates = {
        "real madrid": 0.35, "arsenal": 0.31, "barcelona": 0.32,
        "manchester city": 0.30, "man city": 0.30, "liverpool": 0.34,
        "atletico madrid": 0.34, "atletico": 0.34, "aston villa": 0.36,
        "paris saint-germain": 0.33, "psg": 0.33, "bayern munich": 0.33
    }
    h_gk_rate = gk_rates.get(home_lower, 0.28)
    a_gk_rate = gk_rates.get(away_lower, 0.28)
    
    # Progression probability (Extra Time / Shootouts for UCL knockouts)
    p_et_pens_home = 0.50 + 0.0008 * elo_diff + 0.10 * (h_gk_rate - a_gk_rate)
    p_et_pens_home = max(0.30, min(0.70, p_et_pens_home))
    
    p_home_advances = blended["home_win"] + blended["draw"] * p_et_pens_home
    p_away_advances = 1.0 - p_home_advances
    
    prog_probs = {
        "home_advances": round(p_home_advances, 4),
        "away_advances": round(p_away_advances, 4)
    }
    
    return PredictionResult(
        home=home_team,
        away=away_team,
        probabilities=blended,
        model_breakdown=ml_breakdown,
        sentiment=sentiment_diff,
        elo_diff=elo_diff,
        progression_probabilities=prog_probs
    )


def math_log(val: float) -> float:
    try:
        return math.log(max(val, 0.01))
    except Exception:
        return 0.0
