# CLAUDE.md

Guidance for Claude Code (and humans) working in this repo.

## What this is
**NSE Halal Algo Trader** — a CLI that screens NSE stocks for Shariah-compliant,
fundamentally strong buys, paper-trades them within a budget, mirrors the
portfolio to Google Sheets, emails a "why" summary on execution, and can
backtest the current basket against NIFTY.

Pipeline (in `main.py run_scan`): universe → fetch (yfinance) → halal screen →
fundamentals → conviction score → tiered signals → paper execution → email →
Google Sheets sync.

## Commands
```bash
python main.py scan            # full pipeline: screen, paper-trade, email, sync sheet
python main.py scan --universe nifty50 --mode STANDARD --no-execute
python main.py brief           # pre-market market/global brief
python main.py portfolio       # analyse real holdings (CSV/Upstox)
python main.py paper [--history]   # show paper portfolio
python main.py sync-sheets     # push paper portfolio to Google Sheets
python main.py backtest --universe nifty50 --years 5 --amount 7000  # SIP vs NIFTY
python main.py last30days [--days 30]  # market/sector/company sentiment memory
python main.py dashboard       # Flask web dashboard (localhost:5000)
```
Key `scan` flags: `--no-execute` (signals only, no trades), `--live` (real Upstox
orders, asks per order), `--output csv|none`, `--detail SYMBOL`, `--show-rejected`.

## Architecture
- `data/` — `nse_universe.py` (symbol lists), `fetcher.py` (yfinance fundamentals + price; **current snapshot only, no point-in-time history**)
- `screening/halal_screener.py` — AAOIFI / Nifty50-Shariah thresholds (`STANDARD` vs `STRICT_INDIA`)
- `analysis/` — `fundamental.py` (metrics incl. `price`), `scorer.py` (conviction + hard gates), `backtest.py` (SIP simulator + XIRR)
- `signals/generator.py` — `BuySignal` dataclass; tiers STRONG BUY / BUY / WATCH; `strengths`/`risks` ("the why")
- `paper_trading/` — `sqlite_engine.py` (trades / daily_pnl / portfolio_snapshots; SQLite or Postgres via `DATABASE_URL`), `executor.py` (budget-aware buy/sell), `db.py`
- `integrations/gsheets.py` — service-account Sheets sync + dashboard
- `reports/` — `cli_report.py`, `csv_report.py`, `email_report.py` (Gmail API)
- `market_intelligence/` — `morning_brief.py`, `pre_market.py`, `india_macro.py` (VIX/FII), `crypto_pulse.py`, `sentiment.py` (keyword news scoring + yfinance headlines), `regime.py` (market snapshot + 30-day market/sector/company summarisers)
- `brokers/` — Upstox live executor (sandbox/live)

## Paper trading & budget model
- **Paper validation budget** is sized large to build a track record fast (paper money is free): `MONTHLY_BUDGET_INR` (config). Total open exposure is capped at this, split equally across the top-scoring picks, max `MAX_POSITIONS`.
- **Real-money budget** is separate: `REAL_MONTHLY_BUDGET_INR = 7000` (used as the default backtest SIP amount and for live sizing intent). The ₹7k cap only applies to real money.
- `executor.execute_buy_signals` opens new positions only up to remaining budget/free slots, highest score first; returns rich info (invested, qty, sector, strengths) used by the email.
- Sells: `check_sell_signals` (stop-loss `SELL_DRAWDOWN_STOP`, halal breach, score collapse, overvaluation, Beneish, pledge).

## Google Sheets dashboard
- Auth: **service account** (`GOOGLE_SERVICE_ACCOUNT_JSON` raw JSON or path, or `GOOGLE_APPLICATION_CREDENTIALS`). Service accounts **cannot create** files in a personal Drive — so pre-create a sheet, share it (Editor) with the SA email, set `GOOGLE_SHEET_ID`. Sync self-heals/validates the configured id.
- Tabs rebuilt from the DB each sync: **Trades**, **Daily P&L**, **Snapshots** (includes `NIFTY 50` level), **Dashboard**.
- Dashboard shows: totals, **Total % Change**, **NIFTY 50 since inception**, **Strategy vs NIFTY**, win rate, top movers, equity-curve chart.

## Email notifications
- `reports/email_report.send_portfolio_digest` emails a **daily digest every run** (even with no new trades): all current holdings with live % change, totals, and **vs NIFTY since inception**, plus market/global context and any new buys that day.
- `reports/email_report.send_trade_notification` (legacy) emails only after trades execute: per-stock "why" (strengths) + market/global context + portfolio summary.
- Needs Gmail OAuth: `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` (one-time `setup_gmail()`), `REPORT_EMAIL_TO`. Silently skips if unconfigured.

## Backtest
- `analysis/backtest.py`: unbiased, unit-tested monthly-SIP simulator + money-weighted (XIRR) annualised return; `load_monthly_prices` via yfinance.
- `main.py backtest` selects the current BUY/STRONG BUY basket and simulates a SIP vs NIFTY (`^NSEI`).
- ⚠️ **Look-ahead/survivorship bias**: basket chosen with today's fundamentals (yfinance has no point-in-time fundamentals). Treat results as an optimistic sanity check, not a forecast. A clean backtest needs paid historical-fundamental data.

## CI workflows (`.github/workflows/`)
- `daily_scan.yml` — weekday 9:30 AM IST (cron `0 4 * * 1-5`) + manual. Runs scan (records paper trades, emails, syncs Sheets), commits `output/` (incl. sqlite DB & `gsheet_id.txt` when no Postgres). Scheduled runs use the **default branch** only.
- `daily_run.yml` — 8:00 AM IST scan (no trading/sync).
- `backtest.yml` — manual dispatch (`workflow_dispatch`) with universe/years/amount inputs; prints result to the job summary.

## Secrets / env (see `.env.example`)
`GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_ID`, `GSHEET_SHARE_EMAIL`,
`GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN`, `REPORT_EMAIL_TO`, `DATABASE_URL`
(Postgres for persistent history), `UPSTOX_*`. Never commit secrets — `.env` is gitignored.

## Testing
`python -m pytest -q` — covers halal screening, fundamentals, scoring, the SIP
backtest math, and the Sheets row/benchmark builders. Pure helpers are designed
to be testable without network.

## Conventions / gotchas
- yfinance/Yahoo hosts and Google APIs must be reachable — blocked in some
  sandboxes (403); runs succeed in GitHub Actions.
- `data/fetcher.py` returns **current** data only; do not assume historical
  point-in-time fundamentals exist.
- Symbols carry the `.NS` suffix internally.
- Don't set `LIVE_TRADING=True` in committed config.

## Changelog — added 2026-06-22
- Google Sheets paper-trade dashboard + sync (`integrations/gsheets.py`, `sync-sheets` command).
- Budget-aware sizing: paper validation budget (`MONTHLY_BUDGET_INR`/`MAX_POSITIONS`) vs real `REAL_MONTHLY_BUDGET_INR = 7000`.
- Trade-notification emails with per-stock "why" + market/global context.
- Backtest mode (`analysis/backtest.py`, `backtest` command, `backtest.yml`).
- **NIFTY benchmark tracker**: snapshots store the NIFTY level; dashboard shows "NIFTY 50 since inception" and "Strategy vs NIFTY".
- CI: `daily_scan.yml` records paper trades + syncs sheet + emails (Upstox order step removed); secrets wired.
- Fix: SyntaxError in `morning_brief.print_brief` (nested f-string backslash).

## Changelog — added 2026-06-22 (market memory + news)
- **Market memory**: each scan logs a `market_regime` row (global indices + India VIX + FII) → `last30days` command + `/last30days` skill report market/sector/company sentiment over N days. New DB tables `market_regime`, `sector_sentiment`, `stock_news`; **Market Regime** tab added to the Sheet.
- **News-aware picks**: `market_intelligence/sentiment.py` pulls free yfinance headlines and keyword-scores them; `executor.execute_buy_signals(signals, news_map)` nudges ranking by news (bounded ±5) and stores the headline (`trades.news` column, **News** column in the Sheet).
- Trade email now quotes the actual headline behind each buy.
- Tests: `test_sentiment.py`, `test_regime.py` (pure scoring/summarising).
