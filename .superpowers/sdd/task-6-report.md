# Task 6 Report: Probability Modeling & Poisson CDF

## Implementation Details
We implemented the `get_corners_probability` method inside the `ParlayEngine` class (`src/parlay/parlay_engine.py`).
The method calculates the probability of total corners exceeding a given `line` value using a Poisson CDF with:
1. **Lambda calculations**: Expected corners won by home/away teams normalized against the baseline tournament average of 4.8 corners conceded.
2. **Poisson CDF**: P(X <= k) is evaluated iteratively and then subtracted from 1.0 to get P(X > k).
3. **Bound constraints**: The output probability is clamped between `0.0` and `1.0` and rounded to 4 decimal places.

## Testing & Verification
We wrote unit tests in `scratch/test_parlay_engine_corners.py` following TDD.
1. The test mocks recent corner statistics for home/away teams.
2. Verified that `get_corners_probability` calculates expected values correctly.
3. Ran test suite to verify success.

### Test Output
```
Ran 1 test in 2.544s

OK
```

## Git Commit
- **SHA**: `c46c581`
- **Subject**: `feat: implement corner expectation Poisson modeling and get_corners_probability`
