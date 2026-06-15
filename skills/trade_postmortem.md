# Trade Postmortem

Adapted from tradermonty/claude-trading-skills signal-postmortem.
For reviewing closed paper trades and learning from them.

## Trigger
Use after a trade is closed to analyse what happened.
Run with: `/trade_postmortem TRADE_ID`

## What to Review

For each closed trade, analyse:

### 1. Entry Quality
- Was the halal screen correct? Did anything change post-entry?
- What was the conviction score at entry? Was it genuinely ≥ 60?
- Was it near 52-week high at entry (bad timing) or near 52-week low (good timing)?
- What was the macro regime at entry?

### 2. Holding Period
- Did we hold for minimum 1 year? If not, why did sell trigger early?
- If stop-loss hit (-30%): was the original thesis wrong, or just volatility?
- If halal breach triggered: was this predictable from the original screen?

### 3. Exit Quality
- Did we exit at the right time? (score collapse, halal breach, valuation extreme)
- Did the Beneish M-Score signal manipulation before the exit?
- Were there red flags we missed?

### 4. P&L Attribution
- Which score category drove the outcome? (valuation/profitability/growth/quality/health/india)
- Would a stricter gate (STRICT_INDIA mode) have avoided this trade?

### 5. Lessons
- What would we do differently?
- Should any sector_map.py or config.py thresholds be adjusted?
- Add to MANUAL_BLACKLIST if company turned haram post-entry?

## Output Format
1. Entry quality: GOOD / FAIR / POOR
2. Exit quality: GOOD / FAIR / POOR
3. Main lesson in one sentence
4. Recommended config change (if any)
