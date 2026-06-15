"""
Generates the daily pre-market morning brief.
Combines global indicators, crypto pulse, India macro, and portfolio impact.
"""
from datetime import datetime
from market_intelligence.pre_market import (
    fetch_global_indicators, assess_market_sentiment, sector_impact_summary
)
from market_intelligence.crypto_pulse import fetch_crypto_prices, fetch_fear_greed, crypto_market_signal
from market_intelligence.india_macro import fetch_india_vix, fetch_fii_dii_flows, upcoming_events


def generate_brief(portfolio_sectors: list[str] = None) -> dict:
    """
    Fetches all market intelligence and returns a structured brief dict.
    portfolio_sectors: list of sector names from your holdings
    """
    brief = {
        "timestamp": datetime.now().isoformat(),
        "global": {},
        "crypto": {},
        "india": {},
        "sector_impact": {},
        "upcoming_events": [],
        "overall_sentiment": "UNKNOWN",
        "summary_lines": [],
    }

    # Global
    indicators = fetch_global_indicators()
    brief["global"] = indicators
    sentiment = assess_market_sentiment(indicators)
    brief["overall_sentiment"] = sentiment

    # Crypto
    prices = fetch_crypto_prices()
    fg = fetch_fear_greed()
    brief["crypto"] = {"prices": prices, "fear_greed": fg, "signal": crypto_market_signal(prices, fg)}

    # India macro
    vix = fetch_india_vix()
    fii = fetch_fii_dii_flows()
    brief["india"] = {"vix": vix, "fii_dii": fii}

    # Upcoming events
    brief["upcoming_events"] = upcoming_events(days_ahead=14)

    # Sector impact for portfolio
    if portfolio_sectors and indicators:
        brief["sector_impact"] = sector_impact_summary(indicators, portfolio_sectors)

    # Build summary lines
    lines = [f"Market Sentiment: {sentiment}"]

    sp500 = indicators.get("S&P 500", {})
    if sp500:
        lines.append(f"S&P 500: {sp500['price']:,.0f} ({sp500['change_pct']:+.1%})")

    vix_val = vix.get("value")
    if vix_val:
        lines.append(f"India VIX: {vix_val:.1f} — {vix.get('signal', '')}")

    fii_sig = fii.get("signal", "")
    if fii_sig and fii_sig != "UNKNOWN":
        lines.append(f"FII/DII: {fii_sig}")

    crude = indicators.get("Brent Crude", {})
    if crude:
        lines.append(f"Brent Crude: ${crude['price']:.1f} ({crude['change_pct']:+.1%})")

    usdinr = indicators.get("USD/INR", {})
    if usdinr:
        lines.append(f"USD/INR: {usdinr['price']:.2f} ({usdinr['change_pct']:+.1%})")

    btc = prices.get("BTC", {})
    if btc:
        lines.append(f"BTC: ${btc['price_usd']:,.0f} ({btc['change_24h']:+.1%})  "
                     f"Fear & Greed: {fg.get('value', '?')} ({fg.get('label', '?')})")

    lines.append(brief["crypto"]["signal"])

    brief["summary_lines"] = lines
    return brief


def print_brief(brief: dict) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

    console = Console()
    ts = brief.get("timestamp", "")[:16]
    sentiment = brief.get("overall_sentiment", "UNKNOWN")
    colour = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "yellow"}.get(sentiment, "white")

    console.print()
    console.print(Panel(
        f"[bold]NSE Pre-Market Brief[/bold]  [{colour}]{sentiment}[/{colour}]  —  {ts}",
        border_style=colour,
    ))

    # Global table
    g = brief.get("global", {})
    if g:
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        t.add_column("Indicator", width=20)
        t.add_column("Price",     justify="right", width=12)
        t.add_column("Change",    justify="right", width=9)

        key_order = ["S&P 500", "Nasdaq", "Nikkei 225", "Hang Seng", "India VIX",
                     "USD/INR", "Brent Crude", "Gold", "US 10Y Yield"]
        for name in key_order:
            if name not in g:
                continue
            chg = g[name]["change_pct"]
            chg_col = "green" if chg > 0 else "red"
            t.add_row(name, f"{g[name]['price']:,.2f}", f"[{chg_col}]{chg:+.1%}[/{chg_col}]")
        console.print(t)

    # FII/DII + VIX
    india = brief.get("india", {})
    fii = india.get("fii_dii", {})
    vix = india.get("vix", {})
    if fii or vix:
        if vix.get("value"):
            console.print(f"  India VIX: [yellow]{vix['value']:.1f}[/yellow] — {vix.get('signal', '')}")
        if fii.get("signal"):
            console.print(f"  FII/DII:   {fii['signal']}")

    # Crypto
    crypto = brief.get("crypto", {})
    console.print(f"\n  [dim]Crypto:[/dim] {crypto.get('signal', '')}")

    # Upcoming events
    events = brief.get("upcoming_events", [])
    if events:
        console.print("\n  [bold]Upcoming Events:[/bold]")
        for ev in events[:3]:
            console.print(f"    {'TODAY' if ev['days_away'] == 0 else f'In {ev[\"days_away\"]}d'}: {ev['event']}")

    # Sector impact
    impacts = brief.get("sector_impact", {})
    if impacts:
        console.print("\n  [bold]Portfolio Sector Impact:[/bold]")
        for sector, impact in impacts.items():
            console.print(f"    {sector[:25]}: {impact}")

    console.print()
