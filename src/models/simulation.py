import numpy as np
from scipy.stats import poisson
import json
from pathlib import Path

from src.predictor import get_fitted_dixon_coles, normalize_team_name, ELO_PREDICTOR, load_elo
from src.data.scrapers.fixtures import get_match_lineups

# Goalkeeper penalty save rates
GOALIE_SAVE_RATES = {
    "alisson": 0.33,
    "pickford": 0.28,
    "suzuki": 0.25,
    "zion suzuki": 0.25
}

TEAM_GOALIE_FALLBACK = {
    "brazil": 0.33,
    "england": 0.28,
    "japan": 0.25
}

def get_goalie_rate(team_name: str) -> float:
    """
    Resolves the goalkeeper save rate for a given team name (case-insensitive).
    Checks starting lineup first, then falls back to a team-level dictionary,
    and finally defaults to 0.25.
    """
    team_norm = normalize_team_name(team_name)
    
    # Try to find goalie from lineups
    try:
        lineups = get_match_lineups(team_norm, "placeholder")
        lineup = lineups.get("home_lineup", [])
        for player in lineup:
            player_clean = player.lower().strip()
            for goalie, rate in GOALIE_SAVE_RATES.items():
                if goalie in player_clean:
                    return rate
    except Exception:
        pass
        
    # Fallback to team level mapping
    return TEAM_GOALIE_FALLBACK.get(team_norm, 0.25)


def load_top_8_teams() -> list:
    """
    Loads top 8 teams based on current ELO ratings.
    """
    try:
        load_elo()
        ratings = ELO_PREDICTOR.ratings
        if ratings:
            sorted_ratings = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
            return [team for team, elo in sorted_ratings[:8]]
    except Exception:
        pass
    # Fallback to standard top 8 nations
    return ["argentina", "france", "brazil", "england", "spain", "portugal", "netherlands", "germany"]


def run_tournament_simulation(num_runs: int = 10000, teams: list = None) -> dict:
    """
    Simulates the knockout bracket starting from Quarterfinals to Finals.
    Tracks progression probabilities for each team.
    
    Returns:
        dict: A dictionary containing aggregated stage progression probabilities.
    """
    if teams is None:
        teams = load_top_8_teams()
    
    if len(teams) != 8:
        raise ValueError("Tournament simulation requires exactly 8 teams for the Quarterfinals stage.")
        
    # Case-insensitive normalization
    normalized_teams = [normalize_team_name(t) for t in teams]
    
    # Load Dixon-Coles model parameters
    dc_model = get_fitted_dixon_coles()
    
    # Compute mean alphas/betas for teams not in model indices
    alphas = dc_model.params.get('alphas', np.array([]))
    betas = dc_model.params.get('betas', np.array([]))
    
    mean_alpha = np.mean(alphas) if len(alphas) > 0 else 0.0
    mean_beta = np.mean(betas) if len(betas) > 0 else -0.1
    gamma = dc_model.params.get('gamma', 0.2)
    rho = dc_model.params.get('rho', 0.0)
    
    match_cache = {}
    
    def get_match_sim_data(home, away):
        key = (home, away)
        if key in match_cache:
            return match_cache[key]
            
        h_idx = dc_model.team_indices.get(home)
        a_idx = dc_model.team_indices.get(away)
        
        alpha_h = dc_model.params['alphas'][h_idx] if h_idx is not None else mean_alpha
        beta_h = dc_model.params['betas'][h_idx] if h_idx is not None else mean_beta
        alpha_a = dc_model.params['alphas'][a_idx] if a_idx is not None else mean_alpha
        beta_a = dc_model.params['betas'][a_idx] if a_idx is not None else mean_beta
        
        # Regulation (90m) intensities
        eta_h = np.clip(alpha_h + beta_a + gamma, -10, 10)
        eta_a = np.clip(alpha_a + beta_h, -10, 10)
        lam = np.exp(eta_h)
        mu = np.exp(eta_a)
        
        # Regulation probability matrix
        max_goals = 10
        prob_matrix = np.zeros((max_goals + 1, max_goals + 1))
        for x in range(max_goals + 1):
            for y in range(max_goals + 1):
                poisson_h = poisson.pmf(x, lam)
                poisson_a = poisson.pmf(y, mu)
                tau_val = dc_model._tau(x, y, lam, mu, rho)
                if tau_val <= 0:
                    tau_val = 1e-10
                prob_matrix[x, y] = tau_val * poisson_h * poisson_a
                
        prob_matrix /= np.sum(prob_matrix)
        flat_probs = prob_matrix.flatten()
        
        # Extra Time (30m) intensities (scaled by 1/3)
        lam_et = lam / 3.0
        mu_et = mu / 3.0
        max_goals_et = 4
        prob_matrix_et = np.zeros((max_goals_et + 1, max_goals_et + 1))
        for x in range(max_goals_et + 1):
            for y in range(max_goals_et + 1):
                poisson_h_et = poisson.pmf(x, lam_et)
                poisson_a_et = poisson.pmf(y, mu_et)
                tau_val_et = dc_model._tau(x, y, lam_et, mu_et, rho)
                if tau_val_et <= 0:
                    tau_val_et = 1e-10
                prob_matrix_et[x, y] = tau_val_et * poisson_h_et * poisson_a_et
                
        prob_matrix_et /= np.sum(prob_matrix_et)
        flat_probs_et = prob_matrix_et.flatten()
        
        # Shootout win probability
        h_gk = get_goalie_rate(home)
        a_gk = get_goalie_rate(away)
        p_shootout_home = h_gk / (h_gk + a_gk) if (h_gk + a_gk) > 0 else 0.5
        
        sim_data = {
            "flat_probs": flat_probs,
            "flat_probs_et": flat_probs_et,
            "p_shootout_home": p_shootout_home,
            "max_goals": max_goals,
            "max_goals_et": max_goals_et
        }
        match_cache[key] = sim_data
        return sim_data

    def simulate_match(home, away) -> str:
        sim_data = get_match_sim_data(home, away)
        
        # Regulation
        max_goals = sim_data["max_goals"]
        idx = np.random.choice(len(sim_data["flat_probs"]), p=sim_data["flat_probs"])
        h_g = idx // (max_goals + 1)
        a_g = idx % (max_goals + 1)
        
        if h_g > a_g:
            return home
        elif a_g > h_g:
            return away
            
        # Extra Time
        max_goals_et = sim_data["max_goals_et"]
        idx_et = np.random.choice(len(sim_data["flat_probs_et"]), p=sim_data["flat_probs_et"])
        h_g_et = idx_et // (max_goals_et + 1)
        a_g_et = idx_et % (max_goals_et + 1)
        
        h_tot = h_g + h_g_et
        a_tot = a_g + a_g_et
        
        if h_tot > a_tot:
            return home
        elif a_tot > h_tot:
            return away
            
        # Penalty Shootout
        if np.random.rand() < sim_data["p_shootout_home"]:
            return home
        else:
            return away

    # Track progression counts
    progression_counts = {t: {"quarterfinals": 0, "semifinals": 0, "finals": 0, "champion": 0} for t in normalized_teams}
    
    # Monte Carlo simulation loop
    for _ in range(num_runs):
        # Quarterfinals
        qf_winners = []
        for i in range(4):
            t_home = normalized_teams[2 * i]
            t_away = normalized_teams[2 * i + 1]
            progression_counts[t_home]["quarterfinals"] += 1
            progression_counts[t_away]["quarterfinals"] += 1
            
            winner = simulate_match(t_home, t_away)
            qf_winners.append(winner)
            
        # Semifinals
        sf_winners = []
        for i in range(2):
            t_home = qf_winners[2 * i]
            t_away = qf_winners[2 * i + 1]
            progression_counts[t_home]["semifinals"] += 1
            progression_counts[t_away]["semifinals"] += 1
            
            winner = simulate_match(t_home, t_away)
            sf_winners.append(winner)
            
        # Finals
        t_home = sf_winners[0]
        t_away = sf_winners[1]
        progression_counts[t_home]["finals"] += 1
        progression_counts[t_away]["finals"] += 1
        
        champion = simulate_match(t_home, t_away)
        progression_counts[champion]["champion"] += 1

    # Convert counts to probabilities
    probabilities = []
    for team in normalized_teams:
        team_probs = {
            "team": team,
            "quarterfinals": round(progression_counts[team]["quarterfinals"] / num_runs, 4),
            "semifinals": round(progression_counts[team]["semifinals"] / num_runs, 4),
            "finals": round(progression_counts[team]["finals"] / num_runs, 4),
            "champion": round(progression_counts[team]["champion"] / num_runs, 4)
        }
        probabilities.append(team_probs)
        
    # Gather ELO ratings and goalkeeper save rates for all teams
    from src.predictor import ELO_PREDICTOR
    all_teams = list(ELO_PREDICTOR.ratings.keys()) if ELO_PREDICTOR.ratings else normalized_teams
    elo_ratings = {t: float(ELO_PREDICTOR.ratings.get(t, 1500)) for t in all_teams}
    goalie_rates = {t: float(get_goalie_rate(t)) for t in all_teams}
    
    alphas_list = [float(a) for a in alphas]
    betas_list = [float(b) for b in betas]
        
    return {
        "probabilities": probabilities,
        "dixon_coles": {
            "alphas": alphas_list,
            "betas": betas_list,
            "team_indices": dc_model.team_indices,
            "gamma": float(gamma),
            "rho": float(rho),
            "mean_alpha": float(mean_alpha),
            "mean_beta": float(mean_beta)
        },
        "elo_ratings": elo_ratings,
        "goalie_rates": goalie_rates,
        "starting_teams": normalized_teams
    }

