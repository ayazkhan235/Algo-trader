"""
Market 'memory': log global-market mood each morning and summarise the last N
days at three levels — overall market, sector, and company.

• snapshot_market()      → network: today's global-market regime row
• summarize_market()     → pure: bullish/bearish/neutral trend over N days
• summarize_sectors()    → pure: which sectors ran hot/cold (from company news)
• summarize_companies()  → pure: per-company net news sentiment over N days

The pure summarisers take plain lists of DB rows so they're unit-testable
without any network.
"""
from __future__ import annotations
from datetime import date

# Global EQUITY indices used for the numeric market score
_EQUITY = ["S&P 500", "Dow Jones", "Nasdaq", "Nikkei 225", "Hang Seng"]


def snapshot_market() -> dict:
    """Fetch today's global-market regime (network, best-effort)."""
    from market_intelligence.pre_market import fetch_global_indicators, assess_market_sentiment
    from market_intelligence.india_macro import fetch_india_vix, fetch_fii_dii_flows

    ind = fetch_global_indicators()
    sentiment = assess_market_sentiment(ind)
    vix = fetch_india_vix() or {}
    fii = fetch_fii_dii_flows() or {}

    def chg(name):
        d = ind.get(name) or {}
        return d.get("change_pct")

    eq = [chg(n) for n in _EQUITY if chg(n) is not None]
    score = round(sum(eq) / len(eq), 4) if eq else 0.0

    return {
        "date": date.today().isoformat(),
        "sentiment": sentiment,
        "score": score,
        "sp500": chg("S&P 500"),
        "dow": chg("Dow Jones"),
        "nasdaq": chg("Nasdaq"),
        "nikkei": chg("Nikkei 225"),
        "hangseng": chg("Hang Seng"),
        "india_vix": vix.get("value"),
        "fii_signal": fii.get("signal", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pure summarisers (no network)
# ─────────────────────────────────────────────────────────────────────────────
def _recent(rows: list[dict], days: int) -> list[dict]:
    return sorted(rows, key=lambda r: r.get("date", ""))[-days:]


def summarize_market(rows: list[dict], days: int = 30) -> dict:
    rows = _recent(rows, days)
    if not rows:
        return {"label": "NO DATA", "days": 0, "bullish": 0, "bearish": 0,
                "neutral": 0, "avg_score": 0.0, "trend": "—"}
    bull = sum(1 for r in rows if (r.get("sentiment") or "").upper() == "BULLISH")
    bear = sum(1 for r in rows if (r.get("sentiment") or "").upper() == "BEARISH")
    neu = len(rows) - bull - bear
    scores = [r["score"] for r in rows if isinstance(r.get("score"), (int, float))]
    avg = round(sum(scores) / len(scores), 4) if scores else 0.0

    if bull > bear * 1.3:
        label = "BULLISH"
    elif bear > bull * 1.3:
        label = "BEARISH"
    else:
        label = "NEUTRAL / CHOPPY"

    # Simple trend: avg score of first half vs second half
    half = len(scores) // 2
    trend = "—"
    if half:
        first = sum(scores[:half]) / half
        second = sum(scores[half:]) / (len(scores) - half)
        trend = "improving" if second > first else "weakening" if second < first else "flat"

    return {"label": label, "days": len(rows), "bullish": bull, "bearish": bear,
            "neutral": neu, "avg_score": avg, "trend": trend}


def _group_avg(rows: list[dict], key: str, days: int) -> dict[str, dict]:
    rows = _recent(rows, days)
    groups: dict[str, list[float]] = {}
    extra: dict[str, str] = {}
    for r in rows:
        k = r.get(key)
        s = r.get("score")
        if k is None or not isinstance(s, (int, float)):
            continue
        groups.setdefault(k, []).append(s)
        if r.get("headline"):
            extra[k] = r["headline"]  # keep latest headline
    out = {}
    for k, vals in groups.items():
        avg = round(sum(vals) / len(vals), 3)
        label = "POSITIVE" if avg > 0.1 else "NEGATIVE" if avg < -0.1 else "NEUTRAL"
        out[k] = {"avg": avg, "label": label, "n": len(vals), "headline": extra.get(k, "")}
    return out


def summarize_sectors(rows: list[dict], days: int = 30) -> list[dict]:
    g = _group_avg(rows, "sector", days)
    items = [{"sector": k, **v} for k, v in g.items()]
    return sorted(items, key=lambda x: -x["avg"])


def summarize_companies(rows: list[dict], days: int = 30) -> list[dict]:
    g = _group_avg(rows, "symbol", days)
    items = [{"symbol": k, **v} for k, v in g.items()]
    return sorted(items, key=lambda x: -x["avg"])
