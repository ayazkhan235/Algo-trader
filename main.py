#!/usr/bin/env python3
"""
NSE Halal Algo Trader — CLI Entry Point

Usage:
  python main.py scan                        Full scan of configured universe
  python main.py scan --universe nifty50     Scan Nifty 50 only (faster)
  python main.py scan --refresh              Clear cache and re-fetch all data
  python main.py scan --top-n 30             Show top 30 recommendations
  python main.py scan --min-score 65         Only show BUY tier and above
  python main.py scan --show-rejected        Also show halal rejections
  python main.py scan --detail RELIANCE      Show detailed analysis for one stock
  python main.py scan --output csv           Export results to CSV
  python main.py scan --mode STRICT_INDIA    Use Nifty50 Shariah stricter thresholds
"""
import argparse
import sys
import config
from data.nse_universe import get_symbols
from data.fetcher import fetch_batch
from screening.halal_screener import screen_batch
from analysis.fundamental import compute
from analysis.scorer import compute_conviction_score
from signals.generator import generate
from reports.cli_report import (
    print_summary_stats, print_signals_table,
    print_signal_detail, print_halal_rejections, console
)
from reports import csv_report


def parse_args():
    p = argparse.ArgumentParser(description="NSE Halal Algo Trader")
    sub = p.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan NSE stocks for halal buy signals")
    scan.add_argument("--universe", default=config.NSE_UNIVERSE,
                      choices=["nifty50", "nifty200", "nifty500"],
                      help="Stock universe to scan (default: nifty500)")
    scan.add_argument("--top-n", type=int, default=config.TOP_N_RECOMMENDATIONS)
    scan.add_argument("--min-score", type=float, default=config.WATCH_THRESHOLD)
    scan.add_argument("--refresh", action="store_true", help="Clear cache and re-fetch")
    scan.add_argument("--show-rejected", action="store_true", help="Show halal rejections")
    scan.add_argument("--detail", metavar="SYMBOL", help="Print detailed view for one symbol")
    scan.add_argument("--output", choices=["csv", "none"], default="csv")
    scan.add_argument("--mode", choices=["STANDARD", "STRICT_INDIA"], default="STANDARD")

    return p.parse_args()


def run_scan(args) -> None:
    # Apply screening mode
    config.SCREENING_MODE = args.mode
    if args.mode == "STRICT_INDIA":
        console.print("[yellow]Mode: STRICT_INDIA (Nifty50 Shariah — 25% debt threshold)[/yellow]")

    # ── Step 1: Universe ──────────────────────────────────────────────────────
    console.print(f"[cyan]Loading {args.universe} universe...[/cyan]")
    symbols = get_symbols(args.universe, refresh=args.refresh)

    # ── Step 2: Fetch data ────────────────────────────────────────────────────
    console.print(f"[cyan]Fetching data for {len(symbols)} stocks...[/cyan]")
    data = fetch_batch(symbols, refresh=args.refresh, max_workers=config.MAX_WORKERS)

    # ── Step 3: Halal screen ──────────────────────────────────────────────────
    console.print("[cyan]Running halal screen...[/cyan]")
    halal_results = screen_batch(data)

    halal_passed = {s: d for s, d in data.items() if halal_results[s].passed}
    rejections   = [(s, r) for s, r in halal_results.items() if not r.passed]

    # ── Step 4: Fundamentals ──────────────────────────────────────────────────
    console.print(f"[cyan]Computing fundamentals for {len(halal_passed)} halal stocks...[/cyan]")
    metrics = {s: compute(s, d) for s, d in halal_passed.items()}

    # ── Step 5: Conviction scores ─────────────────────────────────────────────
    scores = {s: compute_conviction_score(d, metrics[s]) for s, d in halal_passed.items()}

    quality_passed = sum(1 for sc in scores.values() if not sc["hard_gate_fails"])

    # ── Step 6: Generate signals ──────────────────────────────────────────────
    signals = generate(data, halal_results, metrics, scores, min_score=args.min_score)

    # ── Step 7: Report ────────────────────────────────────────────────────────
    print_summary_stats(
        total=len(symbols),
        halal=len(halal_passed),
        quality=quality_passed,
        n_signals=len(signals),
    )

    if args.detail:
        sym = args.detail.upper()
        if not sym.endswith(".NS"):
            sym += ".NS"
        match = next((s for s in signals if s.symbol == sym), None)
        if match:
            print_signal_detail(match)
        else:
            console.print(f"[red]{sym} not found in signals (may have failed screening or scoring)[/red]")
    else:
        print_signals_table(signals, top_n=args.top_n)

    if args.show_rejected:
        print_halal_rejections(rejections)

    if args.output == "csv" and signals:
        csv_report.export(signals)


def main():
    args = parse_args()

    if args.command == "scan":
        run_scan(args)
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
