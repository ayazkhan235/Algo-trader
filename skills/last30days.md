# Last 30 Days — Market Memory

Summarises the **last 30 days** of sentiment at three levels so you can judge
whether the environment is bullish or bearish before trusting fresh picks.

## Trigger
Run with: `/last30days` (or `python main.py last30days --days 30`).
Use before/after a scan to gauge the regime and sector/company news mood.

## What it does
Reads the rolling history that the daily scan logs (one row per scan day) and
reports:

1. **Market-wide regime** — from global indices (Dow, Nasdaq, S&P 500, Nikkei,
   Hang Seng) + India VIX + FII flows. Counts bullish / bearish / neutral days
   and the score trend (improving / weakening).
2. **Sector-wise sentiment** — news sentiment averaged per NSE sector over the
   window; shows which sectors ran hot or cold.
3. **Company-wise sentiment** — per shortlisted/held stock, the net news
   sentiment over the window, with the most sentiment-laden headline.

## Data sources (free, no paid key)
- Global indices & VIX: yfinance (`market_intelligence/pre_market.py`, `india_macro.py`).
- News headlines: yfinance per-ticker news (`market_intelligence/sentiment.py`),
  scored with a transparent keyword model (no LLM).

## How history accumulates
Each `python main.py scan` run logs:
- `market_regime` — one row/day (global mood)
- `sector_sentiment` — per-sector news score/day
- `stock_news` — per-stock headline + score/day

So `/last30days` gets richer the longer the bot runs. With no history yet it
says so — give it a few daily runs.

## How it feeds trading
- News sentiment nudges the conviction ranking in `executor.execute_buy_signals`
  (bounded ±5 points) so genuinely positive-news names rank a little higher.
- The trade email quotes the actual headline behind each buy.
- The Google Sheet gets a **Market Regime** tab and a **News** column on Trades.

## Limitations
- Keyword sentiment is crude (positive/negative word counts), not true NLP.
- yfinance news coverage is uneven for smaller names.
- Market regime is descriptive memory, not a hard trading gate (yet).
