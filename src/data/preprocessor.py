import numpy as np
import pandas as pd
import math
from datetime import datetime
from src.data.scrapers import fbref, elo_db, news
from src.data.cache import get_team_last_travel
from src.data.scrapers.fixtures import search_wc_fixture

# The 17 general features (no team-specific IDs) + 8 new fatigue/travel features (total 25)
FEATURE_NAMES = [
    "B365H", "B365D", "B365A",
    "HTGS", "HTGC", "HTP", "HTGD",
    "ATGS", "ATGC", "ATP", "ATGD",
    "HTFormPts", "ATFormPts",
    "DiffFormPts", "DiffPts", "DiffGD",
    "SentimentScore",
    "HTRestDays", "ATRestDays", "RestDisparity",
    "HTExtremeFatigue", "ATExtremeFatigue",
    "HTTravel", "ATTravel", "TravelDisparity"
]

VENUE_COORDS = {
    # 2026 World Cup Host Cities
    "toronto": (43.6328, -79.4186),
    "vancouver": (49.2768, -123.1120),
    "mexico city": (19.3029, -99.1505),
    "guadalajara": (20.6811, -103.4627),
    "monterrey": (25.6689, -100.2443),
    "atlanta": (33.7554, -84.4009),
    "boston": (42.0909, -71.2643),
    "dallas": (32.7473, -97.0945),
    "houston": (29.6847, -95.4078),
    "kansas city": (39.0489, -94.4839),
    "los angeles": (33.9535, -118.3390),
    "miami": (25.9581, -80.2389),
    "new york": (40.8135, -74.0743),
    "new jersey": (40.8135, -74.0743),
    "philadelphia": (39.9008, -75.1675),
    "san francisco": (37.4033, -121.9694),
    "seattle": (47.5952, -122.3316),
    
    # Test / Friendly venues
    "lisbon": (38.7223, -9.1393),
    "london": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522),
    "munich": (48.1351, 11.5820),
    "doha": (25.2854, 51.5310),
    "lusail": (25.4208, 51.4912),
}


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth's radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def get_venue_coords(venue_name: str) -> tuple:
    if not venue_name:
        return None
    venue_lower = venue_name.lower()
    for city, coords in VENUE_COORDS.items():
        if city in venue_lower:
            return coords
    return None


def calculate_team_fatigue_travel(team: str, current_date_str: str, current_coords: tuple) -> tuple:
    """
    Returns (rest_days, travel_dist_km, extreme_fatigue_flag).
    """
    last_travel = get_team_last_travel(team)
    if not last_travel:
        # Default: fully rested (7 days), no travel
        return 7.0, 0.0, 0.0

    # Calculate rest days
    try:
        d1_str = current_date_str.split("T")[0]
        d2_str = last_travel["date"].split("T")[0]
        d1 = datetime.strptime(d1_str, "%Y-%m-%d")
        d2 = datetime.strptime(d2_str, "%Y-%m-%d")
        rest_days = float((d1 - d2).days)
        if rest_days < 0:
            rest_days = 0.0
    except Exception:
        rest_days = 7.0

    # Calculate travel distance
    travel_dist = 0.0
    if current_coords:
        lat1, lon1 = last_travel["lat"], last_travel["lon"]
        lat2, lon2 = current_coords
        travel_dist = calculate_distance_km(lat1, lon1, lat2, lon2)

    extreme_fatigue = 1.0 if rest_days <= 3.0 else 0.0
    return rest_days, travel_dist, extreme_fatigue


def get_match_features(home_team: str, away_team: str, kalshi_probs: dict = None) -> np.ndarray:
    """
    Fetches real-time stats and maps them to the 17-feature vector (extended to 25 features)
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

    # 5. Fatigue & Travel distance features
    fixture = search_wc_fixture(home_team, away_team)
    if fixture:
        current_date_str = fixture.get("date", "")
        venue_name = fixture.get("venue", "")
        current_coords = get_venue_coords(venue_name)
    else:
        current_date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        current_coords = None

    ht_rest, ht_travel, ht_fatigue = calculate_team_fatigue_travel(home_team, current_date_str, current_coords)
    at_rest, at_travel, at_fatigue = calculate_team_fatigue_travel(away_team, current_date_str, current_coords)
    
    rest_disparity = ht_rest - at_rest
    travel_disparity = ht_travel - at_travel

    # 6. Assemble the array
    features = np.array([
        b365h, b365d, b365a,
        htgs, htgc, htp, htgd,
        atgs, atgc, atp, atgd,
        ht_form_pts, at_form_pts,
        diff_form_pts, diff_pts, diff_gd,
        sentiment_diff,
        ht_rest, at_rest, rest_disparity,
        ht_fatigue, at_fatigue,
        ht_travel, at_travel, travel_disparity
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
    # Ensure all FEATURE_NAMES columns exist in df
    for col in FEATURE_NAMES:
        if col not in df.columns:
            if "Fatigue" in col or "Extreme" in col:
                df[col] = 0.0
            elif "Travel" in col:
                df[col] = 0.0
            elif "RestDays" in col:
                df[col] = 7.0
            elif "Rest" in col or "Disparity" in col:
                df[col] = 0.0
            else:
                df[col] = 0.0

    df[FEATURE_NAMES] = df[FEATURE_NAMES].fillna(df[FEATURE_NAMES].median())
    
    X = df[FEATURE_NAMES].values
    y_result = df["FTR_class"].values
    
    # Goals targets
    if "FTHG" in df.columns and "FTAG" in df.columns:
        y_goals = df[["FTHG", "FTAG"]].values
    else:
        y_goals = np.zeros((len(df), 2))
        
    return X, y_result, y_goals
