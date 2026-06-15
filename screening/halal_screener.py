"""
6-test halal screening engine.
Based on AAOIFI Standard No. 21 + Nifty50 Shariah Index methodology.

IMPORTANT: Uses total assets and market cap as denominators — NOT equity (D/E ratio).
All major Islamic finance standards use assets/market-cap based thresholds.
"""
from dataclasses import dataclass, field
from typing import Optional
import config
from screening.sector_map import classify


@dataclass
class HalalResult:
    symbol: str
    passed: bool
    classification: str          # "halal" | "haram" | "review"
    fail_reasons: list[str] = field(default_factory=list)
    pass_notes: list[str] = field(default_factory=list)
    impure_income_pct: float = 0.0   # for dividend purification
    # Financial ratios (for report display)
    debt_to_assets: Optional[float] = None
    debt_to_market_cap: Optional[float] = None
    cash_to_assets: Optional[float] = None
    receivables_to_assets: Optional[float] = None
    interest_income_pct: Optional[float] = None


def _first(lst: list) -> Optional[float]:
    """Return first non-None value from a list."""
    for v in lst:
        if v is not None:
            return v
    return None


def screen(symbol: str, data: dict) -> HalalResult:
    """
    Runs all 6 halal tests on a single stock.
    data = output of data.fetcher.fetch_ticker_data()
    """
    info = data.get("info", {})
    fin = data.get("financials", {})

    fail_reasons: list[str] = []
    pass_notes: list[str] = []

    # ── TEST 1: Sector / Industry ─────────────────────────────────────────────
    sector = info.get("sector", "")
    industry = info.get("industry", "")
    classification, reason = classify(symbol, sector, industry)

    if classification == "haram":
        return HalalResult(symbol=symbol, passed=False, classification="haram",
                           fail_reasons=[reason])

    if classification == "review":
        pass_notes.append(f"REVIEW FLAGGED: {reason}")

    # ── Extract balance sheet values ──────────────────────────────────────────
    total_assets     = _first(fin.get("total_assets", []))
    total_debt       = _first(fin.get("total_debt_bs", [])) or info.get("total_debt")
    cash             = _first(fin.get("cash", []))
    receivables      = _first(fin.get("net_receivables", []))
    ppe              = _first(fin.get("ppe", []))
    market_cap       = info.get("market_cap")
    revenue          = _first(fin.get("revenue", []))
    interest_income  = _first(fin.get("interest_income", []))

    debt_to_assets      = None
    debt_to_mktcap      = None
    cash_to_assets      = None
    receivables_to_assets = None
    interest_pct        = None

    # ── TEST 2: Debt / Total Assets ───────────────────────────────────────────
    if total_assets and total_assets > 0 and total_debt is not None:
        debt_to_assets = total_debt / total_assets
        threshold = config.get_debt_threshold()
        if debt_to_assets > threshold:
            fail_reasons.append(
                f"Debt/Assets {debt_to_assets:.1%} > {threshold:.0%} threshold"
            )
        else:
            pass_notes.append(f"Debt/Assets {debt_to_assets:.1%} ✓")

    if market_cap and market_cap > 0 and total_debt is not None:
        debt_to_mktcap = total_debt / market_cap
        if debt_to_mktcap > config.DEBT_TO_MARKET_CAP_MAX:
            fail_reasons.append(
                f"Debt/MarketCap {debt_to_mktcap:.1%} > {config.DEBT_TO_MARKET_CAP_MAX:.0%}"
            )
        else:
            pass_notes.append(f"Debt/MarketCap {debt_to_mktcap:.1%} ✓")

    # ── TEST 3: Cash & Interest-Bearing Securities / Total Assets ─────────────
    if total_assets and total_assets > 0 and cash is not None:
        cash_to_assets = cash / total_assets
        if cash_to_assets > config.CASH_SECURITIES_TO_ASSETS_MAX:
            fail_reasons.append(
                f"Cash/Assets {cash_to_assets:.1%} > {config.CASH_SECURITIES_TO_ASSETS_MAX:.0%}"
            )
        else:
            pass_notes.append(f"Cash/Assets {cash_to_assets:.1%} ✓")

    # ── TEST 4: Receivables / Total Assets ───────────────────────────────────
    if total_assets and total_assets > 0 and receivables is not None:
        receivables_to_assets = receivables / total_assets
        if receivables_to_assets > config.RECEIVABLES_TO_ASSETS_MAX:
            fail_reasons.append(
                f"Receivables/Assets {receivables_to_assets:.1%} > {config.RECEIVABLES_TO_ASSETS_MAX:.0%}"
            )
        else:
            pass_notes.append(f"Receivables/Assets {receivables_to_assets:.1%} ✓")

    # ── TEST 5: Interest Income / Revenue ─────────────────────────────────────
    if revenue and revenue > 0 and interest_income is not None and interest_income > 0:
        interest_pct = interest_income / revenue
        threshold = config.get_interest_income_threshold()
        if interest_pct > threshold:
            fail_reasons.append(
                f"Interest income {interest_pct:.1%} of revenue > {threshold:.1%} threshold"
            )
        else:
            pass_notes.append(f"Interest income {interest_pct:.1%} of revenue ✓")

    # ── TEST 6: Fixed Assets Floor (STRICT_INDIA / Zamzam Capital) ───────────
    if config.fixed_assets_floor_enabled():
        if total_assets and total_assets > 0 and ppe is not None:
            ppe_ratio = ppe / total_assets
            if ppe_ratio < config.FIXED_ASSETS_FLOOR:
                fail_reasons.append(
                    f"Fixed assets {ppe_ratio:.1%} of total assets < "
                    f"{config.FIXED_ASSETS_FLOOR:.0%} floor (Zamzam Capital)"
                )
            else:
                pass_notes.append(f"Fixed assets {ppe_ratio:.1%} ✓")

    # ── Dividend purification estimate ────────────────────────────────────────
    impure_pct = 0.0
    net_income = _first(fin.get("net_income", []))
    if net_income and net_income > 0 and interest_income and interest_income > 0:
        impure_pct = min(interest_income / net_income, 1.0)

    passed = len(fail_reasons) == 0

    return HalalResult(
        symbol=symbol,
        passed=passed,
        classification=classification if passed else "haram",
        fail_reasons=fail_reasons,
        pass_notes=pass_notes,
        impure_income_pct=round(impure_pct, 4),
        debt_to_assets=debt_to_assets,
        debt_to_market_cap=debt_to_mktcap,
        cash_to_assets=cash_to_assets,
        receivables_to_assets=receivables_to_assets,
        interest_income_pct=interest_pct,
    )


def screen_batch(data: dict[str, dict]) -> dict[str, HalalResult]:
    results = {}
    for symbol, ticker_data in data.items():
        results[symbol] = screen(symbol, ticker_data)
    passed = sum(1 for r in results.values() if r.passed)
    print(f"[halal] {passed}/{len(results)} stocks passed halal screening")
    return results
