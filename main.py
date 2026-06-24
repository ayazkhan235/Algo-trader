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
    scan.add_argument("--live", action="store_true",
                      help="Semi-auto live trading via Upstox (asks confirmation per order)")
    scan.add_argument("--no-execute", action="store_true",
                      help="Skip paper trade execution (signals only — used by CI)")

    brief = sub.add_parser("brief", help="Show pre-market morning brief")

    portfolio = sub.add_parser("portfolio", help="Analyse your real holdings")

    paper = sub.add_parser("paper", help="Show paper trading portfolio")
    paper.add_argument("--history", action="store_true", help="Show all trades")

    sub.add_parser("dashboard", help="Launch web dashboard")

    sub.add_parser("sync-sheets", help="Push paper portfolio to Google Sheets")

    bt = sub.add_parser("backtest", help="Backtest current picks as a monthly SIP vs NIFTY")
    bt.add_argument("--universe", default="nifty50",
                    choices=["nifty50", "nifty200", "nifty500"])
    bt.add_argument("--years", type=int, default=5, help="Years of history (default 5)")
    bt.add_argument("--amount", type=float, default=config.REAL_MONTHLY_BUDGET_INR,
                    help="Monthly SIP amount (default = your ₹7k real budget)")
    bt.add_argument("--mode", choices=["STANDARD", "STRICT_INDIA"], default="STANDARD")

    l30 = sub.add_parser("last30days",
                         help="30-day market / sector / company sentiment memory")
    l30.add_argument("--days", type=int, default=30)

    return p.parse_args()


def run_scan(args) -> None:
    # Apply screening mode
    config.SCREENING_MODE = args.mode
    if args.mode == "STRICT_INDIA":
        console.print("[yellow]Mode: STRICT_INDIA (Nifty50 Shariah — 25% debt threshold)[/yellow]")

    # ── Step 0: Morning global-market check (logged for 30-day memory) ─────────
    _log_market_regime()

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

    # ── Step 8: Execution (paper or live) ────────────────────────────────────
    if getattr(args, "no_execute", False):
        console.print("[dim]--no-execute: skipping trade placement (CI mode)[/dim]")
    elif args.live:
        config.LIVE_TRADING = True
        from brokers.live_executor import execute_live_signals
        execute_live_signals(signals)
    else:
        from paper_trading.executor import execute_buy_signals
        # ── News: headlines + sector sentiment for the shortlist (logged) ──────
        news_map = _gather_news(signals)
        executed = execute_buy_signals(signals, news_map=news_map)
        if executed:
            console.print(f"[green]Paper trades placed: {len(executed)} new positions[/green]")
            for t in executed:
                console.print(f"  [green]+[/green] {t['symbol']}  {t['tier']}  "
                              f"₹{t['invested']:,.0f} @ ₹{t['price']:,.2f}")

        # ── Step 9: Sync paper portfolio to Google Sheets ──────────────────────
        _sync_google_sheets(metrics)

        # ── Step 10: Email a daily portfolio digest (always, even no new trades) ─
        _email_daily_digest(executed, metrics)


def _email_daily_digest(executed: list, metrics: dict) -> None:
    """Email all current holdings + % change + vs NIFTY every run (if configured)."""
    from reports.email_report import send_portfolio_digest
    from paper_trading.sqlite_engine import (
        get_open_trades, portfolio_summary, get_all_snapshots,
    )
    from integrations.gsheets import benchmark_return

    prices = {s: m["price"] for s, m in metrics.items() if m.get("price")}
    holdings = []
    for t in get_open_trades():
        entry = t["entry_price"]
        price = prices.get(t["symbol"], entry)
        holdings.append({
            "symbol": t["symbol"], "name": t.get("name") or "",
            "entry": entry, "qty": t["quantity"], "price": price,
            "value": price * t["quantity"],
            "pct": (price / entry - 1) if entry else 0.0,
        })

    brief = {}
    try:
        from market_intelligence.morning_brief import generate_brief
        brief = generate_brief()
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]Market brief unavailable for digest: {e}[/dim]")

    summary = portfolio_summary(prices)
    nifty_return = benchmark_return(get_all_snapshots())
    send_portfolio_digest(holdings, summary, brief=brief,
                          nifty_return=nifty_return, executed=executed)


def _email_trade_summary(executed: list, metrics: dict) -> None:
    """Send a short email summarising the executed trades and why (if configured)."""
    from reports.email_report import send_trade_notification
    from paper_trading.sqlite_engine import portfolio_summary

    # Market / global context (best-effort — needs network)
    brief = {}
    try:
        from market_intelligence.morning_brief import generate_brief
        brief = generate_brief()
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]Market brief unavailable for email: {e}[/dim]")

    prices = {s: m["price"] for s, m in metrics.items() if m.get("price")}
    summary = portfolio_summary(prices)
    send_trade_notification(executed, brief=brief, paper_summary=summary)


def _sync_google_sheets(metrics: dict) -> None:
    """Mirror the paper portfolio + dashboard to Google Sheets (if configured)."""
    from integrations import gsheets
    if not gsheets.is_configured():
        console.print("[dim]Google Sheets sync skipped (no credentials configured)[/dim]")
        return
    prices = {s: m["price"] for s, m in metrics.items() if m.get("price")}
    try:
        url = gsheets.sync(prices)
        console.print(f"[green]Google Sheet updated:[/green] {url}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Google Sheets sync failed: {e}[/red]")


def run_brief(args) -> None:
    from market_intelligence.morning_brief import generate_brief, print_brief
    brief = generate_brief()
    print_brief(brief)


def run_portfolio(args) -> None:
    from portfolio.aggregator import get_consolidated_holdings
    from portfolio.analyzer import analyse_portfolio, print_portfolio_report
    from data.fetcher import fetch_batch

    holdings = get_consolidated_holdings()
    if not holdings:
        console.print("[yellow]No holdings found. Add CSV files to /input/ or configure Upstox API.[/yellow]")
        return

    symbols = [h.symbol for h in holdings]
    console.print(f"[cyan]Fetching data for {len(symbols)} held stocks...[/cyan]")
    data = fetch_batch(symbols, max_workers=config.MAX_WORKERS)

    analyses = analyse_portfolio(holdings, data)
    print_portfolio_report(analyses)


def _log_market_regime() -> None:
    """Fetch + log today's global-market mood for the 30-day memory."""
    try:
        from market_intelligence.regime import snapshot_market
        from paper_trading.sqlite_engine import init_db, save_market_regime
        init_db()
        row = snapshot_market()
        save_market_regime(row)
        console.print(f"[cyan]Global market: {row['sentiment']} "
                      f"(avg {row['score']:+.2%}, India VIX {row.get('india_vix') or '—'})[/cyan]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]Market regime log skipped: {e}[/dim]")


def _gather_news(signals) -> dict:
    """Fetch headlines for BUY/STRONG BUY + held names; log company + sector sentiment."""
    from datetime import date as _date
    try:
        from market_intelligence.sentiment import fetch_headlines, score_headlines
        from paper_trading.sqlite_engine import (
            init_db, save_stock_news, save_sector_sentiment, get_open_trades,
        )
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]News skipped: {e}[/dim]")
        return {}

    init_db()
    sector_of = {s.symbol: s.sector for s in signals}
    targets = {s.symbol for s in signals if s.tier in ("STRONG BUY", "BUY")}
    targets.update(t["symbol"] for t in get_open_trades())
    if not targets:
        return {}

    console.print(f"[cyan]Checking news for {len(targets)} stocks...[/cyan]")
    news_map, news_rows = {}, []
    sector_scores: dict[str, list] = {}
    for sym in targets:
        agg = score_headlines(fetch_headlines(sym))
        news_map[sym] = agg
        news_rows.append({"symbol": sym, "score": agg["score"],
                          "label": agg["label"], "headline": agg["top_headline"]})
        sec = sector_of.get(sym)
        if sec:
            sector_scores.setdefault(sec, []).append(agg["score"])

    today = _date.today().isoformat()
    save_stock_news(today, news_rows)
    sectors = {
        sec: {"avg": round(sum(v) / len(v), 3),
              "label": "POSITIVE" if sum(v) / len(v) > 0.1
              else "NEGATIVE" if sum(v) / len(v) < -0.1 else "NEUTRAL"}
        for sec, v in sector_scores.items() if v
    }
    save_sector_sentiment(today, sectors)
    return news_map


def run_last30days(args) -> None:
    """Report market / sector / company sentiment over the last N days."""
    from paper_trading.sqlite_engine import (
        init_db, get_market_regime, get_sector_sentiment, get_stock_news,
    )
    from market_intelligence.regime import (
        summarize_market, summarize_sectors, summarize_companies,
    )
    init_db()
    days = getattr(args, "days", 30)

    mkt = summarize_market(get_market_regime(), days)
    console.print(f"\n[bold]═══ LAST {days} DAYS — MARKET MEMORY ═══[/bold]")
    console.print(f"[bold]Market regime:[/bold] {mkt['label']}  "
                  f"({mkt['bullish']} bullish / {mkt['bearish']} bearish / {mkt['neutral']} neutral "
                  f"over {mkt['days']}d, avg {mkt['avg_score']:+.2%}, trend {mkt['trend']})")

    secs = summarize_sectors(get_sector_sentiment(), days)
    if secs:
        console.print("\n[bold]Sector sentiment (news-based):[/bold]")
        for s in secs[:10]:
            console.print(f"  {s['sector']:24} {s['label']:8} ({s['avg']:+.2f}, {s['n']} obs)")

    comps = summarize_companies(get_stock_news(), days)
    if comps:
        console.print("\n[bold]Company sentiment (news-based):[/bold]")
        for c in comps[:15]:
            hl = f" — \"{c['headline'][:60]}\"" if c["headline"] else ""
            console.print(f"  {c['symbol'].replace('.NS',''):12} {c['label']:8} "
                          f"({c['avg']:+.2f}, {c['n']} obs){hl}")

    if mkt["days"] == 0:
        console.print("\n[yellow]No history yet — runs accumulate one row per scan day. "
                      "Check back after a few daily runs.[/yellow]")


def run_backtest(args) -> None:
    """Backtest the current BUY basket as a monthly SIP vs the NIFTY index."""
    from data.nse_universe import get_symbols
    from data.fetcher import fetch_batch
    from screening.halal_screener import screen_batch
    from analysis.fundamental import compute
    from analysis.scorer import compute_conviction_score
    from signals.generator import generate
    from analysis.backtest import load_monthly_prices, simulate_sip

    config.SCREENING_MODE = args.mode

    console.print(f"[cyan]Selecting current picks from {args.universe}...[/cyan]")
    symbols = get_symbols(args.universe)
    data = fetch_batch(symbols, max_workers=config.MAX_WORKERS)
    halal = screen_batch(data)
    passed = {s: d for s, d in data.items() if halal[s].passed}
    metrics = {s: compute(s, d) for s, d in passed.items()}
    scores = {s: compute_conviction_score(d, metrics[s]) for s, d in passed.items()}
    signals = generate(data, halal, metrics, scores, min_score=config.BUY_THRESHOLD)

    basket = [s for s in signals if s.tier in ("STRONG BUY", "BUY")]
    basket.sort(key=lambda s: s.score, reverse=True)
    basket = basket[:config.MAX_POSITIONS]
    if not basket:
        console.print("[red]No BUY signals to backtest.[/red]")
        return

    basket_syms = [s.symbol for s in basket]
    console.print(f"[cyan]Backtesting {len(basket_syms)} stocks as ₹{args.amount:,.0f}/mo "
                  f"SIP over {args.years}y...[/cyan]")

    months, prices = load_monthly_prices(basket_syms, args.years)
    bench_months, bench_prices = load_monthly_prices(["^NSEI"], args.years)

    strat = simulate_sip(months, prices, args.amount)
    bench = simulate_sip(bench_months, bench_prices, args.amount)

    def _line(label, r):
        ann = f"{r['annual_return']:+.1%}/yr" if r["annual_return"] is not None else "n/a"
        console.print(f"  {label:18} invested ₹{r['invested']:,.0f}  →  "
                      f"₹{r['final_value']:,.0f}  ({r['return_pct']:+.1%}, {ann})")

    console.print("\n[bold]═══ BACKTEST (monthly SIP) ═══[/bold]")
    _line("Strategy basket", strat)
    _line("NIFTY 50", bench)
    edge = strat["return_pct"] - bench["return_pct"]
    verdict = "[green]beat[/green]" if edge > 0 else "[red]lagged[/red]"
    console.print(f"\n  Strategy {verdict} NIFTY by {edge:+.1%} over the period.")

    console.print("\n  [bold]Per-stock (final value):[/bold]")
    for sym, b in strat["breakdown"].items():
        console.print(f"    {sym.replace('.NS',''):12} ₹{b['value']:>9,.0f}  "
                      f"({b['shares']} sh @ ₹{b['last_price']:,.2f})")

    console.print("\n[yellow]⚠ Look-ahead/survivorship bias: basket chosen with today's "
                  "fundamentals. Treat as an optimistic sanity check, not a guarantee.[/yellow]")


def run_sync_sheets(args) -> None:
    """Fetch live prices for held positions and push the portfolio to Google Sheets."""
    from integrations import gsheets
    from paper_trading.sqlite_engine import init_db, get_open_trades
    from data.fetcher import fetch_batch

    if not gsheets.is_configured():
        console.print("[red]Google Sheets not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
                      "or GOOGLE_APPLICATION_CREDENTIALS.[/red]")
        return

    init_db()
    open_trades = get_open_trades()
    prices: dict[str, float] = {}
    if open_trades:
        symbols = sorted({t["symbol"] for t in open_trades})
        console.print(f"[cyan]Fetching live prices for {len(symbols)} held positions...[/cyan]")
        data = fetch_batch(symbols, max_workers=config.MAX_WORKERS)
        for s, d in data.items():
            cp = (d or {}).get("info", {}).get("current_price")
            if cp:
                prices[s] = cp

    url = gsheets.sync(prices)
    console.print(f"[green]Google Sheet updated:[/green] {url}")


def run_paper(args) -> None:
    from paper_trading.executor import print_portfolio_summary
    from paper_trading.sqlite_engine import get_all_trades
    print_portfolio_summary()

    if args.history:
        trades = get_all_trades()
        console.print(f"\n[dim]All trades ({len(trades)} total):[/dim]")
        for t in trades[:20]:
            status = "[green]OPEN[/green]" if t["status"] == "OPEN" else "[dim]CLOSED[/dim]"
            pnl = f"P&L: {t['pnl_pct']:+.1%}" if t["pnl_pct"] else ""
            console.print(f"  {t['entry_date']}  {t['symbol']:15}  {t['signal_tier']:10}  {status}  {pnl}")


def main():
    args = parse_args()

    if args.command == "scan":
        run_scan(args)
    elif args.command == "brief":
        run_brief(args)
    elif args.command == "portfolio":
        run_portfolio(args)
    elif args.command == "paper":
        run_paper(args)
    elif args.command == "sync-sheets":
        run_sync_sheets(args)
    elif args.command == "backtest":
        run_backtest(args)
    elif args.command == "last30days":
        run_last30days(args)
    elif args.command == "dashboard":
        from dashboard.app import app as flask_app
        console.print("[cyan]Starting dashboard at http://localhost:5000[/cyan]")
        flask_app.run(debug=False, port=5000)
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
