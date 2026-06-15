"""
Piotroski F-Score, Altman Z-Score, and Beneish M-Score implementations.
These are industry-standard quantitative models used by professional quants.
"""
from typing import Optional


def _first(lst: list) -> Optional[float]:
    for v in lst:
        if v is not None:
            return v
    return None


# ── Piotroski F-Score (0-9) ───────────────────────────────────────────────────
def piotroski_f_score(data: dict) -> tuple[int, dict]:
    """
    9-point scoring system for financial strength.
    Returns (score, breakdown_dict).
    Requires: financials from data.fetcher output.
    """
    fin = data.get("financials", {})
    info = data.get("info", {})

    # Extract values
    net_incomes  = fin.get("net_income", [])
    total_assets = fin.get("total_assets", [])
    op_cf        = fin.get("operating_cf", [])
    debts        = fin.get("total_debt_bs", [])
    curr_assets  = fin.get("current_assets", [])
    curr_liab    = fin.get("current_liabilities", [])
    gross_p      = fin.get("gross_profit", [])
    revenues     = fin.get("revenue", [])
    shares       = info.get("shares_outstanding")

    def safe_div(a, b):
        if a is not None and b and b != 0:
            return a / b
        return None

    ni_now  = _first(net_incomes)
    ni_prev = net_incomes[1] if len(net_incomes) > 1 else None
    a_now   = _first(total_assets)
    a_prev  = total_assets[1] if len(total_assets) > 1 else None
    cf_now  = _first(op_cf)
    d_now   = _first(debts)
    d_prev  = debts[1] if len(debts) > 1 else None
    ca_now  = _first(curr_assets)
    cl_now  = _first(curr_liab)
    ca_prev = curr_assets[1] if len(curr_assets) > 1 else None
    cl_prev = curr_liab[1] if len(curr_liab) > 1 else None
    gp_now  = _first(gross_p)
    gp_prev = gross_p[1] if len(gross_p) > 1 else None
    rev_now = _first(revenues)
    rev_prev= revenues[1] if len(revenues) > 1 else None

    roa_now  = safe_div(ni_now, a_now)
    roa_prev = safe_div(ni_prev, a_prev)

    scores = {}

    # Profitability signals (4 points)
    scores["roa_positive"]      = 1 if (roa_now is not None and roa_now > 0) else 0
    scores["operating_cf_pos"]  = 1 if (cf_now is not None and cf_now > 0) else 0
    scores["roa_improving"]     = 1 if (roa_now and roa_prev and roa_now > roa_prev) else 0
    # Accruals: operating CF > net income (quality of earnings)
    scores["low_accruals"]      = 1 if (cf_now and ni_now and cf_now > ni_now) else 0

    # Leverage / liquidity signals (3 points)
    leverage_ratio_now  = safe_div(d_now, a_now)
    leverage_ratio_prev = safe_div(d_prev, a_prev)
    scores["leverage_decreasing"] = 1 if (
        leverage_ratio_now is not None and leverage_ratio_prev is not None
        and leverage_ratio_now < leverage_ratio_prev
    ) else 0

    cr_now  = safe_div(ca_now, cl_now)
    cr_prev = safe_div(ca_prev, cl_prev)
    scores["current_ratio_improving"] = 1 if (cr_now and cr_prev and cr_now > cr_prev) else 0
    scores["no_dilution"] = 0  # simplified — would need share count history

    # Efficiency signals (2 points)
    gm_now_val  = safe_div(gp_now, rev_now)
    gm_prev_val = safe_div(gp_prev, rev_prev)
    scores["gross_margin_improving"] = 1 if (gm_now_val and gm_prev_val and gm_now_val > gm_prev_val) else 0

    at_now  = safe_div(rev_now, a_now)
    at_prev = safe_div(rev_prev, a_prev)
    scores["asset_turnover_improving"] = 1 if (at_now and at_prev and at_now > at_prev) else 0

    total = sum(scores.values())
    return total, scores


# ── Altman Z-Score ────────────────────────────────────────────────────────────
def altman_z_score(data: dict) -> Optional[float]:
    """
    Predicts financial distress. Z > 2.99 = safe, 1.81-2.99 = grey, < 1.81 = distress.
    Formula for non-manufacturing (India context): modified version.
    """
    fin = data.get("financials", {})
    info = data.get("info", {})

    ta = _first(fin.get("total_assets", []))
    if not ta or ta == 0:
        return None

    ca   = _first(fin.get("current_assets", []))
    cl   = _first(fin.get("current_liabilities", []))
    re   = _first(fin.get("retained_earnings", []))
    ebit = _first(fin.get("ebit", []))
    rev  = _first(fin.get("revenue", []))
    debt = _first(fin.get("total_debt_bs", []))
    mktcap = info.get("market_cap")

    wc   = (ca - cl) if ca and cl else None
    bv_equity = mktcap  # use market cap as proxy for market value of equity

    x1 = (wc / ta) if wc is not None else 0
    x2 = (re / ta) if re else 0
    x3 = (ebit / ta) if ebit else 0
    x4 = (bv_equity / debt) if bv_equity and debt and debt > 0 else 0
    x5 = (rev / ta) if rev else 0

    return round(1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5, 3)


# ── Beneish M-Score ───────────────────────────────────────────────────────────
def beneish_m_score(data: dict) -> Optional[float]:
    """
    Detects earnings manipulation. M > -1.78 = possible manipulation.
    Requires 2 years of financial data.
    """
    fin = data.get("financials", {})

    revenues = fin.get("revenue", [])
    gross_p  = fin.get("gross_profit", [])
    assets   = fin.get("total_assets", [])
    net_inc  = fin.get("net_income", [])
    curr_a   = fin.get("current_assets", [])
    curr_l   = fin.get("current_liabilities", [])
    op_cf    = fin.get("operating_cf", [])
    receivables = fin.get("net_receivables", [])
    debts    = fin.get("total_debt_bs", [])

    if len(revenues) < 2 or len(assets) < 2:
        return None

    def g(lst, i):
        try:
            return lst[i] if lst[i] is not None else 0
        except IndexError:
            return 0

    rev1, rev0  = g(revenues,0), g(revenues,1)
    gp1, gp0   = g(gross_p,0),  g(gross_p,1)
    ta1, ta0   = g(assets,0),   g(assets,1)
    ni1        = g(net_inc,0)
    ca1, ca0   = g(curr_a,0),   g(curr_a,1)
    cl1, cl0   = g(curr_l,0),   g(curr_l,1)
    ocf1       = g(op_cf,0)
    rec1, rec0 = g(receivables,0), g(receivables,1)
    dbt1, dbt0 = g(debts,0),    g(debts,1)

    def safe(n, d):
        return n / d if d and d != 0 else 0

    dsri = safe(safe(rec1, rev1), safe(rec0, rev0))  # Days Sales Receivable Index
    gmi  = safe(safe(gp0, rev0), safe(gp1, rev1))    # Gross Margin Index
    aqi  = safe(1 - safe(ca1 + g(fin.get("ppe",[]),0), ta1),
                1 - safe(ca0 + g(fin.get("ppe",[]),1), ta0))  # Asset Quality Index
    sgi  = safe(rev1, rev0)                            # Sales Growth Index
    depi = safe(safe(g(fin.get("capex",[]),1), ta0), safe(g(fin.get("capex",[]),0), ta1))
    sgai = 0                                           # SG&A not always available
    lvgi = safe(safe(dbt1, ta1), safe(dbt0, ta0))
    tata = safe(ocf1, ta1)

    m = (-4.84 + 0.920*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi
         + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi)
    return round(m, 3)
