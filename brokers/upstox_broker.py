"""
Upstox API v2 — OAuth authentication + order placement.

Setup steps (one-time):
  1. Go to https://developer.upstox.com → Create App
  2. Set redirect URI to http://127.0.0.1:8080/callback
  3. Add UPSTOX_API_KEY and UPSTOX_API_SECRET to your .env file
  4. Run: python -m brokers.upstox_broker --login
     This opens a browser, you log in, and the access token is saved to .env
"""
import os
import json
import webbrowser
import threading
import urllib.parse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import config

_TOKEN_FILE = Path(__file__).parent.parent / ".upstox_token.json"

_SANDBOX = os.getenv("UPSTOX_SANDBOX", "true").lower() != "false"

UPSTOX_BASE = (
    "https://api-sandbox.upstox.com/v2" if _SANDBOX
    else "https://api.upstox.com/v2"
)
AUTH_URL = (
    "https://api-sandbox.upstox.com/v2/login/authorization/dialog" if _SANDBOX
    else "https://api.upstox.com/v2/login/authorization/dialog"
)
TOKEN_URL = (
    "https://api-sandbox.upstox.com/v2/login/authorization/token" if _SANDBOX
    else "https://api.upstox.com/v2/login/authorization/token"
)

_MODE = "SANDBOX" if _SANDBOX else "LIVE"


# ── OAuth Login Flow ──────────────────────────────────────────────────────────

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;text-align:center;padding:60px">
                <h2>&#10003; Login successful!</h2>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing auth code")

    def log_message(self, format, *args):
        pass  # silence HTTP logs


def login() -> str:
    """
    Full OAuth2 login flow.
    Opens browser → user logs in → catches redirect → exchanges code for token.
    Returns access_token string.
    """
    if not config.UPSTOX_API_KEY or not config.UPSTOX_API_SECRET:
        raise RuntimeError(
            "UPSTOX_API_KEY and UPSTOX_API_SECRET must be set in .env\n"
            "Get them from: https://developer.upstox.com"
        )

    global _auth_code
    _auth_code = None

    # Start local callback server
    server = HTTPServer(("127.0.0.1", 8080), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    # Build auth URL and open browser
    params = {
        "response_type": "code",
        "client_id": config.UPSTOX_API_KEY,
        "redirect_uri": config.UPSTOX_REDIRECT_URI,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print(f"\n[upstox] Mode: {_MODE}")
    print(f"[upstox] Opening browser for login...")
    print(f"[upstox] If browser doesn't open, visit:\n  {url}\n")
    webbrowser.open(url)

    thread.join(timeout=120)
    server.server_close()

    if not _auth_code:
        raise RuntimeError("Login timed out — no auth code received within 2 minutes.")

    # Exchange code for access token
    resp = requests.post(TOKEN_URL, data={
        "code":          _auth_code,
        "client_id":     config.UPSTOX_API_KEY,
        "client_secret": config.UPSTOX_API_SECRET,
        "redirect_uri":  config.UPSTOX_REDIRECT_URI,
        "grant_type":    "authorization_code",
    }, headers={"accept": "application/json"})
    resp.raise_for_status()

    token_data = resp.json()
    access_token = token_data["access_token"]

    # Save token to file
    _TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    print(f"[upstox] Access token saved to {_TOKEN_FILE}")
    print(f"\n[upstox] Add this to your .env file:")
    print(f"  UPSTOX_ACCESS_TOKEN={access_token}\n")

    return access_token


def get_access_token() -> str:
    """Returns access token from env or saved token file."""
    if config.UPSTOX_ACCESS_TOKEN:
        return config.UPSTOX_ACCESS_TOKEN
    if _TOKEN_FILE.exists():
        data = json.loads(_TOKEN_FILE.read_text())
        return data.get("access_token", "")
    return ""


def _headers() -> dict:
    token = get_access_token()
    if not token:
        raise RuntimeError(
            "No Upstox access token found.\n"
            "Run: python -m brokers.upstox_broker --login"
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ── Instrument Master ────────────────────────────────────────────────────────

_instrument_cache: dict[str, str] = {}   # symbol → instrument_key
_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"


def _load_instruments() -> dict[str, str]:
    """
    Downloads Upstox NSE instruments master (no auth needed) and builds
    a symbol → instrument_key lookup. Cached in memory for the session.
    """
    global _instrument_cache
    if _instrument_cache:
        return _instrument_cache

    import gzip, io
    print("[upstox] Downloading NSE instruments master...")
    resp = requests.get(_INSTRUMENTS_URL, timeout=30)
    resp.raise_for_status()

    instruments = json.loads(gzip.decompress(resp.content))
    lookup: dict[str, str] = {}
    for item in instruments:
        segment = item.get("segment", "")
        symbol  = item.get("trading_symbol", "") or item.get("tradingsymbol", "")
        key     = item.get("instrument_key", "")
        itype   = item.get("instrument_type", "") or item.get("instrumenttype", "")
        # Only NSE equity (not F&O, not SME)
        if segment == "NSE_EQ" and symbol and key:
            lookup[symbol.upper()] = key
        # Also handle EQ suffix variants
        if symbol.endswith("-EQ") and key:
            lookup[symbol.replace("-EQ", "").upper()] = key

    _instrument_cache = lookup
    print(f"[upstox] Loaded {len(lookup)} NSE equity instruments")
    return lookup


# ── Market Data ───────────────────────────────────────────────────────────────

def get_instrument_key(trading_symbol: str) -> str | None:
    """
    Converts NSE trading symbol (e.g. 'EICHERMOT') to Upstox instrument key
    (e.g. 'NSE_EQ|INE066A01021').
    Uses Upstox instruments master file (no auth needed, cached per run).
    """
    sym = trading_symbol.replace(".NS", "").upper()
    instruments = _load_instruments()
    key = instruments.get(sym)
    if not key:
        # Try common suffix variants
        for variant in [f"{sym}-EQ", sym.replace("&", "AND")]:
            key = instruments.get(variant)
            if key:
                break
    return key


def get_ltp(instrument_key: str) -> float | None:
    """Returns Last Traded Price for an instrument key."""
    url = f"{UPSTOX_BASE}/market-quote/ltp"
    resp = requests.get(url, params={"instrument_key": instrument_key}, headers=_headers())
    if resp.status_code != 200:
        return None
    data = resp.json().get("data", {})
    if data:
        first = next(iter(data.values()))
        return first.get("last_price")
    return None


# ── Order Placement ───────────────────────────────────────────────────────────

def place_market_buy(
    trading_symbol: str,
    quantity: int,
    instrument_key: str,
) -> dict:
    """
    Places a market buy order on NSE via Upstox API v2.
    Returns order response dict.
    """
    url = f"{UPSTOX_BASE}/order/place"
    payload = {
        "quantity":       quantity,
        "product":        "D",          # D = Delivery (CNC for long-term holding)
        "validity":       "DAY",
        "price":          0,            # 0 = market order
        "tag":            "algo_halal",
        "instrument_token": instrument_key,
        "order_type":     "MARKET",
        "transaction_type": "BUY",
        "disclosed_quantity": 0,
        "trigger_price":  0,
        "is_amo":         False,
    }
    resp = requests.post(url, json=payload, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def place_market_sell(
    trading_symbol: str,
    quantity: int,
    instrument_key: str,
) -> dict:
    """Places a market sell order."""
    url = f"{UPSTOX_BASE}/order/place"
    payload = {
        "quantity":       quantity,
        "product":        "D",
        "validity":       "DAY",
        "price":          0,
        "tag":            "algo_halal",
        "instrument_token": instrument_key,
        "order_type":     "MARKET",
        "transaction_type": "SELL",
        "disclosed_quantity": 0,
        "trigger_price":  0,
        "is_amo":         False,
    }
    resp = requests.post(url, json=payload, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def get_order_status(order_id: str) -> dict:
    url = f"{UPSTOX_BASE}/order/details"
    resp = requests.get(url, params={"order_id": order_id}, headers=_headers())
    resp.raise_for_status()
    return resp.json().get("data", {})


# ── CLI entrypoint for standalone login ───────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--login" in sys.argv:
        token = login()
        print(f"[upstox] Login complete. Token: {token[:20]}...")
    else:
        print(__doc__)
