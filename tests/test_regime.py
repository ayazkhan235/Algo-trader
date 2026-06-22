"""Unit tests for the 30-day regime summarisers (no network)."""
from market_intelligence.regime import (
    summarize_market, summarize_sectors, summarize_companies,
)
from paper_trading.executor import effective_score


def _mkt(date, sentiment, score):
    return {"date": date, "sentiment": sentiment, "score": score}


def test_market_bullish_label_and_counts():
    rows = [
        _mkt("2026-06-01", "BULLISH", 0.01),
        _mkt("2026-06-02", "BULLISH", 0.02),
        _mkt("2026-06-03", "BULLISH", 0.015),
        _mkt("2026-06-04", "BEARISH", -0.01),
    ]
    r = summarize_market(rows, 30)
    assert r["bullish"] == 3 and r["bearish"] == 1
    assert r["label"] == "BULLISH"


def test_market_no_data():
    r = summarize_market([], 30)
    assert r["label"] == "NO DATA" and r["days"] == 0


def test_sectors_sorted_by_avg():
    rows = [
        {"date": "2026-06-01", "sector": "Energy", "score": 0.5},
        {"date": "2026-06-01", "sector": "Technology", "score": -0.4},
        {"date": "2026-06-02", "sector": "Energy", "score": 0.3},
    ]
    out = summarize_sectors(rows, 30)
    assert out[0]["sector"] == "Energy" and out[0]["label"] == "POSITIVE"
    assert out[-1]["sector"] == "Technology" and out[-1]["label"] == "NEGATIVE"


def test_companies_keep_headline():
    rows = [
        {"date": "2026-06-01", "symbol": "X.NS", "score": 0.4, "headline": "X wins big order"},
    ]
    out = summarize_companies(rows, 30)
    assert out[0]["symbol"] == "X.NS" and out[0]["headline"] == "X wins big order"


def test_effective_score_bounded_news_bonus():
    # +ve news adds, -ve subtracts, capped at ±5
    assert effective_score(70, {"score": 1.0}) == 75
    assert effective_score(70, {"score": -1.0}) == 65
    assert effective_score(70, None) == 70
