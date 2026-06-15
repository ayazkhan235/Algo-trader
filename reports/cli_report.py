"""
Rich terminal output — colour-coded buy signal tables.
"""
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box
from signals.generator import BuySignal

console = Console()

TIER_COLOURS = {
    "STRONG BUY": "bold green",
    "BUY":        "bold yellow",
    "WATCH":      "bold cyan",
}


def _fmt(val, fmt=".1f", suffix="", na="—") -> str:
    if val is None:
        return na
    try:
        return f"{val:{fmt}}{suffix}"
    except Exception:
        return na


def print_summary_stats(total: int, halal: int, quality: int, n_signals: int) -> None:
    console.print()
    console.print("[bold white]═══ NSE HALAL ALGO TRADER ═══[/bold white]")
    console.print(
        f"  Universe: [cyan]{total}[/cyan] stocks  →  "
        f"Halal: [green]{halal}[/green]  →  "
        f"Quality gates: [yellow]{quality}[/yellow]  →  "
        f"Signals: [bold green]{n_signals}[/bold green]"
    )
    console.print()


def print_signals_table(signals: list[BuySignal], top_n: int = 20) -> None:
    t = Table(
        title="Buy Signals",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold white on grey23",
    )

    t.add_column("#",       style="dim",        width=3)
    t.add_column("Symbol",  style="bold white",  width=14)
    t.add_column("Signal",  width=12)
    t.add_column("Score",   justify="right",     width=6)
    t.add_column("P/E",     justify="right",     width=6)
    t.add_column("P/B",     justify="right",     width=6)
    t.add_column("ROE",     justify="right",     width=7)
    t.add_column("Rev↑3y",  justify="right",     width=7)
    t.add_column("FCF Yld", justify="right",     width=8)
    t.add_column("Piok",    justify="right",     width=5)
    t.add_column("Sector",  width=20)
    t.add_column("Top Strength", width=35)

    for i, sig in enumerate(signals[:top_n], 1):
        m = sig.metrics
        tier_style = TIER_COLOURS.get(sig.tier, "white")
        tier_text  = Text(sig.tier, style=tier_style)

        strength = sig.strengths[0] if sig.strengths else "—"

        t.add_row(
            str(i),
            sig.symbol.replace(".NS", ""),
            tier_text,
            _fmt(sig.score, ".0f"),
            _fmt(m.get("trailing_pe")),
            _fmt(m.get("price_book")),
            _fmt(m.get("roe"), ".1%") if m.get("roe") else "—",
            _fmt(m.get("rev_cagr_3y"), ".1%") if m.get("rev_cagr_3y") else "—",
            _fmt(m.get("fcf_yield"), ".1%") if m.get("fcf_yield") else "—",
            str(sig.score_breakdown.get("piotroski", "—")),
            sig.sector[:20],
            strength[:35],
        )

    console.print(t)


def print_signal_detail(sig: BuySignal) -> None:
    m = sig.metrics
    sb = sig.score_breakdown
    colour = TIER_COLOURS.get(sig.tier, "white")

    console.rule(f"[{colour}]{sig.symbol} — {sig.name}[/{colour}]")
    console.print(f"  Sector: [cyan]{sig.sector}[/cyan]  |  Industry: {sig.industry}")
    console.print(f"  Signal: [{colour}]{sig.tier}[/{colour}]  |  Conviction Score: [{colour}]{sig.score:.0f}/100[/{colour}]")
    console.print()

    score_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    score_table.add_column("Category", width=18)
    score_table.add_column("Score", justify="right", width=8)
    for cat in ["valuation", "profitability", "growth", "quality", "health", "india"]:
        score_table.add_row(cat.capitalize(), f"{sb.get(cat, 0):.0f}/100")
    score_table.add_row("Piotroski F", f"{sb.get('piotroski', '—')}/9")
    score_table.add_row("Altman Z",    f"{sb.get('altman_z', '—'):.2f}" if sb.get("altman_z") else "—")
    score_table.add_row("Beneish M",   f"{sb.get('beneish_m', '—'):.2f}" if sb.get("beneish_m") else "—")
    console.print(score_table)

    if sig.strengths:
        console.print("  [bold green]Strengths:[/bold green]")
        for s in sig.strengths:
            console.print(f"    ✓ {s}")
    if sig.risks:
        console.print("  [bold red]Risks:[/bold red]")
        for r in sig.risks:
            console.print(f"    ✗ {r}")

    if sig.impure_income_pct > 0:
        console.print(
            f"\n  [yellow]Dividend Purification:[/yellow] "
            f"{sig.impure_income_pct:.2%} of any dividend received should be donated to charity."
        )
    console.print()


def print_halal_rejections(rejections: list[tuple[str, object]], max_show: int = 10) -> None:
    console.print(f"\n[dim]Halal rejections (showing {min(len(rejections), max_show)}/{len(rejections)}):[/dim]")
    t = Table(box=box.SIMPLE, show_header=True)
    t.add_column("Symbol", width=14)
    t.add_column("Reason", width=60)
    for sym, result in rejections[:max_show]:
        t.add_row(sym.replace(".NS",""), "; ".join(result.fail_reasons[:2]))
    console.print(t)
