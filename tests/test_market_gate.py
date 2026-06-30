"""Unit tests for the market-open gate (pure, no network)."""
import config
from market_intelligence.pre_market import assess_market_gate


def test_block_on_sharp_selloff():
    gate = assess_market_gate({"change_pct": -0.02})
    assert gate["action"] == "block"
    assert gate["score_bump"] == 0.0


def test_caution_on_soft_tape():
    gate = assess_market_gate({"change_pct": -0.01})
    assert gate["action"] == "caution"
    assert gate["score_bump"] == config.NIFTY_GATE_SCORE_BUMP


def test_allow_on_constructive_tape():
    gate = assess_market_gate({"change_pct": 0.005})
    assert gate["action"] == "allow"


def test_allow_when_no_intraday_read():
    assert assess_market_gate(None)["action"] == "allow"
    assert assess_market_gate({"change_pct": None})["action"] == "allow"


def test_boundary_just_inside_caution():
    # Exactly at the caution threshold counts as caution (<=).
    gate = assess_market_gate({"change_pct": config.NIFTY_GATE_CAUTION_PCT})
    assert gate["action"] == "caution"


def test_gate_disabled_always_allows(monkeypatch):
    monkeypatch.setattr(config, "MARKET_GATE_ENABLED", False)
    assert assess_market_gate({"change_pct": -0.05})["action"] == "allow"
