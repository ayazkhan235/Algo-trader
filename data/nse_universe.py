"""
Fetches NSE stock universe from official NSE CSV files.
Nifty500 is the default — 500 most liquid NSE stocks, ~95% of market cap.
"""
import io
import requests
import pandas as pd
from typing import Optional
from data import cache

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.nseindia.com",
    "Accept-Language": "en-US,en;q=0.9",
}

UNIVERSE_URLS = {
    "nifty50":   "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "nifty200":  "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    "nifty500":  "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "nifty_full": "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
}

FALLBACK_NIFTY50 = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE", "BHARTIARTL", "ASIANPAINT",
    "MARUTI", "TITAN", "WIPRO", "ULTRACEMCO", "NESTLEIND", "TECHM", "SUNPHARMA",
    "POWERGRID", "NTPC", "ADANIPORTS", "ONGC", "JSWSTEEL", "TATACONSUM",
    "HCLTECH", "BAJAJFINSV", "DIVISLAB", "DRREDDY", "CIPLA", "EICHERMOT",
    "HINDZINC", "BRITANNIA", "SBILIFE", "HDFCLIFE", "ADANIENT", "BPCL",
    "COALINDIA", "GRASIM", "INDUSINDBK", "M&M", "SBIN", "TATAMOTORS",
    "TATASTEEL", "UPL", "HEROMOTOCO", "BAJAJ-AUTO", "APOLLOHOSP", "SHRIRAMFIN",
]


def _fetch_csv(url: str) -> Optional[pd.DataFrame]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return pd.read_csv(io.StringIO(resp.text))
    except Exception as e:
        print(f"[universe] fetch failed for {url}: {e}")
        return None


def get_symbols(universe: str = "nifty500", refresh: bool = False) -> list[str]:
    """
    Returns list of yfinance-compatible symbols (SYMBOL.NS format).
    Falls back to hardcoded Nifty50 list if NSE is unreachable.
    """
    cache_key = f"universe_{universe}"
    if not refresh:
        cached = cache.get(cache_key, ttl_hours=72)
        if cached:
            return cached

    url = UNIVERSE_URLS.get(universe)
    if not url:
        raise ValueError(f"Unknown universe: {universe}. Choose from {list(UNIVERSE_URLS)}")

    df = _fetch_csv(url)

    if df is None:
        print("[universe] Using hardcoded Nifty50 fallback")
        symbols = [f"{s}.NS" for s in FALLBACK_NIFTY50]
        cache.set(cache_key, symbols)
        return symbols

    if universe == "nifty_full":
        symbol_col = "SYMBOL"
        df = df[df.get("SERIES", pd.Series(["EQ"] * len(df))) == "EQ"]
    else:
        symbol_col = "Symbol"

    if symbol_col not in df.columns:
        symbol_col = df.columns[2]  # fallback: 3rd column is usually symbol

    symbols = [f"{s.strip()}.NS" for s in df[symbol_col].dropna().unique()]
    print(f"[universe] Loaded {len(symbols)} symbols for '{universe}'")

    cache.set(cache_key, symbols)
    return symbols
