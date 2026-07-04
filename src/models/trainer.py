import os
import pandas as pd
import numpy as np
from pathlib import Path
from src.data.preprocessor import clean_and_load_dataset, FEATURE_NAMES, get_match_features
from src.models.machine_learning import (
    LogisticRegressionModel, SVMModel, GDAModel,
    RandomForestModel, XGBoostModel, NeuralNetworkModel
)
from src.data.scrapers.elo_db import get_national_elo

DATA_DIR = Path(__file__).parent.parent.parent / "data"
MASTER_CSV_PATH = DATA_DIR / "processed" / "master_dataset.csv"
RAW_SOURCE_CSV = DATA_DIR / "raw" / "final_ml_dataset.csv"
USER_BACKUP_CSV = Path("C:/Users/Bikash/Desktop/CSCI635/CSCI635_MLProject/src/final_ml_dataset.csv")


def initialize_master_dataset():
    """
    Copies the Premier League raw dataset to start as the master training set.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "processed").mkdir(parents=True, exist_ok=True)
    
    if not MASTER_CSV_PATH.exists():
        if RAW_SOURCE_CSV.exists():
            df = pd.read_csv(RAW_SOURCE_CSV)
            df.to_csv(MASTER_CSV_PATH, index=False)
            print(f"Initialized master dataset at {MASTER_CSV_PATH}")
        elif USER_BACKUP_CSV.exists():
            df = pd.read_csv(USER_BACKUP_CSV)
            df.to_csv(MASTER_CSV_PATH, index=False)
            print(f"Initialized master dataset at {MASTER_CSV_PATH} from backup source")
        else:
            # Create standard blank fallback dataset if not found
            df = pd.DataFrame(columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"] + FEATURE_NAMES)
            df.to_csv(MASTER_CSV_PATH, index=False)
            print("Warning: Raw PL source not found. Initialized blank master dataset.")


def calculate_sample_weights(dates: pd.Series) -> np.ndarray:
    """Calculates exponential time-decay sample weights with a 4-year half-life."""
    current_time = pd.Timestamp.now()
    # Convert to pd.Series to ensure the .dt accessor is available
    dates_series = pd.Series(dates)
    # Compute years ago
    years_ago = (current_time - pd.to_datetime(dates_series)).dt.days / 365.25
    # Half life decay lambda = ln(2)/4 = 0.173286
    weights = np.exp(-0.173286 * years_ago)
    # Clamp at 0.05
    return np.maximum(0.05, weights.values)



def train_and_save_all():
    """
    Retrains all 6 ML models on the master dataset and saves their parameters.
    """
    initialize_master_dataset()
    
    print("Loading data for training...")
    X, y_res, y_goals = clean_and_load_dataset(str(MASTER_CSV_PATH))
    
    # Calculate sample weights
    try:
        df = pd.read_csv(MASTER_CSV_PATH)
        weights = calculate_sample_weights(df["Date"])
        if len(weights) != X.shape[0]:
            print("Warning: weights length does not match X shape. Using equal weights.")
            weights = None
    except Exception as e:
        print(f"Error calculating sample weights: {e}. Defaulting to equal weights.")
        weights = None
    
    models = [
        LogisticRegressionModel(),
        SVMModel(),
        GDAModel(),
        RandomForestModel(),
        XGBoostModel(),
        NeuralNetworkModel()
    ]
    
    print(f"Training on {X.shape[0]} match records with {X.shape[1]} features...")
    for model in models:
        try:
            print(f"Training {model.model_name}...")
            if model.model_name in ("LogisticRegression", "SupportVectorMachine", "XGBoost"):
                model.train(X, y_res, y_goals, sample_weight=weights)
            else:
                model.train(X, y_res, sample_weight=weights)
            model.save()
            print(f"Saved {model.model_name}")
        except Exception as e:
            print(f"Error training {model.model_name}: {e}")



def add_completed_match(home_team: str, away_team: str, home_goals: int, away_goals: int):
    """
    Appends a new completed World Cup match to the master dataset,
    updates dynamic ratings, and retrains all models.
    """
    initialize_master_dataset()
    
    # Calculate target outcome
    if home_goals > away_goals:
        ftr = "H"
    elif home_goals < away_goals:
        ftr = "A"
    else:
        ftr = "D"
        
    # Get pre-match features to append
    # (Since we want features *before* the match played)
    features = get_match_features(home_team, away_team)
    
    # Build dictionary matching columns
    row_dict = {
        "Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "HomeTeam": home_team,
        "AwayTeam": away_team,
        "FTHG": float(home_goals),
        "FTAG": float(away_goals),
        "FTR": ftr
    }
    for i, name in enumerate(FEATURE_NAMES):
        row_dict[name] = float(features[i])
        
    # Append to master dataset
    df = pd.read_csv(MASTER_CSV_PATH)
    df = pd.concat([df, pd.DataFrame([row_dict])], ignore_index=True)
    df.to_csv(MASTER_CSV_PATH, index=False)
    print(f"Added match: {home_team} {home_goals}-{away_goals} {away_team} to master dataset.")
    
    # Retrain ML models
    train_and_save_all()
