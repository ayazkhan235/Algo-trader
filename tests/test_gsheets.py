"""Unit tests for the Google Sheets row builders (no network)."""
from integrations import gsheets


def _trade(**kw):
    base = dict(
        id=1, symbol="RELIANCE.NS", name="Reliance", entry_date="2026-06-01",
        entry_price=100.0, quantity=10.0, position_inr=1000.0, signal_tier="BUY",
        score=72.0, status="OPEN", exit_date=None, exit_price=None,
        exit_reason=None, pnl_inr=None, pnl_pct=None, hold_days=None,
    )
    base.update(kw)
    return base


def test_trade_rows_open_position_computes_pct_change():
    rows = gsheets.build_trade_rows([_trade()], {"RELIANCE.NS": 110.0})
    assert rows[0] == gsheets.TRADES_HEADER
    r = rows[1]
    # current price, current value, unrealized pnl, % change
    assert r[9] == 110.0
    assert r[10] == 1100.0
    assert r[11] == 100.0
    assert r[12] == 0.1


def test_trade_rows_open_falls_back_to_entry_when_no_price():
    rows = gsheets.build_trade_rows([_trade()], {})
    r = rows[1]
    assert r[9] == 100.0  # falls back to entry price
    assert r[12] == 0.0   # 0% change


def test_trade_rows_closed_position_blanks_live_fields():
    t = _trade(status="CLOSED", exit_price=120.0, pnl_inr=200.0, pnl_pct=0.2, hold_days=20)
    rows = gsheets.build_trade_rows([t], {"RELIANCE.NS": 999.0})
    r = rows[1]
    assert r[9] == "" and r[12] == ""  # live fields blank for closed
    assert r[17] == 200.0 and r[18] == 0.2  # realized fields populated


def test_snapshot_and_daily_headers():
    assert gsheets.build_snapshot_rows([])[0] == gsheets.SNAP_HEADER
    assert gsheets.build_daily_rows([])[0] == gsheets.DAILY_HEADER
