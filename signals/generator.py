"""
Generates tiered buy signals from halal results + conviction scores.
"""
from dataclasses import dataclass, field
from typing import Optional
import config


@dataclass
class BuySignal:
    symbol: str
    name: str
    sector: str
    industry: str
    tier: str                        # STRONG BUY | BUY | WATCH
    score: float                     # 0-100 composite
    score_breakdown: dict            # per-category scores
    metrics: dict                    # raw computed metrics
    halal_notes: list[str]           # why it passed halal
    strengths: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    impure_income_pct: float = 0.0   # for dividend purification


def _tier(score: float) -> str:
    if score >= config.STRONG_BUY_THRESHOLD:
        return "STRONG BUY"
    if score >= config.BUY_THRESHOLD:
        return "BUY"
    return "WATCH"


def _build_reasons(m: dict, score_breakdown: dict) -> tuple[list[str], list[str]]:
    strengths, risks = [], []

    roe = m.get("roe")
    if roe and roe > 0.20:
        strengths.append(f"Strong ROE of {roe:.1%} — efficient capital use")
    elif roe and roe < 0.12:
        risks.append(f"Low ROE of {roe:.1%}")

    rev_cagr = m.get("rev_cagr_3y")
    if rev_cagr and rev_cagr > 0.15:
        strengths.append(f"Revenue grew {rev_cagr:.1%} CAGR over 3 years")
    elif rev_cagr and rev_cagr < 0.05:
        risks.append(f"Slow revenue growth: {rev_cagr:.1%} 3y CAGR")

    fcf_yield = m.get("fcf_yield")
    if fcf_yield and fcf_yield > 0.05:
        strengths.append(f"High FCF yield of {fcf_yield:.1%} — strong cash generation")

    pe = m.get("trailing_pe")
    if pe and pe < 18:
        strengths.append(f"Attractive valuation: P/E {pe:.1f}")
    elif pe and pe > 35:
        risks.append(f"Expensive valuation: P/E {pe:.1f}")

    if score_breakdown.get("piotroski", 0) >= 7:
        strengths.append(f"Strong financial health: Piotroski {score_breakdown['piotroski']}/9")

    cc = m.get("cash_conversion")
    if cc and cc > 0.9:
        strengths.append("Earnings backed by real cash (conversion ratio > 0.9)")
    elif cc and cc < 0.4:
        risks.append("Low cash conversion — earnings quality concern")

    gm_trend = m.get("gm_trend")
    if gm_trend and gm_trend > 0.02:
        strengths.append("Gross margin expanding — pricing power signal")
    elif gm_trend and gm_trend < -0.02:
        risks.append("Gross margin contracting — competitive pressure")

    altman = score_breakdown.get("altman_z")
    if altman and altman > 3.0:
        strengths.append(f"Financially healthy: Altman Z {altman:.2f}")

    return strengths, risks


def generate(
    data: dict[str, dict],
    halal_results: dict,
    metrics: dict[str, dict],
    scores: dict[str, dict],
    min_score: float = config.WATCH_THRESHOLD,
) -> list[BuySignal]:
    """
    Filters halal-passed stocks, applies hard gates, and returns ranked signals.
    """
    signals = []

    for symbol, halal in halal_results.items():
        if not halal.passed:
            continue

        score_dict = scores.get(symbol)
        if not score_dict:
            continue

        if score_dict["hard_gate_fails"]:
            continue

        composite = score_dict["composite"]
        if composite < min_score:
            continue

        m = metrics.get(symbol, {})
        strengths, risks = _build_reasons(m, score_dict)

        # Add hard-gate-adjacent risks
        for fail in score_dict.get("hard_gate_fails", []):
            risks.append(fail)

        signals.append(BuySignal(
            symbol=symbol,
            name=m.get("name", ""),
            sector=m.get("sector", ""),
            industry=m.get("industry", ""),
            tier=_tier(composite),
            score=composite,
            score_breakdown=score_dict,
            metrics=m,
            halal_notes=halal.pass_notes,
            strengths=strengths,
            risks=risks,
            impure_income_pct=halal.impure_income_pct,
        ))

    signals.sort(key=lambda s: s.score, reverse=True)
    return signals
