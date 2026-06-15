"""
Merges and deduplicates holdings from all brokers (Upstox, Zerodha, Groww CSV).
When same symbol held across multiple brokers, merges into a single position.
"""
from portfolio.csv_importer import Holding, load_all_csvs
from portfolio.upstox_live import get_holdings as upstox_holdings


def get_consolidated_holdings(include_live: bool = True) -> list[Holding]:
    all_holdings: list[Holding] = []

    # 1. Upstox live API (if available)
    if include_live:
        all_holdings += upstox_holdings()

    # 2. CSV imports (Groww + any other broker)
    all_holdings += load_all_csvs()

    # Deduplicate: merge same symbol across brokers
    merged: dict[str, Holding] = {}
    for h in all_holdings:
        sym = h.symbol
        if sym not in merged:
            merged[sym] = h
        else:
            existing = merged[sym]
            total_qty = existing.quantity + h.quantity
            # Weighted average buy price
            avg = (existing.avg_buy_price * existing.quantity +
                   h.avg_buy_price * h.quantity) / total_qty
            merged[sym] = Holding(
                symbol=sym,
                name=existing.name or h.name,
                quantity=total_qty,
                avg_buy_price=round(avg, 2),
                current_price=h.current_price or existing.current_price,
                broker=f"{existing.broker}+{h.broker}",
            )

    result = list(merged.values())
    print(f"[portfolio] {len(result)} unique holdings across all brokers")
    return result
