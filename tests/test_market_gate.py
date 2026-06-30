"""Unit tests for the regime / dip-accumulation gate (pure, no network)."""
import config
from market_intelligence.pre_market import assess_regime_gate


def _trend(price, sma_short, sma_long, week_change=0.0):
    return {"price": price, "sma_short": sma_short, "sma_long": sma_long,
            "week_change": week_change}


def test_pause_when_below_long_ma():
    # NIFTY under its 200-day average = confirmed downtrend.
    gate = assess_regime_gate(_trend(95, 100, 100))
    assert gate["action"] == "pause"
    assert gate["budget_mult"] == 1.0


def test_dip_buy_when_below_short_ma_but_healthy():
    # Above the 200-day (healthy) but below the 50-day (short-term dip).
    gate = assess_regime_gate(_trend(102, 105, 100))
    assert gate["action"] == "allow"
    assert gate["dip"] is True
    assert gate["budget_mult"] == config.DIP_BUDGET_MULT


def test_dip_buy_on_weekly_drop():
    # Above both MAs but down sharply on the week still counts as a dip.
    gate = assess_regime_gate(_trend(110, 105, 100, week_change=-0.03))
    assert gate["action"] == "allow"
    assert gate["dip"] is True


def test_normal_accumulation_in_calm_uptrend():
    gate = assess_regime_gate(_trend(110, 105, 100, week_change=0.005))
    assert gate["action"] == "allow"
    assert gate["dip"] is False
    assert gate["budget_mult"] == 1.0


def test_missing_trend_allows_normal_buying():
    gate = assess_regime_gate(None)
    assert gate["action"] == "allow"
    assert gate["budget_mult"] == 1.0


def test_gate_disabled_always_allows(monkeypatch):
    monkeypatch.setattr(config, "REGIME_GATE_ENABLED", False)
    gate = assess_regime_gate(_trend(80, 100, 100))   # deep downtrend
    assert gate["action"] == "allow"
