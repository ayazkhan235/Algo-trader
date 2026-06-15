"""
Auto-executes paper trades based on buy/sell signals.
Runs daily — checks new buy signals and monitors open positions for sell triggers.
"""
from typing import Optional
import config
from paper_trading.sqlite_engine import (
    init_db, open_trade, close_trade,
    get_open_trades, is_already_held, portfolio_summary,
)
from signals.generator import BuySignal
from screening.halal_screener import HalalResult


def execute_buy_signals(signals: list[BuySignal]) -> list[dict]:
    """
    Places paper buy trades for STRONG BUY and BUY signals.
    Skips if symbol is already held.
    """
    init_db()
    executed = []

    for sig in signals:
        if sig.tier not in ("STRONG BUY", "BUY"):
            continue
        if is_already_held(sig.symbol):
            continue
        if not sig.metrics.get("price"):
            continue

        trade_id = open_trade(
            symbol=sig.symbol,
            name=sig.name,
            entry_price=sig.metrics["price"],
            signal_tier=sig.tier,
            score=sig.score,
        )
        executed.append({"trade_id": trade_id, "symbol": sig.symbol,
                         "price": sig.metrics["price"], "tier": sig.tier})

    return executed


def check_sell_signals(
    current_scores: dict[str, dict],
    current_metrics: dict[str, dict],
    halal_results: dict[str, HalalResult],
    current_prices: dict[str, float],
) -> list[dict]:
    """
    Reviews open positions and closes any that trigger a sell rule.
    Returns list of closed trade dicts.
    """
    init_db()
    open_trades = get_open_trades()
    closed = []

    for trade in open_trades:
        sym = trade["symbol"]
        price = current_prices.get(sym, trade["entry_price"])
        score_dict = current_scores.get(sym, {})
        metrics = current_metrics.get(sym, {})
        halal = halal_results.get(sym)

        reason = _check_sell_reason(trade, price, score_dict, metrics, halal)

        if reason:
            result = close_trade(trade["id"], price, reason)
            closed.append({"symbol": sym, "reason": reason, **result})

    return closed


def _check_sell_reason(
    trade: dict,
    current_price: float,
    score_dict: dict,
    metrics: dict,
    halal: Optional[HalalResult],
) -> Optional[str]:
    entry_price = trade["entry_price"]
    drawdown = (current_price - entry_price) / entry_price

    # Hard stop loss
    if drawdown <= config.SELL_DRAWDOWN_STOP:
        return f"Stop loss hit: {drawdown:.1%} from entry"

    # Halal breach
    if halal and not halal.passed:
        return f"Halal breach: {halal.fail_reasons[0] if halal.fail_reasons else 'Failed screen'}"

    # Score collapse
    composite = score_dict.get("composite")
    if composite is not None and composite < config.SELL_SCORE_FLOOR:
        return f"Score collapsed to {composite:.0f} (below {config.SELL_SCORE_FLOOR})"

    # Extreme overvaluation
    pe = metrics.get("trailing_pe")
    if pe and pe > config.MAX_PE_SELL:
        return f"Extreme overvaluation: P/E {pe:.1f} > {config.MAX_PE_SELL}"

    # Earnings manipulation detected
    beneish = score_dict.get("beneish_m")
    if beneish and beneish > config.BENEISH_M_THRESHOLD:
        return f"Beneish M-Score {beneish:.2f} — earnings manipulation risk"

    # Promoter pledge spike
    hard_fails = score_dict.get("hard_gate_fails", [])
    pledge_fail = next((f for f in hard_fails if "pledge" in f.lower()), None)
    if pledge_fail:
        return f"Promoter pledge: {pledge_fail}"

    return None


def print_portfolio_summary(current_prices: dict[str, float] = None) -> dict:
    summary = portfolio_summary(current_prices)
    print("\n── Paper Portfolio Summary ───────────────────────────")
    print(f"  Open positions : {summary['open_positions']}")
    print(f"  Total invested : ₹{summary['total_invested']:,.0f}")
    print(f"  Current value  : ₹{summary['total_value']:,.0f}")
    print(f"  Open P&L       : ₹{summary['open_pnl_inr']:+,.0f}  ({summary['open_pnl_pct']:+.1%})")
    print(f"  Closed trades  : {summary['closed_trades']}  (P&L: ₹{summary['closed_pnl_inr']:+,.0f})")
    print(f"  Total P&L      : ₹{summary['total_pnl_inr']:+,.0f}")
    print("──────────────────────────────────────────────────────\n")
    return summary
