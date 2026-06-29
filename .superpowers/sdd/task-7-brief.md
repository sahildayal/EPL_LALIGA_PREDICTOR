### Task 7: End-to-End Integration Verification
**Files:**
* Create: `scratch/test_player_props_integration.py`

- [ ] **Step 1: Write complete integration test**
  Create `scratch/test_player_props_integration.py`:
  ```python
  import sys
  import os
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  
  import subprocess
  
  def run_e2e_test():
      print("Running predict command for South Africa vs Canada...")
      cmd = ["python", "main.py", "predict", "South Africa vs Canada"]
      result = subprocess.run(cmd, capture_output=True, text=True)
      
      print("STDOUT:")
      print(result.stdout)
      print("STDERR:")
      print(result.stderr)
      
      assert result.returncode == 0
      assert "Player Goals" in result.stdout or "Player Assists" in result.stdout or "Player G/A" in result.stdout
      assert "Predict Portfolio Bot Paper Bets" in result.stdout
      print("ALL END-TO-END VERIFICATION CHECKS PASSED!")

  if __name__ == "__main__":
      run_e2e_test()
  ```

- [ ] **Step 2: Execute integration test and verify output**
  Run: `python scratch/test_player_props_integration.py`
  Expected: PASS with full output printing prediction matrix, player props table with value edits, and paper bets.

- [ ] **Step 3: Commit**
  ```bash
  git add scratch/test_player_props_integration.py
  git commit -m "test: verify end-to-end player prop predictions and trading bot bets"
  ```
