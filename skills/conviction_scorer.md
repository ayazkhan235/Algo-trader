# NSE Halal Conviction Scorer

Adapted from tradermonty/claude-trading-skills stanley-druckenmiller-investment skill.
Modified for NSE India long-term halal investing.

## Trigger
Use when you need to explain or validate a stock's 0-100 conviction score.
Run with: `/conviction_scorer SYMBOL`

## What This Skill Does

Synthesises 6 upstream scoring categories into a single conviction score (0-100) and explains what drives it:

| Category       | Weight | What it measures                          |
|----------------|--------|-------------------------------------------|
| Valuation      | 20%    | P/E, P/FCF, EV/EBITDA, PEG, Graham Number|
| Profitability  | 25%    | ROE, ROCE, net margin, gross margin trend |
| Growth         | 15%    | Revenue CAGR, earnings CAGR, FCF growth   |
| Quality/Moat   | 15%    | Cash conversion, capex intensity, FCF yield|
| Financial Health | 15%  | Piotroski F-Score, Altman Z, interest coverage |
| India-Specific | 10%    | Promoter holding, pledge %, FII trend, dividend |

## Hard Gates (auto-disqualify)
- Negative ROE
- Piotroski F-Score < 4/9
- Altman Z-Score < 1.81 (distress zone)
- Beneish M-Score > -1.78 (manipulation risk)
- Promoter pledge > 40%

## Signal Tiers
- 75-100: STRONG BUY — buy with full position size
- 60-74:  BUY — buy with normal position size
- 50-59:  WATCH — monitor for entry opportunity
- <50:    NO SIGNAL — do not buy

## Instructions for Claude

When this skill is invoked:
1. Read the stock's score_breakdown dict from the analysis output
2. Identify the two highest and two lowest scoring categories
3. Explain in plain English WHY the score is what it is
4. State whether any hard gates are close to triggering
5. Give a one-line verdict: "Buy conviction is HIGH/MODERATE/LOW because..."
6. If score is borderline (58-65), highlight what would push it into STRONG BUY

Always frame output in the context of a patient, long-term halal investor.
Do NOT mention short-term price movements as a factor.
