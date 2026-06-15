# Position Sizer

Universal risk-based position sizing for long-term halal investing.
Adapted from tradermonty/claude-trading-skills position-sizer (no changes needed — pure math).

## Trigger
Use when deciding how much to invest in a new buy signal.
Run with: `/position_sizer SYMBOL SCORE`

## Rules

### Base Position Size
Default: ₹10,000 per trade (configurable in config.py as POSITION_SIZE_INR)
For real portfolio: 2-5% of total portfolio per position maximum.

### Signal-Based Sizing
| Signal Tier    | Size Multiplier | Max % of Portfolio |
|----------------|-----------------|--------------------|
| STRONG BUY (75+) | 1.5×          | 5%                 |
| BUY (60-74)    | 1.0×            | 3%                 |
| WATCH (50-59)  | 0.5×            | 1.5%               |

### Concentration Rules (Halal Portfolio)
Since banks are excluded, IT and Pharma tend to dominate halal portfolios.
Apply sector caps:
- No single sector > 30% of portfolio
- No single stock > 8% of portfolio
- Minimum 10 positions for adequate diversification

### Risk Per Trade
Maximum loss tolerance per position: 5% of total portfolio
This implies: if stop-loss is at -30%, max position = 5% / 30% ≈ 16.7% of portfolio
→ Sector cap (30%) keeps this in check

### Rebalancing Signal
If a position grows to > 10% of portfolio (due to price appreciation):
- Trim back to 8% (take partial profits)
- This locks in gains while keeping the winner running

## Output Format
When this skill is invoked, output:
1. Recommended position size in ₹ and % of portfolio
2. Number of shares at current price
3. Stop-loss price (entry × (1 + SELL_DRAWDOWN_STOP))
4. Position limit check: does this breach any concentration rule?
