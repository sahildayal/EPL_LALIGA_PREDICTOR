# Design Spec: Corners & Knockout Progression Parlays

**Date:** 2026-07-01  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Introduce corner kick statistics and knockout tournament progression (To-Qualify) markets into the World Cup Predictor. The system will scrape dynamic corner averages, model corner expectations using a Poisson distribution, and calculate joint probabilities for Same-Game Parlays (SGPs) and cross-game parlays on Kalshi.

---

## 2. Architecture & Data Flow

### A. Corners Scraper (`src/data/scrapers/corners.py`)
- **Data Source**: ESPN Match Summary API (`summary?event=ID`).
- **Mechanism**:
  - For a given team, query their 5 most recent completed tournament fixtures.
  - Parse `boxscore -> teams -> statistics` for the entry with `name == 'wonCorners'`.
  - Compute the average corners won and conceded per match.
  - Default fallback: 5.0 won, 5.0 conceded if data is missing or query fails.
- **Caching**:
  - Save results to the SQLite cache under namespace `"corners"`.
  - Set a TTL of **24 hours** (86,400 seconds) to limit API requests.

### B. Probability Modeling (`src/parlay/parlay_engine.py`)
- **Corner Expectations**:
  - For a match between Home ($H$) and Away ($A$) teams:
    $$\lambda_H = \text{Home Corner Avg Won} \times \frac{\text{Away Corner Avg Conceded}}{\text{Tournament Baseline (4.8)}}$$
    $$\lambda_A = \text{Away Corner Avg Won} \times \frac{\text{Home Corner Avg Conceded}}{\text{Tournament Baseline (4.8)}}$$
  - Total Corners expectation: $\lambda_{\text{total}} = \lambda_H + \lambda_A$.
- **Poisson Probabilities**:
  - Compute the probability of total corners exceeding line $X$ (e.g., $P(\text{Corners} > 7.5)$):
    $$P(C_{\text{total}} > X) = 1 - \sum_{k=0}^{\lfloor X \rfloor} \frac{e^{-\lambda_{\text{total}}} \lambda_{\text{total}}^k}{k!}$$
- **SGP Joint Correlation**:
  - Corners are assumed independent of goals.
  - To-Qualify (progression) is correlated with the regulation result:
    $$P(\text{Home Win} \cap \text{Home Qualifies}) = P(\text{Home Win})$$
    $$P(\text{Draw} \cap \text{Home Qualifies}) = P(\text{Draw}) \times P(\text{Home Qualifies in Extra Time/Pens})$$

### C. CLI Output & LLM Debates (`main.py`)
- **`predict`**: Display corner expectation matrix (Won/Conceded/Total) and probabilities for Over 7.5, 8.5, and 9.5 corners.
- **`ask`**: Inject corner stats and To-Qualify progression numbers into the Gemini prompt.
- **`parlay`**: Retrieve active corner and qualification contracts, filter for positive expected value (EV), and suggest optimal >= 5x payout combos.

---

## 3. Testing & Validation Plan
- **Unit Tests (`scratch/test_corners.py`)**:
  - Test corner summary parsing from mocked ESPN JSON.
  - Test Poisson probability limits and edge cases.
- **Integration Tests (`scratch/test_parlay_integration.py`)**:
  - Verify same-game parlay joint probability calculations (regulation wins combined with qualification).
  - Verify corners and To-Qualify are properly loaded into parlay options.
