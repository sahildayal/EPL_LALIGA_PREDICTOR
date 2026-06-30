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
    if ELO_FILE_PATH.exists():
        try:
            with open(ELO_FILE_PATH, "r") as f:
                ratings = json.load(f)
                for t, elo in ratings.items():
                    ELO_PREDICTOR.set(t, elo)
                return
        except Exception:
            pass
    # Fallback to static seed
    for t, elo in elo_db.NATIONAL_TEAM_ELO.items():
        ELO_PREDICTOR.set(t, elo)

def save_elo():
    ELO_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ELO_FILE_PATH, "w") as f:
            json.dump(ELO_PREDICTOR.ratings, f, indent=2)
    except Exception:
        pass

# Load ratings
load_elo()


def get_fitted_dixon_coles() -> DixonColesRegressor:
    """
    Retrieves or fits the time-decayed Dixon-Coles regressor.
    Caches parameters in the SQLite database to avoid fitting on every prediction.
    """
    from src.data import cache
    master_csv_path = Path(__file__).parent.parent / "data" / "processed" / "master_dataset.csv"
    
    # Calculate a simple cache key key based on CSV modification time/size
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
        
    # Fit the regressor
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
                
                # Cache parameters (convert np arrays to lists for JSON serialization)
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
            
    # Fallback/Empty fit if error or file doesn't exist
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


CONFEDERATION_BOOST = {
    "conmebol": 50.0,
    "uefa": 40.0,
    "caf": 0.0,
    "afc": -20.0,
    "concacaf": -30.0,
    "ofc": -80.0,
    "neutral": 0.0
}

TEAM_CONFEDERATION = {
    "brazil": "conmebol", "argentina": "conmebol", "uruguay": "conmebol", "colombia": "conmebol", "ecuador": "conmebol", "chile": "conmebol", "paraguay": "conmebol",
    "france": "uefa", "england": "uefa", "spain": "uefa", "portugal": "uefa", "netherlands": "uefa", "germany": "uefa", "italy": "uefa", "croatia": "uefa", "belgium": "uefa", "denmark": "uefa", "switzerland": "uefa", "sweden": "uefa", "norway": "uefa",
    "morocco": "caf", "senegal": "caf", "egypt": "caf", "tunisia": "caf",
    "japan": "afc", "south korea": "afc", "australia": "afc", "saudi arabia": "afc", "iran": "afc", "jordan": "afc",
    "mexico": "concacaf", "usa": "concacaf", "canada": "concacaf", "haiti": "concacaf",
    "new zealand": "ofc"
}


def predict_match(home_team: str, away_team: str, kalshi_probs: dict = None, neutral: bool = True) -> PredictionResult:
    """
    Orchestrates the 8 models to predict a single match.
    Blends ELO + Dixon-Coles + 6 ML models.
    """
    home_lower = normalize_team_name(home_team)
    away_lower = normalize_team_name(away_team)
    
    h_conf = TEAM_CONFEDERATION.get(home_lower, "neutral")
    a_conf = TEAM_CONFEDERATION.get(away_lower, "neutral")
    
    h_boost = CONFEDERATION_BOOST.get(h_conf, 0.0)
    a_boost = CONFEDERATION_BOOST.get(a_conf, 0.0)
    
    # 1. Fetch team ELOs and averages
    h_elo = ELO_PREDICTOR.get(home_lower)
    a_elo = ELO_PREDICTOR.get(away_lower)
    
    # Apply boost and round to 1 decimal place
    elo_diff = round((h_elo + h_boost) - (a_elo + a_boost), 1)
    
    # 2. Dixon-Coles statistical prediction
    dc_reg = get_fitted_dixon_coles()
    p_h, p_d, p_a = dc_reg.predict_match_probs(home_lower, away_lower)
    dc_prob = {
        "home_win": round(p_h, 4),
        "draw": round(p_d, 4),
        "away_win": round(p_a, 4)
    }
    
    # Calibrated ELO rating fed into ELO probability prediction
    temp_elo_predictor = EloModel()
    temp_elo_predictor.set(home_lower, h_elo + h_boost)
    temp_elo_predictor.set(away_lower, a_elo + a_boost)
    elo_prob = temp_elo_predictor.predict(home_lower, away_lower, home_advantage=(0 if neutral else 65))
    
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
                
    # 4. Blend probabilities
    # Weights: 30% ELO, 30% Dixon-Coles, 40% ML Ensemble average
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
    
    # Sentiment
    h_news = news.get_sentiment(home_lower)
    a_news = news.get_sentiment(away_lower)
    sentiment_diff = h_news.get("score", 0.0) - a_news.get("score", 0.0)
    
    # Goalkeeper penalty save rate logic
    # Brazil GK (Alisson): 33%, Japan GK (Zion Suzuki): 25%
    gk_rates = {
        "brazil": 0.33,
        "japan": 0.25
    }
    h_gk_rate = gk_rates.get(home_lower, 0.28)
    a_gk_rate = gk_rates.get(away_lower, 0.28)
    
    # Probability of home team advancing if it goes to Extra Time/Penalties
    # Adjusted by Elo diff and Goalkeeper penalty-saving rates
    p_et_pens_home = 0.50 + 0.0008 * elo_diff + 0.10 * (h_gk_rate - a_gk_rate)
    p_et_pens_home = max(0.30, min(0.70, p_et_pens_home))
    
    # Combined advances probability
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
