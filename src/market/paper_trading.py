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
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
        },
        "ask": {
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
        },
        "parlay_standard": {
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
        },
        "parlay_longshot": {
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
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
                    "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
                    "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
                },
                "ask": state,
                "parlay_standard": {
                    "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
                    "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
                },
                "parlay_longshot": {
                    "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
                    "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
                }
            }
            save_state(migrated_state)
            return migrated_state
            
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
    state = load_state()
    if portfolio not in state:
        state[portfolio] = {
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
        }
    p_data = state[portfolio].get(personality)
    if not p_data:
        return False
        
    stake = min(stake, p_data["bankroll"])
    if stake <= 0:
        return False
        
    p_data["bankroll"] = round(p_data["bankroll"] - stake, 2)
    
    bet_obj = {
        "home": home.lower().strip() if home else None,
        "away": away.lower().strip() if away else None,
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
    state = load_state()
    if portfolio not in state:
        state[portfolio] = {
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
        }
    p_data = state[portfolio].get(personality)
    if not p_data:
        return {"action": "error", "message": "Invalid personality"}

    home_clean = home.lower().strip() if home else None
    away_clean = away.lower().strip() if away else None

    # Find if there is an active bet for this match
    active_idx = -1
    for idx, bet in enumerate(p_data["active_bets"]):
        if is_parlay:
            if bet.get("is_parlay") and bet.get("home") == home_clean and bet.get("away") == away_clean:
                active_idx = idx
                break
        else:
            if not bet.get("is_parlay") and bet.get("home") == home_clean and bet.get("away") == away_clean:
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

def _check_bet_win(bet_type: str, home: str, away: str, home_goals: int, away_goals: int) -> bool:
    """Helper to check if a specific bet type won based on goals scored."""
    b_type = bet_type.lower()
    home_lower = home.lower().strip()
    away_lower = away.lower().strip()
    
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

def resolve_pending_bets(home: str, away: str, home_goals: int, away_goals: int) -> list:
    """
    Resolves pending single bets and parlay legs across all portfolios.
    Updates bankrolls and moves resolved bets to history.
    """
    state = load_state()
    home_lower = home.lower().strip()
    away_lower = away.lower().strip()
    
    results = []
    
    for portfolio in ["predict", "ask", "parlay_standard", "parlay_longshot"]:
        if portfolio not in state:
            continue
            
        for personality in ["big_d", "sigmaballs"]:
            p_data = state[portfolio][personality]
            still_active = []
            
            for bet in p_data.get("active_bets", []):
                if bet.get("is_parlay"):
                    # Resolve legs matching this match
                    legs = bet.get("legs", [])
                    any_leg_lost = False
                    all_legs_won = True
                    
                    for leg in legs:
                        l_home = leg.get("home", "").lower().strip()
                        l_away = leg.get("away", "").lower().strip()
                        
                        if l_home == home_lower and l_away == away_lower:
                            won = _check_bet_win(leg["bet_type"], home, away, home_goals, away_goals)
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
                    b_home = bet.get("home", "").lower().strip()
                    b_away = bet.get("away", "").lower().strip()
                    
                    if b_home == home_lower and b_away == away_lower:
                        won = _check_bet_win(bet["bet_type"], home, away, home_goals, away_goals)
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
            "big_d": {"bankroll": 1000.0, "active_bets": [], "history": []},
            "sigmaballs": {"bankroll": 1000.0, "active_bets": [], "history": []}
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
