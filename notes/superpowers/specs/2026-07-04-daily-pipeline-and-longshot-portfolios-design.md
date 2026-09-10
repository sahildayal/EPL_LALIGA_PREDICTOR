# Design Spec: Daily Ingestion, execution pipeline and 50x-400x Parlay portfolios

**Date:** 2026-07-04  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Build an automated daily betting pipeline and enhance the longshot parlay engine. Specifically:
1. Rename the bot personalities to **Magnus** (Scout) and **Athena** (Quant) across the codebase.
2. Upgrade `python main.py update` to dynamically fetch today's and tomorrow's upcoming tournament fixtures, storing them in `data/processed/daily_schedule.json`.
3. Scrape live tournament player statistics (goals/assists) during `update` and store them in `data/processed/tournament_player_stats.json` to dynamically calibrate player prop probabilities.
4. Implement a new CLI command `python main.py run-daily` that runs the prediction, debate, and parlay pipeline for all of today's matches sequentially.
5. Upgrade the parlay engine to target **50x to 400x** payout longshots, and generate a diverse **10-card portfolio** (using flat $2 stakes) that covers multiple permutations of outcomes to maximize net returns.

---

## 2. Component Design & Interfaces

### A. Bot Renaming & Migration
- **Target Personalities**:
  - `big_d` $\rightarrow$ `magnus`
  - `sigmaballs` $\rightarrow$ `athena`
- **Migration logic**: 
  - Update `src/market/paper_trading.py -> load_state()` to migrate historical database keys dynamically.

### B. Ingestion Layer (`src/data/scrapers/upcoming_and_stats.py`)
1. **Upcoming Fixtures Ingestion**:
   - Query the ESPN World Cup scoreboard for the current day and next 2 days.
   - Filter for uncompleted matches.
   - Output to `data/processed/daily_schedule.json`.
2. **Live Tournament Stats Ingestion**:
   - Query `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/statistics`.
   - Parse top 15 goals and assists leaders.
   - Output to `data/processed/tournament_player_stats.json`.

### C. Parlay Engine Enhancements (`src/parlay/parlay_engine.py`)
1. **Player Prop Tournament Calibration**:
   - Look up player World Cup goals ($G_{\text{wc}}$) and assists ($A_{\text{wc}}$) in `tournament_player_stats.json`.
   - Compute World Cup rate: $G_{90,\text{wc}} = G_{\text{wc}} / M_{\text{wc}}$ where $M_{\text{wc}}$ is the team's completed tournament match count (or a default of 3 if not found).
   - Blend: $G_{90,\text{blended}} = 0.5 \times G_{90,\text{historical}} + 0.5 \times G_{90,\text{wc}}$.
   - Clamp `share` within `[0.0, 1.0]`.
2. **50x-400x Longshot Portfolio Generation**:
   - Filter candidate parlays for payout multiplier range `[50.0, 400.0]`.
   - Generate a **diverse 10-card portfolio**:
     - Sort all candidate combos by **Edge descending** (Model Joint Prob - Market Implied Prob).
     - Select Card #1 (highest edge).
     - For Cards #2 to #10, select the next best parlay that shares **at most 2 legs** with any already-selected parlay in the portfolio. This ensures wide permutation coverage (hedging).

### D. Daily Execution Command (`main.py`)
- Implement `python main.py run-daily`.
- Read `data/processed/daily_schedule.json`.
- For each match scheduled for today:
  1. Print match banner.
  2. Run `run_predict(home, away)` (ML model ensemble and corners expectation).
  3. Run `run_ask(home, away, model)` (Magnus vs. Athena Gemini debate, places paper trades).
  4. Generate and display standard & longshot portfolios (places flat $2 card paper trades).

---

## 3. Testing & Verification Plan
- **Unit Tests (`scratch/test_stats_ingestion.py`)**:
  - Verify scraping and parsing of ESPN tournament player statistics.
  - Verify upcoming fixtures JSON output format.
- **Integration Tests (`scratch/test_longshot_portfolio.py`)**:
  - Test `ParlayEngine` diverse portfolio algorithm to verify exactly 10 cards are selected with less than 3 shared legs.
  - Test dynamic goal scorer blending and bounds.
- **Bot Renaming Tests (`scratch/test_bot_rename.py`)**:
  - Verify state migration logic loads legacy files and converts them correctly.
