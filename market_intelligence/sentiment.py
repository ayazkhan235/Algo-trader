"""
Lightweight news sentiment for NSE stocks — free, no API key.

Headlines come from yfinance's per-ticker news feed. Scoring is a transparent
keyword model (no LLM): positive/negative finance words → a score in [-1, 1].
Crude but deterministic and explainable; the actual headline is always kept so
the email/report can show *why*.
"""
from __future__ import annotations

POSITIVE = {
    "profit", "surge", "surges", "jump", "jumps", "gain", "gains", "rise", "rises",
    "beat", "beats", "record", "high", "growth", "grow", "win", "wins", "order",
    "orders", "deal", "deals", "upgrade", "upgraded", "expansion", "expand",
    "approval", "approved", "dividend", "buyback", "strong", "rally", "rallies",
    "outperform", "bullish", "acquire", "acquires", "acquisition", "partnership",
    "launch", "launches", "boost", "boosts", "soar", "soars", "robust", "rerating",
    "tailwind", "demand", "bags", "secures", "milestone",
}
NEGATIVE = {
    "loss", "losses", "fall", "falls", "drop", "drops", "decline", "declines",
    "miss", "misses", "fraud", "probe", "downgrade", "downgraded", "cut", "cuts",
    "weak", "lawsuit", "fine", "fined", "penalty", "resign", "resigns", "default",
    "ban", "banned", "slump", "slumps", "plunge", "plunges", "bearish", "warning",
    "warns", "recall", "strike", "layoff", "layoffs", "scam", "raid", "stake sale",
    "headwind", "downturn", "slowdown", "debt", "crisis", "selloff", "sell-off",
    "downgrades", "hit", "hits",
}


def score_text(text: str) -> dict:
    """Score a single headline. Returns {score in [-1,1], label, pos, neg}."""
    if not text:
        return {"score": 0.0, "label": "NEUTRAL", "pos": 0, "neg": 0}
    words = "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in text).split()
    pos = sum(1 for w in words if w in POSITIVE)
    neg = sum(1 for w in words if w in NEGATIVE)
    total = pos + neg
    score = 0.0 if total == 0 else (pos - neg) / total
    label = "POSITIVE" if score > 0.15 else "NEGATIVE" if score < -0.15 else "NEUTRAL"
    return {"score": round(score, 3), "label": label, "pos": pos, "neg": neg}


def score_headlines(titles: list[str]) -> dict:
    """
    Aggregate sentiment across several headlines.
    Returns {score, label, n, top_headline} where top_headline is the most
    sentiment-laden (positive or negative) title — the one worth quoting.
    """
    titles = [t for t in (titles or []) if t]
    if not titles:
        return {"score": 0.0, "label": "NEUTRAL", "n": 0, "top_headline": ""}

    scored = [(t, score_text(t)) for t in titles]
    avg = round(sum(s["score"] for _, s in scored) / len(scored), 3)
    label = "POSITIVE" if avg > 0.1 else "NEGATIVE" if avg < -0.1 else "NEUTRAL"
    # Most sentiment-laden headline (largest |score|, then most keywords)
    top = max(scored, key=lambda ts: (abs(ts[1]["score"]), ts[1]["pos"] + ts[1]["neg"]))
    return {"score": avg, "label": label, "n": len(titles), "top_headline": top[0]}


def fetch_headlines(symbol: str, limit: int = 6) -> list[str]:
    """Recent headline titles for a ticker (yfinance, best-effort)."""
    try:
        import yfinance as yf
        items = yf.Ticker(symbol).news or []
        titles = []
        for it in items[:limit]:
            # yfinance shapes vary: {'title': ...} or {'content': {'title': ...}}
            title = it.get("title") or (it.get("content") or {}).get("title")
            if title:
                titles.append(title)
        return titles
    except Exception as e:  # noqa: BLE001
        print(f"[news] {symbol}: headline fetch failed ({e})")
        return []
