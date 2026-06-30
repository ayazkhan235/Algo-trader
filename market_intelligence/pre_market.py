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


def fetch_nifty_trend(refresh: bool = False) -> Optional[dict]:
    """
    NIFTY 50 (^NSEI) level vs its 50- and 200-day moving averages — the
    multi-week trend that actually matters to a months-long holder (not an
    intraday wiggle). Returns
      {price, sma_short, sma_long, pct_vs_long, week_change}
    or None if unavailable.
    """
    import config
    long_n = getattr(config, "REGIME_LONG_MA_DAYS", 200)
    short_n = getattr(config, "REGIME_SHORT_MA_DAYS", 50)
    cache_key = f"nifty_trend_{datetime.now().strftime('%Y%m%d')}"
    if not refresh:
        cached = cache.get(cache_key, ttl_hours=12)
        if cached:
            return cached
    try:
        t = yf.Ticker("^NSEI")
        closes = t.history(period="1y", interval="1d")["Close"].dropna()
        if len(closes) < long_n:
            return None
        price = float(closes.iloc[-1])
        sma_short = float(closes.tail(short_n).mean())
        sma_long = float(closes.tail(long_n).mean())
        week_ago = float(closes.iloc[-6]) if len(closes) >= 6 else price
        result = {
            "price": round(price, 2),
            "sma_short": round(sma_short, 2),
            "sma_long": round(sma_long, 2),
            "pct_vs_long": round((price - sma_long) / sma_long, 4),
            "week_change": round((price - week_ago) / week_ago, 4) if week_ago else 0.0,
        }
        cache.set(cache_key, result)
        return result
    except Exception:
        return None


def assess_regime_gate(trend: Optional[dict]) -> dict:
    """
    Months-horizon gate for a SIP accumulator (pure, unit-testable). Returns
      {action, budget_mult, dip, pct_vs_long, reason}
    where action is 'allow' | 'pause':
      • 'pause'  — NIFTY below its long MA: confirmed downtrend, keep cash.
      • 'allow' + dip=True — healthy market but a short-term pullback (below the
        short MA, or down on the week): deploy MORE (budget_mult) for a cheaper
        basis on names we'd hold for months anyway.
      • 'allow' + dip=False — normal accumulation.
    A missing reading never pauses — it just allows normal buying.
    """
    import config
    if not getattr(config, "REGIME_GATE_ENABLED", True) or not trend:
        return {"action": "allow", "budget_mult": 1.0, "dip": False,
                "pct_vs_long": None, "reason": "No trend read — accumulating normally"}

    price = trend.get("price")
    sma_long = trend.get("sma_long")
    sma_short = trend.get("sma_short")
    if not price or not sma_long:
        return {"action": "allow", "budget_mult": 1.0, "dip": False,
                "pct_vs_long": None, "reason": "No trend read — accumulating normally"}

    pct_vs_long = (price - sma_long) / sma_long
    if price < sma_long:
        return {"action": "pause", "budget_mult": 1.0, "dip": False,
                "pct_vs_long": round(pct_vs_long, 4),
                "reason": f"NIFTY {pct_vs_long:+.1%} vs 200-day avg — confirmed downtrend, preserving cash"}

    week_change = trend.get("week_change", 0.0) or 0.0
    is_dip = (sma_short and price < sma_short) or week_change <= config.DIP_WEEK_DROP_PCT
    if is_dip:
        return {"action": "allow", "budget_mult": float(config.DIP_BUDGET_MULT), "dip": True,
                "pct_vs_long": round(pct_vs_long, 4),
                "reason": "Healthy uptrend + short-term dip — deploying extra for a cheaper basis"}
    return {"action": "allow", "budget_mult": 1.0, "dip": False,
            "pct_vs_long": round(pct_vs_long, 4),
            "reason": f"NIFTY {pct_vs_long:+.1%} above 200-day avg — normal accumulation"}


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
