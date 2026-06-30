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


def effective_score(base_score: float, news: dict, max_bonus: float = 5.0) -> float:
    """Conviction score nudged by news sentiment (bounded ±max_bonus)."""
    if not news:
        return base_score
    return base_score + max(-max_bonus, min(max_bonus, news.get("score", 0.0) * max_bonus))


def execute_buy_signals(signals: list[BuySignal], news_map: dict = None,
                        regime_gate: dict = None) -> list[dict]:
    """
    Places paper buy trades mirroring a real ₹X/month SIP plan.

    Each calendar month a fresh `config.MONTHLY_BUDGET_INR` is available to
    deploy; positions accumulate month over month (total holdings capped at
    `config.MAX_POSITIONS`). Within a month, up to `config.MAX_NEW_PER_MONTH`
    new names are bought, highest news-adjusted conviction first, in whole
    shares only. Already-held names are skipped.

    `regime_gate` (from `pre_market.assess_regime_gate`) tunes accumulation to
    the market's multi-week trend: action 'pause' keeps cash during a confirmed
    downtrend (NIFTY below its 200-day average); a 'dip' inside a healthy
    uptrend raises the deployable budget (`budget_mult`) so we buy more cheaply.
    """
    from datetime import date
    init_db()
    news_map = news_map or {}
    regime_gate = regime_gate or {}
    executed = []

    if regime_gate.get("action") == "pause":
        print(f"[paper] Regime PAUSE — {regime_gate.get('reason', 'downtrend')}; "
              f"no new buys, preserving cash")
        return executed

    budget_mult = regime_gate.get("budget_mult", 1.0) or 1.0
    open_trades = get_open_trades()
    month = date.today().isoformat()[:7]   # 'YYYY-MM'
    invested_this_month = sum(
        t["position_inr"] for t in open_trades
        if (t.get("entry_date") or "")[:7] == month
    )
    month_budget = config.MONTHLY_BUDGET_INR * budget_mult
    if budget_mult != 1.0:
        print(f"[paper] Dip tilt — {regime_gate.get('reason', 'dip')}; "
              f"month budget ₹{config.MONTHLY_BUDGET_INR:,.0f}→₹{month_budget:,.0f}")
    month_remaining = month_budget - invested_this_month
    free_slots = config.MAX_POSITIONS - len(open_trades)

    if month_remaining < 1 or free_slots <= 0:
        print(f"[paper] This month's ₹{config.MONTHLY_BUDGET_INR:,.0f} budget already "
              f"deployed (₹{invested_this_month:,.0f}) or position cap reached "
              f"({len(open_trades)}/{config.MAX_POSITIONS}) — no new trades")
        return executed

    # Highest-conviction, not-yet-held BUY/STRONG BUY signals with a price
    candidates = [
        s for s in signals
        if s.tier in ("STRONG BUY", "BUY")
        and s.metrics.get("price")
        and not is_already_held(s.symbol)
    ]
    candidates.sort(key=lambda s: effective_score(s.score, news_map.get(s.symbol)), reverse=True)
    n = min(free_slots, getattr(config, "MAX_NEW_PER_MONTH", 3), len(candidates))
    candidates = candidates[:n]
    if not candidates:
        return executed

    per_position = month_remaining / len(candidates)

    for sig in candidates:
        price = sig.metrics["price"]
        qty = int(per_position // price)   # whole shares only (NSE has no fractions)
        if qty < 1:
            # too expensive to buy even 1 share with this slice of the budget
            print(f"[paper] SKIP {sig.symbol} — ₹{price:,.0f} > slice ₹{per_position:,.0f}")
            continue
        invested = qty * price
        news = news_map.get(sig.symbol) or {}
        headline = news.get("top_headline") or ""
        trade_id = open_trade(
            symbol=sig.symbol,
            name=sig.name,
            entry_price=price,
            signal_tier=sig.tier,
            score=sig.score,
            position_size_inr=invested,
            news=headline or None,
            qty=qty,
        )
        executed.append({
            "trade_id": trade_id,
            "symbol": sig.symbol,
            "name": sig.name,
            "price": price,
            "tier": sig.tier,
            "score": sig.score,
            "sector": sig.sector,
            "invested": round(invested, 2),
            "qty": qty,
            "strengths": list(sig.strengths[:3]),
            "news_headline": headline,
            "news_label": news.get("label", ""),
        })

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
    init_db()
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
