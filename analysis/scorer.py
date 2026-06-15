"""
Druckenmiller-style 0-100 conviction scorer.
Combines 6 weighted categories into a single conviction score.
Each category score is independently computed and visible in the output.
"""
from typing import Optional
import config
from analysis.scoring_models import piotroski_f_score, altman_z_score, beneish_m_score


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _linear(val: Optional[float], lo: float, hi: float, invert: bool = False) -> float:
    """Map val linearly from [lo, hi] → [0, 100]. Returns 50 if val is None."""
    if val is None:
        return 50.0
    if invert:
        val = lo + hi - val
        lo, hi = lo, hi
    if hi == lo:
        return 50.0
    score = (val - lo) / (hi - lo) * 100
    return _clamp(score)


# ── Category scorers ──────────────────────────────────────────────────────────

def score_valuation(m: dict) -> float:
    scores = []

    # P/E: 100 at PE=10, 0 at PE=40
    if m.get("trailing_pe") and m["trailing_pe"] > 0:
        scores.append(_clamp((40 - m["trailing_pe"]) / 30 * 100))

    # Price/FCF: 100 at 12, 0 at 40
    if m.get("price_fcf") and m["price_fcf"] > 0:
        scores.append(_clamp((40 - m["price_fcf"]) / 28 * 100))

    # EV/EBITDA: 100 at 6, 0 at 20
    if m.get("ev_ebitda") and m["ev_ebitda"] > 0:
        scores.append(_clamp((20 - m["ev_ebitda"]) / 14 * 100))

    # PEG: 100 at 0.5, 0 at 2.0
    if m.get("peg") and m["peg"] > 0:
        scores.append(_clamp((2.0 - m["peg"]) / 1.5 * 100))

    # Graham Number: 100 if price < Graham, 0 if price > 2× Graham
    if m.get("graham_number") and m.get("price") and m["price"] > 0:
        ratio = m["price"] / m["graham_number"]
        scores.append(_clamp((2.0 - ratio) / 1.0 * 100))

    return sum(scores) / len(scores) if scores else 50.0


def score_profitability(m: dict) -> float:
    scores = []

    # ROE: 100 at 25%, 0 at 10%
    if m.get("roe") is not None:
        scores.append(_clamp((m["roe"] - 0.10) / 0.15 * 100))

    # ROCE: 100 at 20%, 0 at 8%
    if m.get("roce") is not None:
        scores.append(_clamp((m["roce"] - 0.08) / 0.12 * 100))

    # Net margin: 100 at 25%, 0 at 5%
    if m.get("net_margin") is not None:
        scores.append(_clamp((m["net_margin"] - 0.05) / 0.20 * 100))

    # Gross margin trend: +20 bonus for expanding, -20 for contracting
    if m.get("gm_trend") is not None:
        scores.append(50 + m["gm_trend"] * 500)  # ±10% change → ±50 pts

    return _clamp(sum(scores) / len(scores)) if scores else 50.0


def score_growth(m: dict) -> float:
    scores = []

    # Revenue CAGR 3y: 100 at 20%, 0 at 0%
    if m.get("rev_cagr_3y") is not None:
        scores.append(_clamp(m["rev_cagr_3y"] / 0.20 * 100))

    # Earnings CAGR 3y: 100 at 20%, 0 at 0%
    if m.get("earn_cagr_3y") is not None:
        scores.append(_clamp(m["earn_cagr_3y"] / 0.20 * 100))

    # FCF CAGR 3y: 100 at 15%, 0 at 0%
    if m.get("fcf_cagr_3y") is not None:
        scores.append(_clamp(m["fcf_cagr_3y"] / 0.15 * 100))

    # Earnings consistency: direct 0-100
    if m.get("earn_consistency") is not None:
        scores.append(m["earn_consistency"] * 100)

    return _clamp(sum(scores) / len(scores)) if scores else 50.0


def score_quality(m: dict) -> float:
    scores = []

    # Cash conversion ratio: 100 at >1.0, 0 at <0.3
    if m.get("cash_conversion") is not None:
        scores.append(_clamp((m["cash_conversion"] - 0.3) / 0.7 * 100))

    # Capex intensity: 100 at <3%, 0 at >20% (lower is better)
    if m.get("capex_intensity") is not None:
        scores.append(_clamp((0.20 - m["capex_intensity"]) / 0.17 * 100))

    # FCF yield: 100 at >8%, 0 at 0%
    if m.get("fcf_yield") is not None:
        scores.append(_clamp(m["fcf_yield"] / 0.08 * 100))

    return _clamp(sum(scores) / len(scores)) if scores else 50.0


def score_health(data: dict, m: dict) -> tuple[float, int, Optional[float], Optional[float]]:
    """Returns (category_score, piotroski, altman_z, beneish_m)."""
    scores = []

    f_score, _ = piotroski_f_score(data)
    altman_z   = altman_z_score(data)
    beneish_m  = beneish_m_score(data)

    # Piotroski: direct 0-100
    scores.append(f_score / 9 * 100)

    # Altman Z: 100 at >3.0, 0 at <1.81
    if altman_z is not None:
        scores.append(_clamp((altman_z - 1.81) / 1.19 * 100))

    # Interest coverage: 100 at >10x, 0 at <2x
    if m.get("interest_coverage") is not None:
        scores.append(_clamp((m["interest_coverage"] - 2) / 8 * 100))

    # Current ratio: 100 at >2.5, 0 at <1.0
    if m.get("current_ratio") is not None:
        scores.append(_clamp((m["current_ratio"] - 1.0) / 1.5 * 100))

    cat_score = _clamp(sum(scores) / len(scores)) if scores else 50.0
    return cat_score, f_score, altman_z, beneish_m


def score_india(m: dict, promoter_holding: Optional[float] = None,
                promoter_pledge: Optional[float] = None) -> float:
    scores = []

    # Promoter holding: 100 at >65%, 0 at <30%
    if promoter_holding is not None:
        scores.append(_clamp((promoter_holding - 30) / 35 * 100))
    else:
        scores.append(50.0)  # neutral if unknown

    # Promoter pledge: 100 at 0%, 0 at >40%
    if promoter_pledge is not None:
        scores.append(_clamp((40 - promoter_pledge) / 40 * 100))
    else:
        scores.append(70.0)  # slightly positive assumption if unknown

    # Dividend yield as consistency proxy: 100 at >3%, 0 at 0%
    if m.get("dividend_yield") is not None and m["dividend_yield"] > 0:
        scores.append(_clamp(m["dividend_yield"] / 0.03 * 100))

    return _clamp(sum(scores) / len(scores)) if scores else 50.0


# ── Hard gate check ───────────────────────────────────────────────────────────

def check_hard_gates(m: dict, f_score: int, altman_z: Optional[float],
                     beneish_m: Optional[float],
                     promoter_pledge: Optional[float] = None) -> list[str]:
    """Returns list of disqualifying reasons. Empty list = passes all gates."""
    reasons = []

    if m.get("roe") is not None and m["roe"] < 0:
        reasons.append(f"Negative ROE ({m['roe']:.1%})")

    if m.get("earn_consistency") is not None and m["earn_consistency"] < 0.50:
        reasons.append(f"Earnings loss in majority of last 4 years")

    if m.get("trailing_pe") is not None and m["trailing_pe"] > config.MAX_PE:
        reasons.append(f"P/E {m['trailing_pe']:.1f} > {config.MAX_PE} cap")

    if f_score < config.MIN_PIOTROSKI_SCORE:
        reasons.append(f"Piotroski F-Score {f_score}/9 < {config.MIN_PIOTROSKI_SCORE}")

    if altman_z is not None and altman_z < config.MIN_ALTMAN_Z:
        reasons.append(f"Altman Z-Score {altman_z:.2f} < {config.MIN_ALTMAN_Z} (distress zone)")

    if beneish_m is not None and beneish_m > config.BENEISH_M_THRESHOLD:
        reasons.append(f"Beneish M-Score {beneish_m:.2f} > {config.BENEISH_M_THRESHOLD} (manipulation risk)")

    if promoter_pledge is not None and promoter_pledge > config.MAX_PROMOTER_PLEDGE_PCT:
        reasons.append(f"Promoter pledge {promoter_pledge:.1f}% > {config.MAX_PROMOTER_PLEDGE_PCT}%")

    if m.get("interest_coverage") is not None and m["interest_coverage"] < config.MIN_INTEREST_COVERAGE:
        reasons.append(f"Interest coverage {m['interest_coverage']:.1f}x < {config.MIN_INTEREST_COVERAGE}x")

    return reasons


# ── Master conviction scorer ──────────────────────────────────────────────────

def compute_conviction_score(
    data: dict,
    metrics: dict,
    promoter_holding: Optional[float] = None,
    promoter_pledge: Optional[float] = None,
) -> dict:
    """
    Returns a dict with composite score, category scores, model scores,
    and a list of hard gate failures (empty if all pass).
    """
    cat_val   = score_valuation(metrics)
    cat_prof  = score_profitability(metrics)
    cat_grow  = score_growth(metrics)
    cat_qual  = score_quality(metrics)
    cat_health, f_score, altman_z, beneish_m = score_health(data, metrics)
    cat_india = score_india(metrics, promoter_holding, promoter_pledge)

    w = config.WEIGHTS
    composite = (
        w["valuation"]     * cat_val   +
        w["profitability"] * cat_prof  +
        w["growth"]        * cat_grow  +
        w["quality"]       * cat_qual  +
        w["health"]        * cat_health+
        w["india"]         * cat_india
    )

    hard_gate_fails = check_hard_gates(metrics, f_score, altman_z, beneish_m, promoter_pledge)

    return {
        "composite":        round(composite, 1),
        "valuation":        round(cat_val, 1),
        "profitability":    round(cat_prof, 1),
        "growth":           round(cat_grow, 1),
        "quality":          round(cat_qual, 1),
        "health":           round(cat_health, 1),
        "india":            round(cat_india, 1),
        "piotroski":        f_score,
        "altman_z":         altman_z,
        "beneish_m":        beneish_m,
        "hard_gate_fails":  hard_gate_fails,
    }
