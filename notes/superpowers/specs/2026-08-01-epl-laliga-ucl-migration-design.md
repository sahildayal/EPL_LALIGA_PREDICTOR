# ⚽ Multi-League Football Predictor: Premier League, La Liga & Champions League Migration
## System Design Document
*Date: 2026-08-01*
*Status: Approved Design*

---

## 1. Overview & Vision

Following the conclusion of the World Cup, the prediction engine is migrating to focus on **Premier League (EPL)**, **La Liga (Spain)**, and the **UEFA Champions League (UCL)**.

The system will operate in a **Unified Multi-League Mode**, sharing a single cross-league ELO rating database for top European club teams. This enables direct, calibrated modeling when EPL and La Liga clubs face off in the Champions League (e.g. *Arsenal vs Real Madrid*), while fitting competition-specific Dixon-Coles parameters to capture domestic league goal rates and home advantage dynamics.

---

## 2. Core Architecture & Multi-Competition Layout

### Supported Competitions & Identifiers
*   `epl`: Premier League (England) — ESPN slug `eng.1`, FBref `england-premier-league`, Kalshi `KXEPLGAME` / `KXEPL`.
*   `laliga`: La Liga (Spain) — ESPN slug `esp.1`, FBref `spain-la-liga`, Kalshi `KXLALIGAGAME` / `KXLALIGA`.
*   `ucl`: UEFA Champions League — ESPN slug `uefa.champions`, FBref `uefa-champions-league`, Kalshi `KXUCLGAME` / `KXUCL`.

### Data Directory Topology
```
data/
├── processed/
│   ├── master_dataset.csv            # Historical match dataset (EPL, La Liga, UCL from 2021-2026)
│   ├── elo_ratings.json              # Cross-league club ELO database (~50 top European clubs)
│   ├── tournament_player_stats.json  # Scraped player xG/90, goals, assists for club rosters
│   ├── daily_schedule.json           # Ingested schedule for active matchday across all 3 leagues
│   └── paper_trading.json            # Paper betting ledgers per competition & bot personality
└── models/                           # Retrained ML models (XGBoost, LightGBM, Neural Net, etc.)
```

---

## 3. Data Ingestion & Scrapers

### 1. Scoreboard & Fixture Scraper (`src/data/scrapers/fixtures.py`)
*   Fetches scoreboards, schedules, and live lineups via ESPN API endpoints across `eng.1`, `esp.1`, and `uefa.champions`.
*   Parses completed match results automatically during `python main.py update`.

### 2. Player & Team Performance Scraper (`src/data/scrapers/fbref.py` & `player_stats.py`)
*   Scrapes team-level stats (avg goals scored, avg goals conceded, corner averages) for all 20 EPL clubs, 20 La Liga clubs, and UCL teams.
*   Scrapes player props metrics (goals per 90, assists per 90, expected goals xG) for key club squad members (e.g. Bukayo Saka, Erling Haaland, Kylian Mbappé, Vinícius Jr, Jude Bellingham, Lamine Yamal).

### 3. News & Sentiment Scraper (`src/data/scrapers/news.py`)
*   Scrapes Google News RSS feeds per club for injury reports, squad rotations, and manager pre-match quotes (e.g., "Arteta injury update Arsenal", "Ancelotti press conference Real Madrid").

---

## 4. Modeling Core & ELO Calibration

### 1. Cross-League ELO Database (`src/data/scrapers/elo_db.py` & `src/predictor.py`)
*   Seeds initial club ELO ratings based on historical 2024–2026 domestic finishing positions and UEFA Club Coefficients:
    *   **Tier 1 (Elite UCL Contenders)**: Real Madrid (1980), Man City (1970), Arsenal (1910), Barcelona (1900), Liverpool (1900), Atletico Madrid (1870), Bayern Munich (1930).
    *   **Tier 2 (Upper Mid-Table)**: Aston Villa (1740), Real Sociedad (1720), Newcastle (1730), Athletic Bilbao (1710), Tottenham (1750), Villarreal (1700).
    *   **Tier 3 (Lower Table / Promoted)**: Ipswich (1540), Leganés (1530), Real Valladolid (1520), Leicester (1600).
*   Dynamic ELO updates apply after every match with $K=20$.

### 2. Multi-League Dixon-Coles Poisson Model (`src/models/dixon_coles_decay.py`)
*   Models goal expectation parameters ($\alpha_i$ attack, $\beta_i$ defense) with time-decay ($\xi=0.0019$).
*   Learns competition-specific home advantage parameters ($\gamma$):
    *   $\gamma_{\text{EPL}} \approx +0.32$ goals
    *   $\gamma_{\text{LaLiga}} \approx +0.36$ goals
    *   $\gamma_{\text{UCL}} \approx +0.28$ goals
*   Computes exact bivariate 2D scoreline matrix $M_{h, a}$ ($7 \times 7$).

### 3. Machine Learning Ensemble Retraining (`src/models/trainer.py` & `src/models/stacking_ensemble.py`)
*   Retrains the 6 ML base classifiers (Logistic Regression, Support Vector Machines, Gaussian Discriminant Analysis, Random Forest, XGBoost, Multi-Layer Perceptron Neural Net) and Stacking Meta-Learner on the combined club match feature dataset.

---

## 5. Kalshi Exchange & Same-Game Parlay (SGP) Engine

### 1. Market Scraper (`src/market/kalshi_client.py`)
*   Scrapes active markets for `KXEPLGAME`, `KXLALIGAGAME`, and `KXUCLGAME` series tickers.
*   Extracts implied market probabilities for Moneylines, Goal Lines (Over/Under 1.5, 2.5, 3.5), Both Teams to Score (BTTS), and Corners.

### 2. SGP Validator & Bankroll Sizer (`src/parlay/parlay_engine.py` & `sgp_validator.py`)
*   Integrates joint leg probabilities over the 2D Dixon-Coles scoreline matrix.
*   Applies SGP sandbox validator rules to eliminate mutually exclusive or redundant legs within the same match.
*   Calculates fractional Kelly Criterion stakes ($0.50 \cdot f^*$) for positive-edge tickets with $\ge 5$x multiplier.

---

## 6. CLI UX & LLM Debate Orchestration

### 1. Team Normalization & Automatic League Detection (`src/data/team_mapping.py`)
*   Maps all club names to canonical names and primary competitions.
*   Auto-detects league context from team names:
    *   *Arsenal vs Chelsea* $\rightarrow$ `epl`
    *   *Real Madrid vs Barcelona* $\rightarrow$ `laliga`
    *   *Arsenal vs Real Madrid* $\rightarrow$ `ucl`
*   Command-line flag override supported: `--league epl`, `--league laliga`, `--league ucl`.

### 2. CLI Commands
*   `python main.py init`: Re-initializes dataset and retrains ML ensemble on EPL, La Liga, and UCL match histories.
*   `python main.py update`: Ingests completed scores from ESPN across all 3 leagues, updates ELO ratings, resolves paper bets, and retrains models.
*   `python main.py run-daily`: Executes predictions, debates, and parlay generation for all games scheduled today across EPL, La Liga, and UCL.
*   `python main.py predict "Arsenal vs Chelsea"`: Blends 8 models to print outcome probabilities, ELO diffs, expected goals, and corner expectations.
*   `python main.py ask "Real Madrid vs Barcelona"`: Triggers Magnus (Scout) vs Athena (Quant) debate incorporating club news bulletins and derby rivalry context.
*   `python main.py parlay`: Generates high-edge standard and longshot parlay tickets.
*   `python main.py portfolio`: Prints paper trading bankrolls, win rates, and pending wagers per competition and personality bot.

### 3. Persona Debates (`src/market/llm.py`)
*   **👴 Magnus (The Scout)**: Evaluates manager tactics (Arteta, Ancelotti, Flick), fixture congestion, Champions League mid-week fatigue, and derby rivalries (El Clásico, North London Derby).
*   **🤖 Athena (The Quant)**: Analyzes ELO differentials, Dixon-Coles expected goal matrices, and Kalshi market edge.
