# Design Spec: Same-Game Parlay (SGP) Leg Expansion

**Date:** 2026-07-05  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Expand Same-Game Parlay (SGP) and parlay engine candidate options during the knockout stages. By integrating **To Advance / Qualification** markets and **Total Corners** markets directly into the candidate generator, we can build rich, high-leg (5 to 8+ legs) parlays even on single-game slates.

---

## 2. Technical Design

### A. Kalshi Client Series Extension (`src/market/kalshi_client.py`)
- Append `"KXWCQUAL"` (To Advance) and `"KXWCTCORNERS"` (Corners) to the series tickers list in `get_soccer_markets()`:
  ```python
  series_tickers = ["KXWCGAME", "KXWCBTTS", "KXWCTOTAL", "KXWCGOAL", "KXWCAST", "KXWCSOA", "KXWCQUAL", "KXWCTCORNERS"]
  ```

### B. Market Parsing & Mapping (`main.py`)
- In `run_parlay()`, update the market parsing loop:
  - **To Advance**:
    - If `KXWCQUAL` is in the ticker:
      - If the title matches the home team, assign `odds["to_qualify_home"] = yes_price`.
      - If the title matches the away team, assign `odds["to_qualify_away"] = yes_price`.
  - **Corners**:
    - If `KXWCTCORNERS` is in the ticker or `"corner"` in title:
      - Extract the number line (e.g. `8+` or `8.5`) using regex. Normalize integer `X+` to `X-0.5` (so `8+` is `over_7.5`).
      - Store in `odds[f"corners_over_{line}"] = yes_price`.

### C. Parlay Engine Candidate Generation (`src/parlay/parlay_engine.py`)
- In `generate_combos(self, match_data, ...)`:
  - For each match `m`:
    - **To Advance**:
      - If `"to_qualify_home"` is in `market_odds`, call `predict_match(home, away)` to get the model's home progression probability. If there is a positive edge, append to candidates.
      - Do the same for `"to_qualify_away"`.
    - **Corners**:
      - Find all keys in `market_odds` starting with `"corners_over_"`.
      - Extract `line_val = float(key.split("_")[-1])`.
      - Calculate model probability: `prob = self.get_corners_probability(home, away, line_val)`.
      - If there is a positive edge, append to candidates with outcome `key` (e.g. `corners_over_7.5`).

---

## 3. Testing & Verification Plan
- **Unit Test (`scratch/test_sgp_expansion.py`)**:
  - Mock match data containing `to_qualify_home` and `corners_over_8.5` in `market_odds`.
  - Run `generate_combos` with `max_legs=8` and verify that the candidates include To Advance and Corners outcomes.
  - Verify that the resulting parlay combinations contain these new legs.
