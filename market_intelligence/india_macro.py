"""
India-specific macro indicators.
FII/DII flows, India VIX, PMI, RBI calendar.
Sources: NSE website (free), NSDL (free), yfinance.
"""
import requests
import yfinance as yf
from datetime import datetime, date
from data import cache

NSE_FII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://www.nseindia.com",
    "Accept":     "application/json",
}


def fetch_india_vix() -> dict:
    cache_key = "india_vix"
    cached = cache.get(cache_key, ttl_hours=1)
    if cached:
        return cached

    try:
        t = yf.Ticker("^INDIAVIX")
        info = t.info
        vix = info.get("regularMarketPrice") or info.get("currentPrice")
        prev = info.get("regularMarketPreviousClose")
        result = {
            "value":      vix,
            "change_pct": ((vix - prev) / prev) if vix and prev else None,
            "signal":     _vix_signal(vix),
        }
        cache.set(cache_key, result)
        return result
    except Exception as e:
        print(f"[macro] India VIX fetch failed: {e}")
        return {}


def _vix_signal(vix: float) -> str:
    if vix is None:
        return "UNKNOWN"
    if vix < 13:
        return "VERY LOW — market complacency, potential for correction"
    if vix < 17:
        return "LOW — calm market, favorable for buying"
    if vix < 22:
        return "MODERATE — normal volatility"
    if vix < 27:
        return "HIGH — elevated fear, consider quality stocks on dip"
    return "EXTREME FEAR — consider waiting for stabilization"


def fetch_fii_dii_flows() -> dict:
    """Fetches previous day's FII/DII net investment data from NSE."""
    cache_key = f"fii_dii_{date.today().isoformat()}"
    cached = cache.get(cache_key, ttl_hours=6)
    if cached:
        return cached

    try:
        session = requests.Session()
        # Prime NSE session cookie
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
        resp = session.get(NSE_FII_URL, headers=NSE_HEADERS, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        result = {}
        for entry in raw:
            cat = entry.get("category", "")
            if "FII" in cat.upper():
                result["FII_net"] = entry.get("netValue")
                result["FII_buy"] = entry.get("buyValue")
                result["FII_sell"] = entry.get("sellValue")
            elif "DII" in cat.upper():
                result["DII_net"] = entry.get("netValue")
                result["DII_buy"] = entry.get("buyValue")
                result["DII_sell"] = entry.get("sellValue")

        result["signal"] = _fii_signal(result.get("FII_net"))
        cache.set(cache_key, result)
        return result
    except Exception as e:
        print(f"[macro] FII/DII fetch failed: {e}")
        return {}


def _fii_signal(fii_net) -> str:
    if fii_net is None:
        return "UNKNOWN"
    try:
        val = float(str(fii_net).replace(",", ""))
    except Exception:
        return "UNKNOWN"
    if val > 3000:
        return "STRONG BUY — FII net buying ₹{:.0f} Cr".format(val)
    if val > 500:
        return "POSITIVE — FII net buying ₹{:.0f} Cr".format(val)
    if val > -500:
        return "NEUTRAL — FII roughly flat"
    if val > -3000:
        return "CAUTION — FII net selling ₹{:.0f} Cr".format(abs(val))
    return "BEARISH — FII heavy selling ₹{:.0f} Cr".format(abs(val))


# Upcoming RBI and macro events (static calendar — update quarterly)
RBI_EVENTS_2026 = [
    {"date": "2026-02-07", "event": "RBI MPC Decision"},
    {"date": "2026-04-09", "event": "RBI MPC Decision"},
    {"date": "2026-06-06", "event": "RBI MPC Decision"},
    {"date": "2026-08-08", "event": "RBI MPC Decision"},
    {"date": "2026-10-08", "event": "RBI MPC Decision"},
    {"date": "2026-12-05", "event": "RBI MPC Decision"},
]

RESULTS_SEASONS = [
    {"start": "2026-04-15", "end": "2026-05-30", "label": "Q4 FY26 Results Season"},
    {"start": "2026-07-15", "end": "2026-08-30", "label": "Q1 FY27 Results Season"},
    {"start": "2026-10-15", "end": "2026-11-30", "label": "Q2 FY27 Results Season"},
    {"start": "2027-01-15", "end": "2027-02-28", "label": "Q3 FY27 Results Season"},
]


def upcoming_events(days_ahead: int = 14) -> list[dict]:
    """Returns macro events happening in the next N days."""
    today = date.today()
    upcoming = []

    for ev in RBI_EVENTS_2026:
        ev_date = date.fromisoformat(ev["date"])
        delta = (ev_date - today).days
        if 0 <= delta <= days_ahead:
            upcoming.append({"days_away": delta, **ev})

    for season in RESULTS_SEASONS:
        s = date.fromisoformat(season["start"])
        e = date.fromisoformat(season["end"])
        if s <= today <= e:
            upcoming.append({"days_away": 0, "event": f"ACTIVE: {season['label']}", "date": str(today)})
        elif 0 <= (s - today).days <= days_ahead:
            upcoming.append({"days_away": (s - today).days, "event": season["label"], "date": season["start"]})

    return sorted(upcoming, key=lambda x: x["days_away"])
