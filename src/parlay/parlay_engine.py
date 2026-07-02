import math
import itertools
import numpy as np
from src.models.statistical import DixonColesModel
from src.data.scrapers import player_stats
from src.data.scrapers.corners import get_team_recent_corners


class ParlayEngine:
    """
    Generates high-probability, correlated same-game and cross-game parlays (3-5 legs)
    with positive edge and >= 5x multiplier on Kalshi.
    """

    def __init__(self, dc_model: DixonColesModel):
        self.dc_model = dc_model
        self.memo_avg_goals = {}
        self.memo_player_stats = {}
        self.memo_score_matrices = {}

    def get_same_game_joint_prob(self, home_team: str, away_team: str, outcomes: list, player_props: list = None) -> float:
        """
        Calculates the exact joint probability of multiple outcomes in the same game
        by integrating over the Dixon-Coles bivariate scoreline matrix.
        Outcomes can be: 'home_win', 'draw', 'away_win', 'over_1.5', 'over_2.5', 'btts', 'under_2.5', corners, progression
        player_props: list of tuples (player_name, is_home_player)
        """
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

    def generate_combos(self, match_data: list, max_legs: int = 5, min_odds: float = 5.0, max_odds: float = 150.0) -> list:
        """
        match_data: list of dicts with:
           {
             "home": str, "away": str,
             "market_odds": {"home_win": float, "draw": float, "away_win": float, "over_1.5": float, "btts": float},
             "players": list of (name, is_home)
           }
        """
        # 1. Generate candidate legs (single bets) with positive edges
        candidates = []
        for m in match_data:
            home, away = m["home"], m["away"]
            # Estimate probabilities using Dixon-Coles
            dc_probs = self.dc_model.predict(home, away)
            matrix = self.dc_model.predict_score_matrix(home, away, max_goals=6)
            
            # Game Lines probabilities
            over_15 = float(sum(matrix[h, a] for h in range(7) for a in range(7) if h + a >= 2))
            over_25 = float(sum(matrix[h, a] for h in range(7) for a in range(7) if h + a >= 3))
            btts = float(sum(matrix[h, a] for h in range(7) for a in range(7) if h >= 1 and a >= 1))
            
            lines = {
                "home_win": (dc_probs["home_win"], "Moneyline: " + home.title()),
                "away_win": (dc_probs["away_win"], "Moneyline: " + away.title()),
                "draw": (dc_probs["draw"], "Moneyline: Draw"),
                "over_1.5": (over_15, f"{home.title()} vs {away.title()} Over 1.5 Goals"),
                "over_2.5": (over_25, f"{home.title()} vs {away.title()} Over 2.5 Goals"),
                "btts": (btts, f"{home.title()} vs {away.title()} Both Teams to Score")
            }
            
            # Check edge against market odds
            mkt = m.get("market_odds") or {}
            for outcome, (prob, desc) in lines.items():
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
                    
            # Player props candidates
            if home not in self.memo_avg_goals:
                self.memo_avg_goals[home] = float(fbref_avg_goals(home))
            if away not in self.memo_avg_goals:
                self.memo_avg_goals[away] = float(fbref_avg_goals(away))
            h_avg = self.memo_avg_goals[home]
            a_avg = self.memo_avg_goals[away]

            for name, is_home in m.get("players", []):
                if name not in self.memo_player_stats:
                    self.memo_player_stats[name] = player_stats.get_player_stats(name)
                p_stats = self.memo_player_stats[name]
                p_g90 = p_stats.get("goals_per_90", 0.25)
                share = p_g90 / max(h_avg if is_home else a_avg, 0.01)
                
                # P(Player scores) = sum_h,a matrix[h,a] * (1 - (1-share)^team_goals)
                p_prob = 0.0
                for h in range(7):
                    for a in range(7):
                        g = h if is_home else a
                        p_prob += matrix[h, a] * (1.0 - math_pow(1.0 - share, g))
                
                # Check player prop market if available
                p_mkt_prob = mkt.get(f"scorer_{name.lower().replace(' ', '_')}")
                if p_mkt_prob and p_prob > p_mkt_prob:
                    candidates.append({
                        "type": "player_prop",
                        "match": (home, away),
                        "player": name,
                        "is_home": is_home,
                        "description": f"{name.title()} to Score (Anytime)",
                        "model_prob": p_prob,
                        "market_prob": p_mkt_prob,
                        "odds": 1.0 / p_mkt_prob
                    })

            # Add corners and qualification lines to candidates check
            from src.market.llm import get_tournament_stage
            from src.predictor import predict_match
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

        # Sort and limit candidates to prevent combinatorial explosion, focusing on highest edge
        candidates.sort(key=lambda x: x["model_prob"] - x["market_prob"], reverse=True)
        candidates = candidates[:25]

        # 2. Generate combinations of 3 to 5 legs
        parlays = []
        for r in range(3, min(max_legs, len(candidates)) + 1):
            for combo in itertools.combinations(candidates, r):
                # Group legs by match to check mutual exclusions
                match_legs = {}
                for leg in combo:
                    match_legs.setdefault(leg["match"], []).append(leg)
                
                # Enforce sports betting mutual exclusions:
                # - Max 1 Moneyline outcome (home_win, away_win, draw) per match
                # - Max 1 Totals/Spread outcome (over_1.5, over_2.5, under_2.5) per match
                invalid_combo = False
                for match_key, legs in match_legs.items():
                    ml_count = sum(1 for leg in legs if leg.get("outcome") in ["home_win", "away_win", "draw"])
                    totals_count = sum(1 for leg in legs if leg.get("outcome") in ["over_1.5", "over_2.5", "under_2.5"])
                    if ml_count > 1 or totals_count > 1:
                        invalid_combo = True
                        break
                if invalid_combo:
                    continue

                # Ensure we don't have conflicting outcomes in the same match
                matches_in_combo = [leg["match"] for leg in combo]
                if len(matches_in_combo) != len(set(matches_in_combo)):
                    # Contains same-game legs, need to group and calculate joint same-game prob
                    grouped = {}
                    for leg in combo:
                        grouped.setdefault(leg["match"], []).append(leg)
                    
                    joint_prob = 1.0
                    total_odds = 1.0
                    for match, legs in grouped.items():
                        if len(legs) == 1:
                            joint_prob *= legs[0]["model_prob"]
                            total_odds *= legs[0]["odds"]
                        else:
                            # Same game combo!
                            outcomes = [l["outcome"] for l in legs if l["type"] == "game_line"]
                            p_props = [(l["player"], l["is_home"]) for l in legs if l["type"] == "player_prop"]
                            
                            sg_prob = self.get_same_game_joint_prob(match[0], match[1], outcomes, p_props)
                            joint_prob *= sg_prob
                            # Parlay odds for same game (implied Kalshi odds product)
                            total_odds *= np.prod([l["odds"] for l in legs])
                else:
                    # Pure cross-game, independent events
                    joint_prob = np.prod([leg["model_prob"] for leg in combo])
                    total_odds = np.prod([leg["odds"] for leg in combo])

                # Check if total payout multiplier is within our target range
                if min_odds <= total_odds <= max_odds:
                    market_implied = 1.0 / total_odds
                    edge = joint_prob - market_implied
                    
                    if edge > 0.0:
                        parlays.append({
                            "legs": combo,
                            "legs_count": len(combo),
                            "payout_multiplier": round(total_odds, 2),
                            "joint_probability": round(joint_prob, 4),
                            "market_probability": round(market_implied, 4),
                            "edge": round(edge, 4),
                        })
                        
        # Sort by edge descending
        parlays.sort(key=lambda x: x["edge"], reverse=True)
        return parlays

    def get_corners_probability(self, home: str, away: str, line: float) -> float:
        """
        Calculates probability of total corners exceeding 'line' using Poisson CDF.
        """
        h_stats = get_team_recent_corners(home)
        a_stats = get_team_recent_corners(away)
        
        # Calculate expected lambda for both sides
        # Baseline tournament corners conceded is 4.8
        lambda_h = h_stats["won"] * (a_stats["conceded"] / 4.8)
        lambda_a = a_stats["won"] * (h_stats["conceded"] / 4.8)
        
        lambda_total = lambda_h + lambda_a
        if lambda_total <= 0:
            lambda_total = 9.6 # fallback default

        # Poisson CDF: P(X <= k) = sum_{i=0}^k e^{-lambda} * lambda^i / i!
        k = int(line)
        cdf = 0.0
        for i in range(k + 1):
            cdf += math.exp(-lambda_total) * (lambda_total ** i) / math.factorial(i)
            
        p_over = 1.0 - cdf
        return round(max(0.0, min(1.0, p_over)), 4)


def fbref_avg_goals(team: str) -> float:
    # Quick helper for team averages
    from src.data.scrapers import fbref
    d = fbref.get_team_data(team)
    return d.get("avg_goals", 1.4)


def math_pow(base: float, exp: float) -> float:
    try:
        return math.pow(base, exp)
    except OverflowError:
        return 0.0
