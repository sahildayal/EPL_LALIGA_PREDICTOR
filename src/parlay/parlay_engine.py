import math
import itertools
import numpy as np
from src.models.statistical import DixonColesModel
from src.data.scrapers import player_stats


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
        Outcomes can be: 'home_win', 'draw', 'away_win', 'over_1.5', 'over_2.5', 'btts', 'under_2.5'
        player_props: list of tuples (player_name, is_home_player)
        """
        # Generate scoreline probability matrix (up to 7x7 goals)
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
                # Player share of team goals safely avoiding division by zero
                share = p_g90 / max(h_avg, 0.01) if is_home else p_g90 / max(a_avg, 0.01)
                player_shares.append((share, is_home))

        joint_prob = 0.0
        for h in range(matrix.shape[0]):
            for a in range(matrix.shape[1]):
                p_score = matrix[h, a]
                
                # Check if this cell satisfies all game line outcomes
                cell_ok = True
                for outcome in outcomes:
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
                
                # Calculate probability of player props occurring *in this specific scoreline*
                # (Assuming binomial distribution of goal scorers within team goals)
                p_players = 1.0
                for share, is_home in player_shares:
                    goals_scored = h if is_home else a
                    # Probability player scores at least 1 goal given team scores goals_scored
                    p_player_scores = 1.0 - math_pow(1.0 - share, goals_scored)
                    p_players *= p_player_scores
                
                joint_prob += p_score * p_players
                
        return round(joint_prob, 4)

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
