"""Unit test for the daily portfolio digest HTML builder (no network)."""
from reports.email_report import _build_digest_html


def test_digest_lists_holdings_and_vs_nifty():
    holdings = [
        {"symbol": "COALINDIA.NS", "name": "Coal India", "entry": 449.0,
         "qty": 3.1, "price": 470.0, "value": 1457.0, "pct": 0.0468},
        {"symbol": "WIPRO.NS", "name": "Wipro", "entry": 180.0,
         "qty": 7.7, "price": 175.0, "value": 1347.5, "pct": -0.0278},
    ]
    summary = {"total_invested": 100000, "total_value": 102000,
               "open_pnl_inr": 2000, "open_pnl_pct": 0.02}
    html = _build_digest_html(holdings, summary, {"overall_sentiment": "BULLISH",
                              "summary_lines": ["Market Sentiment: BULLISH"]},
                              nifty_return=0.012, executed=[])
    assert "Current Holdings (2)" in html
    assert "COALINDIA" in html and "WIPRO" in html
    assert "Strategy vs NIFTY" in html          # +2.0% - +1.2% = +0.8%
    assert "+2.0%" in html


def test_digest_handles_empty_portfolio():
    html = _build_digest_html([], {"total_invested": 0, "total_value": 0,
                              "open_pnl_inr": 0, "open_pnl_pct": 0}, {}, None, [])
    assert "No open positions" in html
