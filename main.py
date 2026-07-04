#!/usr/bin/env python3
import sys
import argparse
from src.models import trainer, statistical
from src.predictor import predict_match, ELO_PREDICTOR, math_log, save_elo
from src.market.kalshi_client import KalshiClient
from src.parlay.parlay_engine import ParlayEngine
from src.data.scrapers import fbref, player_stats, news, fixtures
from src.data.scrapers.corners import get_team_recent_corners
from src.market.llm import generate_debate, GEMINI_AVAILABLE
from src.data.team_mapping import normalize_team_name, is_team_match
from src.data.scrapers.fixtures import get_match_lineups
from src.models.player_props import calculate_player_prop_probs
import os
import re
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def banner():
    console.print(Panel(
        "[bold cyan]🏆 2026 World Cup Predictor & Parlay Engine ⚽[/bold cyan]\n"
        "[dim]Dynamic Machine Learning + Statistical Ensembles for Kalshi[/dim]\n\n"
        "[bold white]Available commands:[/bold white]\n"
        "  [green]init[/green]            - Run initial training on master historical dataset\n"
        "  [green]update[/green]          - Auto-sync completed tournament matches & retrain models\n"
        "  [green]predict[/green] \"A vs B\" - Blends 8 models to predict upcoming match\n"
        "  [green]ask[/green] \"A vs B\"     - Stages a scout vs quant debate on upcoming match\n"
        "  [green]parlay[/green]          - Search live Kalshi markets for >= 5x parlay options\n"
        "  [green]parlay -l[/green]       - Generate a portfolio of high-payout long-shot parlays\n"
        "  [green]complete[/green] A B H A - Record completed match score and retrain models\n"
        "  [green]portfolio[/green]       - Fetch live Kalshi balance and closed positions",
        border_style="cyan"
    ))


def run_init():
    console.print("\n[yellow]Starting initial training loop...[/yellow]")
    trainer.train_and_save_all()
    console.print("[bold green]Success! All 6 ML Models trained and saved to data/models/[/bold green]\n")


def run_predict(query: str):
    parts = query.lower().split(" vs ")
    if len(parts) < 2:
        console.print("[red]Error: Format must be 'TeamA vs TeamB'[/red]")
        return

    home, away = parts[0].strip(), parts[1].strip()
    home = normalize_team_name(home)
    away = normalize_team_name(away)
    console.print(f"\n[cyan]Predicting match: {home.title()} vs {away.title()}...[/cyan]")
    
    # Run public search on Kalshi for current prices to serve as feature input
    client = KalshiClient()
    markets = client.get_soccer_markets()
    
    kalshi_probs = None
    for ev in markets:
        title = ev["event_title"].lower()
        if " vs " in title:
            t_parts = title.split(" vs ")
            t_home = normalize_team_name(t_parts[0])
            t_away = normalize_team_name(t_parts[1])
            if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                # Map probabilities
                probs = {}
                for m in ev["markets"]:
                    t = m["title"].lower()
                    ticker = m.get("ticker", "").upper()
                    if "KXWCGAME" in ticker:
                        if is_team_match(home, t):
                            probs["home_win"] = m["yes_price"]
                        elif is_team_match(away, t):
                            probs["away_win"] = m["yes_price"]
                        elif "draw" in t or "tie" in t:
                            probs["draw"] = m["yes_price"]
                if len(probs) >= 2:
                    kalshi_probs = probs
                    break
                
    result = predict_match(home, away, kalshi_probs)
    
    table = Table(title=f"{home.title()} vs {away.title()} Forecast Matrix", box=box.SIMPLE)
    table.add_column("Outcome", style="cyan")
    table.add_column("Blended Prob", style="bold green")
    table.add_column("Model Breakdown", style="dim")
    
    probs = result.probabilities
    breakdown = result.model_breakdown
    
    for outcome in ["home_win", "draw", "away_win"]:
        label = home.title() if outcome == "home_win" else (away.title() if outcome == "away_win" else "Draw")
        b_str = ", ".join([f"{k}: {v[outcome]*100:.1f}%" for k, v in breakdown.items() if v and outcome in v])
        table.add_row(label, f"{probs[outcome]*100:.2f}%", b_str)
        
    console.print(table)

    # To-Qualify / Progression Forecast Matrix (Only for Knockout Stage)
    from src.market.llm import get_tournament_stage
    stage_name = get_tournament_stage()
    if "knockout" in stage_name.lower():
        prog_table = Table(title=f"{home.title()} vs {away.title()} To-Qualify (Progression) Forecast", box=box.SIMPLE)
        prog_table.add_column("Team", style="cyan")
        prog_table.add_column("Advance Probability", style="bold green")
        prog_table.add_row(home.title(), f"{result.progression_probabilities['home_advances']*100:.2f}%")
        prog_table.add_row(away.title(), f"{result.progression_probabilities['away_advances']*100:.2f}%")
        console.print(prog_table)

    h_elo = ELO_PREDICTOR.get(home)
    a_elo = ELO_PREDICTOR.get(away)
    from src.predictor import TEAM_CONFEDERATION, CONFEDERATION_BOOST
    h_conf = TEAM_CONFEDERATION.get(home, "neutral")
    a_conf = TEAM_CONFEDERATION.get(away, "neutral")
    h_boost = CONFEDERATION_BOOST.get(h_conf, 0.0)
    a_boost = CONFEDERATION_BOOST.get(a_conf, 0.0)
    
    console.print(f"\n[bold white]News Sentiment Diff:[/bold white] {result.sentiment:+.2f}")
    console.print(f"[bold white]ELO ratings diff:[/bold white] {result.elo_diff:+.1f} pts (Calibrated ELO: {home.title()} {h_elo+h_boost:.0f} vs {away.title()} {a_elo+a_boost:.0f} | Raw: {h_elo:.0f} vs {a_elo:.0f})")

    # Under ELO ratings print in main.py:
    try:
        from src.data.scrapers.corners import get_team_recent_corners
        h_crn = get_team_recent_corners(home)
        a_crn = get_team_recent_corners(away)
        
        lambda_h = h_crn["won"] * (a_crn["conceded"] / 4.8)
        lambda_a = a_crn["won"] * (h_crn["conceded"] / 4.8)
        
        crn_table = Table(title=f"{home.title()} vs {away.title()} Corner Kicks Expectation", box=box.SIMPLE)
        crn_table.add_column("Team", style="cyan")
        crn_table.add_column("Avg Corners Won", style="green")
        crn_table.add_column("Expected Corners (Match)", style="bold green")
        crn_table.add_row(home.title(), f"{h_crn['won']:.1f}", f"{lambda_h:.1f}")
        crn_table.add_row(away.title(), f"{a_crn['won']:.1f}", f"{lambda_a:.1f}")
        crn_table.add_row("Total Expected", "-", f"{lambda_h + lambda_a:.1f}")
        console.print(crn_table)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load corner kick expectations: {e}[/yellow]")

    # Set up Dixon-Coles for goal-based markets (Over/Under, BTTS, Player scorer)
    dc = statistical.DixonColesModel()
    h_data = fbref.get_team_data(home)
    a_data = fbref.get_team_data(away)
    dc.attack[home] = math_log(h_data.get("avg_goals", 1.4))
    dc.defense[home] = -math_log(h_data.get("avg_conceded", 1.1))
    dc.attack[away] = math_log(a_data.get("avg_goals", 1.4))
    dc.defense[away] = -math_log(a_data.get("avg_conceded", 1.1))
    dc.is_fitted = True
    
    matrix = dc.predict_score_matrix(home, away, max_goals=6)
    
    # Calculate probabilities
    over_15_prob = float(sum([matrix[h, a] for h in range(7) for a in range(7) if h + a >= 2]))
    over_25_prob = float(sum([matrix[h, a] for h in range(7) for a in range(7) if h + a >= 3]))
    btts_prob = float(sum([matrix[h, a] for h in range(7) for a in range(7) if h >= 1 and a >= 1]))

    h_avg = float(h_data.get("avg_goals", 1.4))
    a_avg = float(a_data.get("avg_goals", 1.4))
    
    # Retrieve dynamic starting lineups from ESPN
    try:
        lineups_res = get_match_lineups(home, away)
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to fetch lineups dynamically: {e}[/yellow]")
        lineups_res = {
            "home_lineup": [],
            "away_lineup": [],
            "source": "error_fallback_empty"
        }
    home_lineup = lineups_res.get("home_lineup", [])
    away_lineup = lineups_res.get("away_lineup", [])
    
    console.print(f"[dim]Lineups sourced via: {lineups_res.get('source', 'unknown')}[/dim]")
    
    # Build predictions for all players in both lineups
    player_prop_predictions = []
    for is_home, lineup, team_avg in [(True, home_lineup, h_avg), (False, away_lineup, a_avg)]:
        for name in lineup:
            p_stats = player_stats.get_player_stats(name)
            p_probs = calculate_player_prop_probs(p_stats, is_home, matrix, team_avg)
            
            # Map to prop formats
            player_prop_predictions.append({
                "name": name,
                "is_home": is_home,
                "probs": p_probs
            })

    # Kalshi Betting Value Analysis Table
    bets_table = Table(title="Kalshi Value Bets & Target Prices", box=box.SIMPLE)
    bets_table.add_column("Category", style="cyan")
    bets_table.add_column("Bet / Market", style="white")
    bets_table.add_column("Model Prob", style="bold green")
    bets_table.add_column("Kalshi Price", style="yellow")
    bets_table.add_column("Edge / Recommendation", style="bold magenta")
    
    # Add Moneylines
    mkt_odds = kalshi_probs or {}
    for outcome, label in [("home_win", home.title() + " Win"), ("draw", "Draw"), ("away_win", away.title() + " Win")]:
        prob = probs[outcome]
        live_p = mkt_odds.get(outcome)
        if live_p:
            edge = prob - live_p
            edge_str = f"+{edge*100:.1f}% [STRONG VALUE]" if edge > 0.05 else (f"+{edge*100:.1f}% [VALUE]" if edge > 0 else f"{edge*100:.1f}%")
            bets_table.add_row("Moneyline", label, f"{prob*100:.1f}%", f"${live_p:.2f}", edge_str)
        else:
            bets_table.add_row("Moneyline", label, f"{prob*100:.1f}%", "N/A", f"Buy YES < ${prob:.2f}")
            
    # Add Game Lines (O/U & BTTS)
    live_game_lines = {}
    for outcome, label, prob in [("over_1.5", "Over 1.5 Goals", over_15_prob), 
                                 ("over_2.5", "Over 2.5 Goals", over_25_prob), 
                                 ("btts", "Both Teams to Score", btts_prob)]:
        live_p = None
        for ev in markets:
            title = ev["event_title"].lower()
            if " vs " in title:
                t_parts = title.split(" vs ")
                t_home = normalize_team_name(t_parts[0])
                t_away = normalize_team_name(t_parts[1])
                if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                    for m in ev["markets"]:
                        t = m["title"].lower()
                        if outcome == "over_1.5" and "over 1.5" in t:
                            live_p = m["yes_price"]
                        elif outcome == "over_2.5" and "over 2.5" in t:
                            live_p = m["yes_price"]
                        elif outcome == "btts" and "both teams" in t:
                            live_p = m["yes_price"]
        
        if live_p:
            live_game_lines[outcome] = live_p
            edge = prob - live_p
            edge_str = f"+{edge*100:.1f}% [STRONG VALUE]" if edge > 0.05 else (f"+{edge*100:.1f}% [VALUE]" if edge > 0 else f"{edge*100:.1f}%")
            bets_table.add_row("Game Lines", label, f"{prob*100:.1f}%", f"${live_p:.2f}", edge_str)
        else:
            bets_table.add_row("Game Lines", label, f"{prob*100:.1f}%", "N/A", f"Buy YES < ${prob:.2f}")

    candidates = []
    # Add Player Props to the Kalshi Value Bets Table
    for pred in player_prop_predictions:
        name = pred["name"]
        is_home = pred["is_home"]
        p_probs = pred["probs"]
        
        name_lower = name.lower().strip()
        player_pattern = re.compile(r'(?<!\w)' + re.escape(name_lower) + r'(?!\w)')
        
        # Match markets in Kalshi
        for outcome_key, label_suffix, prob_val in [
            ("goals_1", "1+ Goals", p_probs["goals_1"]),
            ("goals_2", "2+ Goals", p_probs["goals_2"]),
            ("assists_1", "1+ Assists", p_probs["assists_1"]),
            ("assists_2", "2+ Assists", p_probs["assists_2"]),
            ("goal_or_assist", "Score or Assist", p_probs["goal_or_assist"])
        ]:
            live_p = None
            for ev in markets:
                title = ev["event_title"].lower()
                if " vs " in title:
                    t_parts = title.split(" vs ")
                    t_home = normalize_team_name(t_parts[0])
                    t_away = normalize_team_name(t_parts[1])
                    if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                        for m in ev["markets"]:
                            t = m["title"].lower()
                            
                            if player_pattern.search(t):
                                if outcome_key == "goals_1" and "goal" in t and "1+" in t:
                                    live_p = m["yes_price"]
                                elif outcome_key == "goals_2" and "goal" in t and "2+" in t:
                                    live_p = m["yes_price"]
                                elif outcome_key == "assists_1" and "assist" in t and "1+" in t:
                                    live_p = m["yes_price"]
                                elif outcome_key == "assists_2" and "assist" in t and "2+" in t:
                                    live_p = m["yes_price"]
                                elif outcome_key == "goal_or_assist" and "score or assist" in t:
                                    live_p = m["yes_price"]
            
            category_str = "Player Goals" if "Goals" in label_suffix else ("Player Assists" if "Assists" in label_suffix else "Player G/A")
            market_label = f"{name.title()} {label_suffix}"
            
            if live_p:
                edge = prob_val - live_p
                edge_str = f"+{edge*100:.1f}% [STRONG VALUE]" if edge > 0.05 else (f"+{edge*100:.1f}% [VALUE]" if edge > 0 else f"{edge*100:.1f}%")
                bets_table.add_row(category_str, market_label, f"{prob_val*100:.1f}%", f"${live_p:.2f}", edge_str)
                if edge > 0.02:
                    candidates.append((edge, f"Player Props - {name.title()} {label_suffix}", live_p))
            else:
                bets_table.add_row(category_str, market_label, f"{prob_val*100:.1f}%", "N/A", f"Buy YES < ${prob_val:.2f}")

    console.print()
    console.print(bets_table)

    # Automated Bot Betting for 'predict' portfolio
    from src.market import paper_trading
    d_sum = paper_trading.get_personality_summary("predict", "magnus")
    s_sum = paper_trading.get_personality_summary("predict", "athena")
    
    magnus_bet_type = None
    magnus_odds = None
    if probs["home_win"] >= probs["away_win"] and probs["home_win"] >= probs["draw"]:
        live_price = mkt_odds.get("home_win")
        if live_price:
            magnus_bet_type = f"Moneyline - {home.title()} Win"
            magnus_odds = 1.0 / live_price
    elif probs["away_win"] >= probs["home_win"] and probs["away_win"] >= probs["draw"]:
        live_price = mkt_odds.get("away_win")
        if live_price:
            magnus_bet_type = f"Moneyline - {away.title()} Win"
            magnus_odds = 1.0 / live_price
    else:
        live_price = mkt_odds.get("draw")
        if live_price:
            magnus_bet_type = "Moneyline - Draw"
            magnus_odds = 1.0 / live_price
            
    for outcome, label in [("home_win", f"Moneyline - {home.title()} Win"),
                           ("draw", "Moneyline - Draw"),
                           ("away_win", f"Moneyline - {away.title()} Win")]:
        live_price = mkt_odds.get(outcome)
        if live_price:
            edge = probs[outcome] - live_price
            if edge > 0:
                candidates.append((edge, label, live_price))
                
    for outcome, label, prob in [("over_1.5", "Game Lines - Over 1.5 Goals", over_15_prob),
                                 ("over_2.5", "Game Lines - Over 2.5 Goals", over_25_prob),
                                 ("btts", "Game Lines - Both Teams to Score", btts_prob)]:
        live_price = live_game_lines.get(outcome)
        if live_price:
            edge = prob - live_price
            if edge > 0:
                candidates.append((edge, label, live_price))
                
    athena_bet_type = None
    athena_odds = None
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_edge, athena_bet_type, live_price = candidates[0]
        athena_odds = 1.0 / live_price
        
    bot_alerts = []
    if magnus_bet_type and magnus_odds:
        stake = round(d_sum["bankroll"] * 0.1, 2)
        res = paper_trading.update_bet("predict", "magnus", home, away, magnus_bet_type, stake, magnus_odds)
        action = res.get("action")
        if action == "placed":
            new = res["new"]
            bot_alerts.append(f"[green][+] Magnus placed new position:[/green] {new['bet_type']} (${new['stake']:.2f} at {new['odds']:.2f}x)")
        elif action == "updated":
            old, new = res["old"], res["new"]
            bot_alerts.append(f"[bold yellow][!] Magnus changed recommendation:[/bold yellow] {new['bet_type']} replacing {old['bet_type']} (${new['stake']:.2f} at {new['odds']:.2f}x)")
        elif action == "none":
            bet = res["bet"]
            bot_alerts.append(f"[dim][=] Magnus kept existing position:[/dim] {bet['bet_type']} (${bet['stake']:.2f} at {bet['odds']:.2f}x)")
            
    if athena_bet_type and athena_odds:
        # Fractional Kelly sizing: f_star = (p * b - (1 - p)) / b
        p_val = live_price + best_edge
        b_val = athena_odds - 1.0
        if b_val > 0:
            f_star = (p_val * b_val - (1.0 - p_val)) / b_val
            # Quarter-Kelly (0.25) capped at 15% (0.15) of bankroll, minimum 2% (0.02)
            kelly_fraction = max(0.02, min(0.15, 0.25 * f_star))
        else:
            kelly_fraction = 0.05
        
        stake = round(s_sum["bankroll"] * kelly_fraction, 2)
        res = paper_trading.update_bet("predict", "athena", home, away, athena_bet_type, stake, athena_odds)
        action = res.get("action")
        if action == "placed":
            new = res["new"]
            bot_alerts.append(f"[green][+] Athena placed new position:[/green] {new['bet_type']} (${new['stake']:.2f} at {new['odds']:.2f}x)")
        elif action == "updated":
            old, new = res["old"], res["new"]
            bot_alerts.append(f"[bold yellow][!] Athena changed recommendation:[/bold yellow] {new['bet_type']} replacing {old['bet_type']} (${new['stake']:.2f} at {new['odds']:.2f}x)")
        elif action == "none":
            bet = res["bet"]
            bot_alerts.append(f"[dim][=] Athena kept existing position:[/dim] {bet['bet_type']} (${bet['stake']:.2f} at {bet['odds']:.2f}x)")
            
    if bot_alerts:
        console.print()
        console.print(Panel(
            "\n".join(bot_alerts),
            title="[bold cyan]Predict Portfolio Bot Paper Bets[/bold cyan]",
            border_style="cyan"
        ))


def run_parlay(longshot: bool = False, today_only: bool = False):
    console.print("\n[yellow]Retrieving live Kalshi markets and matches...[/yellow]")
    client = KalshiClient()
    markets = client.get_soccer_markets()
    
    matches = []
    if markets:
        for ev in markets:
            title = ev["event_title"].lower()
            if " vs " in title:
                parts = title.split(" vs ")
                h = normalize_team_name(parts[0].strip())
                a = normalize_team_name(parts[1].strip())
                # Parse odds
                odds = {}
                for m in ev["markets"]:
                    t = m["title"].lower()
                    ticker = m.get("ticker", "").upper()
                    if "KXWCGAME" in ticker:
                        if is_team_match(h, t):
                            odds["home_win"] = m["yes_price"]
                        elif is_team_match(a, t):
                            odds["away_win"] = m["yes_price"]
                        elif "draw" in t or "tie" in t:
                            odds["draw"] = m["yes_price"]
                    elif "over 1.5" in t:
                        odds["over_1.5"] = m["yes_price"]
                    elif "over 2.5" in t:
                        odds["over_2.5"] = m["yes_price"]
                    elif "both teams" in t or "btts" in t:
                        odds["btts"] = m["yes_price"]
                
                # Scorer props
                KEY_PLAYERS_FLAT = ["harry kane", "jude bellingham", "bukayo saka", "kylian mbappe", "antoine griezmann", "lionel messi", "lautaro martinez", "vinicius jr", "cristiano ronaldo", "robert lewandowski", "jamal musiala", "florian wirtz", "alvaro morata", "antoine semenyo", "mohammed kudus"]
                players = []
                for m in ev["markets"]:
                    t = m["title"].lower()
                    for player in KEY_PLAYERS_FLAT:
                        if player in t and ("score" in t or "goal" in t):
                            key_name = f"scorer_{player.replace(' ', '_')}"
                            odds[key_name] = m["yes_price"]
                            is_h = False
                            if h == "england" and player in ["harry kane", "jude bellingham", "bukayo saka"]:
                                is_h = True
                            elif h == "france" and player in ["kylian mbappe", "antoine griezmann"]:
                                is_h = True
                            elif h == "argentina" and player in ["lionel messi", "lautaro martinez"]:
                                is_h = True
                            elif h == "brazil" and player in ["vinicius jr"]:
                                is_h = True
                            elif h == "portugal" and player in ["cristiano ronaldo"]:
                                is_h = True
                            elif h == "poland" and player in ["robert lewandowski"]:
                                is_h = True
                            elif h == "germany" and player in ["jamal musiala", "florian wirtz"]:
                                is_h = True
                            elif h == "spain" and player in ["alvaro morata"]:
                                is_h = True
                            elif h == "ghana" and player in ["antoine semenyo", "mohammed kudus"]:
                                is_h = True
                            
                            p_tuple = (player, is_h)
                            if p_tuple not in players:
                                players.append(p_tuple)
                    
                matches.append({
                    "home": h,
                    "away": a,
                    "market_odds": odds,
                    "players": players,
                    "occurrence_time": ev.get("occurrence_time")
                })

    if today_only:
        from datetime import datetime, timedelta, timezone
        today_utc = datetime.now(timezone.utc).date()
        today_str = today_utc.strftime("%Y-%m-%d")
        filtered_matches = []
        for m in matches:
            occ = m.get("occurrence_time")
            if not occ:
                continue
            try:
                # Handle ISO datetime parsing with timezone conversion
                dt_utc = datetime.fromisoformat(occ.replace("Z", "+00:00")).astimezone(timezone.utc)
                is_today = (dt_utc.date() == today_utc)
                is_early_tomorrow = (dt_utc.date() == today_utc + timedelta(days=1) and dt_utc.hour < 6)
                if is_today or is_early_tomorrow:
                    filtered_matches.append(m)
            except Exception:
                if occ.startswith(today_str):
                    filtered_matches.append(m)
        matches = filtered_matches
        console.print(f"[cyan]Filtering for matches playing today ({today_str})... Found {len(matches)} matches.[/cyan]")

    if not matches:
        if today_only:
            console.print("[yellow]No active match markets found playing today on Kalshi.[/yellow]")
            return
        console.print("[yellow]No active match markets found on Kalshi. Generating sample/demo parlays.[/yellow]")
        # Mock matches for generating demo parlays
        matches = [
            {
                "home": "argentina", "away": "chile",
                "market_odds": {"home_win": 0.65, "draw": 0.22, "away_win": 0.13, "over_1.5": 0.70, "over_2.5": 0.50, "btts": 0.48},
                "players": [("lionel messi", True)]
            },
            {
                "home": "france", "away": "poland",
                "market_odds": {"home_win": 0.70, "draw": 0.20, "away_win": 0.10, "over_1.5": 0.75, "over_2.5": 0.55, "btts": 0.45},
                "players": [("kylian mbappe", True)]
            },
            {
                "home": "england", "away": "usa",
                "market_odds": {"home_win": 0.58, "draw": 0.25, "away_win": 0.17, "over_1.5": 0.65, "over_2.5": 0.45, "btts": 0.50},
                "players": [("harry kane", True)]
            }
        ]

    # Limit to the next 8 upcoming matches to keep computation fast and focus on soonest games
    if len(matches) > 8:
        matches = matches[:8]

    dc = statistical.DixonColesModel()
    # Simple fit on team averages
    for m in matches:
        h, a = m["home"], m["away"]
        h_data = fbref.get_team_data(h)
        a_data = fbref.get_team_data(a)
        dc.attack[h] = math_log(h_data.get("avg_goals", 1.4))
        dc.defense[h] = -math_log(h_data.get("avg_conceded", 1.1))
        dc.attack[a] = math_log(a_data.get("avg_goals", 1.4))
        dc.defense[a] = -math_log(a_data.get("avg_conceded", 1.1))
    dc.is_fitted = True

    engine = ParlayEngine(dc)
    
    if longshot:
        # Long-shot targeting 50x to 400x payouts
        parlays = engine.generate_combos(matches, max_legs=12, min_odds=50.0, max_odds=400.0)
        if today_only:
            parlays.sort(key=lambda x: x["joint_probability"], reverse=True)
        else:
            parlays.sort(key=lambda x: x["edge"], reverse=True)
    else:
        # Standard targeting 5x to 150x payouts
        parlays = engine.generate_combos(matches, max_legs=6, min_odds=5.0, max_odds=150.0)
        parlays.sort(key=lambda x: x["joint_probability"], reverse=True)
    
    if not parlays:
        if longshot:
            console.print("[yellow]No positive edge long-shot parlays >= 10x found with current odds.[/yellow]")
        else:
            console.print("[yellow]No positive edge parlays >= 5x found with current odds.[/yellow]")
        return
        
    if longshot:
        console.print(f"\n[bold yellow]Long-Shot Round Robin Portfolio Generated ({len(parlays)} Combos)[/bold yellow]")
        console.print("[dim]Targeting high-multiplier cards (50x - 400x payout) with positive EV edge.[/dim]\n")
        
        selected_parlays = parlays[:10]
        total_stake = len(selected_parlays) * 2.0  # $2 stake per card
        console.print(f"[bold white]Portfolio Allocation Suggestion:[/bold white]")
        console.print(f"  - Total Portfolio Stake: [bold yellow]${total_stake:.2f}[/bold yellow] ($2.00 flat stake on each of the {len(selected_parlays)} cards)\n")
        
        for idx, p in enumerate(selected_parlays):
            legs_str = "\n".join([f"    - {leg['description']} (Odds: {leg['odds']:.2f}x)" for leg in p["legs"]])
            est_win = 2.0 * p["payout_multiplier"]
            net_profit = est_win - total_stake
            
            console.print(Panel(
                f"[bold yellow]Card #{idx+1} [Payout: {p['payout_multiplier']}x][/bold yellow]\n" +
                f"{legs_str}\n\n" +
                f"[bold white]Staked:[/bold white] $2.00 | [bold white]Est. Return:[/bold white] [green]${est_win:.2f}[/green]\n" +
                f"[bold white]Net Portfolio Profit if hits:[/bold white] [bold green]+${net_profit:.2f}[/bold green] (P&L: {net_profit/total_stake*100:+.0f}%)\n" +
                f"[dim]Model Probability: {p['joint_probability']*100:.2f}% | Kalshi Prob: {p['market_probability']*100:.2f}% | Edge: {p['edge']*100:+.1f}%[/dim]",
                border_style="yellow"
            ))
            
        console.print("\n[bold green]Round Robin Portfolio Rationale:[/bold green]")
        console.print("  Because each card carries extreme payout multipliers, you only need [bold]one[/bold] of these cards to hit ")
        console.print(f"  to easily cover the total stake of all cards and lock in a significant overall net profit.\n")

        # Place long-shot parlay bets
        from src.market import paper_trading
        bot_alerts = []
        for idx, p in enumerate(selected_parlays):
            d_sum = paper_trading.get_personality_summary("parlay_longshot", "magnus")
            s_sum = paper_trading.get_personality_summary("parlay_longshot", "athena")
            
            bet_legs = []
            for leg in p["legs"]:
                bet_legs.append({
                    "home": leg["match"][0],
                    "away": leg["match"][1],
                    "bet_type": leg["description"],
                    "result": "pending"
                })
                
            p_desc = f"Longshot Card #{idx+1} ({p['legs_count']} legs)"
            payout = p["payout_multiplier"]
            
            stake_d = 2.0
            res_d = paper_trading.update_bet(
                "parlay_longshot", "magnus", "parlay", f"longshot_{idx+1}",
                p_desc, stake_d, payout, is_parlay=True, legs=bet_legs
            )
            action_d = res_d.get("action")
            if action_d == "placed":
                new = res_d["new"]
                bot_alerts.append(f"[green][+] Magnus placed Card #{idx+1}:[/green] {new['odds']:.2f}x (${new['stake']:.2f})")
            elif action_d == "updated":
                new = res_d["new"]
                bot_alerts.append(f"[bold yellow][!] Magnus updated Card #{idx+1}:[/bold yellow] {new['odds']:.2f}x (${new['stake']:.2f})")
            elif action_d == "none":
                bet = res_d["bet"]
                bot_alerts.append(f"[dim][=] Magnus kept existing Card #{idx+1}:[/dim] {bet['odds']:.2f}x (${bet['stake']:.2f})")
                
            stake_s = 2.0
            res_s = paper_trading.update_bet(
                "parlay_longshot", "athena", "parlay", f"longshot_{idx+1}",
                p_desc, stake_s, payout, is_parlay=True, legs=bet_legs
            )
            action_s = res_s.get("action")
            if action_s == "placed":
                new = res_s["new"]
                bot_alerts.append(f"[green][+] Athena placed Card #{idx+1}:[/green] {new['odds']:.2f}x (${new['stake']:.2f})")
            elif action_s == "updated":
                new = res_s["new"]
                bot_alerts.append(f"[bold yellow][!] Athena updated Card #{idx+1}:[/bold yellow] {new['odds']:.2f}x (${new['stake']:.2f})")
            elif action_s == "none":
                bet = res_s["bet"]
                bot_alerts.append(f"[dim][=] Athena kept existing Card #{idx+1}:[/dim] {bet['odds']:.2f}x (${bet['stake']:.2f})")

        if bot_alerts:
            console.print()
            console.print(Panel(
                "\n".join(bot_alerts),
                title="[bold yellow]Longshot Portfolio Bot Paper Bets[/bold yellow]",
                border_style="yellow"
            ))
    else:
        console.print(f"\n[bold green]Found {len(parlays)} parlays with positive edge & >= 5x payout:[/bold green]\n")
        limit = 5 if today_only else 3
        for idx, p in enumerate(parlays[:limit]):
            console.print(Panel(
                f"[bold yellow]Combo Recommendation #{idx+1} [Payout: {p['payout_multiplier']}x][/bold yellow]\n" +
                "\n".join([f"  - {leg['description']} (Odds: {leg['odds']:.2f}x)" for leg in p["legs"]]) +
                f"\n\n[bold white]Model Combined Probability:[/bold white] {p['joint_probability']*100:.2f}% "
                f"| [bold white]Kalshi Prob:[/bold white] {p['market_probability']*100:.2f}% "
                f"| [bold green]Edge:[/bold green] +{p['edge']*100:.1f}%",
                border_style="green"
            ))

        # Place standard parlay bet
        from src.market import paper_trading
        d_sum = paper_trading.get_personality_summary("parlay_standard", "magnus")
        s_sum = paper_trading.get_personality_summary("parlay_standard", "athena")
        
        best_parlay = parlays[0]
        bet_legs = []
        for leg in best_parlay["legs"]:
            bet_legs.append({
                "home": leg["match"][0],
                "away": leg["match"][1],
                "bet_type": leg["description"],
                "result": "pending"
            })
            
        p_desc = f"Standard Parlay ({best_parlay['legs_count']} legs)"
        payout = best_parlay["payout_multiplier"]
        
        bot_alerts = []
        stake_d = round(d_sum["bankroll"] * 0.1, 2)
        res_d = paper_trading.update_bet(
            "parlay_standard", "magnus", "parlay", "standard",
            p_desc, stake_d, payout, is_parlay=True, legs=bet_legs
        )
        action_d = res_d.get("action")
        if action_d == "placed":
            new = res_d["new"]
            bot_alerts.append(f"[green][+] Magnus placed Standard Parlay:[/green] Payout {new['odds']:.2f}x (${new['stake']:.2f})")
        elif action_d == "updated":
            new = res_d["new"]
            bot_alerts.append(f"[bold yellow][!] Magnus updated Standard Parlay:[/bold yellow] Payout {new['odds']:.2f}x (${new['stake']:.2f})")
        elif action_d == "none":
            bet = res_d["bet"]
            bot_alerts.append(f"[dim][=] Magnus kept existing Standard Parlay:[/dim] Payout {bet['odds']:.2f}x (${bet['stake']:.2f})")

        stake_s = round(s_sum["bankroll"] * 0.05, 2)
        res_s = paper_trading.update_bet(
            "parlay_standard", "athena", "parlay", "standard",
            p_desc, stake_s, payout, is_parlay=True, legs=bet_legs
        )
        action_s = res_s.get("action")
        if action_s == "placed":
            new = res_s["new"]
            bot_alerts.append(f"[green][+] Athena placed Standard Parlay:[/green] Payout {new['odds']:.2f}x (${new['stake']:.2f})")
        elif action_s == "updated":
            new = res_s["new"]
            bot_alerts.append(f"[bold yellow][!] Athena updated Standard Parlay:[/bold yellow] Payout {new['odds']:.2f}x (${new['stake']:.2f})")
        elif action_s == "none":
            bet = res_s["bet"]
            bot_alerts.append(f"[dim][=] Athena kept existing Standard Parlay:[/dim] Payout {bet['odds']:.2f}x (${bet['stake']:.2f})")

        if bot_alerts:
            console.print()
            console.print(Panel(
                "\n".join(bot_alerts),
                title="[bold cyan]Parlay Portfolio Bot Paper Bets[/bold cyan]",
                border_style="cyan"
            ))


def run_complete(home: str, away: str, home_goals: int, away_goals: int):
    home = normalize_team_name(home)
    away = normalize_team_name(away)
    console.print(f"\n[cyan]Ingesting completed match result: {home.title()} {home_goals} - {away_goals} {away.title()}[/cyan]")
    
    # Calculate result
    res = 0.5
    if home_goals > away_goals:
        res = 1.0
    elif home_goals < away_goals:
        res = 0.0
        
    # Update ELO
    h_elo = ELO_PREDICTOR.get(home)
    a_elo = ELO_PREDICTOR.get(away)
    ELO_PREDICTOR.update(home, away, res)
    console.print(f"Updated ELOs: {home.title()}: {h_elo:.1f} -> {ELO_PREDICTOR.get(home):.1f} | {away.title()}: {a_elo:.1f} -> {ELO_PREDICTOR.get(away):.1f}")
    
    # Append match to master training CSV and retrain ML models
    trainer.add_completed_match(home, away, home_goals, away_goals)
    console.print("[bold green]Success! Models retrained dynamically.[/bold green]")
    save_elo()
    
    # Resolve paper bets
    from src.market import paper_trading
    results = paper_trading.resolve_pending_bets(home, away, home_goals, away_goals)
    if results:
        console.print("\n[bold cyan]Resolved Personality Paper Bets:[/bold cyan]")
        for portfolio, personality, bet in results:
            p_name = "Magnus" if personality == "magnus" else "Athena"
            color = "green" if bet["result"] == "WIN" else "red"
            sign = "+" if bet["pnl"] >= 0 else ""
            console.print(f"  - [{portfolio.upper()}] {p_name}: {bet['bet_type']} for ${bet['stake']:.2f} at {bet['odds']:.2f}x -> [{color}]{bet['result']} ({sign}${bet['pnl']:.2f} P&L)[/{color}]")
        
        # Print updated bankrolls
        console.print(f"  [bold white]Updated Bankrolls:[/bold white]")
        for port in ["predict", "ask", "parlay_standard", "parlay_longshot"]:
            d_sum = paper_trading.get_personality_summary(port, "magnus")
            s_sum = paper_trading.get_personality_summary(port, "athena")
            console.print(f"    * {port.title()}: Magnus: ${d_sum['bankroll']:.2f} | Athena: ${s_sum['bankroll']:.2f}")
        console.print()


def run_portfolio():
    console.print("\n[cyan]Retrieving Kalshi portfolio balance and closed positions...[/cyan]")
    client = KalshiClient()
    balance = client.get_balance()
    closed = client.get_closed_positions()
    
    console.print(f"\n[bold white]Cash Balance:[/bold white] ${balance:,.2f}")
    
    table = Table(title="Closed Positions History", box=box.SIMPLE)
    table.add_column("Trade ID", style="dim")
    table.add_column("Match", style="white")
    table.add_column("Bet Option", style="cyan")
    table.add_column("Contracts", style="dim")
    table.add_column("Price Paid", style="dim")
    table.add_column("Result", style="bold green")
    table.add_column("P&L ($)", style="bold green")
    
    total_pnl = 0.0
    for pos in closed:
        result_color = "green" if pos["result"] == "WIN" else "red"
        pnl_val = pos["pnl"]
        total_pnl += pnl_val
        pnl_str = f"+${pnl_val:.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):.2f}"
        
        table.add_row(
            pos["id"],
            pos["match"],
            pos["outcome"],
            str(pos["contracts"]),
            f"${pos['price_paid']:.2f}",
            f"[{result_color}]{pos['result']}[/{result_color}]",
            f"[{result_color}]{pnl_str}[/{result_color}]"
        )
        
    console.print(table)
    pnl_color = "green" if total_pnl >= 0 else "red"
    console.print(f"\n[bold white]Total Realized P&L:[/bold white] [{pnl_color}]${total_pnl:+.2f}[/{pnl_color}]\n")


def run_ask(query: str, user_model: str):
    parts = query.lower().split(" vs ")
    if len(parts) < 2:
        console.print("[red]Error: Format must be 'TeamA vs TeamB'[/red]")
        return

    home, away = parts[0].strip(), parts[1].strip()
    home = normalize_team_name(home)
    away = normalize_team_name(away)
    console.print(f"\n[cyan]Running forecasting pipeline for: {home.title()} vs {away.title()}...[/cyan]")
    
    # Run public search on Kalshi for current prices to serve as feature input
    client = KalshiClient()
    markets = client.get_soccer_markets()
    
    kalshi_probs = None
    for ev in markets:
        title = ev["event_title"].lower()
        if " vs " in title:
            t_parts = title.split(" vs ")
            t_home = normalize_team_name(t_parts[0])
            t_away = normalize_team_name(t_parts[1])
            if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                # Map probabilities
                probs = {}
                for m in ev["markets"]:
                    t = m["title"].lower()
                    ticker = m.get("ticker", "").upper()
                    if "KXWCGAME" in ticker:
                        if is_team_match(home, t):
                            probs["home_win"] = m["yes_price"]
                        elif is_team_match(away, t):
                            probs["away_win"] = m["yes_price"]
                        elif "draw" in t or "tie" in t:
                            probs["draw"] = m["yes_price"]
                if len(probs) >= 2:
                    kalshi_probs = probs
                    break
                
    result = predict_match(home, away, kalshi_probs)
    
    # Calculate Dixon-Coles goal expectation for additional betting categories
    dc = statistical.DixonColesModel()
    h_data = fbref.get_team_data(home)
    a_data = fbref.get_team_data(away)
    dc.attack[home] = math_log(h_data.get("avg_goals", 1.4))
    dc.defense[home] = -math_log(h_data.get("avg_conceded", 1.1))
    dc.attack[away] = math_log(a_data.get("avg_goals", 1.4))
    dc.defense[away] = -math_log(a_data.get("avg_conceded", 1.1))
    dc.is_fitted = True
    
    matrix = dc.predict_score_matrix(home, away, max_goals=6)
    
    over_15_prob = float(sum([matrix[h, a] for h in range(7) for a in range(7) if h + a >= 2]))
    over_25_prob = float(sum([matrix[h, a] for h in range(7) for a in range(7) if h + a >= 3]))
    btts_prob = float(sum([matrix[h, a] for h in range(7) for a in range(7) if h >= 1 and a >= 1]))
    
    # Compile targets
    target_bets = []
    probs = result.probabilities
    mkt_odds = kalshi_probs or {}
    
    # Moneylines
    for outcome, label in [("home_win", home.title() + " Win"), ("draw", "Draw"), ("away_win", away.title() + " Win")]:
        prob = probs[outcome]
        live_p = mkt_odds.get(outcome)
        if live_p:
            edge = prob - live_p
            rec = f"{label} (Kalshi: ${live_p:.2f}, Model: {prob*100:.1f}%, Edge: {edge*100:+.1f}%)"
        else:
            rec = f"{label} (Kalshi: N/A, Model: {prob*100:.1f}%, Target Buy Price < ${prob:.2f})"
        target_bets.append(rec)
        
    # Game Lines
    for outcome, label, prob in [("over_1.5", "Over 1.5 Goals", over_15_prob), 
                                 ("over_2.5", "Over 2.5 Goals", over_25_prob), 
                                 ("btts", "Both Teams to Score", btts_prob)]:
        live_p = None
        for ev in markets:
            title = ev["event_title"].lower()
            if " vs " in title:
                t_parts = title.split(" vs ")
                t_home = normalize_team_name(t_parts[0])
                t_away = normalize_team_name(t_parts[1])
                if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                    for m in ev["markets"]:
                        t = m["title"].lower()
                        if outcome == "over_1.5" and "over 1.5" in t:
                            live_p = m["yes_price"]
                        elif outcome == "over_2.5" and "over 2.5" in t:
                            live_p = m["yes_price"]
                        elif outcome == "btts" and "both teams" in t:
                            live_p = m["yes_price"]
        if live_p:
            edge = prob - live_p
            rec = f"{label} (Kalshi: ${live_p:.2f}, Model: {prob*100:.1f}%, Edge: {edge*100:+.1f}%)"
        else:
            rec = f"{label} (Kalshi: N/A, Model: {prob*100:.1f}%, Target Buy Price < ${prob:.2f})"
        target_bets.append(rec)
        
    # Player Props
    KEY_PLAYERS = {
        "england": ["harry kane", "jude bellingham", "bukayo saka"],
        "france": ["kylian mbappe", "antoine griezmann"],
        "argentina": ["lionel messi", "lautaro martinez"],
        "brazil": ["vinicius jr"],
        "portugal": ["cristiano ronaldo"],
        "poland": ["robert lewandowski"],
        "germany": ["jamal musiala", "florian wirtz"],
        "spain": ["alvaro morata"],
        "ghana": ["antoine semenyo", "mohammed kudus"],
    }
    
    players = []
    h_avg = float(h_data.get("avg_goals", 1.4))
    a_avg = float(a_data.get("avg_goals", 1.4))
    
    for team, p_names in KEY_PLAYERS.items():
        if team in (home, away):
            is_home = (team == home)
            for name in p_names:
                p_stats = player_stats.get_player_stats(name)
                share = p_stats.get("goals_per_90", 0.25) / (h_avg if is_home else a_avg)
                
                # P(Player scores)
                p_prob = 0.0
                for h in range(7):
                    for a in range(7):
                        g = h if is_home else a
                        p_prob += matrix[h, a] * (1.0 - (1.0 - share) ** g)
                players.append((name, p_prob))
                
    for name, p_prob in players:
        live_p = None
        for ev in markets:
            title = ev["event_title"].lower()
            if " vs " in title:
                t_parts = title.split(" vs ")
                t_home = normalize_team_name(t_parts[0])
                t_away = normalize_team_name(t_parts[1])
                if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                    for m in ev["markets"]:
                        t = m["title"].lower()
                        if name in t and ("score" in t or "goal" in t):
                            live_p = m["yes_price"]
        label = f"{name.title()} to Score"
        if live_p:
            edge = p_prob - live_p
            rec = f"{label} (Kalshi: ${live_p:.2f}, Model: {p_prob*100:.1f}%, Edge: {edge*100:+.1f}%)"
        else:
            rec = f"{label} (Kalshi: N/A, Model: {p_prob*100:.1f}%, Target Buy Price < ${p_prob:.2f})"
        target_bets.append(rec)
        
    # Sentiment flags
    h_news = news.get_sentiment(home)
    a_news = news.get_sentiment(away)
    news_flags = h_news.get("flags", []) + a_news.get("flags", [])
    
    # Corners expectation
    try:
        h_crn = get_team_recent_corners(home)
        a_crn = get_team_recent_corners(away)
        lambda_h = h_crn["won"] * (a_crn["conceded"] / 4.8)
        lambda_a = a_crn["won"] * (h_crn["conceded"] / 4.8)
        corners_expectation = {
            home.title(): f"{lambda_h:.1f}",
            away.title(): f"{lambda_a:.1f}",
            "Total Expected": f"{lambda_h + lambda_a:.1f}"
        }
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load corner kick expectations: {e}[/yellow]")
        corners_expectation = {
            home.title(): "N/A",
            away.title(): "N/A",
            "Total Expected": "N/A"
        }
    
    # Generate debate
    if not GEMINI_AVAILABLE:
        console.print("\n[bold red]ERROR: GEMINI_API_KEY is not configured or google-generativeai package is missing.[/bold red]")
        console.print("[red]Enforced: Mock fallback debates are disabled to prevent nonsensical data.[/red]")
        console.print("[yellow]Please set the GEMINI_API_KEY in your .env file or export it in your shell environment.[/yellow]\n")
        return
        
    mapped_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if not user_model else user_model
    console.print(f"[green]Calling Gemini API ({mapped_model}) to generate live scout-quant debate...[/green]")
        
    try:
        debate = generate_debate(
            home=home,
            away=away,
            probs=result.probabilities,
            elo_diff=result.elo_diff,
            sentiment=result.sentiment,
            news_flags=news_flags,
            target_bets=target_bets,
            user_model=user_model,
            progression_probs=result.progression_probabilities,
            corners_expectation=corners_expectation
        )
    except Exception as e:
        console.print(f"\n[bold red]ERROR running debate: {e}[/bold red]\n")
        return
    
    # Save/register their chosen bets
    from src.market import paper_trading
    pb = debate.get("personal_bets")
    changes = {}
    if pb:
        for personality in ["magnus", "athena"]:
            bet = pb.get(personality)
            if bet and isinstance(bet, dict):
                b_type = bet.get("bet_type")
                stake = bet.get("stake", 0.0)
                odds = bet.get("odds", 1.0)
                if b_type and stake > 0:
                    res = paper_trading.update_bet("ask", personality, home, away, b_type, stake, odds)
                    changes[personality] = res
                    
    d_sum = paper_trading.get_personality_summary("ask", "magnus")
    s_sum = paper_trading.get_personality_summary("ask", "athena")
    
    # Display comparison alerts if there are any position changes or status updates
    update_alerts = []
    for personality, res in changes.items():
        name = "Magnus" if personality == "magnus" else "Athena"
        action = res.get("action")
        if action == "updated":
            old = res["old"]
            new = res["new"]
            update_alerts.append(
                f"[bold yellow][!] {name} CHANGED RECOMMENDATION![/bold yellow]\n"
                f"  - Previous: {old['bet_type']} (${old['stake']:.2f} at {old['odds']:.2f}x)\n"
                f"  - New:      {new['bet_type']} (${new['stake']:.2f} at {new['odds']:.2f}x)\n"
                f"  - Rationale: Live odds shift or updated analysis prompted a hedge or replacement."
            )
        elif action == "placed":
            new = res["new"]
            update_alerts.append(
                f"[green][+] {name} placed new position:[/green] {new['bet_type']} (${new['stake']:.2f} at {new['odds']:.2f}x)"
            )
        elif action == "none":
            bet = res["bet"]
            update_alerts.append(
                f"[dim][=] {name} kept existing position:[/dim] {bet['bet_type']} (${bet['stake']:.2f} at {bet['odds']:.2f}x)"
            )
            
    if update_alerts:
        console.print(Panel(
            "\n\n".join(update_alerts),
            title="[bold cyan]Position & Recommendation Updates[/bold cyan]",
            border_style="cyan"
        ))
    
    # Format their active bet summary for this match
    d_active_match = next((
        b for b in d_sum["active_bets"]
        if (b.get("home") == home and b.get("away") == away) or
           (b.get("home") == away and b.get("away") == home)
    ), None)
    d_bet_str = "No bet placed"
    if d_active_match:
        d_bet_str = f"RISKING ${d_active_match['stake']:.2f} on '{d_active_match['bet_type']}' at {d_active_match['odds']:.2f}x"
        
    s_active_match = next((
        b for b in s_sum["active_bets"]
        if (b.get("home") == home and b.get("away") == away) or
           (b.get("home") == away and b.get("away") == home)
    ), None)
    s_bet_str = "No bet placed"
    if s_active_match:
        s_bet_str = f"RISKING ${s_active_match['stake']:.2f} on '{s_active_match['bet_type']}' at {s_active_match['odds']:.2f}x"
    
    console.print()
    console.print(Panel(
        f"{debate['magnus']}\n\n[bold white]Bankroll:[/bold white] ${d_sum['bankroll']:.2f} (P&L: {d_sum['total_pnl']:+.2f}) | [bold white]Active Bet:[/bold white] {d_bet_str}",
        title="[bold red]Magnus's Scout Eye-Test[/bold red]",
        border_style="red",
        padding=(1, 2)
    ))
    console.print()
    console.print(Panel(
        f"{debate['athena']}\n\n[bold white]Bankroll:[/bold white] ${s_sum['bankroll']:.2f} (P&L: {s_sum['total_pnl']:+.2f}) | [bold white]Active Bet:[/bold white] {s_bet_str}",
        title="[bold blue]Athena's Quant Analysis[/bold blue]",
        border_style="blue",
        padding=(1, 2)
    ))
    console.print()
    console.print(Panel(
        debate["consensus"],
        title="[bold green]Consensus Recommendation[/bold green]",
        border_style="green",
        padding=(1, 2)
    ))
    console.print()


def run_update():
    console.print("\n[yellow]Checking ESPN for newly completed World Cup matches...[/yellow]")
    
    # Tournament matches range (June 11 to present). 
    # Dates query param supports YYYYMMDD-YYYYMMDD range.
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    from datetime import datetime, timedelta
    today = datetime.now()
    start_str = "20260601"
    end_str = (today + timedelta(days=2)).strftime("%Y%m%d")
    date_range = f"{start_str}-{end_str}"
    try:
        resp = requests.get(url, params={"dates": date_range, "limit": 100}, headers=fixtures.ESPN_HEADERS, timeout=12)
        if resp.status_code != 200:
            console.print(f"[red]Error fetching from ESPN API (HTTP {resp.status_code})[/red]")
            return
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Failed to connect to ESPN API: {e}[/red]")
        return
        
    events = data.get("events", [])
    if not events:
        console.print("[green]No events found for this tournament period.[/green]")
        return
        
    # Sort events chronologically to preserve ELO timeline updates
    events.sort(key=lambda e: e.get("date", ""))
    
    trainer.initialize_master_dataset()
    import pandas as pd
    from src.data.preprocessor import FEATURE_NAMES, get_match_features
    
    df = pd.read_csv(trainer.MASTER_CSV_PATH)
    
    updated = False
    new_count = 0
    resolved_bets_total = []
    
    for event in events:
        status_obj = event.get("status", {})
        completed = status_obj.get("type", {}).get("completed", False)
        if not completed:
            continue
            
        comps = event.get("competitions", [{}])
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue
            
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
        
        home_team = normalize_team_name(home.get("team", {}).get("displayName", ""))
        away_team = normalize_team_name(away.get("team", {}).get("displayName", ""))
        
        try:
            home_goals = int(home.get("score", 0))
            away_goals = int(away.get("score", 0))
        except ValueError:
            continue
            
        match_date = event.get("date", "")[:10]
        
        # Check if match is already in master dataset
        exists = ((df["HomeTeam"].str.lower() == home_team.lower()) & 
                  (df["AwayTeam"].str.lower() == away_team.lower())).any()
                  
        if not exists:
            # 1. Calculate result factor (for ELO rating update)
            if home_goals > away_goals:
                res_val = 1.0
                ftr = "H"
            elif home_goals < away_goals:
                res_val = 0.0
                ftr = "A"
            else:
                res_val = 0.5
                ftr = "D"
                
            # 2. Calculate pre-match features (using current ELO ratings before update)
            features = get_match_features(home_team, away_team)
            
            # 3. Update ELO rating
            h_elo_before = ELO_PREDICTOR.get(home_team)
            a_elo_before = ELO_PREDICTOR.get(away_team)
            ELO_PREDICTOR.update(home_team, away_team, res_val)
            
            # 4. Resolve any pending paper bets
            from src.market import paper_trading
            bets_resolved = paper_trading.resolve_pending_bets(home_team, away_team, home_goals, away_goals)
            resolved_bets_total.extend(bets_resolved)
            
            # 5. Build and append row
            row_dict = {
                "Date": match_date,
                "HomeTeam": home_team,
                "AwayTeam": away_team,
                "FTHG": float(home_goals),
                "FTAG": float(away_goals),
                "FTR": ftr
            }
            for i, name in enumerate(FEATURE_NAMES):
                row_dict[name] = float(features[i])
                
            df = pd.concat([df, pd.DataFrame([row_dict])], ignore_index=True)
            
            console.print(f"  [green]- Ingested:[/green] {home_team} {home_goals} - {away_goals} {away_team} ({match_date}) "
                          f"[dim]| ELOs updated: {home_team} ({h_elo_before:.0f}->{ELO_PREDICTOR.get(home_team):.0f}), {away_team} ({a_elo_before:.0f}->{ELO_PREDICTOR.get(away_team):.0f})[/dim]")
            updated = True
            new_count += 1
            
    if updated:
        df.to_csv(trainer.MASTER_CSV_PATH, index=False)
        save_elo()
        console.print(f"\n[bold green]Ingested {new_count} new matches. Starting dynamic ML model retraining...[/bold green]")
        trainer.train_and_save_all()
        console.print("[bold green]Success! Synchronized all models & ratings.[/bold green]")
        
        # Display resolved bets summary if any
        if resolved_bets_total:
            console.print("\n[bold cyan]Resolved Personality Paper Bets during sync:[/bold cyan]")
            for portfolio, personality, bet in resolved_bets_total:
                p_name = "Magnus" if personality == "magnus" else "Athena"
                color = "green" if bet["result"] == "WIN" else "red"
                sign = "+" if bet["pnl"] >= 0 else ""
                console.print(f"  - [{portfolio.upper()}] {p_name}: {bet['bet_type']} for ${bet['stake']:.2f} at {bet['odds']:.2f}x -> [{color}]{bet['result']} ({sign}${bet['pnl']:.2f} P&L)[/{color}]")
            
            # Print updated bankrolls
            console.print(f"  [bold white]Updated Bankrolls:[/bold white]")
            for port in ["predict", "ask", "parlay_standard", "parlay_longshot"]:
                d_sum = paper_trading.get_personality_summary(port, "magnus")
                s_sum = paper_trading.get_personality_summary(port, "athena")
                console.print(f"    * {port.title()}: Magnus: ${d_sum['bankroll']:.2f} | Athena: ${s_sum['bankroll']:.2f}")
            console.print()
    else:
        console.print("[green]Everything is already up-to-date! No new completed matches found.[/green]\n")

    # Sync upcoming fixtures & stats
    from src.data.scrapers.upcoming_and_stats import scrape_upcoming_fixtures, scrape_tournament_stats
    console.print("\n[yellow]Syncing upcoming fixtures and live tournament player statistics...[/yellow]")
    scrape_upcoming_fixtures()
    scrape_tournament_stats()
    console.print("[bold green]Success! Schedule and tournament stats prepared.[/bold green]")


def run_daily():
    import json
    from datetime import datetime, timezone
    
    schedule_path = os.path.join("data", "processed", "daily_schedule.json")
    if not os.path.exists(schedule_path):
        console.print("[red]Error: daily_schedule.json not found. Run 'update' command first.[/red]")
        return
    try:
        with open(schedule_path, "r") as f:
            schedule = json.load(f)
    except Exception as e:
        console.print(f"[red]Failed to read schedule: {e}[/red]")
        return

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    todays_matches = []
    for m in schedule:
        if m.get("date", "").startswith(today_str):
            todays_matches.append(m)
            
    if not todays_matches:
        console.print(f"[yellow]No matches scheduled for today ({today_str}).[/yellow]")
        return

    console.print(Panel(
        f"[bold green]Executing Daily Betting Pipeline for {today_str}[/bold green]\n"
        f"Matches found: {len(todays_matches)}",
        border_style="green"
    ))
    
    for idx, m in enumerate(todays_matches):
        h = m["home"]
        a = m["away"]
        query = f"{h} vs {a}"
        
        console.print(f"\n[bold cyan]=== [Match #{idx+1}] {query.upper()} ===[/bold cyan]\n")
        run_predict(query)
        run_ask(query, "Gemini 2.5 Flash")
            
    console.print("\n[yellow]Running Parlay Engine for today's matches...[/yellow]")
    run_parlay(longshot=False, today_only=True)
    run_parlay(longshot=True, today_only=True)
    
    console.print("\n[bold green]=== Daily Pipeline Execution Completed ===[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="World Cup Predictor & Parlay Engine CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("init", help="Run initial model training on history")
    subparsers.add_parser("update", help="Automatically sync completed tournament match results & retrain")
    subparsers.add_parser("run-daily", help="Runs predictions & debates for all of today's matches")
    
    pred_parser = subparsers.add_parser("predict", help="Predict match outcome")
    pred_parser.add_argument("query", help="Match query, e.g. 'Argentina vs France'")
    
    ask_parser = subparsers.add_parser("ask", help="Stages a Magnus & Athena debate on a match")
    ask_parser.add_argument("query", help="Match query, e.g. 'Argentina vs France'")
    ask_parser.add_argument("--model", "-m", default="Gemini 3.5 Flash (Medium)", help="Model to use for prediction/debate")
    
    parlay_parser = subparsers.add_parser("parlay", help="Find high edge parlays on Kalshi")
    parlay_parser.add_argument("--longshot", "-l", action="store_true", help="Generate a portfolio of high-payout long-shot parlays (Round Robin)")
    parlay_parser.add_argument("--today", "-t", action="store_true", help="Generate parlays only for matches playing today")
    
    comp_parser = subparsers.add_parser("complete", help="Record completed match result")
    comp_parser.add_argument("home", help="Home team name")
    comp_parser.add_argument("away", help="Away team name")
    comp_parser.add_argument("home_goals", type=int, help="Home goals scored")
    comp_parser.add_argument("away_goals", type=int, help="Away goals scored")
    
    subparsers.add_parser("portfolio", help="Fetch Kalshi balance and closed trades")
    
    args = parser.parse_args()
    
    if args.command == "init":
        run_init()
    elif args.command == "update":
        run_update()
    elif args.command == "run-daily":
        run_daily()
    elif args.command == "predict":
        run_predict(args.query)
    elif args.command == "ask":
        run_ask(args.query, args.model)
    elif args.command == "parlay":
        run_parlay(args.longshot, args.today)
    elif args.command == "complete":
        run_complete(args.home, args.away, args.home_goals, args.away_goals)
    elif args.command == "portfolio":
        run_portfolio()
    else:
        banner()


if __name__ == "__main__":
    main()
