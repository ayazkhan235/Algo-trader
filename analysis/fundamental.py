"""
Computes all fundamental metrics from raw ticker data.
Prefers multi-year computed values over single-point yfinance info fields.
"""
from typing import Optional
import math


def _first(lst: list) -> Optional[float]:
    for v in lst:
        if v is not None:
            return v
    return None


def cagr(values: list, years: int = 3) -> Optional[float]:
    """
    Compute CAGR from a list [most_recent, ..., oldest].
    Returns None if insufficient data or negative base.
    """
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    newest, oldest = vals[0], vals[min(years, len(vals) - 1)]
    if oldest is None or oldest <= 0 or newest is None:
        return None
    n = min(years, len(vals) - 1)
    return (newest / oldest) ** (1 / n) - 1


def earnings_consistency(net_incomes: list) -> float:
    """Fraction of years with positive net income (0.0 – 1.0)."""
    vals = [v for v in net_incomes if v is not None]
    if not vals:
        return 0.0
    return sum(1 for v in vals if v > 0) / len(vals)


def graham_number(eps: Optional[float], book_value: Optional[float]) -> Optional[float]:
    """Benjamin Graham intrinsic value: sqrt(22.5 × EPS × Book Value per share)."""
    if eps and book_value and eps > 0 and book_value > 0:
        return math.sqrt(22.5 * eps * book_value)
    return None


def compute(symbol: str, data: dict) -> dict:
    """
    Returns a flat metrics dict for a single ticker.
    All ratios are floats (or None if data missing).
    """
    info = data.get("info", {})
    fin = data.get("financials", {})

    revenues    = fin.get("revenue", [])
    net_incomes = fin.get("net_income", [])
    gross_p     = fin.get("gross_profit", [])
    ebits       = fin.get("ebit", [])
    int_exp     = fin.get("interest_expense", [])
    total_assets= fin.get("total_assets", [])
    total_debt  = fin.get("total_debt_bs", [])
    equity      = fin.get("equity", [])
    curr_assets = fin.get("current_assets", [])
    curr_liab   = fin.get("current_liabilities", [])
    capex_vals  = fin.get("capex", [])
    fcf_vals    = fin.get("free_cf", [])
    op_cf_vals  = fin.get("operating_cf", [])
    ppe_vals    = fin.get("ppe", [])
    ret_earn    = fin.get("retained_earnings", [])

    rev0    = _first(revenues)
    ni0     = _first(net_incomes)
    asset0  = _first(total_assets)
    debt0   = _first(total_debt)
    eq0     = _first(equity)
    ebit0   = _first(ebits)
    ie0     = _first(int_exp)
    ca0     = _first(curr_assets)
    cl0     = _first(curr_liab)
    capex0  = _first(capex_vals)
    fcf0    = info.get("free_cashflow") or _first(fcf_vals)
    op_cf0  = info.get("operating_cashflow") or _first(op_cf_vals)

    mktcap  = info.get("market_cap")
    price   = info.get("current_price")
    ev      = info.get("enterprise_value")
    ebitda  = info.get("ebitda")

    # ── Valuation ─────────────────────────────────────────────────────────────
    trailing_pe  = info.get("trailing_pe")
    forward_pe   = info.get("forward_pe")
    price_book   = info.get("price_to_book")
    ev_ebitda    = info.get("ev_to_ebitda") or (ev / ebitda if ev and ebitda and ebitda > 0 else None)
    price_sales  = info.get("price_to_sales")
    price_fcf    = (mktcap / fcf0) if mktcap and fcf0 and fcf0 > 0 else None
    eps          = info.get("trailing_eps")
    book_val     = info.get("book_value")
    graham       = graham_number(eps, book_val)
    peg          = (trailing_pe / (info.get("earnings_growth", 0) * 100)
                    if trailing_pe and info.get("earnings_growth") and info.get("earnings_growth") > 0
                    else None)
    earnings_yield = (1 / trailing_pe) if trailing_pe and trailing_pe > 0 else None

    # ── Profitability ─────────────────────────────────────────────────────────
    roe          = info.get("roe")
    roa          = info.get("roa")
    net_margin   = info.get("net_margin")
    op_margin    = info.get("operating_margin")
    gross_margin = info.get("gross_margin")

    # ROCE = EBIT / Capital Employed (Total Assets - Current Liabilities)
    roce = None
    if ebit0 and asset0 and cl0:
        cap_employed = asset0 - cl0
        if cap_employed > 0:
            roce = ebit0 / cap_employed

    # Gross margin trend (expanding = positive)
    gm_trend = None
    if len(gross_p) >= 2 and len(revenues) >= 2 and revenues[0] and revenues[-1]:
        gm_now  = (gross_p[0] / revenues[0]) if gross_p[0] and revenues[0] else None
        gm_then = (gross_p[-1] / revenues[-1]) if gross_p[-1] and revenues[-1] else None
        if gm_now is not None and gm_then is not None:
            gm_trend = gm_now - gm_then  # positive = expanding

    # ── Growth ────────────────────────────────────────────────────────────────
    rev_cagr_3y  = cagr(revenues, 3)
    earn_cagr_3y = cagr(net_incomes, 3)
    fcf_cagr_3y  = cagr(fcf_vals, 3)
    earn_consist = earnings_consistency(net_incomes)

    # ── Quality / Moat ────────────────────────────────────────────────────────
    cash_conversion = (fcf0 / ni0) if fcf0 and ni0 and ni0 > 0 else None
    capex_intensity = (abs(capex0) / rev0) if capex0 and rev0 and rev0 > 0 else None

    # ── Financial Health ──────────────────────────────────────────────────────
    interest_coverage = (ebit0 / abs(ie0)) if ebit0 and ie0 and ie0 != 0 else None
    current_ratio = info.get("current_ratio") or (ca0 / cl0 if ca0 and cl0 and cl0 > 0 else None)
    quick_ratio   = info.get("quick_ratio")
    fcf_yield     = (fcf0 / mktcap) if fcf0 and mktcap and mktcap > 0 else None

    # ── India-specific ────────────────────────────────────────────────────────
    dividend_yield = info.get("dividend_yield")
    beta           = info.get("beta")
    high_52w       = info.get("52w_high")
    low_52w        = info.get("52w_low")
    pct_from_52w_high = ((price - high_52w) / high_52w) if price and high_52w else None
    pct_from_52w_low  = ((price - low_52w) / low_52w) if price and low_52w else None

    return {
        "symbol":           symbol,
        "name":             info.get("name", ""),
        "sector":           info.get("sector", ""),
        "industry":         info.get("industry", ""),
        "price":            price,
        "market_cap":       mktcap,
        # Valuation
        "trailing_pe":      trailing_pe,
        "forward_pe":       forward_pe,
        "price_book":       price_book,
        "ev_ebitda":        ev_ebitda,
        "price_sales":      price_sales,
        "price_fcf":        price_fcf,
        "peg":              peg,
        "graham_number":    graham,
        "earnings_yield":   earnings_yield,
        # Profitability
        "roe":              roe,
        "roa":              roa,
        "roce":             roce,
        "net_margin":       net_margin,
        "op_margin":        op_margin,
        "gross_margin":     gross_margin,
        "gm_trend":         gm_trend,
        # Growth
        "rev_cagr_3y":      rev_cagr_3y,
        "earn_cagr_3y":     earn_cagr_3y,
        "fcf_cagr_3y":      fcf_cagr_3y,
        "earn_consistency": earn_consist,
        # Quality
        "cash_conversion":  cash_conversion,
        "capex_intensity":  capex_intensity,
        "fcf_yield":        fcf_yield,
        # Health
        "interest_coverage":interest_coverage,
        "current_ratio":    current_ratio,
        "quick_ratio":      quick_ratio,
        # India
        "dividend_yield":   dividend_yield,
        "beta":             beta,
        "pct_from_52w_high":pct_from_52w_high,
        "pct_from_52w_low": pct_from_52w_low,
    }
