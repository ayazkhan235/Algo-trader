"""
Analyses your real portfolio holdings through the same halal + fundamental lens.
Shows halal status, current score, P&L, and rebalancing suggestions.
"""
from dataclasses import dataclass
from typing import Optional
from portfolio.csv_importer import Holding
from screening.halal_screener import screen, HalalResult
from analysis.fundamental import compute
from analysis.scorer import compute_conviction_score


@dataclass
class HoldingAnalysis:
    holding: Holding
    halal: HalalResult
    metrics: dict
    score: dict
    pnl_inr: Optional[float]
    pnl_pct: Optional[float]
    action: str              # HOLD | REVIEW | EXIT
    notes: list[str]
    dividend_purification_inr: Optional[float]  # how much to donate per ₹1000 dividend


def analyse_holding(holding: Holding, ticker_data: dict) -> HoldingAnalysis:
    halal  = screen(holding.symbol, ticker_data)
    metrics = compute(holding.symbol, ticker_data)
    score   = compute_conviction_score(ticker_data, metrics)

    # P&L
    current_price = metrics.get("price") or holding.current_price
    pnl_inr = pnl_pct = None
    if current_price and holding.avg_buy_price:
        pnl_inr = (current_price - holding.avg_buy_price) * holding.quantity
        pnl_pct = (current_price / holding.avg_buy_price) - 1

    # Determine action
    notes = []
    action = "HOLD"

    if not halal.passed:
        action = "EXIT"
        notes.append(f"Halal breach: {'; '.join(halal.fail_reasons[:2])}")
    elif score["hard_gate_fails"]:
        action = "REVIEW"
        notes.extend(score["hard_gate_fails"][:2])
    elif score["composite"] < 40:
        action = "REVIEW"
        notes.append(f"Conviction score dropped to {score['composite']:.0f}")

    # Dividend purification
    purif = None
    if halal.impure_income_pct > 0:
        purif = round(halal.impure_income_pct * 1000, 2)
        notes.append(f"Purification: donate ₹{purif:.2f} per ₹1000 dividend received")

    return HoldingAnalysis(
        holding=holding,
        halal=halal,
        metrics=metrics,
        score=score,
        pnl_inr=pnl_inr,
        pnl_pct=pnl_pct,
        action=action,
        notes=notes,
        dividend_purification_inr=purif,
    )


def analyse_portfolio(holdings: list[Holding], data: dict[str, dict]) -> list[HoldingAnalysis]:
    results = []
    for h in holdings:
        ticker_data = data.get(h.symbol)
        if not ticker_data:
            continue
        results.append(analyse_holding(h, ticker_data))
    return results


def print_portfolio_report(analyses: list[HoldingAnalysis]) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    console.print("\n[bold white]═══ Portfolio Analysis ═══[/bold white]\n")

    t = Table(box=box.ROUNDED, show_lines=True, header_style="bold white on grey23")
    t.add_column("Symbol",  width=12)
    t.add_column("Halal",   width=6)
    t.add_column("Score",   justify="right", width=6)
    t.add_column("Action",  width=8)
    t.add_column("P&L",     justify="right", width=12)
    t.add_column("P&L %",   justify="right", width=8)
    t.add_column("Notes",   width=40)

    total_invested = total_value = 0.0

    for a in sorted(analyses, key=lambda x: x.score["composite"], reverse=True):
        halal_icon = "[green]✓[/green]" if a.halal.passed else "[red]✗[/red]"
        action_col = {"HOLD": "[green]HOLD[/green]",
                      "REVIEW": "[yellow]REVIEW[/yellow]",
                      "EXIT": "[red]EXIT[/red]"}.get(a.action, a.action)

        pnl_str     = f"₹{a.pnl_inr:+,.0f}" if a.pnl_inr is not None else "—"
        pnl_pct_str = f"{a.pnl_pct:+.1%}" if a.pnl_pct is not None else "—"
        pnl_col     = "green" if (a.pnl_inr or 0) >= 0 else "red"

        sym = a.holding.symbol.replace(".NS", "")
        notes_str = "; ".join(a.notes[:2])[:38]

        t.add_row(
            sym,
            halal_icon,
            f"{a.score['composite']:.0f}",
            action_col,
            f"[{pnl_col}]{pnl_str}[/{pnl_col}]",
            f"[{pnl_col}]{pnl_pct_str}[/{pnl_col}]",
            notes_str,
        )

        invested = a.holding.avg_buy_price * a.holding.quantity
        total_invested += invested
        total_value    += invested + (a.pnl_inr or 0)

    console.print(t)

    total_pnl = total_value - total_invested
    pnl_pct   = total_pnl / total_invested if total_invested else 0
    col = "green" if total_pnl >= 0 else "red"
    console.print(
        f"\n  Total invested: ₹{total_invested:,.0f}  "
        f"Current value: ₹{total_value:,.0f}  "
        f"P&L: [{col}]₹{total_pnl:+,.0f} ({pnl_pct:+.1%})[/{col}]\n"
    )
