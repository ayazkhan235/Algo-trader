"""
Fetches global pre-market indicators before NSE opens (9:15 AM IST).
All data via yfinance — free, no API key needed.
"""
import yfinance as yf
from datetime import datetime
from typing import Optional
from data import cache

INDICATORS = {
    "SGX Nifty":       "^SG30",        # Singapore proxy (CNX Nifty futures)
    "S&P 500":         "^GSPC",
    "Dow Jones":       "^DJI",
    "Nasdaq":          "^IXIC",
    "Nikkei 225":      "^N225",
    "Hang Seng":       "^HSI",
    "India VIX":       "^INDIAVIX",
    "US VIX":          "^VIX",
    "USD/INR":         "USDINR=X",
    "US 10Y Yield":    "^TNX",
    "Crude Oil (WTI)": "CL=F",
    "Brent Crude":     "BZ=F",
    "Gold":            "GC=F",
    "Silver":          "SI=F",
    "EUR/USD":         "EURUSD=X",
    "JPY/USD":         "JPY=X",
}

SECTOR_IMPACT = {
    "Information Technology": {
        "S&P 500":    ("negative", 0.7),   # (direction if down, sensitivity)
        "Nasdaq":     ("negative", 0.9),
        "USD/INR":    ("positive", 0.5),   # weak INR helps IT exporters
        "US 10Y Yield": ("negative", 0.4),
    },
    "Healthcare": {
        "USD/INR":    ("positive", 0.5),
        "US VIX":     ("negative", 0.3),
    },
    "Energy": {
        "Brent Crude": ("positive", 0.9),
        "Crude Oil (WTI)": ("positive", 0.9),
    },
    "Materials": {
        "Hang Seng":  ("positive", 0.6),   # China demand proxy
        "USD/INR":    ("negative", 0.4),
    },
    "Consumer Staples": {
        "USD/INR":    ("negative", 0.3),   # import costs
        "Gold":       ("positive", 0.2),
    },
    "Industrials": {
        "Crude Oil (WTI)": ("negative", 0.4),
        "USD/INR":    ("negative", 0.3),
    },
    "Utilities": {
        "Crude Oil (WTI)": ("negative", 0.3),
        "US 10Y Yield": ("negative", 0.5),
    },
}


def _pct_change(ticker_sym: str) -> Optional[dict]:
    try:
        t = yf.Ticker(ticker_sym)
        hist = t.history(period="2d", interval="1d")
        if hist.empty or len(hist) < 2:
            info = t.info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            prev  = info.get("regularMarketPreviousClose")
            if price and prev:
                chg = (price - prev) / prev
                return {"price": price, "change_pct": chg}
            return None
        latest = hist["Close"].iloc[-1]
        prev   = hist["Close"].iloc[-2]
        return {"price": round(latest, 2), "change_pct": round((latest - prev) / prev, 4)}
    except Exception:
        return None


def fetch_global_indicators(refresh: bool = False) -> dict:
    cache_key = f"pre_market_{datetime.now().strftime('%Y%m%d')}"
    if not refresh:
        cached = cache.get(cache_key, ttl_hours=1)
        if cached:
            return cached

    result = {}
    for name, sym in INDICATORS.items():
        data = _pct_change(sym)
        if data:
            result[name] = data

    cache.set(cache_key, result)
    return result


def metal_trend(symbol: str = "GC=F", lookback: str = "1mo") -> Optional[dict]:
    """
    1-month trend for a precious metal (default gold) + a plain-English signal
    on what it implies for equities. Returns {change, signal} or None.
    Gold is a safe-haven: a sharp rise = fear/risk-off (can pressure stocks);
    a fall = risk appetite returning (supportive for stocks).
    """
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=lookback, interval="1d")
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        change = (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0]
        if change >= 0.05:
            signal = "strong safe-haven buying — investors cautious, can pressure equities"
        elif change >= 0.02:
            signal = "firm — mild risk-off tilt"
        elif change <= -0.05:
            signal = "falling — risk appetite returning, supportive for equities"
        else:
            signal = "broadly flat — neutral for equities"
        return {"change": round(float(change), 4), "signal": signal}
    except Exception:
        return None


def fetch_nifty_intraday(refresh: bool = False) -> Optional[dict]:
    """
    Live intraday move of NIFTY 50 (^NSEI) vs the previous close — i.e. how NSE
    is *actually* trading right now, after digesting overnight global cues.
    Returns {price, prev_close, change_pct} or None if unavailable / market shut.
    """
    cache_key = f"nifty_intraday_{datetime.now().strftime('%Y%m%d%H')}"
    if not refresh:
        cached = cache.get(cache_key, ttl_hours=1)
        if cached:
            return cached
    try:
        t = yf.Ticker("^NSEI")
        # 1-minute bars for today; fall back to daily if intraday is empty.
        intraday = t.history(period="1d", interval="1m")
        daily = t.history(period="5d", interval="1d")
        if daily.empty:
            return None
        prev_close = float(daily["Close"].iloc[-2]) if len(daily) >= 2 else float(daily["Close"].iloc[0])
        if not intraday.empty:
            price = float(intraday["Close"].iloc[-1])
        else:
            price = float(daily["Close"].iloc[-1])
        if not prev_close:
            return None
        result = {
            "price": round(price, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": round((price - prev_close) / prev_close, 4),
        }
        cache.set(cache_key, result)
        return result
    except Exception:
        return None


def assess_market_gate(intraday: Optional[dict]) -> dict:
    """
    Decide whether new buys are warranted given how NSE is trading today.

    Pure function (no network) so it is unit-testable. Returns:
      {action, score_bump, nifty_pct, reason}
    where action is 'allow' | 'caution' | 'block'. On a clearly weak tape we
    block new buys; in a mild-weakness zone we demand higher conviction; an
    unavailable reading (market shut / no data) never blocks — it just allows.
    """
    import config
    if not getattr(config, "MARKET_GATE_ENABLED", True) or not intraday:
        return {"action": "allow", "score_bump": 0.0,
                "nifty_pct": None, "reason": "No intraday read — gate inactive"}

    pct = intraday.get("change_pct")
    if pct is None:
        return {"action": "allow", "score_bump": 0.0,
                "nifty_pct": None, "reason": "No intraday read — gate inactive"}

    if pct <= config.NIFTY_GATE_BLOCK_PCT:
        return {"action": "block", "score_bump": 0.0, "nifty_pct": pct,
                "reason": f"NIFTY {pct:+.1%} intraday — risk-off, no new buys today"}
    if pct <= config.NIFTY_GATE_CAUTION_PCT:
        return {"action": "caution", "score_bump": float(config.NIFTY_GATE_SCORE_BUMP),
                "nifty_pct": pct,
                "reason": f"NIFTY {pct:+.1%} intraday — soft, buying only top conviction"}
    return {"action": "allow", "score_bump": 0.0, "nifty_pct": pct,
            "reason": f"NIFTY {pct:+.1%} intraday — tape constructive"}


def assess_market_sentiment(indicators: dict) -> str:
    """Returns overall market sentiment: BULLISH / NEUTRAL / BEARISH."""
    if not indicators:
        return "UNKNOWN"

    score = 0
    checked = 0

    positive_on_up = ["S&P 500", "Nasdaq", "Nikkei 225", "Hang Seng"]
    negative_on_up = ["US VIX", "USD/INR", "US 10Y Yield"]

    for name in positive_on_up:
        if name in indicators:
            chg = indicators[name]["change_pct"]
            score += 1 if chg > 0.003 else (-1 if chg < -0.003 else 0)
            checked += 1

    for name in negative_on_up:
        if name in indicators:
            chg = indicators[name]["change_pct"]
            score += -1 if chg > 0.003 else (1 if chg < -0.003 else 0)
            checked += 1

    if checked == 0:
        return "UNKNOWN"
    ratio = score / checked
    if ratio > 0.3:
        return "BULLISH"
    if ratio < -0.3:
        return "BEARISH"
    return "NEUTRAL"


def sector_impact_summary(indicators: dict, portfolio_sectors: list[str]) -> dict[str, str]:
    """
    For each sector in the portfolio, summarize expected pre-market impact.
    Returns {sector: impact_string}
    """
    impacts = {}
    for sector in portfolio_sectors:
        correlations = SECTOR_IMPACT.get(sector, {})
        sector_score = 0
        for indicator, (direction, sensitivity) in correlations.items():
            if indicator not in indicators:
                continue
            chg = indicators[indicator]["change_pct"]
            # direction = "positive" means indicator UP is good for sector
            effect = chg * sensitivity if direction == "positive" else -chg * sensitivity
            sector_score += effect

        if sector_score > 0.005:
            impacts[sector] = f"✓ Mild positive ({sector_score:+.1%} expected)"
        elif sector_score < -0.005:
            impacts[sector] = f"✗ Mild negative ({sector_score:+.1%} expected)"
        else:
            impacts[sector] = "→ Neutral"

    return impacts
