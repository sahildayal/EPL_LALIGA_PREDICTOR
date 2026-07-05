import os
import time
import requests
import base64
import re
from dotenv import load_dotenv

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

load_dotenv()

# Base without /trade-api/v2 so signature paths align
KALSHI_BASE_URL = "https://api.elections.kalshi.com"


class KalshiClient:
    """
    Authenticated Kalshi V2 API client using RSA key signature.
    """

    def __init__(self):
        self.key_id = os.getenv("KALSHI_API_KEY_ID")
        self.private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        self.private_key = None
        self.mock_mode = False

        if not CRYPTOGRAPHY_AVAILABLE:
            print("Warning: 'cryptography' library not installed. Switch to Demo/Mock mode.")
            self.mock_mode = True
        elif not self.key_id or not self.private_key_path:
            print("Warning: Kalshi RSA Key credentials not found in .env. Switch to Demo/Mock mode.")
            self.mock_mode = True
        else:
            self._load_private_key()

    def _load_private_key(self):
        try:
            with open(self.private_key_path, "rb") as key_file:
                self.private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None
                )
            print("Successfully loaded Kalshi RSA Private Key.")
        except Exception as e:
            print(f"Error loading private key: {e}. Switching to Demo/Mock mode.")
            self.mock_mode = True

    def _sign_request(self, timestamp: str, method: str, path: str) -> str:
        """
        Generates RSA-PSS SHA256 signature for Kalshi V2 authentication.
        """
        # Strip query parameters if present
        clean_path = path.split("?")[0]
        message = f"{timestamp}{method}{clean_path}".encode("utf-8")
        
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode("utf-8")

    def _request(self, method: str, api_path: str, params: dict = None, json_data: dict = None) -> requests.Response:
        """
        Runs signed request to Kalshi API.
        """
        url = f"{KALSHI_BASE_URL}{api_path}"
        
        if self.mock_mode:
            # Simulated requests
            raise ConnectionError("Running in mock mode")

        timestamp = str(int(time.time() * 1000))
        signature = self._sign_request(timestamp, method, api_path)
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "WorldCupPredictor/1.0",
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp
        }

        if method == "GET":
            return requests.get(url, headers=headers, params=params, timeout=12)
        elif method == "POST":
            return requests.post(url, headers=headers, json=json_data, timeout=12)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    def get_balance(self) -> float:
        """
        Returns cash balance in USD.
        """
        if self.mock_mode:
            return 1450.75

        path = "/trade-api/v2/portfolio/balance"
        try:
            resp = self._request("GET", path)
            if resp.status_code == 200:
                # Balance is returned in cents
                cents = resp.json().get("balance", 0)
                return cents / 100.0
            else:
                print(f"Kalshi request failed (Status: {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Kalshi request error: {e}")
        return 1450.75

    def get_closed_positions(self) -> list:
        """
        Returns completed fills/trades history.
        """
        if self.mock_mode:
            return [
                {
                    "id": "t-8fa2",
                    "match": "Argentina vs France",
                    "outcome": "Argentina Win",
                    "contracts": 120,
                    "price_paid": 0.58,
                    "result": "WIN",
                    "pnl": 50.40,
                    "date": "2026-06-21"
                }
            ]

        path = "/trade-api/v2/portfolio/settlements"
        try:
            resp = self._request("GET", path, params={"limit": 50})
            if resp.status_code == 200:
                settlements = resp.json().get("settlements", [])
                parsed_settlements = []
                for s in settlements:
                    ticker = s.get("ticker", "")
                    
                    yes_count = float(s.get("yes_count_fp", 0.0) or 0.0)
                    no_count = float(s.get("no_count_fp", 0.0) or 0.0)
                    
                    if yes_count > 0:
                        contracts = yes_count
                        cost = float(s.get("yes_total_cost_dollars", 0.0) or 0.0)
                        side = "Yes"
                    else:
                        contracts = no_count
                        cost = float(s.get("no_total_cost_dollars", 0.0) or 0.0)
                        side = "No"
                        
                    revenue = float(s.get("revenue", 0) or 0) / 100.0
                    pnl = revenue - cost
                    price_paid = cost / contracts if contracts > 0 else 0.0
                    result = "WIN" if pnl > 0.001 else "LOSS"
                    
                    # Generate a clean short trade ID
                    trade_id = s.get("ticker", "")[-8:]
                    
                    parsed_settlements.append({
                        "id": trade_id,
                        "match": ticker,
                        "outcome": side,
                        "contracts": int(contracts),
                        "price_paid": round(price_paid, 2),
                        "result": result,
                        "pnl": round(pnl, 2),
                        "date": s.get("settled_time", "")[:10]
                    })
                return parsed_settlements
            else:
                print(f"Kalshi request failed (Status: {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Kalshi request error: {e}")
        return []

    def get_soccer_markets(self) -> list:
        """
        Fetches open soccer markets (using public API, doesn't require signature).
        Queries trade-api/v2/markets directly for sports tickers to bypass event exclusions.
        """
        if self.mock_mode:
            # Return realistic mock soccer events immediately to prevent network timeouts/delays
            return [
                {
                    "event_title": "Portugal vs France",
                    "subtitle": None,
                    "category": "Sports",
                    "occurrence_time": "2026-06-27T18:00:00Z",
                    "markets": [
                        {"ticker": "KXWCGAME-26JUN27-POR-FRA-YES", "title": "Portugal Win", "yes_price": 0.33, "no_price": 0.67, "status": "open"},
                        {"ticker": "KXWCGAME-26JUN27-POR-FRA-NO", "title": "France Win", "yes_price": 0.34, "no_price": 0.66, "status": "open"},
                        {"ticker": "KXWCGAME-26JUN27-POR-FRA-DRAW", "title": "Draw", "yes_price": 0.33, "no_price": 0.67, "status": "open"},
                        {"ticker": "KXWCBTTS-26JUN27-POR-FRA", "title": "Both Teams to Score", "yes_price": 0.60, "no_price": 0.40, "status": "open"},
                        {"ticker": "KXWCTOTAL-26JUN27-POR-FRA-O1.5", "title": "Over 1.5 Goals", "yes_price": 0.80, "no_price": 0.20, "status": "open"},
                        {"ticker": "KXWCTOTAL-26JUN27-POR-FRA-O2.5", "title": "Over 2.5 Goals", "yes_price": 0.50, "no_price": 0.50, "status": "open"},
                        {"ticker": "KXWCGOAL-26JUN27-POR-FRA-CR7-1", "title": "Cristiano Ronaldo: 1+ goals?", "yes_price": 0.40, "no_price": 0.60, "status": "open"},
                        {"ticker": "KXWCGOAL-26JUN27-POR-FRA-CR7-2", "title": "Cristiano Ronaldo: 2+ goals?", "yes_price": 0.15, "no_price": 0.85, "status": "open"},
                        {"ticker": "KXWCAST-26JUN27-POR-FRA-CR7-1", "title": "Cristiano Ronaldo: 1+ assists?", "yes_price": 0.25, "no_price": 0.75, "status": "open"},
                        {"ticker": "KXWCAST-26JUN27-POR-FRA-CR7-2", "title": "Cristiano Ronaldo: 2+ assists?", "yes_price": 0.05, "no_price": 0.95, "status": "open"},
                        {"ticker": "KXWCSOA-26JUN27-POR-FRA-CR7-1", "title": "Cristiano Ronaldo: score or assist?", "yes_price": 0.55, "no_price": 0.45, "status": "open"},
                    ]
                },
                {
                    "event_title": "South Africa vs Canada",
                    "subtitle": None,
                    "category": "Sports",
                    "occurrence_time": "2026-06-27T20:00:00Z",
                    "markets": [
                        {"ticker": "KXWCGAME-26JUN27-RSA-CAN-YES", "title": "South Africa Win", "yes_price": 0.18, "no_price": 0.82, "status": "open"},
                        {"ticker": "KXWCGAME-26JUN27-RSA-CAN-NO", "title": "Canada Win", "yes_price": 0.60, "no_price": 0.40, "status": "open"},
                        {"ticker": "KXWCGAME-26JUN27-RSA-CAN-DRAW", "title": "Draw", "yes_price": 0.22, "no_price": 0.78, "status": "open"},
                        {"ticker": "KXWCBTTS-26JUN27-RSA-CAN", "title": "Both Teams to Score", "yes_price": 0.55, "no_price": 0.45, "status": "open"},
                        {"ticker": "KXWCTOTAL-26JUN27-RSA-CAN-O1.5", "title": "Over 1.5 Goals", "yes_price": 0.78, "no_price": 0.22, "status": "open"},
                        {"ticker": "KXWCTOTAL-26JUN27-RSA-CAN-O2.5", "title": "Over 2.5 Goals", "yes_price": 0.45, "no_price": 0.55, "status": "open"},
                    ]
                }
            ]

        series_tickers = ["KXWCGAME", "KXWCBTTS", "KXWCTOTAL", "KXWCGOAL", "KXWCAST", "KXWCSOA", "KXWCQUAL", "KXWCTCORNERS"]
        raw_markets = []
        for ticker in series_tickers:
            url = f"{KALSHI_BASE_URL}/trade-api/v2/markets"
            params = {"series_ticker": ticker, "status": "open", "limit": 100}
            try:
                resp = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=10)
                if resp.status_code == 200:
                    markets = resp.json().get("markets", [])
                    raw_markets.extend(markets)
            except Exception as e:
                pass

        # Helper to extract full team names from title or rules_primary
        def extract_match_teams(mkt):
            title = mkt.get("title", "")
            if " vs " in title:
                title_clean = title.replace(" Winner?", "").replace("?", "").strip()
                if " vs " in title_clean:
                    return title_clean

            rules = mkt.get("rules_primary", "")
            if " vs " in rules:
                match = re.search(r'([\w\s]+)\s+vs\s+([\w\s]+?)(?=\s+(?:professional|FIFA|soccer|game|match|originally))', rules)
                if match:
                    home = match.group(1).strip()
                    if " in the " in home:
                        home = home.split(" in the ")[-1].strip()
                    elif " in " in home:
                        home = home.split(" in ")[-1].strip()
                    away = match.group(2).strip()
                    return f"{home} vs {away}"
            return None

        # Group by match key (suffix of event_ticker after the first dash)
        groups = {}
        for mkt in raw_markets:
            event_ticker = mkt.get("event_ticker", "")
            if not event_ticker or "-" not in event_ticker:
                continue
            suffix = event_ticker.split("-", 1)[1]
            groups.setdefault(suffix, []).append(mkt)

        soccer_events = []
        for suffix, mkts in groups.items():
            event_title = None
            occurrence_time = None
            for mkt in mkts:
                if not event_title:
                    event_title = extract_match_teams(mkt)
                if not occurrence_time:
                    occurrence_time = mkt.get("occurrence_datetime")
                if event_title and occurrence_time:
                    break
            
            if not occurrence_time and mkts:
                occurrence_time = mkts[0].get("occurrence_datetime")

            if not event_title:
                match = re.search(r'\d{2}[A-Z]{3}\d{2}([A-Z]{3})([A-Z]{3})', suffix)
                if match:
                    event_title = f"{match.group(1)} vs {match.group(2)}"
                else:
                    event_title = suffix

            parsed_markets = []
            for mkt in mkts:
                ticker = mkt.get("ticker", "")
                if "KXWCGAME" in ticker:
                    subtitle = mkt.get("yes_sub_title", mkt.get("title", ""))
                else:
                    subtitle = mkt.get("title", "")

                yes_price = float(mkt.get("yes_ask_dollars") or 0.0)
                no_price = float(mkt.get("no_ask_dollars") or 0.0)
                if no_price == 0.0:
                    no_price = 1.0 - yes_price

                parsed_markets.append({
                    "ticker": mkt.get("ticker"),
                    "title": subtitle,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "status": mkt.get("status")
                })

            soccer_events.append({
                "event_title": event_title,
                "subtitle": None,
                "category": "Sports",
                "markets": parsed_markets,
                "occurrence_time": occurrence_time
            })

        # Sort events by occurrence_time (earliest first)
        soccer_events.sort(key=lambda x: x.get("occurrence_time") or "9999-12-31")
        return soccer_events
