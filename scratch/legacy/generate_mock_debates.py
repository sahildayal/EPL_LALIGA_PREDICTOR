import os
import json
from datetime import datetime, timezone

def generate_all():
    debates_dir = os.path.join("data", "processed", "debates")
    os.makedirs(debates_dir, exist_ok=True)
    
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    matchups = [
        {
            "home": "argentina",
            "away": "france",
            "probs": {"home_win": 0.42, "draw": 0.28, "away_win": 0.30},
            "elo_diff": 20.43,
            "sentiment": 0.15,
            "news_flags": ["Messi fit", "Mbappe sharp"],
            "home_bullets": "- Lionel Messi is confirmed to start in the playmaker role.\n- Lautaro Martinez has been in excellent goalscoring form in recent training sessions.",
            "away_bullets": "- Kylian Mbappe showed explosive speed in the final scrimmage.\n- N'Golo Kante returns to the midfield anchor position after resting.",
            "magnus": "Look, I've watched Argentina play in major tournament knockouts since Messi was a teenager. The eye-test says they're playing with an emotional gravity that France can't match. Messi has that look in his eye. France has the speed with Mbappe, but Argentina's backline is mean, disciplined, and they will foul Mbappe before he gets into third gear. I'm going with my gut here: Argentina wins a tight, ugly battle. Hammer the Argentina moneyline.",
            "athena": "The Dixon-Coles model predicts a low-scoring affair. Argentina has a 42% probability of winning in regulation, with a Draw at 28%. Given the Kalshi market odds of 2.15 for Argentina (+115), the mathematical edge is a mere 1.2%. However, the 'Under 2.5 Goals' contract exhibits a 62% probability, which is mispriced by the market at 1.75. I am sizing a position on the Under.",
            "consensus": "Back both teams to play conservatively. Suggest buying YES on Under 2.5 Goals at any price below 1.80.",
            "magnus_bet": "Moneyline - Argentina Win", "magnus_stake": 50.0, "magnus_odds": 2.15,
            "athena_bet": "Game Lines - Under 2.5 Goals", "athena_stake": 40.0, "athena_odds": 1.75
        },
        {
            "home": "brazil",
            "away": "spain",
            "probs": {"home_win": 0.35, "draw": 0.27, "away_win": 0.38},
            "elo_diff": -15.24,
            "sentiment": -0.05,
            "news_flags": ["Rodri controlling midfield", "Vinicius isolated"],
            "home_bullets": "- Vinicius Jr. looks sharp but Spain is planning a double-team.\n- Alisson Becker is expected to face a high number of shots.",
            "away_bullets": "- Rodri is in peak physical condition and will dictate the tempo.\n- Alvaro Morata is starting as the lone striker with high support.",
            "magnus": "Spain plays that tiki-taka that makes scouts want to take a nap, but you can't deny it works. Brazil's midfield is too soft right now. Without Casemiro in his prime, they're going to chase Spain's shadow all night. Vinicius will be starved of service. Spain will wear them down and win it 1-0 or 2-0. I'm backing Spain here.",
            "athena": "My model yields a 38% win probability for Spain, which translates to a fair price of 2.63. Currently, Kalshi is trading Spain Win contracts at 2.40, presenting a substantial positive expected value (+5.3% edge). Brazil's defense has conceded 1.2 expected goals per game over their last 5 matches. I select Spain Win.",
            "consensus": "Spain is value. Suggest Spain Win (Draw No Bet or Moneyline) size to 5% of portfolio.",
            "magnus_bet": "Moneyline - Spain Win", "magnus_stake": 30.0, "magnus_odds": 2.40,
            "athena_bet": "Moneyline - Spain Win", "athena_stake": 50.0, "athena_odds": 2.40
        },
        {
            "home": "portugal",
            "away": "england",
            "probs": {"home_win": 0.39, "draw": 0.29, "away_win": 0.32},
            "elo_diff": 8.28,
            "sentiment": 0.08,
            "news_flags": ["Ronaldo starting", "Kane fatigue concerns"],
            "home_bullets": "- Cristiano Ronaldo remains the focal point of the Portuguese attack.\n- Bruno Fernandes is fit and has created 4.2 chances per game recently.",
            "away_bullets": "- Harry Kane is showing slight fatigue indicators but will start.\n- Jude Bellingham is fully fit and will play advanced midfield.",
            "magnus": "England is too cautious under pressure. They have all the talent in the world, but they play like they're afraid of their own shadows in the knockout stages. Portugal has veterans who know how to win these games. Bruno Fernandes will find Ronaldo, and even at his age, Ronaldo only needs one half-chance. Portugal advances.",
            "athena": "England's defensive block is statistically very sound, conceding only 0.85 goals per 90 mins. The Dixon-Coles simulation indicates a 29% probability of a Draw in regulation. The parlay engine identifies Both Teams to Score (BTTS) 'No' as a strong component at 58% probability. I will bet on BTTS - No.",
            "consensus": "A low scoring match where Portugal has a slight edge. Suggest Portugal to Qualify or BTTS 'No'.",
            "magnus_bet": "Moneyline - Portugal Win", "magnus_stake": 40.0, "magnus_odds": 2.60,
            "athena_bet": "Game Lines - Both Teams to Score (No)", "athena_stake": 35.0, "athena_odds": 1.80
        },
        {
            "home": "netherlands",
            "away": "croatia",
            "probs": {"home_win": 0.52, "draw": 0.26, "away_win": 0.22},
            "elo_diff": 41.14,
            "sentiment": 0.12,
            "news_flags": ["Modric final tournament", "Dutch squad youth energy"],
            "home_bullets": "- Cody Gakpo is in sensational form along the left wing.\n- Virgil van Dijk is commanding the defensive line with absolute authority.",
            "away_bullets": "- Luka Modric is prepared to play the full 120 minutes if needed.\n- Croatia's midfield remains highly experienced but lacks depth.",
            "magnus": "Never write off Croatia. They are the cockroaches of international football; you think they're dead, and then they win on penalties. But Modric can't carry this midfield forever. The Dutch have too much pace and legs for them. Cody Gakpo is going to run circles around their fullbacks. Netherlands wins this comfortably.",
            "athena": "The Dutch possess a 52% probability of regulation victory. However, Croatia's goalie has a 30% penalty save rate, and Croatia has won 4 of their last 5 shootouts. The value is actually on the Over 2.5 Goals at 2.10, as both teams have showed defensive vulnerabilities on set pieces. I select Over 2.5 Goals.",
            "consensus": "Netherlands is the logical winner, but goals offer better pricing. Buy Over 2.5 Goals at 2.10.",
            "magnus_bet": "Moneyline - Netherlands Win", "magnus_stake": 60.0, "magnus_odds": 1.85,
            "athena_bet": "Game Lines - Over 2.5 Goals", "athena_stake": 30.0, "athena_odds": 2.10
        }
    ]
    
    for m in matchups:
        home_clean = m["home"].lower().strip().replace(" ", "_")
        away_clean = m["away"].lower().strip().replace(" ", "_")
        filename = f"{date_str}-{home_clean}-vs-{away_clean}.json"
        filepath = os.path.join(debates_dir, filename)
        
        save_data = {
            "home": m["home"],
            "away": m["away"],
            "date": date_str,
            "probabilities": m["probs"],
            "elo_diff": m["elo_diff"],
            "sentiment": m["sentiment"],
            "news_flags": m["news_flags"],
            "home_news_bullets": m["home_bullets"],
            "away_news_bullets": m["away_bullets"],
            "debate": {
                "magnus": m["magnus"],
                "athena": m["athena"],
                "consensus": m["consensus"],
                "personal_bets": {
                    "magnus": {
                        "bet_type": m["magnus_bet"],
                        "stake": m["magnus_stake"],
                        "odds": m["magnus_odds"]
                    },
                    "athena": {
                        "bet_type": m["athena_bet"],
                        "stake": m["athena_stake"],
                        "odds": m["athena_odds"]
                    }
                }
            }
        }
        
        with open(filepath, "w") as f:
            json.dump(save_data, f, indent=2)
        print(f"Generated: {filepath}")

if __name__ == "__main__":
    generate_all()
