import numpy as np
import pandas as pd
from src.data.scrapers import fbref, elo_db, news

# The 17 general features (no team-specific IDs)
FEATURE_NAMES = [
    "B365H", "B365D", "B365A",
    "HTGS", "HTGC", "HTP", "HTGD",
    "ATGS", "ATGC", "ATP", "ATGD",
    "HTFormPts", "ATFormPts",
    "DiffFormPts", "DiffPts", "DiffGD",
    "SentimentScore"
]


def get_match_features(home_team: str, away_team: str, kalshi_probs: dict = None) -> np.ndarray:
    """
    Fetches real-time stats and maps them to the 17-feature vector
    used by the ML models.
    kalshi_probs: dict of live odds {"home_win": p1, "draw": p2, "away_win": p3}
    """
    home_data = fbref.get_team_data(home_team)
    away_data = fbref.get_team_data(away_team)
    
    # 1. Fetch news sentiment
    home_news = news.get_sentiment(home_team)
    away_news = news.get_sentiment(away_team)
    sentiment_diff = home_news.get("score", 0.0) - away_news.get("score", 0.0)

    # 2. Extract averages
    h_avg_g = float(home_data.get("avg_goals", 1.4))
    h_avg_c = float(home_data.get("avg_conceded", 1.1))
    h_form = float(home_data.get("form", 0.60))

    a_avg_g = float(away_data.get("avg_goals", 1.4))
    a_avg_c = float(away_data.get("avg_conceded", 1.1))
    a_form = float(away_data.get("form", 0.60))

    # 3. Simulate mid-season stats (baseline of 10 matches)
    htgs = h_avg_g * 10.0
    htgc = h_avg_c * 10.0
    htp = h_form * 30.0  # e.g., 100% win rate = 30 pts, 50% = 15 pts
    htgd = htgs - htgc

    atgs = a_avg_g * 10.0
    atgc = a_avg_c * 10.0
    atp = a_form * 30.0
    atgd = atgs - atgc

    # Form points in last 5 matches (max 15 pts)
    ht_form_pts = h_form * 15.0
    at_form_pts = a_form * 15.0

    diff_form_pts = ht_form_pts - at_form_pts
    diff_pts = htp - atp
    diff_gd = htgd - atgd

    # 4. Map Kalshi probs to equivalent B365 odds
    b365h, b365d, b365a = 2.0, 3.2, 3.4  # default neutral odds
    if kalshi_probs:
        ph = kalshi_probs.get("home_win") or 0.38
        pd_ = kalshi_probs.get("draw") or 0.28
        pa = kalshi_probs.get("away_win") or 0.34
        b365h = 1.0 / max(ph, 0.01)
        b365d = 1.0 / max(pd_, 0.01)
        b365a = 1.0 / max(pa, 0.01)

    # 5. Assemble the array
    features = np.array([
        b365h, b365d, b365a,
        htgs, htgc, htp, htgd,
        atgs, atgc, atp, atgd,
        ht_form_pts, at_form_pts,
        diff_form_pts, diff_pts, diff_gd,
        sentiment_diff
    ], dtype=np.float32)

    return features


def clean_and_load_dataset(raw_filepath: str) -> tuple:
    """
    Cleans the raw Premier League dataset, dropping specific target & leak columns.
    Excludes team string names to keep features general.
    """
    df = pd.read_csv(raw_filepath)
    
    # Target values mapping FTR to {0,1,2}
    target_map = {"H": 0, "D": 1, "A": 2}
    if "FTR" in df.columns:
        df["FTR_class"] = df["FTR"].map(target_map)
    
    # Fill NAs
    df[FEATURE_NAMES] = df[FEATURE_NAMES].fillna(df[FEATURE_NAMES].median())
    
    X = df[FEATURE_NAMES].values
    y_result = df["FTR_class"].values
    
    # Goals targets
    if "FTHG" in df.columns and "FTAG" in df.columns:
        y_goals = df[["FTHG", "FTAG"]].values
    else:
        y_goals = np.zeros((len(df), 2))
        
    return X, y_result, y_goals
