# NSE Earnings Calendar Skill

Adapted from tradermonty/claude-trading-skills earnings-calendar.
Uses NSE results schedule instead of FMP (Financial Modeling Prep).

## Trigger
Use before placing a new buy to check upcoming earnings risk.
Run with: `/earnings_calendar SYMBOL` or `/earnings_calendar` for full portfolio

## What This Skill Does

Checks when a stock (or your full paper portfolio) is next reporting earnings,
and flags whether buying now carries earnings surprise risk.

## India Results Seasons (FY2026-27)

| Quarter | Results Period | When Most Companies Report |
|---------|---------------|---------------------------|
| Q1 FY27 (Apr-Jun 2026) | Jul 15 – Aug 15 2026 | Large caps first week of Aug |
| Q2 FY27 (Jul-Sep 2026) | Oct 15 – Nov 15 2026 | Large caps first week of Nov |
| Q3 FY27 (Oct-Dec 2026) | Jan 15 – Feb 15 2027 | Large caps first week of Feb |
| Q4 FY27 (Jan-Mar 2027) | Apr 15 – May 31 2027 | Large caps last week of Apr |

## Instructions for Claude

When this skill is invoked:

### For a single symbol (`/earnings_calendar INFY`)
1. Identify the current date and which results season we are in
2. Check if the stock has announced a board meeting date for results (use web search)
3. State: days until next results, last reported EPS, analyst consensus estimate if available
4. Flag earnings risk level:
   - **HIGH RISK**: Results within 15 days — do not initiate new position
   - **MODERATE RISK**: Results within 30 days — buy smaller (0.5× position size)
   - **LOW RISK**: Results more than 30 days away — normal position sizing

### For full portfolio (`/earnings_calendar`)
List all open paper positions with their earnings risk level in a table:

| Symbol | Last Results | Next Expected | Days Away | Risk |
|--------|-------------|---------------|-----------|------|
| INFY   | Apr 17 2026 | Jul 17 2026   | 31        | LOW  |
| ...    | ...         | ...           | ...       | ...  |

### Earnings Surprise Rules (for halal long-term investor)

- **Beat + guidance raised**: Hold / consider adding if score still ≥ 60
- **Beat + guidance maintained**: Hold
- **Miss + guidance cut**: Re-run conviction scorer. If score drops below 50 → exit
- **Miss + guidance maintained**: Hold if thesis intact, monitor next quarter
- **Halal ratio change**: Re-run halal screen immediately if financials changed materially

### Sectors with Predictable Earnings Patterns
- **IT**: US client budget cycles — results usually weak in Q3 (Oct-Dec) due to US holidays
- **Pharma**: Watch for US FDA inspection outcomes — can move stock ±20% independent of earnings
- **Auto**: Monsoon season affects Q2 rural demand; festive season boosts Q3
- **FMCG**: Volume growth more important than margin in monsoon quarters
- **Capital Goods/Infra**: Order book announcements often more important than quarterly P&L

## Output Format
1. Earnings risk table for all held positions
2. Flag any position with results within 15 days as DO NOT ADD
3. Recommend whether to wait for results before initiating any new BUY signals
