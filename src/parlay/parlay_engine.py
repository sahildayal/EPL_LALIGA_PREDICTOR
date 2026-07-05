import os
import json
import math
import itertools
import numpy as np
from src.models.statistical import DixonColesModel
from src.data.scrapers import player_stats
from src.data.scrapers.corners import get_team_recent_corners
from src.parlay.sgp_validator import SgpSandboxValidator

STATS_PATH = os.path.join("data", "processed", "tournament_player_stats.json")
MASTER_PATH = os.path.join("data", "processed", "master_dataset.csv")


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
        self.tourney_stats = None
        self.team_matches = {}
        self._master_df = None

    def get_same_game_joint_prob(self, home_team: str, away_team: str, outcomes: list, player_props: list = None) -> float:
        """
        Calculates the exact joint probability of multiple outcomes in the same game
        by integrating over the Dixon-Coles bivariate scoreline matrix.
        Outcomes can be: 'home_win', 'draw', 'away_win', 'over_1.5', 'over_2.5', 'btts', 'under_2.5', corners, progression
        player_props: list of tuples (player_name, is_home_player)
        """
        if "to_qualify_home" in outcomes and "to_qualify_away" in outcomes:
            return 0.0

        # Extract corner outcomes and progression outcomes
        corner_outcomes = [o for o in outcomes if "corners_over_" in o]
        progression_outcomes = [o for o in outcomes if "to_qualify_" in o]
        regulation_outcomes = [o for o in outcomes if o not in corner_outcomes and o not in progression_outcomes]

        # Generate scoreline probability matrix
        matrix_key = (home_team.lower(), away_team.lower())
        if matrix_key not in self.memo_score_matrices:
            self.memo_score_matrices[matrix_key] = self.dc_model.predict_score_matrix(home_team, away_team, max_goals=6)
        matrix = self.memo_score_matrices[matrix_key]
        
        # Calculate player goal share coefficients
        player_shares = []
        if player_props:
            h_key = home_team.lower()
            a_key = away_team.lower()
            if h_key not in self.memo_avg_goals:
                self.memo_avg_goals[h_key] = float(fbref_avg_goals(home_team))
            if a_key not in self.memo_avg_goals:
                self.memo_avg_goals[a_key] = float(fbref_avg_goals(away_team))
            h_avg = self.memo_avg_goals[h_key]
            a_avg = self.memo_avg_goals[a_key]
            for name, is_home in player_props:
                p_key = name.lower()
                if p_key not in self.memo_player_stats:
                    self.memo_player_stats[p_key] = player_stats.get_player_stats(name)
                p_stats = self.memo_player_stats[p_key]
                team_name = home_team if is_home else away_team
                p_g90_blended = self.get_blended_player_g90(name, team_name, p_stats)
                share = p_g90_blended / max(h_avg if is_home else a_avg, 0.01)
                share = min(1.0, max(0.0, share))
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

        # Redundant double-sum optimization: compute the three matrix sum expressions once outside the nested loops
        sum_home_win = float(sum(matrix[i, j] for i in range(matrix.shape[0]) for j in range(matrix.shape[1]) if i > j))
        sum_draw = max(1e-4, float(sum(matrix[i, j] for i in range(matrix.shape[0]) for j in range(matrix.shape[1]) if i == j)))
        sum_away_win = float(sum(matrix[i, j] for i in range(matrix.shape[0]) for j in range(matrix.shape[1]) if j > i))

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
                    p_cell_prog = 1.0  # Safety boundaries: Initialize to prevent potential UnboundLocalError
                    if prog == "to_qualify_home":
                        # If home team wins regulation, they qualify (prob = 1.0)
                        if h > a:
                            p_cell_prog = 1.0
                        elif h < a:
                            p_cell_prog = 0.0
                        else:
                            # If draw, probability home team advances in ET/shootout
                            p_cell_prog = (p_adv_home - sum_home_win) / sum_draw
                            p_cell_prog = max(0.0, min(1.0, p_cell_prog))
                    elif prog == "to_qualify_away":
                        if a > h:
                            p_cell_prog = 1.0
                        elif a < h:
                            p_cell_prog = 0.0
                        else:
                            p_cell_prog = (p_adv_away - sum_away_win) / sum_draw
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
                "home_win": (dc_probs["home_win"], f"Moneyline: {home.title()} ({home.title()} vs {away.title()})"),
                "away_win": (dc_probs["away_win"], f"Moneyline: {away.title()} ({home.title()} vs {away.title()})"),
                "draw": (dc_probs["draw"], f"Moneyline: Draw ({home.title()} vs {away.title()})"),
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
            h_key = home.lower()
            a_key = away.lower()
            if h_key not in self.memo_avg_goals:
                self.memo_avg_goals[h_key] = float(fbref_avg_goals(home))
            if a_key not in self.memo_avg_goals:
                self.memo_avg_goals[a_key] = float(fbref_avg_goals(away))
            h_avg = self.memo_avg_goals[h_key]
            a_avg = self.memo_avg_goals[a_key]

            for name, is_home in m.get("players", []):
                p_key = name.lower()
                if p_key not in self.memo_player_stats:
                    self.memo_player_stats[p_key] = player_stats.get_player_stats(name)
                p_stats = self.memo_player_stats[p_key]
                team_name = home if is_home else away
                p_g90_blended = self.get_blended_player_g90(name, team_name, p_stats)
                share = p_g90_blended / max(h_avg if is_home else a_avg, 0.01)
                share = min(1.0, max(0.0, share))
                
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
                        "description": f"{name.title()} to Score (Anytime) in {home.title()} vs {away.title()}",
                        "model_prob": p_prob,
                        "market_prob": p_mkt_prob,
                        "odds": 1.0 / p_mkt_prob
                    })

            # To Advance
            from src.predictor import predict_match
            try:
                res = predict_match(home, away)
                p_adv_home = res.progression_probabilities["home_advances"]
                p_adv_away = res.progression_probabilities["away_advances"]
            except Exception:
                p_adv_home = 0.50
                p_adv_away = 0.50
                
            if "to_qualify_home" in mkt:
                prob = p_adv_home
                mkt_p = mkt["to_qualify_home"]
                if prob > mkt_p:
                    candidates.append({
                        "type": "game_line",
                        "match": (home, away),
                        "outcome": "to_qualify_home",
                        "description": f"{home.title()} to Advance ({home.title()} vs {away.title()})",
                        "model_prob": prob,
                        "market_prob": mkt_p,
                        "odds": 1.0 / mkt_p
                    })
            if "to_qualify_away" in mkt:
                prob = p_adv_away
                mkt_p = mkt["to_qualify_away"]
                if prob > mkt_p:
                    candidates.append({
                        "type": "game_line",
                        "match": (home, away),
                        "outcome": "to_qualify_away",
                        "description": f"{away.title()} to Advance ({home.title()} vs {away.title()})",
                        "model_prob": prob,
                        "market_prob": mkt_p,
                        "odds": 1.0 / mkt_p
                    })

            # Corners
            for key, mkt_p in mkt.items():
                if key.startswith("corners_over_"):
                    line_val = float(key.split("_")[-1])
                    prob = self.get_corners_probability(home, away, line_val)
                    if prob > mkt_p:
                        candidates.append({
                            "type": "game_line",
                            "match": (home, away),
                            "outcome": key,
                            "description": f"{home.title()} vs {away.title()} Over {line_val} Corners",
                            "model_prob": prob,
                            "market_prob": mkt_p,
                            "odds": 1.0 / mkt_p
                        })

        # Sort and limit candidates to prevent combinatorial explosion, focusing on highest edge
        if max_legs > 5:
            candidates.sort(key=lambda x: x["model_prob"] * (x["model_prob"] - x["market_prob"]), reverse=True)
        else:
            candidates.sort(key=lambda x: x["model_prob"] - x["market_prob"], reverse=True)
        
        max_cand = 15 if max_legs > 5 else 25
        candidates = candidates[:max_cand]

        # 2. Generate combinations of 3 to 5 legs
        parlays = []
        for r in range(3, min(max_legs, len(candidates)) + 1):
            for combo in itertools.combinations(candidates, r):
                # Enforce sports betting mutual exclusions using SgpSandboxValidator
                if not SgpSandboxValidator.validate_combo(combo):
                    continue

                # Ensure we don't have conflicting outcomes in the same match
                matches_in_combo = [tuple(sorted(t.lower() for t in leg["match"])) for leg in combo]
                if len(matches_in_combo) != len(set(matches_in_combo)):
                    # Contains same-game legs, need to group and calculate joint same-game prob
                    grouped = {}
                    for leg in combo:
                        match_key = tuple(sorted(t.lower() for t in leg["match"]))
                        grouped.setdefault(match_key, []).append(leg)
                    
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
                            
                            orig_match = legs[0]["match"]
                            sg_prob = self.get_same_game_joint_prob(orig_match[0], orig_match[1], outcomes, p_props)
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
        if min_odds >= 10.0:
            diverse_portfolio = []
            for p in parlays:
                if len(diverse_portfolio) >= 10:
                    break
                # Verify this parlay does not share more than 2 legs with any already-selected parlay
                is_diverse = True
                for sel in diverse_portfolio:
                    shared = sum(1 for leg in p["legs"] for s_leg in sel["legs"] if leg["match"] == s_leg["match"] and leg["description"] == s_leg["description"])
                    if shared >= 3:
                        is_diverse = False
                        break
                if is_diverse:
                    diverse_portfolio.append(p)
            return diverse_portfolio
        return parlays

    def _load_tourney_stats(self):
        if self.tourney_stats is None:
            self.tourney_stats = {"goals": {}, "assists": {}}
            if os.path.exists(STATS_PATH):
                try:
                    with open(STATS_PATH, "r") as f:
                        self.tourney_stats = json.load(f)
                except Exception as e:
                    import logging
                    logging.warning("Error loading tournament stats: %s", e)

    def _get_team_wc_matches(self, team: str) -> float:
        team_key = team.lower()
        if team_key not in self.team_matches:
            m_wc = 3.0 # default baseline matches
            if self._master_df is None and os.path.exists(MASTER_PATH):
                try:
                    import pandas as pd
                    self._master_df = pd.read_csv(MASTER_PATH)
                except Exception as e:
                    import logging
                    logging.warning("Error reading master dataset: %s", e)
            
            if self._master_df is not None:
                try:
                    df = self._master_df
                    m_wc = max(1.0, float(((df["HomeTeam"].str.lower() == team_key) | (df["AwayTeam"].str.lower() == team_key)).sum()))
                except Exception as e:
                    import logging
                    logging.warning("Error counting matches from master dataset: %s", e)
            self.team_matches[team_key] = m_wc
        return self.team_matches[team_key]

    def get_blended_player_g90(self, name: str, team: str, p_stats: dict) -> float:
        self._load_tourney_stats()
        p_g_wc = self.tourney_stats.get("goals", {}).get(name.lower(), 0.0)
        m_wc = self._get_team_wc_matches(team)
        g90_wc = p_g_wc / m_wc
        p_g90 = p_stats.get("goals_per_90", 0.25)
        return 0.5 * p_g90 + 0.5 * g90_wc

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
