# World Cup Prediction Model (2026) — Design Specification

## Overview
The **World Cup Prediction Model (2026)** is a unified, sports betting forecasting system designed specifically for the ongoing 2026 FIFA World Cup. It merges features and model architectures from a Premier League betting project (6 machine learning models: Logistic Regression, SVM, GDA, RF, XGBoost, and a Neural Network) with statistical models (ELO, Dixon-Coles) and live data sources (FBRef, Google News RSS, and Kalshi API) from the EdgeFinder codebase.

The goal is to generate high-probability outcome and player prop forecasts, dynamically update based on tournament match results, and recommend optimized 3-to-5-leg parlay/combo bets ($\ge 5x$ multiplier) available on Kalshi.

---

## Directory Layout

The codebase is organized as follows:

```text
WorldCupPredictor/
├── docs/superpowers/specs/    # Design specs and plans
├── data/
│   ├── raw/                   # Historical international match history (2018–2026)
│   ├── processed/             # Master CSV for training ML models
│   ├── models/                # Saved weights/pickles for all 6 ML models
│   └── cache/                 # Scraper and API response cache
├── src/
│   ├── data/
│   │   ├── scrapers/          # Scrapers for FBRef (team/player) and ESPN
│   │   └── preprocessor.py    # Blends team features & player stats (club + intl form)
│   ├── models/
│   │   ├── base.py            # Base class for unified model interface
│   │   ├── statistical.py     # Dixon-Coles and ELO models
│   │   ├── machine_learning.py # Wrapper classes for LR, SVM, GDA, RF, XGBoost, MLP
│   │   └── trainer.py         # Continuous training loop & dataset updater
│   ├── market/
│   │   └── kalshi_client.py   # Kalshi V2 authenticated client (fetching only)
│   ├── parlay/
│   │   └── parlay_engine.py   # Finds 3-to-5-leg correlated combos >= 5x with edge
│   └── predictor.py           # Orchestrator combining models, news, and market data
├── main.py                    # CLI command-line interface
├── app.py                     # Web dashboard
├── requirements.txt           # Required Python packages
└── .env                       # Kalshi credentials, API endpoints
```

---

## Architecture & Data Flow

### 1. Ingestion & Preprocessing
*   📅 **Historical Data:** Collects historical international soccer matches (2018-2026) to provide a rich dataset for the initial training of the ML models.
*   🔍 **Unified Features:** The preprocessor maps team-level features (Rolling form, ELO difference, average goals scored/conceded) and player-level statistics.
*   🏆 **Player Form Composite:** Integrates a weighted blending of a player's club form (last 10 matches) and their national team form to create a highly accurate player prop baseline (e.g. goalscorer probability).

### 2. Model Ensemble
The forecasting engine executes 8 models and weights/blends their predictions:
1.  **Dixon-Coles (Statistical):** Generates full scoreline probability matrices, correcting for underestimation of low-scoring draws.
2.  **ELO Rating (Statistical):** Dynamic team-level strength rating.
3.  **Logistic Regression (ML):** Calibrated outcome baseline.
4.  **Support Vector Machine (ML):** Decision-boundary outcome classifier.
5.  **Gaussian Discriminant Analysis (ML):** Parametric probabilistic classifier.
6.  **Random Forest (ML):** Ensemble tree classifier.
7.  **XGBoost (ML):** Gradient boosted tree classifier.
8.  **Neural Network / MLP (ML):** Dense layer regression model for scorelines and classification for outcomes.

### 3. Continuous Learning
*   ⚡ **Immediate Feature Updates:** As each match concludes, the teams' ELO ratings and Dixon-Coles parameters are instantly recalculated.
*   🔄 **Daily Model Retraining:** The match result and pre-match features are appended to the training set. The 6 ML models are automatically retrained daily on this updated dataset to adapt their weights for the knockout stages.

### 4. Kalshi API Integration (Read-Only)
*   🔑 **Credentials:** Authenticates using `.env` settings (email/password or RSA key pairs).
*   📊 **Fetching Capabilities:** Fetches account balances, current portfolio holdings, and closed positions history.
*   🔍 **Market Scraping:** Scrapes active soccer contracts:
    *   *Game Lines:* Moneyline, Point Totals, Spreads, Team Totals, BTTS (Both Teams to Score).
    *   *Player Props:* Over/Under Goals, Goalscorer.
    *   *Game Props:* Exact Score.

### 5. Parlay / Combo Engine
*   📋 **Leg Count:** Generates combos containing between 3 and 5 legs.
*   🎯 **Payout Target:** Filter for parlays with a cumulative multiplier $\ge 5x$.
*   🔄 **Correlation Modeling:**
    *   *Same-Game:* Sums exact scoreline probabilities from the Dixon-Coles joint distribution (e.g., Team A Win + Over 1.5 Goals) instead of multiplying independent probabilities.
    *   *Cross-Game:* Multiplies probabilities across independent matches.
*   📊 **Edge & Bet Sizing:** Compares joint probability against Kalshi's implied probabilities to output the positive edge and recommended stake using the quarter-Kelly criterion.
