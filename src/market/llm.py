import os
import json
import requests
import warnings
from dotenv import load_dotenv

# Suppress the deprecation/FutureWarning from the legacy google.generativeai SDK package
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

load_dotenv()

# We look for GEMINI_API_KEY in the environment
API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_AVAILABLE and API_KEY:
    genai.configure(api_key=API_KEY)
else:
    GEMINI_AVAILABLE = False


def map_model_name(friendly_name: str) -> str:
    """Maps friendly user models to Google API model keys."""
    if not friendly_name:
        return "gemini-2.5-flash"
    f_lower = friendly_name.lower().strip()
    if "flash" in f_lower:
        return "gemini-2.5-flash"
    elif "pro" in f_lower:
        return "gemini-2.5-pro"
    elif "sonnet" in f_lower or "opus" in f_lower or "claude" in f_lower:
        # Map to Gemini Pro for high-tier thinking
        return "gemini-2.5-pro"
    elif "gpt" in f_lower or "oss" in f_lower:
        return "gemini-2.5-flash"
    return friendly_name


def get_tournament_stage() -> str:
    from datetime import datetime
    # World Cup 2026 Group Stage: June 11 to June 27. Knockout Stage: June 28 to July 19.
    today = datetime.utcnow()
    if today.year > 2026 or (today.year == 2026 and (today.month > 6 or (today.month == 6 and today.day >= 28))):
        return "Knockout Stage (Single Elimination - Extra Time & Penalties apply if tied at 120 mins. Note: Kalshi Moneyline markets still resolve based on regulation 90 mins + injury time scoreline)."
    return "Group Stage (Round Robin - Matches can end in a Draw/Tie after 90 mins + injury time)."


def generate_debate(home: str, away: str, probs: dict, elo_diff: float, sentiment: float, news_flags: list, target_bets: list, user_model: str = None, progression_probs: dict = None, corners_expectation: dict = None) -> dict:
    """
    Calls Gemini API to generate a debate between Big D and SIGMABALLS.
    Injects their bankroll stats and performance history, and parses their chosen personal bets.
    Falls back to a simulated script if API is unavailable.
    """
    from src.market import paper_trading
    
    # 1. Fetch current bankrolls and record history for prompt injection
    d_sum = paper_trading.get_personality_summary("ask", "big_d")
    s_sum = paper_trading.get_personality_summary("ask", "sigmaballs")
    
    d_str = f"Bankroll: ${d_sum['bankroll']:.2f}, P&L: ${d_sum['total_pnl']:+.2f}, Win Rate: {d_sum['win_rate']}% ({d_sum['total_bets']} bets)"
    s_str = f"Bankroll: ${s_sum['bankroll']:.2f}, P&L: ${s_sum['total_pnl']:+.2f}, Win Rate: {s_sum['win_rate']}% ({s_sum['total_bets']} bets)"

    # Look for active/previous bets on this specific match
    d_active = next((b for b in d_sum["active_bets"] if b.get("home") == home.lower().strip() and b.get("away") == away.lower().strip()), None)
    s_active = next((b for b in s_sum["active_bets"] if b.get("home") == home.lower().strip() and b.get("away") == away.lower().strip()), None)
    
    prev_bet_prompt = ""
    if d_active or s_active:
        prev_bet_prompt = "\nActive/Previous bets already placed on this match:\n"
        if d_active:
            prev_bet_prompt += f"- Big D's current active bet: {d_active['bet_type']} | Stake: ${d_active['stake']:.2f} | Odds: {d_active['odds']:.2f}x\n"
        if s_active:
            prev_bet_prompt += f"- SIGMABALLS's current active bet: {s_active['bet_type']} | Stake: ${s_active['stake']:.2f} | Odds: {s_active['odds']:.2f}x\n"
        prev_bet_prompt += (
            "IMPORTANT: The bots already have the above bets placed on this match. "
            "If the live odds or news sentiment have changed, they can choose to either:\n"
            "1. Stick to the EXACT same bet (output the exact same bet_type in JSON).\n"
            "2. Modify/Change their bet to a different one (output a different bet_type in JSON). "
            "If they change it, they MUST explain their reasoning during the debate (e.g. hedging, odds movement, or new news).\n"
        )

    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "Gemini AI API Key ('GEMINI_API_KEY') is not configured or google-generativeai package is missing. "
            "Enforced: Mock fallback debates are disabled to prevent nonsensical data."
        )

    # Use the specified user model or fallback to env variable/default
    raw_model = user_model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    model_name = map_model_name(raw_model)
    
    stage = get_tournament_stage()
    
    prompt = f"""
You are staging a debate between two sports sports betting personalities analyzing the upcoming match: {home.title()} vs {away.title()}.
 
Personalities:
1. **Big D (The Eye-Test Scout)**:
   - Personality: A grizzled, old-school veteran football scout. Doesn't know what a CSV file is and doesn't want to. He has watched 10,000 matches.
   - Current Bankroll & Performance: {d_str}
   - Analysis: He only cares about four things: ranking, form, who they played, and who's healthy. He asks: "Is the better team actually showing up today?" 
   - Style: Direct, opinionated, speaks in scout jargon, quotes historical matches he's seen. He never talks about "expected value" or "vig." He just tells you who is going to win and if they are going to play lazy.
   
2. **SIGMABALLS (The Quant)**:
   - Personality: A brilliant, cold-blooded machine learning engineer. His favorite player is Pascal Gross. Never impressed by a 35-yard screamer.
   - Current Bankroll & Performance: {s_str}
   - Analysis: He only trusts data: ELO ratings, Dixon-Coles Poisson goals, and the machine learning model ensemble. 
   - Style: Highly logical, quotes percentages and edges. He only bets when the model shows a positive edge against Kalshi market odds.
 
Match Data:
- Current Tournament Stage: {stage}
- Blended Probabilities: {probs}
- Progression/To-Qualify Probabilities: {progression_probs}
- ELO Difference: {elo_diff:+.1f} pts
- Expected Corner Kicks: {corners_expectation}
- News Sentiment: {sentiment:+.2f}
- Key News Flags: {news_flags}
- Live/Target Bets Options (Odds/Margins): {target_bets}
{prev_bet_prompt}
 
Generate a short, punchy, realistic dialogue debate where they analyze the game and try to align on a consensus recommendation. Refer to their current bankroll status or recent bet performance if relevant (e.g. if they are on a winning/losing streak).
 
Format your output exactly with these headers:
[Big D's Take]
<his paragraphs>
 
[SIGMABALLS' Take]
<his paragraphs>
 
[Consensus Bet]
<what bet they recommend placing (from the target list) and how they size it>
 
Additionally, on its own lines at the very end of your response, output a structured JSON block representing the personal paper bets they choose to place from the target list for this game. They must select a bet category/description from the options provided, select a stake (up to 10% of their bankroll), and extract the corresponding odds/multiplier.
 
Example format:
[Personal Bets JSON]
{{
  "big_d": {{
    "bet_type": "Moneyline - England Win",
    "stake": 50.0,
    "odds": 1.38
  }},
  "sigmaballs": {{
    "bet_type": "Game Lines - Over 2.5 Goals",
    "stake": 30.0,
    "odds": 1.74
  }}
}}
"""
 
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = response.text
        
        # Parse output
        parts = {"big_d": "", "sigmaballs": "", "consensus": "", "personal_bets": None}
        
        if "[Big D's Take]" in text and "[SIGMABALLS' Take]" in text and "[Consensus Bet]" in text:
            big_d_part = text.split("[Big D's Take]")[1].split("[SIGMABALLS' Take]")[0].strip()
            sigma_part = text.split("[SIGMABALLS' Take]")[1].split("[Consensus Bet]")[0].strip()
            
            # Check if JSON is also at the end
            if "[Personal Bets JSON]" in text:
                consensus_part = text.split("[Consensus Bet]")[1].split("[Personal Bets JSON]")[0].strip()
                json_str = text.split("[Personal Bets JSON]")[1].strip()
                
                try:
                    # Find the first '{' and last '}' to extract valid JSON robustly
                    start_idx = json_str.find("{")
                    end_idx = json_str.rfind("}")
                    if start_idx != -1 and end_idx != -1:
                        json_clean = json_str[start_idx:end_idx+1]
                        parts["personal_bets"] = json.loads(json_clean)
                    else:
                        parts["personal_bets"] = json.loads(json_str)
                except Exception:
                    pass
            else:
                consensus_part = text.split("[Consensus Bet]")[1].strip()
                
            parts["big_d"] = big_d_part
            parts["sigmaballs"] = sigma_part
            parts["consensus"] = consensus_part
            return parts
        else:
            # Simple splitter fallback
            return {
                "big_d": text[:len(text)//3],
                "sigmaballs": text[len(text)//3: 2*len(text)//3],
                "consensus": text[2*len(text)//3:],
                "personal_bets": None
            }
    except Exception as e:
        raise RuntimeError(f"Error calling Gemini API: {e}. Enforced: Mock fallback debates are disabled to prevent nonsensical data.")
 
 
def _get_fallback_debate(home: str, away: str, probs: dict, elo_diff: float, sentiment: float, d_summary: dict, s_summary: dict) -> dict:
    """
    Fallback mock dialogue if Gemini is not configured/errored.
    """
    h_title = home.title()
    a_title = away.title()
    stage = get_tournament_stage()
    is_knockout = "Knockout" in stage
    
    # Simple logic-based mock debate
    if elo_diff > 100:
        big_d = (
            f"Look, I've watched {h_title} play a thousand times. They've got the historical pedigree and "
            f"they are clearly the better squad here. ELO difference is {elo_diff:.0f} points? I don't need your ELO. "
            f"My eyes tell me they are going to control the tempo from the whistle. {a_title} doesn't have the size "
            f"to deal with them. Hammer {h_title} win. Don't overcomplicate it. My bankroll is at ${d_summary['bankroll']:.2f} "
            f"and I'm ready to size this up!"
        )
        sigma = (
            f"Statistically, {h_title} is favored at {probs.get('home_win', 0.5)*100:.1f}%. However, the market "
            f"has already priced this in. Our Dixon-Coles goal expectation shows {a_title} +1.5 has an implied probability "
            f"that is undervalued. I trust the mathematics. With my bankroll at ${s_summary['bankroll']:.2f}, "
            f"I'm placing a calculated bet on the handicap."
        )
        consensus = f"Buy YES on {h_title} Over 1.5 Goals or {h_title} Win if the contract is under ${probs.get('home_win', 0.5):.2f}."
        personal_bets = {
            "big_d": {
                "bet_type": f"Moneyline - {h_title} Win",
                "stake": round(d_summary["bankroll"] * 0.1, 2),
                "odds": 1.45
            },
            "sigmaballs": {
                "bet_type": "Game Lines - Over 1.5 Goals",
                "stake": round(s_summary["bankroll"] * 0.05, 2),
                "odds": 1.55
            }
        }
    else:
        stage_desc = "Nobody wants to risk elimination in the knockouts." if is_knockout else "Nobody wants to lose the group stages."
        big_d = (
            f"This is a classic trap match. {h_title} and {a_title} are too close in form. "
            f"I see both teams playing safe, keeping it compact in the first half. It's going to be a slugfest. "
            f"I smell a Draw all over this. {stage_desc} Let's place a gut bet on the Draw!"
        )
        sigma = (
            f"The model agrees the Draw probability is elevated at {probs.get('draw', 0.3)*100:.1f}%. "
            f"Dixon-Coles score expectations point to a high frequency of 1-1. The math matches your intuition "
            f"for once, D. The edge on the Draw Yes contract is positive. I will allocate capital accordingly."
        )
        consensus = f"Buy YES on the Draw contract or BTTS (Both Teams to Score)."
        personal_bets = {
            "big_d": {
                "bet_type": "Moneyline - Draw",
                "stake": round(d_summary["bankroll"] * 0.08, 2),
                "odds": 3.10
            },
            "sigmaballs": {
                "bet_type": "Game Lines - Both Teams to Score",
                "stake": round(s_summary["bankroll"] * 0.04, 2),
                "odds": 1.85
            }
        }
 
    return {
        "big_d": big_d,
        "sigmaballs": sigma,
        "consensus": consensus,
        "personal_bets": personal_bets
    }
