"""
CSV-based portfolio importer.
Handles Groww export format and a generic fallback format.
Place CSV files in the /input/ folder — they will all be read and merged.
"""
import os
import csv
from dataclasses import dataclass
from typing import Optional


@dataclass
class Holding:
    symbol: str          # NSE symbol with .NS suffix
    name: str
    quantity: float
    avg_buy_price: float
    current_price: Optional[float]
    broker: str          # "groww" | "zerodha" | "upstox" | "manual"


INPUT_DIR = "input"

# Groww P&L export column names (as of 2025)
GROWW_COLS = {
    "symbol":    ["Symbol", "Scrip", "NSE Symbol"],
    "name":      ["Company Name", "Stock Name", "Company"],
    "qty":       ["Qty", "Quantity", "Shares"],
    "avg_price": ["Avg. Buy Price", "Average Buy Price", "Buy Price"],
    "ltp":       ["LTP", "Current Price", "CMP"],
}

# Generic/manual CSV format
GENERIC_COLS = {
    "symbol":    ["symbol", "Symbol", "SYMBOL"],
    "name":      ["name", "Name", "company"],
    "qty":       ["quantity", "qty", "Qty"],
    "avg_price": ["avg_buy_price", "avg_price", "buy_price"],
    "ltp":       ["current_price", "ltp", "cmp"],
}


def _find_col(header: list[str], candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in header:
            return c
    return None


def _to_float(val: str) -> Optional[float]:
    try:
        return float(str(val).replace(",", "").replace("₹", "").strip())
    except Exception:
        return None


def _parse_csv(filepath: str, broker: str = "manual") -> list[Holding]:
    holdings = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        col_map = GROWW_COLS if broker == "groww" else GENERIC_COLS

        sym_col   = _find_col(header, col_map["symbol"])
        name_col  = _find_col(header, col_map["name"])
        qty_col   = _find_col(header, col_map["qty"])
        price_col = _find_col(header, col_map["avg_price"])
        ltp_col   = _find_col(header, col_map["ltp"])

        if not (sym_col and qty_col and price_col):
            print(f"[csv] Could not map required columns in {filepath}. Header: {header}")
            return []

        for row in reader:
            sym = str(row.get(sym_col, "")).strip()
            if not sym:
                continue
            if not sym.endswith(".NS"):
                sym = sym + ".NS"

            qty  = _to_float(row.get(qty_col, ""))
            avg  = _to_float(row.get(price_col, ""))
            ltp  = _to_float(row.get(ltp_col, "")) if ltp_col else None
            name = str(row.get(name_col, "")).strip() if name_col else ""

            if qty and avg:
                holdings.append(Holding(
                    symbol=sym, name=name, quantity=qty,
                    avg_buy_price=avg, current_price=ltp, broker=broker,
                ))

    return holdings


def load_all_csvs(input_dir: str = INPUT_DIR) -> list[Holding]:
    """Load all CSV files from the input directory."""
    if not os.path.isdir(input_dir):
        return []

    all_holdings = []
    for fname in os.listdir(input_dir):
        if not fname.endswith(".csv"):
            continue
        fpath = os.path.join(input_dir, fname)
        broker = "groww" if "groww" in fname.lower() else "manual"
        holdings = _parse_csv(fpath, broker=broker)
        all_holdings.extend(holdings)
        print(f"[csv] Loaded {len(holdings)} holdings from {fname}")

    return all_holdings
