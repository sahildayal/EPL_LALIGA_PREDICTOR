### Task 1: SQLite Storage Scaffolding & Travel Logs Cache

**Files:**
- Modify: `src/data/cache.py`
- Test: `scratch/test_db_scaffolding.py`

**Interfaces:**
- Consumes: None
- Produces: `save_team_travel(team, city, date, lat, lon)`, `get_team_last_travel(team)`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_db_scaffolding.py` and write test to verify scaffolding works.
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.data.cache import save_team_travel, get_team_last_travel, _conn

  class TestDbScaffolding(unittest.TestCase):
      def test_travel_caching(self):
          save_team_travel("portugal", "lisbon", "2026-06-28", 38.72, -9.14)
          last_travel = get_team_last_travel("portugal")
          self.assertEqual(last_travel["city"], "lisbon")
          self.assertEqual(last_travel["lat"], 38.72)
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_db_scaffolding.py`
  Expected: FAIL with `ImportError: cannot import name 'save_team_travel'`
- [ ] **Step 3: Write minimal implementation**
  Modify `src/data/cache.py` to create the `team_travel` table and implement save/get functions.
  ```python
  # Add table definition in cache.py:
  # CREATE TABLE IF NOT EXISTS team_travel (
  #     team TEXT PRIMARY KEY,
  #     city TEXT NOT NULL,
  #     date TEXT NOT NULL,
  #     latitude REAL NOT NULL,
  #     longitude REAL NOT NULL
  # )
  
  def save_team_travel(team: str, city: str, date: str, lat: float, lon: float):
      conn = _conn()
      try:
          conn.execute("""
              INSERT OR REPLACE INTO team_travel (team, city, date, latitude, longitude)
              VALUES (?, ?, ?, ?, ?)
          """, (team.lower().strip(), city.lower().strip(), date, lat, lon))
          conn.commit()
      finally:
          conn.close()

  def get_team_last_travel(team: str) -> dict:
      conn = _conn()
      try:
          cursor = conn.execute("""
              SELECT city, date, latitude, longitude FROM team_travel WHERE team = ?
          """, (team.lower().strip(),))
          row = cursor.fetchone()
          if row:
              return {"city": row[0], "date": row[1], "lat": row[2], "lon": row[3]}
          return None
      finally:
          conn.close()
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_db_scaffolding.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/data/cache.py scratch/test_db_scaffolding.py
  git commit -m "feat: implement team travel cache table and query methods in SQLite"
  ```

---