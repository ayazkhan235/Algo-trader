# India Macro Scenario Analyzer

Adapted from tradermonty/claude-trading-skills scenario-analyzer.
Modified for Indian equity market headlines and NSE sector impacts.

## Trigger
Use when a major macro event or headline could affect your portfolio.
Run with: `/scenario_analyzer "HEADLINE OR EVENT"`

## What This Skill Does

Takes a macro headline and generates 3 scenarios (Bull / Base / Bear) over an 18-month horizon,
with probability weightings and NSE sector impacts.

## Instructions for Claude

When this skill is invoked with a headline:

### Step 1 — Classify the event
Identify what type of event it is:
- RBI policy change (rate cut / hike / pause)
- Union Budget announcement
- Global risk event (US recession, Fed move, crude shock, China slowdown)
- Geopolitical event (India-Pakistan tensions, oil embargo)
- Domestic political event (election result, coalition change)
- Corporate/sector-specific (PLI scheme, new regulation, GST change)

### Step 2 — Generate 3 scenarios

For each scenario provide:
- **Probability** (must sum to 100%)
- **Macro outcome** in 18 months
- **Nifty 500 range** (price impact estimate)
- **INR/USD direction**
- **RBI response**
- **Sector winners** (from NSE halal universe — exclude banks)
- **Sector losers**
- **Portfolio action** (buy more / hold / trim / exit)

| Scenario | Probability | Trigger |
|----------|-------------|---------|
| BULL | X% | What has to go right |
| BASE | X% | Most likely path |
| BEAR | X% | What could go wrong |

### Step 3 — Halal Portfolio Impact

Map each scenario to your held sectors:
- IT stocks: sensitivity to USD/INR and US tech spending
- Pharma: sensitivity to US FDA, INR, raw material costs
- Auto: sensitivity to crude oil, EV transition, rural income
- Consumer: sensitivity to inflation, rural demand, GST
- Capital Goods / Infra: sensitivity to govt capex, elections
- Energy (Coal India, ONGC): sensitivity to crude, energy transition

### Step 4 — Recommended Action

State clearly:
1. Which open positions to protect (add stop-loss)
2. Which positions benefit from this event (hold / add)
3. Whether to delay new buys until clarity emerges
4. One-line summary: "This event is NET POSITIVE / NEUTRAL / NEGATIVE for a halal NSE portfolio because..."

## Example Usage

`/scenario_analyzer "RBI cuts repo rate by 50bps in surprise move"`
`/scenario_analyzer "US imposes 25% tariff on Indian pharma exports"`
`/scenario_analyzer "Crude oil spikes to $120/barrel on Middle East conflict"`
`/scenario_analyzer "India Q4 GDP growth comes in at 5.2% vs 6.8% expected"`
