import os
import json

DATA_DIR = os.path.join("data", "processed")
FILE_PATH = os.path.join(DATA_DIR, "paper_trading.json")

def load_state() -> dict:
    """Loads the paper trading state from JSON file with migration to multi-portfolio format."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        
    initial_state = {
        "predict": {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        },
        "ask": {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        },
        "parlay_standard": {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        },
        "parlay_longshot": {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        }
    }

    if not os.path.exists(FILE_PATH):
        save_state(initial_state)
        return initial_state

    try:
        with open(FILE_PATH, "r") as f:
            state = json.load(f)
            
        # Check if the state is in the old format (direct big_d / sigmaballs keys)
        if "big_d" in state and "bankroll" in state["big_d"]:
            # Migrate the old single-portfolio format to the 'ask' category
            migrated_state = {
                "predict": {
                    "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
                    "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
                },
                "ask": state,
                "parlay_standard": {
                    "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
                    "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
                },
                "parlay_longshot": {
                    "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
                    "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
                }
            }
            save_state(migrated_state)
            state = migrated_state
            
        # Detect old format keys:
        if any("big_d" in state[p] or "sigmaballs" in state[p] for p in state if isinstance(state[p], dict)):
            migrated = {}
            for port, port_data in state.items():
                migrated[port] = {}
                for k, v in port_data.items():
                    new_k = "magnus" if k == "big_d" else "athena" if k == "sigmaballs" else k
                    migrated[port][new_k] = v
            save_state(migrated)
            state = migrated
            
        return state
    except Exception:
        # Fallback if file corrupted
        return initial_state

def save_state(state: dict):
    """Saves the paper trading state to JSON file."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    with open(FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def place_bet(portfolio: str, personality: str, home: str, away: str, bet_type: str, stake: float, odds: float, is_parlay: bool = False, legs: list = None) -> bool:
    """Places a paper bet for a personality within a specific portfolio."""
    from src.data.team_mapping import normalize_team_name
    state = load_state()
    if portfolio not in state:
        state[portfolio] = {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        }
    p_data = state[portfolio].get(personality)
    if not p_data:
        return False
        
    stake = min(stake, p_data["bankroll"])
    if stake <= 0:
        return False
        
    p_data["bankroll"] = round(p_data["bankroll"] - stake, 2)
    
    bet_obj = {
        "home": normalize_team_name(home) if home else None,
        "away": normalize_team_name(away) if away else None,
        "bet_type": bet_type,
        "stake": round(stake, 2),
        "odds": round(odds, 2)
    }
    if is_parlay:
        bet_obj["is_parlay"] = True
        bet_obj["legs"] = legs or []
        
    p_data["active_bets"].append(bet_obj)
    save_state(state)
    return True

def update_bet(portfolio: str, personality: str, home: str, away: str, new_bet_type: str, new_stake: float, new_odds: float, is_parlay: bool = False, legs: list = None) -> dict:
    """
    Checks if there is an existing active bet for this match in the portfolio.
    If the new bet is identical to the active one, does nothing.
    If the new bet is different, refunds the old stake and places the new bet.
    """
    from src.data.team_mapping import normalize_team_name
    state = load_state()
    if portfolio not in state:
        state[portfolio] = {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        }
    p_data = state[portfolio].get(personality)
    if not p_data:
        return {"action": "error", "message": "Invalid personality"}

    home_clean = normalize_team_name(home) if home else None
    away_clean = normalize_team_name(away) if away else None

    # Find if there is an active bet for this match
    active_idx = -1
    for idx, bet in enumerate(p_data["active_bets"]):
        b_home = normalize_team_name(bet.get("home"))
        b_away = normalize_team_name(bet.get("away"))
        
        # Match regardless of team order
        match_normal = (b_home == home_clean and b_away == away_clean)
        match_swapped = (b_home == away_clean and b_away == home_clean)
        
        if is_parlay:
            if bet.get("is_parlay") and (match_normal or match_swapped):
                active_idx = idx
                break
        else:
            if not bet.get("is_parlay") and (match_normal or match_swapped):
                active_idx = idx
                break

    # Helper to canonicalize bet names for comparison
    def clean_btype(bt):
        return bt.lower().replace(" ", "").replace("-", "").replace(":", "")

    if active_idx != -1:
        old_bet = p_data["active_bets"][active_idx]
        if clean_btype(old_bet["bet_type"]) == clean_btype(new_bet_type):
            # Same bet, do nothing
            return {"action": "none", "bet": old_bet}
        else:
            # Different bet! Refund old stake
            refund_amount = old_bet["stake"]
            p_data["bankroll"] = round(p_data["bankroll"] + refund_amount, 2)
            # Remove old bet
            p_data["active_bets"].pop(active_idx)
            
            # Place new bet
            new_stake = min(new_stake, p_data["bankroll"])
            if new_stake > 0:
                p_data["bankroll"] = round(p_data["bankroll"] - new_stake, 2)
                new_bet = {
                    "home": home_clean,
                    "away": away_clean,
                    "bet_type": new_bet_type,
                    "stake": round(new_stake, 2),
                    "odds": round(new_odds, 2)
                }
                if is_parlay:
                    new_bet["is_parlay"] = True
                    new_bet["legs"] = legs or []
                p_data["active_bets"].append(new_bet)
                save_state(state)
                return {"action": "updated", "old": old_bet, "new": new_bet}
            else:
                save_state(state)
                return {"action": "cancelled", "old": old_bet}
    else:
        # Place new bet
        new_stake = min(new_stake, p_data["bankroll"])
        if new_stake <= 0:
            return {"action": "error", "message": "Insufficient bankroll"}
            
        p_data["bankroll"] = round(p_data["bankroll"] - new_stake, 2)
        new_bet = {
            "home": home_clean,
            "away": away_clean,
            "bet_type": new_bet_type,
            "stake": round(new_stake, 2),
            "odds": round(new_odds, 2)
        }
        if is_parlay:
            new_bet["is_parlay"] = True
            new_bet["legs"] = legs or []
        p_data["active_bets"].append(new_bet)
        save_state(state)
        return {"action": "placed", "new": new_bet}

def _find_completed_event_id(team1_norm: str, team2_norm: str) -> tuple | None:
    from datetime import datetime, timedelta, timezone
    from src.data.team_mapping import is_team_match
    from src.data import cache
    import requests
    
    today = datetime.now(timezone.utc)
    # Search scoreboard from 3 days ago to today
    for offset in range(-3, 1):
        date_str = (today + timedelta(days=offset)).strftime("%Y%m%d")
        for league in ["fifa.world", "uefa.nations", "uefa.euro"]:
            cached_sb = cache.get("espn_scoreboard", {"league": league, "date": date_str})
            if cached_sb is not None:
                events = cached_sb.get("events", [])
            else:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
                try:
                    resp = requests.get(url, params={"dates": date_str}, timeout=8)
                    if resp.status_code == 200:
                        response_json = resp.json()
                        cache.set("espn_scoreboard", {"league": league, "date": date_str}, response_json, ttl_seconds=3600 * 6)
                        events = response_json.get("events", [])
                    else:
                        events = []
                except Exception:
                    events = []
            
            for ev in events:
                comps = ev.get("competitions", [{}])
                competitors = comps[0].get("competitors", []) if comps else []
                names = [c.get("team", {}).get("displayName", "").lower() for c in competitors]
                if len(names) >= 2:
                    if (is_team_match(team1_norm, names[0]) and is_team_match(team2_norm, names[1])) or \
                       (is_team_match(team1_norm, names[1]) and is_team_match(team2_norm, names[0])):
                        return ev.get("id"), league
    return None

def _fetch_completed_match_stats(home: str, away: str) -> dict:
    from src.data.team_mapping import normalize_team_name
    from src.data import cache
    import requests
    
    home_norm = normalize_team_name(home)
    away_norm = normalize_team_name(away)
    
    cached_stats = cache.get("completed_match_player_stats", {"home": home_norm, "away": away_norm})
    if cached_stats is not None:
        return cached_stats
        
    res = _find_completed_event_id(home_norm, away_norm)
    if not res:
        return {"goals": {}, "assists": {}}
        
    event_id, league = res
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/summary?event={event_id}"
    
    player_goals = {}
    player_assists = {}
    
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            for roster in data.get("rosters", []):
                for entry in roster.get("roster", []):
                    ath = entry.get("athlete", {})
                    name = ath.get("displayName", "").lower().strip()
                    if not name:
                        continue
                    
                    stats_list = entry.get("statistics", [])
                    for s in stats_list:
                        s_name = s.get("name", "").lower()
                        s_val = float(s.get("value", 0.0) or 0.0)
                        if s_name == "goals" and s_val > 0:
                            player_goals[name] = int(s_val)
                        elif s_name == "assists" and s_val > 0:
                            player_assists[name] = int(s_val)
            
            result = {"goals": player_goals, "assists": player_assists}
            cache.set("completed_match_player_stats", {"home": home_norm, "away": away_norm}, result, ttl_seconds=3600 * 24 * 30)
            return result
    except Exception:
        pass
        
    return {"goals": {}, "assists": {}}

def _check_bet_win(bet_type: str, home: str, away: str, home_goals: int, away_goals: int, match_stats: dict = None) -> bool:
    """Helper to check if a specific bet type won based on goals scored and player stats."""
    from src.data.team_mapping import normalize_team_name
    import re
    b_type = bet_type.lower()
    home_lower = normalize_team_name(home)
    away_lower = normalize_team_name(away)
    
    # 1. Player Props Resolution
    if "player goals" in b_type or "player assists" in b_type or "player g/a" in b_type or "player props" in b_type:
        if not match_stats:
            return False
            
        clean_prop = b_type.replace("player props - ", "").replace("player goals - ", "").replace("player assists - ", "").replace("player g/a - ", "").strip()
        
        is_g1 = "1+ goal" in clean_prop
        is_g2 = "2+ goal" in clean_prop
        is_a1 = "1+ assist" in clean_prop
        is_a2 = "2+ assist" in clean_prop
        is_ga = "score or assist" in clean_prop
        
        name_clean = clean_prop
        for suffix in ["1+ goals", "2+ goals", "1+ assists", "2+ assists", "score or assist", "goals", "assists"]:
            name_clean = name_clean.replace(suffix, "").strip()
            
        player_pattern = re.compile(r'(?<!\w)' + re.escape(name_clean) + r'(?!\w)')
        
        p_goals = 0
        p_assists = 0
        
        for p_name, g_count in match_stats.get("goals", {}).items():
            if player_pattern.search(p_name):
                p_goals = g_count
                break
                
        for p_name, a_count in match_stats.get("assists", {}).items():
            if player_pattern.search(p_name):
                p_assists = a_count
                break
                
        if is_g1:
            return p_goals >= 1
        elif is_g2:
            return p_goals >= 2
        elif is_a1:
            return p_assists >= 1
        elif is_a2:
            return p_assists >= 2
        elif is_ga:
            return (p_goals >= 1) or (p_assists >= 1)
        return False

    # 2. Standard game lines resolution
    if "moneyline" in b_type:
        if home_lower in b_type and home_goals > away_goals:
            return True
        elif away_lower in b_type and home_goals < away_goals:
            return True
        elif ("draw" in b_type or "tie" in b_type) and home_goals == away_goals:
            return True
    elif "win" in b_type:
        if home_lower in b_type and home_goals > away_goals:
            return True
        elif away_lower in b_type and home_goals < away_goals:
            return True
    elif "draw" in b_type or "tie" in b_type:
        if home_goals == away_goals:
            return True
    elif "over 1.5" in b_type:
        if home_goals + away_goals >= 2:
            return True
    elif "over 2.5" in b_type:
        if home_goals + away_goals >= 3:
            return True
    elif "both teams" in b_type or "btts" in b_type:
        if home_goals >= 1 and away_goals >= 1:
            return True
    return False

def _update_player_stats_from_completed_match(home_norm: str, away_norm: str, match_stats: dict, event_id: str = None, league: str = "fifa.world"):
    from src.data.scrapers.fixtures import _fetch_espn_event_lineup
    from src.data.scrapers.player_stats import get_player_stats
    from src.data.cache import save_player_stats
    
    if not event_id:
        return
        
    lineups = _fetch_espn_event_lineup(event_id, home_norm, away_norm, league=league)
    if not lineups:
        # Fallback: only update stats for players who scored or assisted
        all_players = set(list(match_stats.get("goals", {}).keys()) + list(match_stats.get("assists", {}).keys()))
        for p_name in all_players:
            p_name_clean = p_name.lower().strip()
            p_stats = get_player_stats(p_name_clean)
            goals_scored = match_stats.get("goals", {}).get(p_name_clean, 0)
            assists_made = match_stats.get("assists", {}).get(p_name_clean, 0)
            
            old_g = float(p_stats.get("goals_per_90", 0.25))
            old_a = float(p_stats.get("assists_per_90", 0.15))
            old_xg = float(p_stats.get("xg_per_90", 0.30))
            
            new_g = round((old_g * 10.0 + goals_scored) / 11.0, 3)
            new_a = round((old_a * 10.0 + assists_made) / 11.0, 3)
            new_xg = round((old_xg * 10.0 + max(goals_scored, 0.1)) / 11.0, 3)
            
            save_player_stats(p_name_clean, p_stats.get("position", "FW"), new_xg, new_g, new_a, p_stats.get("club_team", ""), p_stats.get("intl_team", ""))
        return

    # Update stats for both teams' starting lineups
    for is_home, lineup in [(True, lineups.get("home_lineup", [])), (False, lineups.get("away_lineup", []))]:
        for p_name in lineup:
            p_name_clean = p_name.lower().strip()
            p_stats = get_player_stats(p_name_clean)
            goals_scored = match_stats.get("goals", {}).get(p_name_clean, 0)
            assists_made = match_stats.get("assists", {}).get(p_name_clean, 0)
            
            old_g = float(p_stats.get("goals_per_90", 0.25))
            old_a = float(p_stats.get("assists_per_90", 0.15))
            old_xg = float(p_stats.get("xg_per_90", 0.30))
            
            new_g = round((old_g * 10.0 + goals_scored) / 11.0, 3)
            new_a = round((old_a * 10.0 + assists_made) / 11.0, 3)
            new_xg = round((old_xg * 10.0 + max(goals_scored, 0.1)) / 11.0, 3)
            
            save_player_stats(p_name_clean, p_stats.get("position", "FW"), new_xg, new_g, new_a, p_stats.get("club_team", ""), p_stats.get("intl_team", ""))


def resolve_pending_bets(home: str, away: str, home_goals: int, away_goals: int) -> list:
    """
    Resolves pending single bets and parlay legs across all portfolios.
    Updates bankrolls and moves resolved bets to history.
    """
    from src.data.team_mapping import normalize_team_name
    state = load_state()
    home_norm = normalize_team_name(home)
    away_norm = normalize_team_name(away)
    
    match_stats = _fetch_completed_match_stats(home_norm, away_norm)
    
    # Update player statistics dynamically based on match performances
    res = _find_completed_event_id(home_norm, away_norm)
    if res:
        event_id, league = res
        _update_player_stats_from_completed_match(home_norm, away_norm, match_stats, event_id, league)
        
    results = []
    
    for portfolio in ["predict", "ask", "parlay_standard", "parlay_longshot"]:
        if portfolio not in state:
            continue
            
        for personality in ["magnus", "athena"]:
            p_data = state[portfolio][personality]
            still_active = []
            
            for bet in p_data.get("active_bets", []):
                if bet.get("is_parlay"):
                    # Resolve legs matching this match
                    legs = bet.get("legs", [])
                    any_leg_lost = False
                    all_legs_won = True
                    
                    for leg in legs:
                        l_home_norm = normalize_team_name(leg.get("home", ""))
                        l_away_norm = normalize_team_name(leg.get("away", ""))
                        
                        match_normal = (l_home_norm == home_norm and l_away_norm == away_norm)
                        match_swapped = (l_home_norm == away_norm and l_away_norm == home_norm)
                        
                        if match_normal or match_swapped:
                            h_goals = home_goals if match_normal else away_goals
                            a_goals = away_goals if match_normal else home_goals
                            won = _check_bet_win(leg["bet_type"], leg["home"], leg["away"], h_goals, a_goals, match_stats)
                            leg["result"] = "WIN" if won else "LOSS"
                            
                        if leg.get("result") == "LOSS":
                            any_leg_lost = True
                        elif leg.get("result") != "WIN":
                            all_legs_won = False
                            
                    if any_leg_lost:
                        # Parlay is lost
                        pnl = -bet["stake"]
                        resolved_bet = {
                            "home": bet.get("home"),
                            "away": bet.get("away"),
                            "bet_type": bet["bet_type"],
                            "stake": bet["stake"],
                            "odds": bet["odds"],
                            "result": "LOSS",
                            "pnl": round(pnl, 2),
                            "legs": legs
                        }
                        p_data["history"].append(resolved_bet)
                        results.append((portfolio, personality, resolved_bet))
                    elif all_legs_won:
                        # Parlay is fully won!
                        payout = bet["stake"] * bet["odds"]
                        p_data["bankroll"] = round(p_data["bankroll"] + payout, 2)
                        pnl = payout - bet["stake"]
                        resolved_bet = {
                            "home": bet.get("home"),
                            "away": bet.get("away"),
                            "bet_type": bet["bet_type"],
                            "stake": bet["stake"],
                            "odds": bet["odds"],
                            "result": "WIN",
                            "pnl": round(pnl, 2),
                            "legs": legs
                        }
                        p_data["history"].append(resolved_bet)
                        results.append((portfolio, personality, resolved_bet))
                    else:
                        # Still pending other games
                        still_active.append(bet)
                else:
                    # Standard single bet
                    b_home_norm = normalize_team_name(bet.get("home", ""))
                    b_away_norm = normalize_team_name(bet.get("away", ""))
                    
                    match_normal = (b_home_norm == home_norm and b_away_norm == away_norm)
                    match_swapped = (b_home_norm == away_norm and b_away_norm == home_norm)
                    
                    if match_normal or match_swapped:
                        h_goals = home_goals if match_normal else away_goals
                        a_goals = away_goals if match_normal else home_goals
                        won = _check_bet_win(bet["bet_type"], bet["home"], bet["away"], h_goals, a_goals, match_stats)
                        pnl = -bet["stake"]
                        if won:
                            payout = bet["stake"] * bet["odds"]
                            p_data["bankroll"] = round(p_data["bankroll"] + payout, 2)
                            pnl = payout - bet["stake"]
                            
                        resolved_bet = {
                            "home": bet["home"],
                            "away": bet["away"],
                            "bet_type": bet["bet_type"],
                            "stake": bet["stake"],
                            "odds": bet["odds"],
                            "result": "WIN" if won else "LOSS",
                            "pnl": round(pnl, 2)
                        }
                        p_data["history"].append(resolved_bet)
                        results.append((portfolio, personality, resolved_bet))
                    else:
                        still_active.append(bet)
                        
            p_data["active_bets"] = still_active
            
    save_state(state)
    return results

def get_personality_summary(portfolio: str, personality: str) -> dict:
    """Returns a dictionary summary of bankroll, history, and active bets for a specific portfolio."""
    state = load_state()
    if portfolio not in state:
        state[portfolio] = {
            "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
        }
    p_data = state[portfolio].get(personality, {})
    
    history = p_data.get("history", [])
    total_pnl = sum([b["pnl"] for b in history])
    wins = sum([1 for b in history if b["result"] == "WIN"])
    total_bets = len(history)
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0.0
    
    return {
        "bankroll": p_data.get("bankroll", 1000.0),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "total_bets": total_bets,
        "recent_bets": history[-5:],
        "active_bets": p_data.get("active_bets", [])
    }
