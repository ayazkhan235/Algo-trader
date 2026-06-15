"""
Fetches fundamental and price data for NSE stocks via yfinance.
Uses concurrent fetching with a thread pool and disk caching.
"""
import time
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from data import cache

_CACHE_TTL = 24  # hours


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def fetch_ticker_data(symbol: str, refresh: bool = False) -> Optional[dict]:
    """
    Returns a unified dict with info + annual balance sheet + income statement.
    All financial values in INR (crores as returned by yfinance for NSE).
    """
    cache_key = f"ticker_{symbol}"
    if not refresh:
        cached = cache.get(cache_key, ttl_hours=_CACHE_TTL)
        if cached:
            return cached

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None  # delisted or bad symbol

        # ── Balance sheet (annual, up to 4 years) ──────────────────────────
        bs = ticker.balance_sheet
        # ── Income statement (annual, up to 4 years) ────────────────────────
        inc = ticker.financials
        # ── Cash flow (annual) ──────────────────────────────────────────────
        cf = ticker.cashflow

        def col_series(df: pd.DataFrame, row: str) -> list:
            """Extract up to 4 years of a balance sheet / income row, most recent first."""
            if df is None or df.empty or row not in df.index:
                return []
            return [_safe_float(v) for v in df.loc[row].values[:4]]

        result = {
            "symbol": symbol,
            "info": {
                "name":            info.get("longName", ""),
                "sector":          info.get("sector", ""),
                "industry":        info.get("industry", ""),
                "market_cap":      _safe_float(info.get("marketCap")),
                "current_price":   _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
                "trailing_pe":     _safe_float(info.get("trailingPE")),
                "forward_pe":      _safe_float(info.get("forwardPE")),
                "price_to_book":   _safe_float(info.get("priceToBook")),
                "ev_to_ebitda":    _safe_float(info.get("enterpriseToEbitda")),
                "price_to_sales":  _safe_float(info.get("priceToSalesTrailing12Months")),
                "roe":             _safe_float(info.get("returnOnEquity")),
                "roa":             _safe_float(info.get("returnOnAssets")),
                "net_margin":      _safe_float(info.get("profitMargins")),
                "operating_margin":_safe_float(info.get("operatingMargins")),
                "gross_margin":    _safe_float(info.get("grossMargins")),
                "revenue_growth":  _safe_float(info.get("revenueGrowth")),
                "earnings_growth": _safe_float(info.get("earningsGrowth")),
                "free_cashflow":   _safe_float(info.get("freeCashflow")),
                "operating_cashflow": _safe_float(info.get("operatingCashflow")),
                "total_debt":      _safe_float(info.get("totalDebt")),
                "current_ratio":   _safe_float(info.get("currentRatio")),
                "quick_ratio":     _safe_float(info.get("quickRatio")),
                "dividend_yield":  _safe_float(info.get("dividendYield")),
                "payout_ratio":    _safe_float(info.get("payoutRatio")),
                "beta":            _safe_float(info.get("beta")),
                "52w_high":        _safe_float(info.get("fiftyTwoWeekHigh")),
                "52w_low":         _safe_float(info.get("fiftyTwoWeekLow")),
                "shares_outstanding": _safe_float(info.get("sharesOutstanding")),
                "enterprise_value":   _safe_float(info.get("enterpriseValue")),
                "ebitda":             _safe_float(info.get("ebitda")),
                "trailing_eps":       _safe_float(info.get("trailingEps")),
                "book_value":         _safe_float(info.get("bookValue")),
            },
            "financials": {
                # Income statement rows
                "revenue":          col_series(inc, "Total Revenue"),
                "gross_profit":     col_series(inc, "Gross Profit"),
                "ebit":             col_series(inc, "EBIT"),
                "net_income":       col_series(inc, "Net Income"),
                "interest_expense": col_series(inc, "Interest Expense"),
                "interest_income":  col_series(inc, "Interest Income"),
                # Balance sheet rows
                "total_assets":     col_series(bs, "Total Assets"),
                "total_debt_bs":    col_series(bs, "Total Debt"),
                "net_receivables":  col_series(bs, "Net Receivables"),
                "cash":             col_series(bs, "Cash And Cash Equivalents"),
                "ppe":              col_series(bs, "Net PPE"),  # Property, Plant & Equipment
                "equity":           col_series(bs, "Stockholders Equity"),
                "current_assets":   col_series(bs, "Current Assets"),
                "current_liabilities": col_series(bs, "Current Liabilities"),
                "retained_earnings":   col_series(bs, "Retained Earnings"),
                # Cash flow rows
                "capex":            col_series(cf, "Capital Expenditure"),
                "operating_cf":     col_series(cf, "Operating Cash Flow"),
                "free_cf":          col_series(cf, "Free Cash Flow"),
            },
        }

        cache.set(cache_key, result)
        return result

    except Exception as e:
        print(f"[fetcher] Error fetching {symbol}: {e}")
        return None


def fetch_batch(
    symbols: list[str],
    refresh: bool = False,
    max_workers: int = 10,
    delay: float = 0.2,
) -> dict[str, dict]:
    """
    Fetches multiple tickers concurrently. Returns {symbol: data_dict}.
    Skips symbols where fetch returns None.
    """
    results: dict[str, dict] = {}

    def _fetch(sym: str) -> tuple[str, Optional[dict]]:
        time.sleep(delay)
        return sym, fetch_ticker_data(sym, refresh=refresh)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch, s): s for s in symbols}
        done = 0
        for future in as_completed(futures):
            sym, data = future.result()
            done += 1
            if data:
                results[sym] = data
            if done % 50 == 0:
                print(f"[fetcher] {done}/{len(symbols)} fetched, {len(results)} valid")

    print(f"[fetcher] Complete: {len(results)}/{len(symbols)} symbols returned data")
    return results
