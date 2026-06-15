"""Unit tests for Piotroski, Altman Z, and Beneish M scoring models."""
import pytest
from analysis.scoring_models import piotroski_f_score, altman_z_score, beneish_m_score


def _healthy_data():
    return {
        "info": {"market_cap": 50000, "shares_outstanding": 100},
        "financials": {
            "net_income":     [800, 600],
            "total_assets":   [10000, 9000],
            "operating_cf":   [1000, 800],
            "total_debt_bs":  [1000, 1200],
            "current_assets": [3000, 2500],
            "current_liabilities": [1000, 1100],
            "gross_profit":   [4000, 3500],
            "revenue":        [10000, 9000],
            "ebit":           [1200, 900],
            "retained_earnings": [5000, 4200],
            "ppe":            [4000, 3800],
            "capex":          [-500, -400],
            "free_cf":        [500, 400],
            "net_receivables":[800, 700],
            "cash":           [500, 400],
            "equity":         [7000, 6500],
            "interest_expense": [-100, -120],
            "interest_income": [],
        },
    }


class TestPiotroski:
    def test_healthy_company_scores_high(self):
        score, breakdown = piotroski_f_score(_healthy_data())
        assert score >= 5, f"Expected >= 5, got {score}. Breakdown: {breakdown}"

    def test_returns_0_to_9(self):
        score, _ = piotroski_f_score(_healthy_data())
        assert 0 <= score <= 9

    def test_empty_data_returns_low_score(self):
        score, _ = piotroski_f_score({"info": {}, "financials": {}})
        assert score <= 3

    def test_positive_roa_scores(self):
        _, breakdown = piotroski_f_score(_healthy_data())
        assert breakdown["roa_positive"] == 1

    def test_positive_cf_scores(self):
        _, breakdown = piotroski_f_score(_healthy_data())
        assert breakdown["operating_cf_pos"] == 1


class TestAltmanZ:
    def test_healthy_company_safe_zone(self):
        z = altman_z_score(_healthy_data())
        assert z is not None
        assert z > 1.81, f"Expected > 1.81, got {z}"

    def test_returns_none_without_assets(self):
        data = {"info": {}, "financials": {}}
        z = altman_z_score(data)
        assert z is None

    def test_distressed_company_low_z(self):
        distressed = {
            "info": {"market_cap": 100},
            "financials": {
                "total_assets":     [10000],
                "current_assets":   [500],
                "current_liabilities": [5000],  # negative working capital
                "retained_earnings": [-3000],
                "ebit":             [-500],
                "revenue":          [1000],
                "total_debt_bs":    [8000],
                "net_receivables":  [], "cash": [], "ppe": [],
                "net_income": [], "gross_profit": [], "operating_cf": [],
                "capex": [], "free_cf": [], "equity": [], "interest_expense": [],
                "interest_income": [],
            },
        }
        z = altman_z_score(distressed)
        assert z is not None and z < 2.0


class TestBeneish:
    def test_clean_company_below_threshold(self):
        m = beneish_m_score(_healthy_data())
        # Clean, growing company should score below 0; threshold for manipulation is -1.78
        if m is not None:
            assert m < 0, f"Clean company M-Score should be negative, got {m}"

    def test_returns_none_without_two_years(self):
        data = {
            "info": {},
            "financials": {
                "revenue": [1000], "total_assets": [5000],
                "gross_profit": [], "net_income": [], "current_assets": [],
                "current_liabilities": [], "operating_cf": [], "net_receivables": [],
                "total_debt_bs": [], "ppe": [], "capex": [],
            },
        }
        m = beneish_m_score(data)
        assert m is None
