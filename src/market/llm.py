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


def get_tournament_stage(league: str = "epl") -> str:
    l_lower = (league or "epl").lower().strip()
    if l_lower == "ucl":
        return "UEFA Champions League (European Elite Competition — Mid-week fixture congestion, cross-league clash)."
    elif l_lower == "laliga":
        return "La Liga Matchday (Spanish Top Flight — Tactical possession, derby rivalries & technical football)."
    return "Premier League Matchday (English Top Flight — High pace, physical intensity & heavy fixture schedule)."


def generate_debate(home: str, away: str, probs: dict, elo_diff: float, sentiment: float, news_flags: list, target_bets: list, user_model: str = None, progression_probs: dict = None, corners_expectation: dict = None, home_bullets: str = "", away_bullets: str = "") -> dict:
    """
    Calls Gemini API to generate a debate between Magnus and Athena.
    Injects their bankroll stats and performance history, and parses their chosen personal bets.
    Falls back to a simulated script if API is unavailable.
    """
    from src.market import paper_trading
    
    # 1. Fetch current bankrolls and record history for prompt injection
    d_sum = paper_trading.get_personality_summary("ask", "magnus")
    s_sum = paper_trading.get_personality_summary("ask", "athena")
    
    d_str = f"Bankroll: ${d_sum['bankroll']:.2f}, P&L: ${d_sum['total_pnl']:+.2f}, Win Rate: {d_sum['win_rate']}% ({d_sum['total_bets']} bets)"
    s_str = f"Bankroll: ${s_sum['bankroll']:.2f}, P&L: ${s_sum['total_pnl']:+.2f}, Win Rate: {s_sum['win_rate']}% ({s_sum['total_bets']} bets)"

    # Look for active/previous bets on this specific match
    d_active = next((b for b in d_sum["active_bets"] if b.get("home") == home.lower().strip() and b.get("away") == away.lower().strip()), None)
    s_active = next((b for b in s_sum["active_bets"] if b.get("home") == home.lower().strip() and b.get("away") == away.lower().strip()), None)
    
    prev_bet_prompt = ""
    if d_active or s_active:
        prev_bet_prompt = "\nActive/Previous bets already placed on this match:\n"
        if d_active:
            prev_bet_prompt += f"- Magnus's current active bet: {d_active['bet_type']} | Stake: ${d_active['stake']:.2f} | Odds: {d_active['odds']:.2f}x\n"
        if s_active:
            prev_bet_prompt += f"- Athena's current active bet: {s_active['bet_type']} | Stake: ${s_active['stake']:.2f} | Odds: {s_active['odds']:.2f}x\n"
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
1. **Magnus (The Eye-Test Scout)**:
   - Personality: A grizzled, old-school veteran football scout. Doesn't know what a CSV file is and doesn't want to. He has watched 10,000 matches.
   - Current Bankroll & Performance: {d_str}
   - Analysis: He only cares about four things: ranking, form, who they played, and who's healthy. He asks: "Is the better team actually showing up today?" 
   - Style: Direct, opinionated, speaks in scout jargon, quotes historical matches he's seen. He never talks about "expected value" or "vig." He just tells you who is going to win and if they are going to play lazy.
   
2. **Athena (The Quant)**:
   - Personality: A brilliant, cold-blooded machine learning engineer. Her favorite player is Pascal Gross. Never impressed by a 35-yard screamer.
   - Current Bankroll & Performance: {s_str}
   - Analysis: She only trusts data: ELO ratings, Dixon-Coles Poisson goals, and the machine learning model ensemble. 
   - Style: Highly logical, quotes percentages and edges. She only bets when the model shows a positive edge against Kalshi market odds.
 
Match Data:
- Current Tournament Stage: {stage}
- Blended Probabilities: {probs}
- Progression/To-Qualify Probabilities: {progression_probs}
- ELO Difference: {elo_diff:+.1f} pts
- Expected Corner Kicks: {corners_expectation}
- News Sentiment: {sentiment:+.2f}
- Key News Flags: {news_flags}
- {home.title()} Recent News Updates:
{home_bullets or "No recent news updates."}
- {away.title()} Recent News Updates:
{away_bullets or "No recent news updates."}
- Live/Target Bets Options (Odds/Margins): {target_bets}
{prev_bet_prompt}
 
Generate a short, punchy, realistic dialogue debate where they analyze the game and try to align on a consensus recommendation. Refer to their current bankroll status or recent bet performance if relevant (e.g. if they are on a winning/losing streak).
 
Format your output exactly with these headers:
[Magnus's Take]
<his paragraphs>
 
[Athena's Take]
<her paragraphs>
 
[Consensus Bet]
<what bet they recommend placing (from the target list) and how they size it>
 
Additionally, on its own lines at the very end of your response, output a structured JSON block representing the personal paper bets they choose to place from the target list for this game. They must select a bet category/description from the options provided, select a stake (up to 10% of their bankroll), and extract the corresponding odds/multiplier.
 
Example format:
[Personal Bets JSON]
{{
  "magnus": {{
    "bet_type": "Moneyline - England Win",
    "stake": 50.0,
    "odds": 1.38
  }},
  "athena": {{
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
        parts = {"magnus": "", "athena": "", "consensus": "", "personal_bets": None}
        
        if "[Magnus's Take]" in text and "[Athena's Take]" in text and "[Consensus Bet]" in text:
            magnus_part = text.split("[Magnus's Take]")[1].split("[Athena's Take]")[0].strip()
            athena_part = text.split("[Athena's Take]")[1].split("[Consensus Bet]")[0].strip()
            
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
                
            parts["magnus"] = magnus_part
            parts["athena"] = athena_part
            parts["consensus"] = consensus_part
            return parts
        else:
            # Simple splitter fallback
            return {
                "magnus": text[:len(text)//3],
                "athena": text[len(text)//3: 2*len(text)//3],
                "consensus": text[2*len(text)//3:],
                "personal_bets": None
            }
    except Exception as e:
        raise RuntimeError(f"Error calling Gemini API: {e}. Enforced: Mock fallback debates are disabled to prevent nonsensical data.")
 
 
# _get_fallback_debate() was removed here. It fabricated a debate with invented
# odds (1.45 / 1.55 / 3.10) untied to any market, and returned personal_bets that
# downstream code would have staked real bankroll against. It was already dead
# code, and under the 2026/27 design the LLM layer is commentary only: it never
# selects or sizes a bet. See docs/superpowers/specs/2026-08-01-season-rebuild-design.md


def search_web(query: str) -> dict:
    """
    Search the web for news updates. Queries Google News RSS as a robust source.
    """
    try:
        import requests
        import xml.etree.ElementTree as ET
        query_encoded = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query_encoded}&hl=en-US&gl=US&ceid=US:en"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return {"summary": "", "citations": []}
        
        root = ET.fromstring(resp.content)
        titles = []
        links = []
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text if title_el is not None else ""
            link = link_el.text if link_el is not None else ""
            if title:
                # Strip source/publication name often present at the end, e.g. "- ESPN"
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                titles.append(title)
            if link:
                links.append(link)
            if len(titles) >= 5:
                break
        
        summary = "\n".join([f"- {t}" for t in titles])
        return {"summary": summary, "citations": links[:5]}
    except Exception:
        return {"summary": "", "citations": []}


def fetch_team_news_bullets(team_name: str) -> str:
    """
    Fetches news bullets for a team query using search_web wrapper.
    """
    try:
        res = search_web(query=f"{team_name} national football team roster injuries 2026")
        summary = res.get("summary", "")
        if not summary:
            return f"No recent updates found for {team_name}."
        return summary
    except Exception:
        return f"Unable to fetch news for {team_name}."


def run_news_debate(home: str, away: str, probs: dict, elo_diff: float, sentiment: float, news_flags: list, target_bets: list, user_model: str = None, progression_probs: dict = None, corners_expectation: dict = None) -> dict:
    """
    Runs a news-enhanced debate: fetches news bullets for both teams,
    injects them into generate_debate, and caches the debate result to JSON.
    """
    home_bullets = fetch_team_news_bullets(home)
    away_bullets = fetch_team_news_bullets(away)
    
    debate = generate_debate(
        home=home,
        away=away,
        probs=probs,
        elo_diff=elo_diff,
        sentiment=sentiment,
        news_flags=news_flags,
        target_bets=target_bets,
        user_model=user_model,
        progression_probs=progression_probs,
        corners_expectation=corners_expectation,
        home_bullets=home_bullets,
        away_bullets=away_bullets
    )
    
    # Save the debate to data/processed/debates/YYYY-MM-DD-<home>-vs-<away>.json
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Ensure directory exists
    os.makedirs(os.path.join("data", "processed", "debates"), exist_ok=True)
    
    # Clean filenames
    home_clean = home.lower().strip().replace(" ", "_")
    away_clean = away.lower().strip().replace(" ", "_")
    filename = f"{date_str}-{home_clean}-vs-{away_clean}.json"
    filepath = os.path.join("data", "processed", "debates", filename)
    
    save_data = {
        "home": home,
        "away": away,
        "date": date_str,
        "probabilities": probs,
        "elo_diff": elo_diff,
        "sentiment": sentiment,
        "news_flags": news_flags,
        "home_news_bullets": home_bullets,
        "away_news_bullets": away_bullets,
        "debate": debate
    }
    
    try:
        with open(filepath, "w") as f:
            json.dump(save_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save debate JSON to {filepath}: {e}")
        
    return debate


