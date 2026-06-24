#!/usr/bin/env python3
import os
import sys
import json
import pandas as pd
from datetime import datetime

# Load configuration
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.market import paper_trading
from src.predictor import ELO_PREDICTOR, load_elo

def print_section(title):
    print("=" * 70)
    print(f" {title.upper()} ")
    print("=" * 70)

def print_portfolio_standings(port_id, port_name):
    big_d = paper_trading.get_personality_summary(port_id, "big_d")
    sigmaballs = paper_trading.get_personality_summary(port_id, "sigmaballs")
    
    print(f"\n  >> {port_name} Portfolio <<")
    print("    Big D (Scout):")
    print(f"      Bankroll : ${big_d['bankroll']:.2f} | P&L: {big_d['total_pnl']:+.2f} | Win Rate: {big_d['win_rate']}% ({big_d['total_bets']} bets) | Active: {len(big_d['active_bets'])}")
    print("    SIGMABALLS (Quant):")
    print(f"      Bankroll : ${sigmaballs['bankroll']:.2f} | P&L: {sigmaballs['total_pnl']:+.2f} | Win Rate: {sigmaballs['win_rate']}% ({sigmaballs['total_bets']} bets) | Active: {len(sigmaballs['active_bets'])}")

def main():
    print("+" + "-" * 68 + "+")
    print("|" + "  2026 World Cup Predictor & Kalshi Parlay Engine Summary Dashboard ".center(68) + "|")
    print("+" + "-" * 68 + "+")
    print(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Local)")
    print()

    # 1. Dataset stats
    print_section("1. Training Data & Features")
    master_csv = os.path.join("data", "processed", "master_dataset.csv")
    if os.path.exists(master_csv):
        df = pd.read_csv(master_csv)
        print(f"  - Master training set path: {master_csv}")
        print(f"  - Total matches in dataset: {len(df)}")
        print(f"  - Model features: 17 inputs (ELO diff, goals scored/conceded averages, sentiment diff, etc.)")
    else:
        print("  - Master dataset not initialized yet (run: python main.py init)")

    # 2. Model Ensemble
    print_section("2. Model Ensemble Architecture (8 Models)")
    print("  - Dixon-Coles Goal Expectation Model (bivariate Poisson distribution)")
    print("  - Elo Rating System (dynamic post-match updates)")
    print("  - 6 Machine Learning Classifiers/Regressors:")
    print("    * Logistic Regression (Baseline)")
    print("    * Support Vector Machine (SVM)")
    print("    * Gaussian Discriminant Analysis (GDA)")
    print("    * Random Forest Classifier")
    print("    * XGBoost Classifier")
    print("    * Multi-Layer Perceptron (Neural Network)")

    # 3. Elo Ratings
    print_section("3. Current Top Elo Ratings")
    load_elo()
    ratings = ELO_PREDICTOR.ratings
    if ratings:
        sorted_ratings = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
        print("  Top 5 Teams:")
        for idx, (team, elo) in enumerate(sorted_ratings[:5]):
            print(f"    {idx+1}. {team.title()}: {elo:.1f} pts")
        print("\n  Bottom 5 Teams:")
        for idx, (team, elo) in enumerate(sorted_ratings[-5:]):
            print(f"    {idx+1}. {team.title()}: {elo:.1f} pts")
    else:
        print("  - No ELO ratings found.")

    # 4. Paper Trading STANDINGS across Portfolios
    print_section("4. Personality Paper Trading Standings by Portfolio")
    print_portfolio_standings("predict", "Predict (Match Forecasts)")
    print_portfolio_standings("ask", "Ask (Debates & LLM Plays)")
    print_portfolio_standings("parlay_standard", "Parlay Standard (5x-150x Combos)")
    print_portfolio_standings("parlay_longshot", "Parlay Longshot (Round Robin Portfolios)")

    # 5. Core features built
    print_section("5. Key Features Implemented")
    print("  [1] Live Kalshi Client: Fetches and parses KXWCGAME (moneyline), KXWCBTTS,")
    print("      KXWCTOTAL (spreads), and KXWCGOAL (player scorer props) markets.")
    print("  [2] Correlated Parlay Engine: Uses a Dixon-Coles goal expectation matrix to")
    print("      calculate exact joint probabilities for same-game and cross-game parlays,")
    print("      while filtering for mutual exclusions (max 1 Moneyline/totals leg per match).")
    print("  [3] Google News RSS Sentiment Scraper: Pulls team-specific news and runs")
    print("      sentiment extraction to dynamically adjust prediction weights.")
    print("  [4] Automated ESPN score sync: 'python main.py update' fetches completed")
    print("      results, resolves paper bets across all 4 portfolios, and retrains models.")

    print("=" * 70)
    print(" Suggestion: Share this printout and ask your mentor the advice questions below!")
    print("=" * 70)

if __name__ == "__main__":
    main()
