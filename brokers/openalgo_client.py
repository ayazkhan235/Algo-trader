"""
OpenAlgo API client.
Sends buy/sell signals from our halal screener to a self-hosted OpenAlgo instance.
OpenAlgo then places the order on Upstox (or any connected broker).

Docs: https://docs.openalgo.in
"""
import os
import requests
import math
import config

OPENALGO_BASE    = os.getenv("OPENALGO_HOST", "http://localhost:5000")
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")
_STRATEGY        = "HalalAlgoTrader"
_PRODUCT         = "MIS"    # MIS = intraday | CNC = delivery (long-term hold)


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-api-key": OPENALGO_API_KEY,
    }


def place_buy(symbol: str, price: float, tier: str, position_size_inr: float = None) -> dict:
    """
    Places a smart market buy order via OpenAlgo.
    Returns OpenAlgo response dict.
    """
    if not OPENALGO_API_KEY:
        raise RuntimeError("OPENALGO_API_KEY not set in environment")

    size = position_size_inr or config.LIVE_POSITION_SIZE_INR
    quantity = max(1, math.floor(size / price))

    payload = {
        "apikey":       OPENALGO_API_KEY,
        "strategy":     _STRATEGY,
        "symbol":       symbol.replace(".NS", ""),
        "action":       "BUY",
        "exchange":     "NSE",
        "pricetype":    "MARKET",
        "product":      _PRODUCT,
        "quantity":     str(quantity),
        "position_size": str(int(size)),
    }

    url = f"{OPENALGO_BASE}/api/v1/placesmartorder"
    resp = requests.post(url, json=payload, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def place_sell(symbol: str, quantity: int) -> dict:
    """Places a market sell order via OpenAlgo."""
    payload = {
        "apikey":    OPENALGO_API_KEY,
        "strategy":  _STRATEGY,
        "symbol":    symbol.replace(".NS", ""),
        "action":    "SELL",
        "exchange":  "NSE",
        "pricetype": "MARKET",
        "product":   _PRODUCT,
        "quantity":  str(quantity),
    }
    url = f"{OPENALGO_BASE}/api/v1/placesmartorder"
    resp = requests.post(url, json=payload, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_positions() -> list:
    """Returns current open positions from OpenAlgo."""
    url = f"{OPENALGO_BASE}/api/v1/positionbook"
    resp = requests.post(url, json={"apikey": OPENALGO_API_KEY}, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_orders() -> list:
    """Returns today's order book from OpenAlgo."""
    url = f"{OPENALGO_BASE}/api/v1/orderbook"
    resp = requests.post(url, json={"apikey": OPENALGO_API_KEY}, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", [])


def ping() -> bool:
    """Returns True if OpenAlgo instance is reachable."""
    try:
        resp = requests.get(f"{OPENALGO_BASE}/", timeout=5)
        return resp.status_code < 500
    except Exception:
        return False
