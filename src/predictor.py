import math
import numpy as np
from src.data.scrapers import fbref, news, fixtures, elo_db
from src.data.preprocessor import get_match_features
from src.models.statistical import DixonColesModel, EloModel
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


class PredictionResult:
    def __init__(self, home: str, away: str, probabilities: dict, model_breakdown: dict, sentiment: float, elo_diff: float):
        self.home = home
        self.away = away
        self.probabilities = probabilities  # {"home_win", "draw", "away_win"}
        self.model_breakdown = model_breakdown
        self.sentiment = sentiment
        self.elo_diff = elo_diff


def predict_match(home_team: str, away_team: str, kalshi_probs: dict = None, neutral: bool = True) -> PredictionResult:
    """
    Orchestrates the 8 models to predict a single match.
    Blends ELO + Dixon-Coles + 6 ML models.
    """
    home_lower = normalize_team_name(home_team)
    away_lower = normalize_team_name(away_team)
    
    # 1. Fetch team ELOs and averages
    h_elo = ELO_PREDICTOR.get(home_lower)
    a_elo = ELO_PREDICTOR.get(away_lower)
    elo_diff = h_elo - a_elo
    
    # 2. Dixon-Coles statistical prediction
    dc = DixonColesModel()
    # Simple fitting on team averages as base
    h_data = fbref.get_team_data(home_lower)
    a_data = fbref.get_team_data(away_lower)
    dc.attack[home_lower] = math_log(h_data.get("avg_goals", 1.4))
    dc.defense[home_lower] = -math_log(h_data.get("avg_conceded", 1.1))
    dc.attack[away_lower] = math_log(a_data.get("avg_goals", 1.4))
    dc.defense[away_lower] = -math_log(a_data.get("avg_conceded", 1.1))
    dc.is_fitted = True
    
    dc_prob = dc.predict(home_lower, away_lower, neutral=neutral)
    elo_prob = ELO_PREDICTOR.predict(home_lower, away_lower, home_advantage=(0 if neutral else 65))
    
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
    
    return PredictionResult(
        home=home_team,
        away=away_team,
        probabilities=blended,
        model_breakdown=ml_breakdown,
        sentiment=sentiment_diff,
        elo_diff=elo_diff
    )


def math_log(val: float) -> float:
    try:
        return math.log(max(val, 0.01))
    except Exception:
        return 0.0
