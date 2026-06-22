"""
Backtest: monthly-SIP simulation of the strategy's current basket vs NIFTY.

What it does
------------
Takes the stocks the bot currently rates BUY / STRONG BUY, then simulates
investing a fixed amount every month (your real ₹7k plan) split equally across
them over the past N years, and compares the result with the same SIP into the
NIFTY 50 index.

⚠️ Honest limitations (read this)
---------------------------------
• Yahoo only exposes *current* fundamentals, not what was known on a past date.
  So the basket is chosen with today's knowledge → this backtest has
  LOOK-AHEAD and SURVIVORSHIP bias. Treat the result as an optimistic upper
  bound / sanity check, NOT a broker-grade expectation.
• A clean, point-in-time fundamental backtest needs paid historical data.

The SIP math itself (below) is unbiased and unit-tested.
"""
from __future__ import annotations


def simulate_sip(months: list, monthly_prices: dict[str, list], monthly_amount: float) -> dict:
    """
    Pure SIP simulator (no network — unit-testable).

    months:          ordered list of period labels (len = N)
    monthly_prices:  {symbol: [price_or_None per month]} aligned to `months`
    monthly_amount:  cash invested each contributing month, split equally across
                     symbols that have a valid price that month.

    Returns dict with invested, final_value, profit, return_pct, annual_return,
    per-symbol breakdown, and the cashflow schedule.
    """
    shares: dict[str, float] = {s: 0.0 for s in monthly_prices}
    last_price: dict[str, float] = {}
    invested = 0.0
    cashflows: list[tuple[int, float]] = []  # (month_index, signed amount)

    for i in range(len(months)):
        valid = [s for s in monthly_prices if _px(monthly_prices[s], i) is not None]
        if not valid:
            continue
        per = monthly_amount / len(valid)
        for s in valid:
            price = monthly_prices[s][i]
            shares[s] += per / price
            last_price[s] = price
        invested += monthly_amount
        cashflows.append((i, -monthly_amount))

    # Mark to the latest available price per symbol
    for s in monthly_prices:
        lp = _last_valid(monthly_prices[s])
        if lp is not None:
            last_price[s] = lp

    final_value = sum(shares[s] * last_price.get(s, 0.0) for s in shares)
    cashflows.append((len(months) - 1, final_value))

    profit = final_value - invested
    return_pct = (profit / invested) if invested else 0.0
    annual = _annualised(cashflows)

    breakdown = {
        s: {
            "shares": round(shares[s], 4),
            "last_price": round(last_price.get(s, 0.0), 2),
            "value": round(shares[s] * last_price.get(s, 0.0), 2),
        }
        for s in sorted(shares, key=lambda x: -shares[x] * last_price.get(x, 0.0))
    }

    return {
        "invested": round(invested, 2),
        "final_value": round(final_value, 2),
        "profit": round(profit, 2),
        "return_pct": round(return_pct, 4),
        "annual_return": round(annual, 4) if annual is not None else None,
        "months": len([c for c in cashflows[:-1]]),
        "breakdown": breakdown,
    }


def _px(series: list, i: int):
    v = series[i] if i < len(series) else None
    return v if (v is not None and v == v and v > 0) else None  # v==v filters NaN


def _last_valid(series: list):
    for v in reversed(series):
        if v is not None and v == v and v > 0:
            return v
    return None


def _annualised(cashflows: list[tuple[int, float]]):
    """Money-weighted (XIRR-style) annualised return from monthly cashflows."""
    if len(cashflows) < 2:
        return None

    def npv(monthly_rate: float) -> float:
        return sum(cf / ((1 + monthly_rate) ** m) for m, cf in cashflows)

    lo, hi = -0.95, 1.0
    if npv(lo) * npv(hi) > 0:
        return None  # no sign change → can't bracket a root
    for _ in range(200):
        mid = (lo + hi) / 2
        v = npv(mid)
        if abs(v) < 1e-6:
            break
        if npv(lo) * v < 0:
            hi = mid
        else:
            lo = mid
    monthly = (lo + hi) / 2
    return (1 + monthly) ** 12 - 1


# ─────────────────────────────────────────────────────────────────────────────
# Network-backed price loading (yfinance)
# ─────────────────────────────────────────────────────────────────────────────
def load_monthly_prices(symbols: list[str], years: int) -> tuple[list, dict[str, list]]:
    """Fetch monthly closing prices for `symbols` over the last `years` years."""
    import yfinance as yf

    per_symbol: dict[str, dict] = {}
    all_months: set = set()
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period=f"{years}y", interval="1mo")
            closes = hist["Close"].dropna()
            m = {ts.strftime("%Y-%m"): float(p) for ts, p in closes.items()}
        except Exception as e:  # noqa: BLE001
            print(f"[backtest] {sym}: price load failed ({e})")
            m = {}
        per_symbol[sym] = m
        all_months.update(m.keys())

    months = sorted(all_months)
    aligned = {sym: [per_symbol[sym].get(mo) for mo in months] for sym in symbols}
    return months, aligned
