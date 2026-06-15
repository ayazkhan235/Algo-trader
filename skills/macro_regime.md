# India Macro Regime Detector

Adapted from tradermonty/claude-trading-skills macro-regime-detector.
Uses yfinance data pointed at Indian indices instead of US.

## Trigger
Use when assessing overall market environment before scanning or buying.
Run with: `/macro_regime`

## What This Skill Does

Determines the current 1-2 year macro regime for Indian equities using cross-asset ratios.

## Key Indicators to Assess

### Risk-On vs Risk-Off
- India VIX < 15 = calm, suitable for full deployment
- India VIX 15-22 = moderate, normal investing
- India VIX > 22 = elevated fear — consider waiting or buying quality dips only
- India VIX > 30 = extreme fear — historically good long-term entry but only top-quality stocks

### Rate Cycle (RBI)
- Rate cut cycle = equity positive (cheaper capital, P/E expansion)
- Rate hike cycle = equity cautious (compression risk, especially growth stocks)
- Check: Is RBI in cutting, hiking, or pause mode?

### Global Liquidity
- US Fed easing = DXY weakens = FII flows into India = positive
- US Fed tightening = DXY strengthens = FII outflows = negative
- Monitor: DXY, US 10Y yield

### FII Trend (30-day)
- FII net buyer for 20+ of last 30 days = BULLISH regime
- FII net seller for 20+ of last 30 days = BEARISH regime
- Mixed = NEUTRAL

### Corporate Earnings Trend
- NSE 500 earnings growth > 15% = earnings expansion regime (buy)
- NSE 500 earnings growth 5-15% = moderate (selective buying)
- NSE 500 earnings growth < 5% = earnings compression (cautious)

## Regime Output

After assessing the above:
1. Assign regime: EXPANSION / CONSOLIDATION / CONTRACTION / RECOVERY
2. Recommend position sizing: FULL (100%) / MODERATE (60%) / CONSERVATIVE (30%) / CASH
3. Identify which sectors outperform in this regime

## India Sector Rotation by Regime

| Regime       | Outperform                | Underperform          |
|--------------|---------------------------|-----------------------|
| EXPANSION    | IT, Consumer Disc, Auto   | Utilities, FMCG       |
| CONSOLIDATION| FMCG, Pharma, IT          | Capital Goods, Metals |
| CONTRACTION  | Pharma, FMCG, Gold proxies| IT, Auto, Metals      |
| RECOVERY     | Capital Goods, Auto, Banks| FMCG, Pharma          |

Note: Banks excluded from halal portfolio — replace with NBFCs/insurance where halal.
