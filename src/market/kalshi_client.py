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


class KalshiUnavailable(RuntimeError):
    """
    Raised when Kalshi data cannot be retrieved.

    Never substitute fabricated prices, balances or fills. A pipeline that
    silently prices bets off invented markets produces a season of results that
    look real and mean nothing.
    """


class KalshiClient:
    """
    Authenticated Kalshi V2 API client using RSA key signature.
    """

    def __init__(self):
        self.key_id = os.getenv("KALSHI_API_KEY_ID")
        self.private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        # CI has no filesystem to put a key on, and writing one to disk in a
        # runner leaves it in the workspace for anything else in the job to read.
        # Supplying the PEM directly keeps the private key in process memory only.
        self.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY_PEM")
        self.private_key = None
        self.credentials_missing = False
        self.credential_source = None

        if not CRYPTOGRAPHY_AVAILABLE:
            print("Warning: 'cryptography' not installed. Kalshi calls will raise.")
            self.credentials_missing = True
        elif not self.key_id:
            print("Warning: KALSHI_API_KEY_ID not set. Kalshi calls will raise.")
            self.credentials_missing = True
        elif not (self.private_key_pem or self.private_key_path):
            print("Warning: no Kalshi private key (KALSHI_PRIVATE_KEY_PEM or "
                  "KALSHI_PRIVATE_KEY_PATH). Kalshi calls will raise.")
            self.credentials_missing = True
        else:
            self._load_private_key()

    def _load_private_key(self):
        """
        Loads the RSA key from the PEM env var if present, else from a file.

        The env var wins so a CI secret cannot be silently overridden by a stale
        key path inherited from a local .env.
        """
        try:
            if self.private_key_pem:
                # GitHub secrets round-trip newlines inconsistently depending on
                # how the secret was pasted; normalise escaped newlines so a
                # correct key is not rejected as malformed PEM.
                pem = self.private_key_pem.replace("\\n", "\n").strip().encode("utf-8")
                self.private_key = serialization.load_pem_private_key(pem, password=None)
                self.credential_source = "KALSHI_PRIVATE_KEY_PEM"
            else:
                with open(self.private_key_path, "rb") as key_file:
                    self.private_key = serialization.load_pem_private_key(
                        key_file.read(), password=None)
                self.credential_source = "KALSHI_PRIVATE_KEY_PATH"
            print(f"Loaded Kalshi RSA private key from {self.credential_source}.")
        except Exception as e:
            # Never echo the exception's payload — a PEM parse failure can quote
            # key material back into the log, and CI logs are retained.
            print(f"Error loading Kalshi private key ({type(e).__name__}). "
                  "Kalshi calls will raise.")
            self.credentials_missing = True

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
        
        if self.credentials_missing:
            raise KalshiUnavailable(
                "No Kalshi credentials loaded; refusing to return data. "
                "Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PEM (or _PATH).")

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
        Returns real Kalshi cash balance in USD.

        Raises KalshiUnavailable rather than returning a number we made up. The
        previous implementation returned a hardcoded 1450.75 when credentials
        were absent and on *any* API error, so an outage silently reported fake money as a
        real balance.

        Note: the season experiment runs entirely on the simulated bankrolls in
        src/market/ledger.py. This method only reads the real account and is not
        part of the betting loop.
        """
        if self.credentials_missing:
            raise KalshiUnavailable(
                "No Kalshi credentials loaded; no real balance available."
            )

        path = "/trade-api/v2/portfolio/balance"
        try:
            resp = self._request("GET", path)
        except Exception as e:
            raise KalshiUnavailable(f"Kalshi balance request errored: {e}") from e

        if resp.status_code != 200:
            raise KalshiUnavailable(
                f"Kalshi balance request failed (status {resp.status_code}): {resp.text}"
            )
        # Balance is returned in cents
        return resp.json().get("balance", 0) / 100.0

    def get_closed_positions(self) -> list:
        """
        Returns completed fills/trades history.
        """
        if self.credentials_missing:
            raise KalshiUnavailable(
                "No Kalshi credentials loaded; no real fills available."
            )

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
        if self.credentials_missing:
            # This previously returned invented Arsenal-Chelsea and Real-Barca
            # markets with invented prices. Downstream code cannot tell a
            # fabricated price from a real one, so it priced and placed bets
            # against fiction.
            raise KalshiUnavailable(
                "No Kalshi credentials loaded; no live market prices available."
            )

        series_tickers = [
            "KXEPLGAME", "KXEPLTOTAL", "KXEPLBTTS", "KXEPLGOAL", "KXEPLCORNERS",
            "KXLALIGAGAME", "KXLALIGATOTAL", "KXLALIGABTTS", "KXLALIGAGOAL",
            "KXUCLGAME", "KXUCLTOTAL", "KXUCLBTTS", "KXUCLQUAL",
            "KXWCGAME", "KXWCBTTS", "KXWCTOTAL", "KXWCGOAL", "KXWCAST", "KXWCSOA", "KXWCQUAL", "KXWCTCORNERS"
        ]
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
