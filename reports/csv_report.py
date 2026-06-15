import csv
import os
from datetime import date
from signals.generator import BuySignal
import config


def export(signals: list[BuySignal], filepath: str = None) -> str:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    if not filepath:
        filepath = os.path.join(config.OUTPUT_DIR, f"signals_{date.today()}.csv")

    fieldnames = [
        "symbol", "name", "tier", "score",
        "valuation_score", "profitability_score", "growth_score",
        "quality_score", "health_score", "india_score",
        "piotroski", "altman_z", "beneish_m",
        "sector", "industry",
        "price", "market_cap",
        "trailing_pe", "forward_pe", "price_book", "ev_ebitda",
        "price_fcf", "peg", "graham_number",
        "roe", "roce", "net_margin", "gross_margin",
        "rev_cagr_3y", "earn_cagr_3y", "fcf_cagr_3y", "earn_consistency",
        "cash_conversion", "capex_intensity", "fcf_yield",
        "interest_coverage", "current_ratio",
        "dividend_yield", "beta",
        "impure_income_pct",
        "strengths", "risks", "halal_notes",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for sig in signals:
            m = sig.metrics
            sb = sig.score_breakdown
            row = {
                "symbol":           sig.symbol,
                "name":             sig.name,
                "tier":             sig.tier,
                "score":            sig.score,
                "valuation_score":  sb.get("valuation"),
                "profitability_score": sb.get("profitability"),
                "growth_score":     sb.get("growth"),
                "quality_score":    sb.get("quality"),
                "health_score":     sb.get("health"),
                "india_score":      sb.get("india"),
                "piotroski":        sb.get("piotroski"),
                "altman_z":         sb.get("altman_z"),
                "beneish_m":        sb.get("beneish_m"),
                "sector":           sig.sector,
                "industry":         sig.industry,
                **{k: m.get(k) for k in [
                    "price", "market_cap", "trailing_pe", "forward_pe",
                    "price_book", "ev_ebitda", "price_fcf", "peg", "graham_number",
                    "roe", "roce", "net_margin", "gross_margin",
                    "rev_cagr_3y", "earn_cagr_3y", "fcf_cagr_3y", "earn_consistency",
                    "cash_conversion", "capex_intensity", "fcf_yield",
                    "interest_coverage", "current_ratio", "dividend_yield", "beta",
                ]},
                "impure_income_pct": sig.impure_income_pct,
                "strengths":  " | ".join(sig.strengths),
                "risks":      " | ".join(sig.risks),
                "halal_notes":" | ".join(sig.halal_notes),
            }
            writer.writerow(row)

    print(f"[report] CSV exported → {filepath}")
    return filepath
