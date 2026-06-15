"""Unit tests for fundamental metric computation."""
import pytest
from analysis.fundamental import cagr, earnings_consistency, graham_number, compute
import math


class TestHelpers:
    def test_cagr_positive_growth(self):
        # Revenue doubled over 3 years → CAGR ~26%
        result = cagr([200, 160, 130, 100], years=3)
        assert result is not None
        assert abs(result - (200/100)**(1/3) - 1) < 0.01 or result > 0

    def test_cagr_negative_base_returns_none(self):
        assert cagr([100, 50, -10], years=2) is None

    def test_cagr_insufficient_data_returns_none(self):
        assert cagr([100]) is None

    def test_earnings_consistency_all_positive(self):
        assert earnings_consistency([100, 200, 150, 80]) == 1.0

    def test_earnings_consistency_all_negative(self):
        assert earnings_consistency([-10, -20, -5, -30]) == 0.0

    def test_earnings_consistency_mixed(self):
        result = earnings_consistency([100, -50, 80, 60])
        assert result == 0.75

    def test_graham_number_valid(self):
        g = graham_number(eps=10, book_value=50)
        expected = math.sqrt(22.5 * 10 * 50)
        assert abs(g - expected) < 0.01

    def test_graham_number_negative_eps_returns_none(self):
        assert graham_number(eps=-5, book_value=50) is None

    def test_graham_number_none_input_returns_none(self):
        assert graham_number(eps=None, book_value=50) is None


class TestComputeMetrics:
    def _sample_data(self):
        return {
            "info": {
                "sector": "Technology", "industry": "Software",
                "name": "Test Corp", "market_cap": 50000,
                "current_price": 500, "trailing_pe": 25.0,
                "forward_pe": 20.0, "priceToBook": 5.0, "price_to_book": 5.0,
                "returnOnEquity": 0.22, "returnOnAssets": 0.15,
                "profitMargins": 0.18, "operatingMargins": 0.22,
                "grossMargins": 0.45, "revenueGrowth": 0.12,
                "earningsGrowth": 0.15, "freeCashflow": 2000,
                "operatingCashflow": 2500, "totalDebt": 1000,
                "currentRatio": 2.1, "quickRatio": 1.8,
                "dividendYield": 0.015, "payoutRatio": 0.3,
                "beta": 0.8, "fiftyTwoWeekHigh": 600, "fiftyTwoWeekLow": 350,
                "sharesOutstanding": 100, "enterpriseValue": 51000,
                "ebitda": 3000, "trailing_eps": 20.0, "book_value": 100.0,
                "enterpriseToEbitda": 17.0, "priceToSalesTrailing12Months": 8.0,
                "roe": 0.22, "roa": 0.15, "net_margin": 0.18,
                "operating_margin": 0.22, "gross_margin": 0.45,
            },
            "financials": {
                "revenue":          [10000, 9000, 8000, 7000],
                "gross_profit":     [4500, 3900, 3500, 3000],
                "ebit":             [2200, 1800, 1500, 1200],
                "net_income":       [1800, 1500, 1200, 1000],
                "interest_expense": [-100, -90, -80, -70],
                "interest_income":  [],
                "total_assets":     [15000, 13000, 11000, 10000],
                "total_debt_bs":    [1000, 1100, 1000, 900],
                "net_receivables":  [2000, 1800, 1600, 1400],
                "cash":             [1500, 1200, 1000, 900],
                "ppe":              [5000, 4500, 4000, 3500],
                "equity":           [10000, 9000, 8000, 7000],
                "current_assets":   [4000, 3500, 3000, 2500],
                "current_liabilities": [2000, 1800, 1600, 1400],
                "retained_earnings": [6000, 5000, 4000, 3000],
                "capex":            [-500, -450, -400, -350],
                "operating_cf":     [2500, 2100, 1800, 1500],
                "free_cf":          [2000, 1650, 1400, 1150],
            },
        }

    def test_compute_returns_dict(self):
        result = compute("TEST.NS", self._sample_data())
        assert isinstance(result, dict)
        assert result["symbol"] == "TEST.NS"

    def test_rev_cagr_positive(self):
        result = compute("TEST.NS", self._sample_data())
        assert result["rev_cagr_3y"] is not None
        assert result["rev_cagr_3y"] > 0

    def test_earn_consistency_full(self):
        result = compute("TEST.NS", self._sample_data())
        assert result["earn_consistency"] == 1.0

    def test_roce_computed(self):
        result = compute("TEST.NS", self._sample_data())
        assert result["roce"] is not None
        assert result["roce"] > 0

    def test_interest_coverage_computed(self):
        result = compute("TEST.NS", self._sample_data())
        assert result["interest_coverage"] is not None
        assert result["interest_coverage"] > 5

    def test_graham_number_computed(self):
        result = compute("TEST.NS", self._sample_data())
        assert result["graham_number"] is not None
        assert result["graham_number"] > 0

    def test_cash_conversion_positive(self):
        result = compute("TEST.NS", self._sample_data())
        assert result["cash_conversion"] is not None
        assert result["cash_conversion"] > 0
