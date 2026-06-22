"""Unit tests for keyword news sentiment (no network)."""
from market_intelligence.sentiment import score_text, score_headlines


def test_positive_headline():
    r = score_text("Company profit surges to record high on strong demand")
    assert r["label"] == "POSITIVE" and r["score"] > 0


def test_negative_headline():
    r = score_text("Firm plunges after fraud probe and downgrade")
    assert r["label"] == "NEGATIVE" and r["score"] < 0


def test_neutral_headline():
    r = score_text("Company to hold annual general meeting next week")
    assert r["label"] == "NEUTRAL" and r["score"] == 0.0


def test_aggregate_picks_top_headline():
    titles = [
        "Board to meet on Tuesday",
        "Stock soars as profit jumps and company wins record order",
    ]
    agg = score_headlines(titles)
    assert agg["n"] == 2
    assert agg["label"] == "POSITIVE"
    assert "soars" in agg["top_headline"]


def test_empty_headlines():
    agg = score_headlines([])
    assert agg["label"] == "NEUTRAL" and agg["n"] == 0 and agg["top_headline"] == ""
