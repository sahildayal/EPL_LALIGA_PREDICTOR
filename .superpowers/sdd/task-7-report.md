# Task 7: Same-Game Parlay (SGP) Integration & Correlation Report

## Status
DONE

## Commits
- **70353f4**: feat: complete Same-Game Parlay correlation calculations for corners and progression
- **afe89ec**: docs: update progress ledger for Task 7

## Design & Implementation Details
- **SGP Joint Probability**: Modified `get_same_game_joint_prob` in [parlay_engine.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/parlay/parlay_engine.py) to parse outcomes into regulation, progression, and corners:
  - Corners are assumed independent of goals/progression, multiplying the joint probability by the Poisson CDF corner probability of each line.
  - Progression outcomes are correlated with goals: if the outcome is to qualify, a regulation win implies qualification (1.0), a regulation loss implies elimination (0.0), and a regulation draw cell is scaled by the conditional probability of advancing (taking the total progression probability from ELO/Goalkeeper shootout models, subtracting the regulation win probability, and dividing by the draw probability).
- **Candidate Parlay Legs**: Updated `generate_combos` to automatically retrieve qualification progression probabilities for knockout matches (using `predict_match`) and corner probabilities (using `get_corners_probability`). Added these options to the parlay candidates pool if their model probability is greater than the market probability, offering a positive edge.

## Testing & Verification
- Created integration test [test_parlay_integration.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_parlay_integration.py) verifying that:
  - All calculated probabilities remain within the `[0.0, 1.0]` bound.
  - Corner multipliers are applied independently.
  - Progression correlates correctly with regulation outcomes (e.g. `to_qualify_home` has no additional impact on probability when combined with `home_win` because `home_win` implies qualification).
- All tests completed successfully.
