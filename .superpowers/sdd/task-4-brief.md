### Task 4: Rest Days, Fatigue Index, and Travel Distance Preprocessing

**Files:**
- Modify: `src/data/preprocessor.py`
- Test: `scratch/test_fatigue_travel.py`

**Interfaces:**
- Consumes: `save_team_travel` and `get_team_last_travel`
- Produces: Travel distance calculation and fatigue rest disparity features added to feature matrix

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_fatigue_travel.py` to verify preprocessor updates:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.data.preprocessor import calculate_distance_km

  class TestFatigueTravel(unittest.TestCase):
      def test_haversine_distance(self):
          # Distance between London (51.5, -0.1) and Paris (48.8, 2.3)
          dist = calculate_distance_km(51.5, -0.1, 48.8, 2.3)
          self.assertTrue(300 < dist < 400)
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_fatigue_travel.py`
  Expected: FAIL with `ImportError` or `AttributeError`
- [ ] **Step 3: Write minimal implementation**
  Edit `src/data/preprocessor.py` to add haversine distance helper and rest disparity metrics.
  ```python
  import math

  def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
      R = 6371.0  # Earth's radius in km
      d_lat = math.radians(lat2 - lat1)
      d_lon = math.radians(lon2 - lon1)
      a = math.sin(d_lat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2
      c = 2 * math.asin(math.sqrt(a))
      return R * c
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_fatigue_travel.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/data/preprocessor.py scratch/test_fatigue_travel.py
  git commit -m "feat: add travel distance math in preprocessor"
  ```

---