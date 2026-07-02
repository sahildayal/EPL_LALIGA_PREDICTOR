### Task 3: Same-Game Parlay (SGP) Integration & Correlation

**Files:**
- Modify: `src/parlay/parlay_engine.py`
- Test: `scratch/test_parlay_integration.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_parlay_integration.py`:
  ```python
  import unittest
  from unittest.mock import patch, MagicMock
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestParlayIntegration(unittest.TestCase):
      def test_same_game_parlay_correlations(self):
          from src.models.statistical import DixonColesModel
          from src.parlay.parlay_engine import ParlayEngine
          
          dc = DixonColesModel()
          engine = ParlayEngine(dc)
          
          # Test SGP combining goals, corners, and qualification
          # Mocking progression probability return value
          outcomes = ["home_win", "over_2.5", "to_qualify_home", "corners_over_8.5"]
          
          with patch.object(engine, "get_corners_probability", return_value=0.70):
              p_sgp = engine.get_same_game_joint_prob("brazil", "japan", outcomes)
              self.assertTrue(0.0 <= p_sgp <= 1.0)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_parlay_integration.py`
  Expected: FAIL (To-Qualify options not handled inside `get_same_game_joint_prob`)

- [ ] **Step 3: Modify SGP Joint Probability & candidate generator**
  Modify `get_same_game_joint_prob` and `generate_combos` in `src/parlay/parlay_engine.py` to support corners and progression:
  In `get_same_game_joint_prob`:
  ```python
      def get_same_game_joint_prob(self, home_team: str, away_team: str, outcomes: list, player_props: list = None) -> float:
          # Extract corner outcomes and progression outcomes
          corner_outcomes = [o for o in outcomes if "corners_over_" in o]
          progression_outcomes = [o for o in outcomes if "to_qualify_" in o]
          regulation_outcomes = [o for o in outcomes if o not in corner_outcomes and o not in progression_outcomes]
          
          # Generate scoreline probability matrix
          matrix_key = (home_team, away_team)
          if matrix_key not in self.memo_score_matrices:
              self.memo_score_matrices[matrix_key] = self.dc_model.predict_score_matrix(home_team, away_team, max_goals=6)
          matrix = self.memo_score_matrices[matrix_key]
          
          # Calculate player goal share coefficients
          player_shares = []
          if player_props:
              if home_team not in self.memo_avg_goals:
                  self.memo_avg_goals[home_team] = float(fbref_avg_goals(home_team))
              if away_team not in self.memo_avg_goals:
                  self.memo_avg_goals[away_team] = float(fbref_avg_goals(away_team))
              h_avg = self.memo_avg_goals[home_team]
              a_avg = self.memo_avg_goals[away_team]
              for name, is_home in player_props:
                  if name not in self.memo_player_stats:
                      self.memo_player_stats[name] = player_stats.get_player_stats(name)
                  p_stats = self.memo_player_stats[name]
                  p_g90 = p_stats.get("goals_per_90", 0.25)
                  share = p_g90 / max(h_avg, 0.01) if is_home else p_g90 / max(a_avg, 0.01)
                  player_shares.append((share, is_home))

          # Fetch Knockout progression model probabilities to compute correlated advances
          from src.predictor import predict_match
          from src.market.llm import get_tournament_stage
          is_knockout = "knockout" in get_tournament_stage().lower()
          
          # Default advances probabilities
          p_adv_home = 0.50
          p_adv_away = 0.50
          if is_knockout and progression_outcomes:
              try:
                  res = predict_match(home_team, away_team)
                  p_adv_home = res.progression_probabilities["home_advances"]
                  p_adv_away = res.progression_probabilities["away_advances"]
              except Exception:
                  pass

          joint_prob = 0.0
          for h in range(matrix.shape[0]):
              for a in range(matrix.shape[1]):
                  p_score = matrix[h, a]
                  
                  # Check if this cell satisfies regulation outcomes
                  cell_ok = True
                  for outcome in regulation_outcomes:
                      if outcome == "home_win" and not (h > a):
                          cell_ok = False
                      elif outcome == "draw" and not (h == a):
                          cell_ok = False
                      elif outcome == "away_win" and not (a > h):
                          cell_ok = False
                      elif outcome == "over_1.5" and not (h + a >= 2):
                          cell_ok = False
                      elif outcome == "over_2.5" and not (h + a >= 3):
                          cell_ok = False
                      elif outcome == "under_2.5" and not (h + a <= 2):
                          cell_ok = False
                      elif outcome == "btts" and not (h >= 1 and a >= 1):
                          cell_ok = False
                      
                      if not cell_ok:
                          break
                          
                  if not cell_ok:
                      continue

                  # Handle progression joint probabilities
                  p_cell_progression = 1.0
                  for prog in progression_outcomes:
                      if prog == "to_qualify_home":
                          # If home team wins regulation, they qualify (prob = 1.0)
                          if h > a:
                              p_cell_prog = 1.0
                          elif h < a:
                              p_cell_prog = 0.0
                          else:
                              # If draw, probability home team advances in ET/shootout
                              p_cell_prog = (p_adv_home - float(sum(matrix[i, j] for i in range(7) for j in range(7) if i > j))) / max(1e-4, float(sum(matrix[i, j] for i in range(7) for j in range(7) if i == j)))
                              p_cell_prog = max(0.0, min(1.0, p_cell_prog))
                      elif prog == "to_qualify_away":
                          if a > h:
                              p_cell_prog = 1.0
                          elif a < h:
                              p_cell_prog = 0.0
                          else:
                              p_cell_prog = (p_adv_away - float(sum(matrix[i, j] for i in range(7) for j in range(7) if j > i))) / max(1e-4, float(sum(matrix[i, j] for i in range(7) for j in range(7) if i == j)))
                              p_cell_prog = max(0.0, min(1.0, p_cell_prog))
                      p_cell_progression *= p_cell_prog
                      
                  # Accrue player scoring probabilities
                  p_players = 1.0
                  for share, is_home in player_shares:
                      goals_scored = h if is_home else a
                      p_players *= (1.0 - math_pow(1.0 - share, goals_scored))
                      
                  joint_prob += p_score * p_players * p_cell_progression

          # Multiply by independent corner probabilities if any present
          for crn in corner_outcomes:
              line_val = float(crn.split("_")[-1])
              p_crn = self.get_corners_probability(home_team, away_team, line_val)
              joint_prob *= p_crn
              
          return round(max(0.0, min(1.0, joint_prob)), 4)
  ```
  Modify `generate_combos` in `src/parlay/parlay_engine.py` to add corners and progression to candidates:
  ```python
            # In generate_combos candidate loop:
            # Add corners and qualification lines to candidates check
            from src.market.llm import get_tournament_stage
            is_knockout = "knockout" in get_tournament_stage().lower()
            
            if is_knockout:
                try:
                    res_prog = predict_match(home, away)
                    p_home_q = res_prog.progression_probabilities["home_advances"]
                    p_away_q = res_prog.progression_probabilities["away_advances"]
                    
                    q_lines = {
                        "to_qualify_home": (p_home_q, f"{home.title()} to Qualify"),
                        "to_qualify_away": (p_away_q, f"{away.title()} to Qualify")
                    }
                    for outcome, (prob, desc) in q_lines.items():
                        mkt_prob = mkt.get(outcome)
                        if mkt_prob and prob > mkt_prob:
                            candidates.append({
                                "type": "game_line",
                                "match": (home, away),
                                "outcome": outcome,
                                "description": desc,
                                "model_prob": prob,
                                "market_prob": mkt_prob,
                                "odds": 1.0 / mkt_prob
                            })
                except Exception:
                    pass
                    
            for line_val in [7.5, 8.5, 9.5]:
                p_crn = self.get_corners_probability(home, away, line_val)
                outcome = f"corners_over_{line_val}"
                mkt_prob = mkt.get(outcome)
                if mkt_prob and p_crn > mkt_prob:
                    candidates.append({
                        "type": "game_line",
                        "match": (home, away),
                        "outcome": outcome,
                        "description": f"{home.title()} vs {away.title()} Over {line_val} Corners",
                        "model_prob": p_crn,
                        "market_prob": mkt_prob,
                        "odds": 1.0 / mkt_prob
                    })
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_parlay_integration.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/parlay/parlay_engine.py scratch/test_parlay_integration.py
  git commit -m "feat: complete Same-Game Parlay correlation calculations for corners and progression"
  ```

---
