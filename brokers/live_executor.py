"""
Semi-automatic live trade executor for Upstox.

Shows each signal and asks for confirmation before placing any real order.
Never places an order without explicit user approval (y/yes).
"""
import math
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from signals.generator import BuySignal
import config
from brokers import upstox_broker

console = Console()


def execute_live_signals(signals: list[BuySignal]) -> list[dict]:
    """
    For each STRONG BUY / BUY signal:
      1. Show signal details
      2. Calculate quantity based on LIVE_POSITION_SIZE_INR
      3. Ask user to confirm
      4. Place real order on Upstox if confirmed
    Returns list of executed order dicts.
    """
    actionable = [s for s in signals if s.tier in ("STRONG BUY", "BUY")]

    if not actionable:
        console.print("[yellow]No STRONG BUY or BUY signals to act on.[/yellow]")
        return []

    # Verify token exists before starting
    try:
        token = upstox_broker.get_access_token()
        if not token:
            raise RuntimeError("No token")
    except Exception:
        console.print(
            "[red bold]Upstox not authenticated.[/red bold]\n"
            "Run this first:\n"
            "  [cyan]python -m brokers.upstox_broker --login[/cyan]"
        )
        return []

    from brokers.upstox_broker import _MODE
    mode_label = "[yellow]SANDBOX (paper)[/yellow]" if _MODE == "SANDBOX" else "[bold red]LIVE (real money)[/bold red]"
    console.print(f"\n[bold cyan]── Upstox Trade Executor ──[/bold cyan]  Mode: {mode_label}  ₹{config.LIVE_POSITION_SIZE_INR:,}/trade")
    console.print(f"[dim]{len(actionable)} signal(s) to review. You will confirm each one.[/dim]\n")

    executed = []

    for sig in actionable:
        _print_signal_card(sig)

        price = sig.metrics.get("price")
        if not price:
            console.print("[red]  ✗ No price data — skipping[/red]\n")
            continue

        quantity = max(1, math.floor(config.LIVE_POSITION_SIZE_INR / price))
        order_value = quantity * price

        console.print(f"  [bold]Proposed order:[/bold] BUY {quantity} share(s) of {sig.symbol.replace('.NS','')} @ ~₹{price:,.2f}  =  ₹{order_value:,.0f}")
        console.print(f"  [dim](Market order, Delivery/CNC, NSE)[/dim]")

        answer = Prompt.ask(
            f"\n  [bold yellow]Place this order?[/bold yellow]",
            choices=["y", "n", "skip"],
            default="n",
        )

        if answer != "y":
            console.print("  [dim]Skipped.[/dim]\n")
            continue

        # Look up instrument key
        console.print(f"  [cyan]Looking up instrument key for {sig.symbol}...[/cyan]")
        sym_clean = sig.symbol.replace(".NS", "")
        instrument_key = upstox_broker.get_instrument_key(sym_clean)

        if not instrument_key:
            console.print(f"  [red]✗ Could not find instrument key for {sym_clean} on Upstox. Skipping.[/red]\n")
            continue

        # Confirm once more with full details
        console.print(f"\n  [bold red]FINAL CONFIRMATION[/bold red]")
        console.print(f"  Symbol   : {sym_clean}")
        console.print(f"  Quantity : {quantity} share(s)")
        console.print(f"  Est. cost: ₹{order_value:,.0f}")
        console.print(f"  Type     : MARKET BUY, Delivery (CNC)")
        console.print(f"  [bold red]This places a REAL order in your Upstox account.[/bold red]")

        confirm = Prompt.ask("  Confirm?", choices=["yes", "no"], default="no")
        if confirm != "yes":
            console.print("  [dim]Order cancelled.[/dim]\n")
            continue

        # Place the order
        try:
            console.print(f"  [cyan]Placing order...[/cyan]")
            result = upstox_broker.place_market_buy(sym_clean, quantity, instrument_key)
            order_id = result.get("data", {}).get("order_id", "unknown")
            console.print(f"  [bold green]✓ Order placed! Order ID: {order_id}[/bold green]")

            executed.append({
                "symbol":        sig.symbol,
                "tier":          sig.tier,
                "score":         sig.score,
                "quantity":      quantity,
                "approx_price":  price,
                "order_value":   order_value,
                "order_id":      order_id,
                "instrument_key": instrument_key,
            })

        except Exception as e:
            console.print(f"  [bold red]✗ Order failed: {e}[/bold red]")

        console.print()

    # Summary
    if executed:
        console.print(f"\n[bold green]── Live Orders Placed: {len(executed)} ──[/bold green]")
        t = Table(show_header=True, header_style="bold")
        t.add_column("Symbol")
        t.add_column("Tier")
        t.add_column("Score")
        t.add_column("Qty")
        t.add_column("Value")
        t.add_column("Order ID")
        for e in executed:
            t.add_row(
                e["symbol"].replace(".NS", ""),
                e["tier"],
                f"{e['score']:.0f}",
                str(e["quantity"]),
                f"₹{e['order_value']:,.0f}",
                e["order_id"],
            )
        console.print(t)

    return executed


def _print_signal_card(sig: BuySignal):
    tier_color = "bold green" if sig.tier == "STRONG BUY" else "bold blue"
    console.print(f"[{tier_color}]▶ {sig.symbol.replace('.NS','')}[/{tier_color}]  [{tier_color}]{sig.tier}[/{tier_color}]  Score: [bold]{sig.score:.1f}[/bold]")
    console.print(f"  [dim]{sig.name}  |  {sig.sector}[/dim]")
    if sig.strengths:
        console.print(f"  [green]Strengths: {' · '.join(sig.strengths[:2])}[/green]")
    if sig.risks:
        console.print(f"  [yellow]Risks:     {' · '.join(sig.risks[:2])}[/yellow]")
