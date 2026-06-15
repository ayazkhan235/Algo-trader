"""
Unit tests for halal screener.
Uses mock data — no network access required.
"""
import pytest
from screening.halal_screener import screen
from screening.sector_map import classify


def _make_data(sector="Technology", industry="Software—Application",
               symbol="TEST.NS", total_debt=100, total_assets=1000,
               market_cap=2000, cash=100, receivables=200,
               ppe=400, revenue=500, interest_income=0, net_income=80):
    return {
        "info": {
            "sector": sector, "industry": industry,
            "market_cap": market_cap, "current_price": 100,
            "total_debt": total_debt,
        },
        "financials": {
            "total_assets":     [total_assets],
            "total_debt_bs":    [total_debt],
            "cash":             [cash],
            "net_receivables":  [receivables],
            "ppe":              [ppe],
            "revenue":          [revenue],
            "interest_income":  [interest_income] if interest_income else [],
            "net_income":       [net_income],
            "total_debt":       [total_debt],
            "gross_profit": [], "ebit": [], "interest_expense": [],
            "equity": [], "current_assets": [], "current_liabilities": [],
            "retained_earnings": [], "capex": [], "operating_cf": [],
            "free_cf": [],
        },
    }


class TestSectorClassification:
    def test_it_sector_is_halal(self):
        cls, _ = classify("TCS.NS", "Technology", "Software—Application")
        assert cls == "halal"

    def test_bank_is_haram(self):
        cls, _ = classify("HDFCBANK.NS", "Financial Services", "Banks—Diversified")
        assert cls == "haram"

    def test_tobacco_keyword_is_haram(self):
        cls, _ = classify("TEST.NS", "Consumer Staples", "Tobacco")
        assert cls == "haram"

    def test_alcohol_keyword_is_haram(self):
        cls, _ = classify("TEST.NS", "Consumer Staples", "Beverages—Wineries & Distilleries")
        assert cls == "haram"

    def test_manual_blacklist_itc(self):
        cls, _ = classify("ITC.NS", "Consumer Staples", "Diversified FMCG")
        assert cls == "haram"

    def test_manual_whitelist_hdfcamc(self):
        cls, _ = classify("HDFCAMC.NS", "Financial Services", "Asset Management")
        assert cls == "halal"

    def test_defense_is_haram(self):
        cls, _ = classify("TEST.NS", "Industrials", "Aerospace & Defense")
        assert cls == "haram"

    def test_pharma_is_halal(self):
        cls, _ = classify("SUNPHARMA.NS", "Healthcare", "Drug Manufacturers")
        assert cls == "halal"

    def test_fmcg_no_haram_keywords_is_halal(self):
        cls, _ = classify("NESTLEIND.NS", "Consumer Staples", "Packaged Foods")
        assert cls in ("halal", "review")  # packaged foods is borderline


class TestHalalScreener:
    def test_clean_it_stock_passes(self):
        data = _make_data(
            sector="Technology", industry="Software—Application",
            symbol="TCS.NS",
            total_debt=50, total_assets=1000, market_cap=5000,
            cash=100, receivables=150, ppe=400,
        )
        result = screen("TCS.NS", data)
        assert result.passed is True

    def test_bank_fails_sector_test(self):
        data = _make_data(sector="Financial Services", industry="Banks—Diversified",
                          symbol="HDFCBANK.NS")
        result = screen("HDFCBANK.NS", data)
        assert result.passed is False
        assert result.classification == "haram"

    def test_high_debt_fails(self):
        # Debt = 400 / Assets = 1000 = 40% > 30% AAOIFI threshold
        data = _make_data(total_debt=400, total_assets=1000, market_cap=2000)
        result = screen("TEST.NS", data)
        assert result.passed is False
        assert any("Debt/Assets" in r for r in result.fail_reasons)

    def test_high_interest_income_fails(self):
        # Interest income = 60 / revenue = 100 = 60% > 5% threshold
        data = _make_data(revenue=100, interest_income=60, total_assets=1000,
                          total_debt=10, market_cap=500)
        result = screen("TEST.NS", data)
        assert result.passed is False
        assert any("Interest income" in r for r in result.fail_reasons)

    def test_high_receivables_fails(self):
        # Receivables = 600 / assets = 1000 = 60% > 49%
        data = _make_data(receivables=600, total_assets=1000, total_debt=10, market_cap=500)
        result = screen("TEST.NS", data)
        assert result.passed is False
        assert any("Receivables" in r for r in result.fail_reasons)

    def test_impure_income_pct_calculated(self):
        data = _make_data(revenue=1000, interest_income=30, net_income=100,
                          total_debt=20, total_assets=500, market_cap=2000)
        result = screen("TEST.NS", data)
        if result.passed:
            assert result.impure_income_pct > 0

    def test_debt_to_market_cap_fails(self):
        # Debt = 400, market_cap = 800 → 50% > 33%
        data = _make_data(total_debt=400, total_assets=5000, market_cap=800,
                          cash=100, receivables=200, ppe=3000)
        result = screen("TEST.NS", data)
        assert result.passed is False
        assert any("MarketCap" in r for r in result.fail_reasons)
