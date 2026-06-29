### Task 6: Paper Trading Bots Prop Bet Placement
**Files:**
* Modify: `main.py:270-312`
* Test: `scratch/test_bot_betting.py` (create)

- [ ] **Step 1: Write test for bot prop bet evaluation**
  Create `scratch/test_bot_betting.py`:
  Verify that player goals, assists, and G/A outcomes are correctly scored/added to the candidates list for paper trading.

- [ ] **Step 2: Run test to verify it fails**
  Expected: Failures or candidate omissions

- [ ] **Step 3: Modify `main.py` automated betting loops**
  Modify `main.py` lines 270-312 to evaluate player props in the candidates lists. Add code:
  ```python
      # Under main.py candidate list additions:
      for pred in player_prop_predictions:
          name = pred["name"]
          p_probs = pred["probs"]
          for outcome_key, label_suffix, prob_val in [
              ("goals_1", "1+ Goals", p_probs["goals_1"]),
              ("goals_2", "2+ Goals", p_probs["goals_2"]),
              ("assists_1", "1+ Assists", p_probs["assists_1"]),
              ("assists_2", "2+ Assists", p_probs["assists_2"]),
              ("goal_or_assist", "Score or Assist", p_probs["goal_or_assist"])
          ]:
              live_price = None
              for ev in markets:
                  title = ev["event_title"].lower()
                  if " vs " in title:
                      t_parts = title.split(" vs ")
                      t_home = normalize_team_name(t_parts[0])
                      t_away = normalize_team_name(t_parts[1])
                      if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                          for m in ev["markets"]:
                              t = m["title"].lower()
                              if name in t:
                                  if "goal" in label_suffix and "goal" in t:
                                      if "1+" in label_suffix and "1+" in t:
                                          live_price = m["yes_price"]
                                      elif "2+" in label_suffix and "2+" in t:
                                          live_price = m["yes_price"]
                                  elif "assist" in label_suffix and "assist" in t:
                                      if "1+" in label_suffix and "1+" in t:
                                          live_price = m["yes_price"]
                                      elif "2+" in label_suffix and "2+" in t:
                                          live_price = m["yes_price"]
                                  elif "score or assist" in label_suffix and "score or assist" in t:
                                      live_price = m["yes_price"]
              
              if live_price and live_price > 0:
                  edge = prob_val - live_price
                  if edge > 0.02:  # Positive edge threshold
                      label = f"Player Props - {name.title()} {label_suffix}"
                      candidates.append((edge, label, live_price))
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_bot_betting.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add main.py scratch/test_bot_betting.py
  git commit -m "feat: enable paper trading bots to place bets on player prop markets"
  ```

---

