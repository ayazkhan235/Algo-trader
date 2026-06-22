"""Unit tests for the SIP backtest math (no network)."""
from analysis.backtest import simulate_sip, _annualised


def test_single_stock_flat_price_no_profit():
    months = ["2024-01", "2024-02", "2024-03"]
    prices = {"X": [100.0, 100.0, 100.0]}
    r = simulate_sip(months, prices, 1000)
    assert r["invested"] == 3000
    assert round(r["final_value"], 2) == 3000.0   # flat price → break-even
    assert abs(r["return_pct"]) < 1e-9


def test_doubling_price_profit():
    months = ["2024-01", "2024-02"]
    # Buy at 100 (10 sh) and at 200 (5 sh) = 15 sh; final price 200 → 3000 value
    prices = {"X": [100.0, 200.0]}
    r = simulate_sip(months, prices, 1000)
    assert r["invested"] == 2000
    assert round(r["final_value"], 2) == 3000.0
    assert round(r["return_pct"], 4) == 0.5


def test_equal_split_across_two_stocks():
    months = ["2024-01"]
    prices = {"A": [100.0], "B": [50.0]}
    r = simulate_sip(months, prices, 1000)  # ₹500 each
    assert r["breakdown"]["A"]["shares"] == 5.0
    assert r["breakdown"]["B"]["shares"] == 10.0


def test_skips_months_with_no_price():
    months = ["2024-01", "2024-02"]
    prices = {"X": [None, 100.0]}  # not listed in month 1
    r = simulate_sip(months, prices, 1000)
    assert r["invested"] == 1000   # only one contributing month


def test_annualised_positive_for_growth():
    # invest 1000 at month 0, worth 1200 at month 12 → ~20%/yr
    ann = _annualised([(0, -1000), (12, 1200)])
    assert ann is not None and 0.15 < ann < 0.25
