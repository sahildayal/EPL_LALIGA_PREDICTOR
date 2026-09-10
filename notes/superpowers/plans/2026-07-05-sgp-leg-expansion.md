# SGP Leg Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate To Advance (qualification) and Corners markets into the Kalshi scraper, parlay engine candidate generator, and same-game parlay builder.

---

### Task 1: Scrape, Map, and Generate Corners & To Advance Candidates

**Files:**
- Modify: `src/market/kalshi_client.py`
- Modify: `main.py`
- Modify: `src/parlay/parlay_engine.py`
- Create: `scratch/test_sgp_expansion.py`

**Interfaces:**
- Consumes: `"KXWCQUAL"` and `"KXWCTCORNERS"` tickers.
- Produces: 5-8+ leg parlay combinations featuring corners and progression outcomes.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_sgp_expansion.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestSgpExpansion(unittest.TestCase):
      def test_generate_combos_with_expanded_markets(self):
          from src.parlay.parlay_engine import ParlayEngine
          from src.models.statistical import DixonColesModel
          
          # Initialize mock DixonColes model
          model = DixonColesModel()
          # Fit with dummy matches so it doesn't fail
          import pandas as pd
          dummy_df = pd.DataFrame([
              {"home_team": "france", "away_team": "sweden", "home_score": 2, "away_score": 1, "date": "2026-06-25"},
              {"home_team": "brazil", "away_team": "japan", "home_score": 3, "away_score": 0, "date": "2026-06-25"}
          ])
          model.fit(dummy_df)
          
          engine = ParlayEngine(model)
          
          # Setup mock match data containing Corners and To Advance odds
          match_data = [
              {
                  "home": "france",
                  "away": "sweden",
                  "market_odds": {
                      "home_win": 0.50,
                      "draw": 0.25,
                      "away_win": 0.25,
                      "over_1.5": 0.80,
                      "btts": 0.60,
                      "to_qualify_home": 0.65,
                      "to_qualify_away": 0.35,
                      "corners_over_7.5": 0.70,
                      "corners_over_8.5": 0.50
                  },
                  "players": [("kylian mbappe", True)]
              }
          ]
          
          combos = engine.generate_combos(match_data, max_legs=8, min_odds=2.0, max_odds=200.0)
          
          # Verify that candidates were generated for To Advance and Corners
          # and that some combos contain more than 4 legs
          self.assertTrue(len(combos) > 0)
          has_corners_leg = False
          has_to_advance_leg = False
          max_legs_found = 0
          for c in combos:
              max_legs_found = max(max_legs_found, len(c["legs"]))
              for leg in c["legs"]:
                  if "corners" in leg.get("outcome", ""):
                      has_corners_leg = True
                  if "to_qualify" in leg.get("outcome", ""):
                      has_to_advance_leg = True
                      
          self.assertTrue(has_corners_leg, "Should include corners outcomes in generated parlay legs")
          self.assertTrue(has_to_advance_leg, "Should include to_qualify outcomes in generated parlay legs")
          print(f"Max legs found in parlay combos: {max_legs_found}")
          self.assertTrue(max_legs_found >= 5, "Should generate combos with 5 or more legs")

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_sgp_expansion.py`
  Expected: FAIL (no corners/qualification legs found or assertion errors)

- [ ] **Step 3: Modify Kalshi Client**
  In `get_soccer_markets()` of `src/market/kalshi_client.py`:
  Add `"KXWCQUAL"` and `"KXWCTCORNERS"` to the `series_tickers` list.

- [ ] **Step 4: Modify Main script parsing**
  In `run_parlay()` in `main.py`:
  - Locate loop: `for m in ev["markets"]`
  - Add parsing for corners:
    ```python
                    elif "KXWCTCORNERS" in ticker or "corner" in t:
                        match = re.search(r'(\d+\.?\d*)', t)
                        if match:
                            line_val = float(match.group(1))
                            if "+" in t:
                                line_val = line_val - 0.5
                            key = f"corners_over_{line_val}"
                            odds[key] = m["yes_price"]
    ```
  - Add parsing for progression:
    ```python
                    elif "KXWCQUAL" in ticker:
                        if is_team_match(h, t):
                            odds["to_qualify_home"] = m["yes_price"]
                        elif is_team_match(a, t):
                            odds["to_qualify_away"] = m["yes_price"]
    ```

- [ ] **Step 5: Modify Parlay Engine candidate generation**
  In `generate_combos` of `src/parlay/parlay_engine.py`:
  - Check `to_qualify_home` and `to_qualify_away` odds, query prediction progression probabilities, calculate edges, and append candidates:
    ```python
            # To Advance
            from src.predictor import predict_match
            try:
                res = predict_match(home, away)
                p_adv_home = res.progression_probabilities["home_advances"]
                p_adv_away = res.progression_probabilities["away_advances"]
            except Exception:
                p_adv_home = 0.50
                p_adv_away = 0.50
                
            if "to_qualify_home" in m["market_odds"]:
                prob = p_adv_home
                mkt_p = m["market_odds"]["to_qualify_home"]
                if prob > mkt_p:
                    candidates.append({
                        "match": (home, away),
                        "outcome": "to_qualify_home",
                        "description": f"{home.title()} to Advance ({home.title()} vs {away.title()})",
                        "model_prob": prob,
                        "odds": 1.0 / mkt_p,
                        "type": "game_line"
                    })
            if "to_qualify_away" in m["market_odds"]:
                prob = p_adv_away
                mkt_p = m["market_odds"]["to_qualify_away"]
                if prob > mkt_p:
                    candidates.append({
                        "match": (home, away),
                        "outcome": "to_qualify_away",
                        "description": f"{away.title()} to Advance ({home.title()} vs {away.title()})",
                        "model_prob": prob,
                        "odds": 1.0 / mkt_p,
                        "type": "game_line"
                    })
    ```
  - Check `corners_over_` odds, calculate Poisson corners probabilities, calculate edges, and append candidates:
    ```python
            # Corners
            for key, mkt_p in m["market_odds"].items():
                if key.startswith("corners_over_"):
                    line_val = float(key.split("_")[-1])
                    prob = self.get_corners_probability(home, away, line_val)
                    if prob > mkt_p:
                        candidates.append({
                            "match": (home, away),
                            "outcome": key,
                            "description": f"{home.title()} vs {away.title()} Over {line_val} Corners",
                            "model_prob": prob,
                            "odds": 1.0 / mkt_p,
                            "type": "game_line"
                        })
    ```

- [ ] **Step 6: Run tests to verify they pass**
  Run: `python scratch/test_sgp_expansion.py`
  Run the full test suite (`python -m unittest discover -s scratch`) and ensure all 79 tests pass successfully.

- [ ] **Step 7: Commit**
  ```bash
  git add src/market/kalshi_client.py main.py src/parlay/parlay_engine.py scratch/test_sgp_expansion.py
  git commit -m "feat: support same-game parlay expansion with corners and progression outcomes"
  ```
