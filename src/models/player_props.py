import numpy as np
import math

def calculate_player_prop_probs(player_stats: dict, is_home: bool, score_matrix: np.ndarray, team_historical_avg: float) -> dict:
    """
    Calculates player prop probabilities using binomial distributions
    conditionally evaluated against the score expectation matrix.
    """
    goals_per_90 = player_stats.get("goals_per_90", 0.25)
    assists_per_90 = player_stats.get("assists_per_90", 0.15)
    
    avg_goals = max(team_historical_avg, 0.5)
    
    # Player shares per team goal
    s_g = min(goals_per_90 / avg_goals, 0.95)
    s_a = min(assists_per_90 / avg_goals, 0.95)
    s_ga = min(s_g + s_a, 0.95)
    
    # Cumulative binomial probability helper
    # P(at least k events in g trials)
    def p_binomial(k, g, share):
        if g < k:
            return 0.0
        if k <= 0:
            return 1.0
        prob = 0.0
        for j in range(k, g + 1):
            # nCr * p^j * (1-p)^(n-j)
            coeff = math.comb(g, j)
            prob += coeff * (share ** j) * ((1.0 - share) ** (g - j))
        return prob

    prob_g1 = 0.0
    prob_g2 = 0.0
    prob_a1 = 0.0
    prob_a2 = 0.0
    prob_ga = 0.0
    
    h_max, a_max = score_matrix.shape
    for h in range(h_max):
        for a in range(a_max):
            cell_p = score_matrix[h, a]
            if cell_p <= 0:
                continue
            
            g = h if is_home else a
            prob_g1 += cell_p * p_binomial(1, g, s_g)
            prob_g2 += cell_p * p_binomial(2, g, s_g)
            prob_a1 += cell_p * p_binomial(1, g, s_a)
            prob_a2 += cell_p * p_binomial(2, g, s_a)
            prob_ga += cell_p * p_binomial(1, g, s_ga)
            
    return {
        "goals_1": round(prob_g1, 4),
        "goals_2": round(prob_g2, 4),
        "assists_1": round(prob_a1, 4),
        "assists_2": round(prob_a2, 4),
        "goal_or_assist": round(prob_ga, 4)
    }
