# 📦 Antigravity Session Content Pack & Master Technical Reference
## Premier League, La Liga & UEFA Champions League Predictor & Kalshi Parlay Engine
*Date: 2026-08-01*
*Document Type: Full Session Technical Content Pack*

---

## 1. Executive Summary & Session Overview

During this session, the engine underwent a full end-to-end architectural migration from the international World Cup model to a **Unified Multi-League Football Predictor & Trading Engine** covering:
1. **Premier League (EPL)** — England (`epl` / ESPN `eng.1` / Kalshi `KXEPLGAME`)
2. **La Liga** — Spain (`laliga` / ESPN `esp.1` / Kalshi `KXLALIGAGAME`)
3. **UEFA Champions League** — Europe (`ucl` / ESPN `uefa.champions` / Kalshi `KXUCLGAME`)

The browser UI dashboard was decommissioned to streamline the workspace into a high-performance **Command Line Interface (CLI)** with rich terminal formatting, automated weekly cron scheduling, full squad roster tracking, and live Kalshi market integration.

---

## 2. Complete Software Architecture & System Topology

```
+-----------------------------------------------------------------------------------+
|                                 1. DATA INGESTION                                 |
|  - ESPN Scoreboard API (eng.1, esp.1, uefa.champions)                             |
|  - ESPN Squad Roster Endpoint (25-30 players per club)                            |
|  - FBref Player xG / Goal / Assist / Position Stats                               |
|  - Google News / RSS Sentiment Scraper per Club                                   |
|  - Kalshi Market API (KXEPL, KXLALIGA, KXUCL Orderbooks)                         |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                                 2. MODELING CORE                                  |
|  - Cross-League ELO Database (Real Madrid 1980, Man City 1970, Arsenal 1910...)   |
|  - Dixon-Coles Bivariate Poisson Regressor (Time-Decay \xi=0.0019 + League \gamma)|
|  - 6 Base ML Classifiers (LogReg, SVM, GDA, RandomForest, XGBoost, NeuralNet)    |
|  - Stacking Ensemble Meta-Learner (L2 Regularized Ridge Classifier)               |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                        3. PREDICTION & PARLAY ENGINE                              |
|  - 90-min Outcome Probability Matrix (Home Win / Draw / Away Win)                 |
|  - Goalkeeper Shootout/Penalties Save Profiles (Courtois, Raya, Ter Stegen...)    |
|  - 2D Dixon-Coles Scoreline Matrix Integration (Over/Under, BTTS, Corners)        |
|  - Same-Game Parlay (SGP) Sandbox Validator (Redundant / Exclusive Leg Filters)   |
|  - Fractional Kelly Criterion Bankroll Allocator (0.50 * f*)                      |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                         4. AI DEBATE ORCHESTRATION                                |
|  - Gemini 2.5/3.5 Flash Model Integration                                         |
|  - 👴 Magnus (Scout): Manager tactics, fixture congestion, El Clásico/Derby context|
|  - 🤖 Athena (Quant): ELO differentials, Dixon-Coles bounds, Kalshi value edges   |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                            5. CLI & CRON SCHEDULER                                |
|  - Auto-detection (Arsenal vs Real Madrid -> UCL, Real Madrid vs Barca -> LaLiga) |
|  - main.py CLI (init, update, run-daily, schedule, predict, ask, parlay, portfolio)|
|  - Weekly Cron Scheduler (Sundays 23:00 UTC)                                      |
+-----------------------------------------------------------------------------------+
```

---

## 3. Mathematical & Machine Learning Stack Details

### A. Dixon-Coles Time-Decayed Poisson Model (`src/models/dixon_coles_decay.py`)
Goal distributions for home team $X$ and away team $Y$ are modeled via bivariate Poisson parameters:
*   $\lambda = \exp(\alpha_{\text{home}} + \beta_{\text{away}} + \gamma_{\text{league}})$
*   $\mu = \exp(\alpha_{\text{away}} + \beta_{\text{home}})$

Where:
*   $\alpha_i$: Attacking strength coefficient for team $i$.
*   $\beta_i$: Defensive resistance coefficient for team $i$.
*   $\gamma_{\text{league}}$: Fitted home advantage parameter ($\gamma_{\text{EPL}} \approx +0.32$, $\gamma_{\text{LaLiga}} \approx +0.36$, $\gamma_{\text{UCL}} \approx +0.28$).
*   $\xi = 0.0019$: Time-decay weight factor ($\exp(-\xi \cdot t)$ giving lower weight to older matches).
*   $\tau(x, y; \lambda, \mu, \rho)$: Low-scoring draw correction factor adjusting $\{0,0\}, \{1,0\}, \{0,1\}, \{1,1\}$ coordinates.

### B. Unified Cross-League ELO Database (`src/data/scrapers/elo_db.py`)
Top European clubs share a unified ELO rating scale initialized by performance tiers and UEFA coefficients:
*   **Tier 1 Elite UCL**: Real Madrid (1980), Man City (1970), Bayern Munich (1930), Arsenal (1910), PSG (1910), Barcelona (1900), Liverpool (1900), Inter Milan (1890), Atletico Madrid (1870).
*   **Tier 2 Upper Mid-Table**: Chelsea (1850), Atalanta (1850), Juventus (1840), RB Leipzig (1840), Aston Villa (1830), Sporting CP (1830), AC Milan (1830), Tottenham (1820), Newcastle (1820), Real Sociedad (1800), Villarreal (1790), Real Betis (1780).
*   **Tier 3 Lower Table / Promoted**: Fulham (1740), Crystal Palace (1730), Brentford (1720), Everton (1710), Wolves (1700), Forest (1700), Leicester (1680), Southampton (1660), Leganés (1650), Ipswich (1640), Real Valladolid (1640).

Cross-league match rating updates apply dynamically after every match with $K=20$.

### C. 8-Model Stacking Ensemble (`src/models/stacking_ensemble.py` & `src/predictor.py`)
1. **Dixon-Coles Model**
2. **Confederation/Club-Boosted ELO Model**
3. **Logistic Regression Classifier**
4. **Support Vector Machine (SVM)**
5. **Gaussian Discriminant Analysis (GDA)**
6. **Random Forest Classifier**
7. **XGBoost Classifier**
8. **Neural Network (Multi-Layer Perceptron)**
*   **Meta-Learner**: StackingClassifier utilizing $L_2$ regularized Logistic Regression.

---

## 4. Full Squad Rosters & Scrapers

### Full Roster Extraction (`src/data/scrapers/upcoming_and_stats.py`)
Instead of tracking only star players, the scraper queries ESPN team roster endpoints (`/teams/{team_id}/roster`) across all 40 EPL & La Liga clubs:
*   Scrapes name, position category (`FW`, `CM`, `DEF`), goals, assists, per-90 metrics, and expected goal share ($xG/90$).
*   Stores player statistics directly in SQLite (`player_statistics`) and `data/processed/tournament_player_stats.json`.

---

## 5. Kalshi Exchange & Same-Game Parlay (SGP) Engine

*   **Supported Tickers**:
    *   `KXEPLGAME`, `KXEPLTOTAL`, `KXEPLBTTS`, `KXEPLGOAL`, `KXEPLCORNERS`
    *   `KXLALIGAGAME`, `KXLALIGATOTAL`, `KXLALIGABTTS`, `KXLALIGAGOAL`
    *   `KXUCLGAME`, `KXUCLTOTAL`, `KXUCLBTTS`, `KXUCLQUAL`
*   **SGP Sandbox Validator (`src/parlay/sgp_validator.py`)**:
    *   Calculates joint probabilities over 2D scoreline matrix.
    *   Prevents mutually exclusive legs (e.g., Moneyline Home Win + Moneyline Away Win).
    *   Filters redundant legs (e.g., discarding `Over 1.5` if `Over 2.5` is selected).
*   **Kelly Criterion Staking**: Computes fractional wager size ($0.50 \cdot f^*$) for tickets with $\ge 5$x multiplier and positive model edge.

---

## 6. Complete CLI Commands Reference

*   **Initialize / Retrain Models**:
    ```bash
    python main.py init
    ```
*   **Auto-Sync Completed Matches & Retrain**:
    ```bash
    python main.py update
    ```
*   **Predict Premier League Match**:
    ```bash
    python main.py predict "Arsenal vs Chelsea"
    ```
*   **Predict La Liga Match**:
    ```bash
    python main.py predict "Real Madrid vs Barcelona"
    ```
*   **Predict Champions League Cross-League Match**:
    ```bash
    python main.py predict "Arsenal vs Real Madrid"
    ```
*   **Stage Gemini Scout vs Quant Debate**:
    ```bash
    python main.py ask "Real Madrid vs Barcelona"
    ```
*   **Generate High-Edge Kalshi Parlays**:
    ```bash
    python main.py parlay --today
    ```
*   **Run Automated Daily Matchday Pipeline**:
    ```bash
    python main.py run-daily
    ```
*   **Launch Weekly Automated Cron Scheduler (Sundays at 23:00 UTC)**:
    ```bash
    python main.py schedule
    ```
*   **Check Live Kalshi Balances & Bot Paper Ledgers**:
    ```bash
    python main.py portfolio
    ```

---

## 7. Changed & Updated Files Ledger

1. `src/data/team_mapping.py` — Added club aliases, `TEAM_COMPETITION` map, and `get_match_league()` auto-detector.
2. `src/data/scrapers/elo_db.py` — Added `CLUB_ELO` rating seeds and `get_team_elo()`.
3. `src/predictor.py` — Updated `predict_match()` for club football, domestic home advantage (+65 pts), and top goalkeeper save rates.
4. `src/data/scrapers/fixtures.py` — Added `ESPN_LEAGUES` for `eng.1`, `esp.1`, `uefa.champions`.
5. `src/data/scrapers/upcoming_and_stats.py` — Implemented full 25-30 squad member roster scraping across all clubs.
6. `src/market/kalshi_client.py` — Added EPL, La Liga, and UCL series tickers and mock markets.
7. `src/models/trainer.py` — Updated dataset generator with club match samples.
8. `src/market/llm.py` — Updated tournament stage and debate persona prompts for club tactics and manager rivalries.
9. `main.py` — Added `--league` CLI flag, updated banner, added `schedule` weekly Sunday cron launcher, and enhanced portfolio active wager outputs.

---
*Content Pack Complete & Verified.*
