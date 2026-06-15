"""
SQLite-based paper trading engine.
Records virtual trades when buy/sell signals fire.
Tracks daily mark-to-market P&L and computes XIRR on exits.
"""
import sqlite3
import os
from datetime import date, datetime
from typing import Optional
import config

DB_PATH = os.path.join(config.OUTPUT_DIR, "paper_trades.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT NOT NULL,
            name          TEXT,
            entry_date    TEXT NOT NULL,
            entry_price   REAL NOT NULL,
            quantity      REAL NOT NULL,
            position_inr  REAL NOT NULL,
            signal_tier   TEXT NOT NULL,
            score         REAL,
            status        TEXT DEFAULT 'OPEN',   -- OPEN | CLOSED
            exit_date     TEXT,
            exit_price    REAL,
            exit_reason   TEXT,
            pnl_inr       REAL,
            pnl_pct       REAL,
            hold_days     INTEGER
        );

        CREATE TABLE IF NOT EXISTS daily_pnl (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            trade_id    INTEGER,
            price       REAL,
            pnl_inr     REAL,
            pnl_pct     REAL
        );

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            total_invested  REAL,
            total_value     REAL,
            total_pnl       REAL,
            total_pnl_pct   REAL,
            open_positions  INTEGER,
            closed_trades   INTEGER
        );
        """)


def open_trade(
    symbol: str,
    name: str,
    entry_price: float,
    signal_tier: str,
    score: float,
    position_size_inr: float = config.POSITION_SIZE_INR,
) -> int:
    """Records a new paper trade. Returns trade ID."""
    qty = round(position_size_inr / entry_price, 4)
    today = date.today().isoformat()

    with _conn() as con:
        cur = con.execute(
            """INSERT INTO trades
               (symbol, name, entry_date, entry_price, quantity, position_inr,
                signal_tier, score, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
            (symbol, name, today, entry_price, qty, qty * entry_price, signal_tier, score),
        )
        trade_id = cur.lastrowid

    print(f"[paper] OPEN  {symbol} @ ₹{entry_price:.2f}  qty={qty:.4f}  "
          f"tier={signal_tier}  score={score:.0f}  id={trade_id}")
    return trade_id


def close_trade(trade_id: int, exit_price: float, reason: str) -> dict:
    """Closes an open trade and records P&L."""
    with _conn() as con:
        row = con.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row or row["status"] != "OPEN":
            raise ValueError(f"Trade {trade_id} not found or already closed")

        pnl_inr = (exit_price - row["entry_price"]) * row["quantity"]
        pnl_pct = (exit_price / row["entry_price"]) - 1
        today = date.today().isoformat()
        entry_dt = datetime.fromisoformat(row["entry_date"])
        hold_days = (datetime.now() - entry_dt).days

        con.execute(
            """UPDATE trades
               SET status='CLOSED', exit_date=?, exit_price=?, exit_reason=?,
                   pnl_inr=?, pnl_pct=?, hold_days=?
               WHERE id=?""",
            (today, exit_price, reason, pnl_inr, pnl_pct, hold_days, trade_id),
        )

    print(f"[paper] CLOSE {row['symbol']} @ ₹{exit_price:.2f}  "
          f"P&L={pnl_pct:.1%} (₹{pnl_inr:+.0f})  reason={reason}")
    return {"pnl_inr": pnl_inr, "pnl_pct": pnl_pct, "hold_days": hold_days}


def get_open_trades() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_date").fetchall()
    return [dict(r) for r in rows]


def get_all_trades() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM trades ORDER BY entry_date DESC").fetchall()
    return [dict(r) for r in rows]


def is_already_held(symbol: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT id FROM trades WHERE symbol=? AND status='OPEN'", (symbol,)
        ).fetchone()
    return row is not None


def record_daily_prices(prices: dict[str, float]) -> None:
    """Update daily P&L for all open positions. prices = {symbol: current_price}"""
    today = date.today().isoformat()
    open_trades = get_open_trades()

    with _conn() as con:
        for trade in open_trades:
            sym = trade["symbol"]
            price = prices.get(sym)
            if price is None:
                continue
            pnl_inr = (price - trade["entry_price"]) * trade["quantity"]
            pnl_pct = (price / trade["entry_price"]) - 1
            con.execute(
                """INSERT INTO daily_pnl (date, symbol, trade_id, price, pnl_inr, pnl_pct)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (today, sym, trade["id"], price, pnl_inr, pnl_pct),
            )


def portfolio_summary(current_prices: dict[str, float] = None) -> dict:
    """Returns current portfolio summary."""
    open_trades = get_open_trades()
    with _conn() as con:
        closed = con.execute(
            "SELECT COUNT(*), SUM(pnl_inr) FROM trades WHERE status='CLOSED'"
        ).fetchone()

    total_invested = sum(t["position_inr"] for t in open_trades)
    total_value = total_invested

    if current_prices:
        total_value = sum(
            current_prices.get(t["symbol"], t["entry_price"]) * t["quantity"]
            for t in open_trades
        )

    closed_count = closed[0] or 0
    closed_pnl   = closed[1] or 0.0
    open_pnl     = total_value - total_invested

    return {
        "open_positions":  len(open_trades),
        "total_invested":  round(total_invested, 2),
        "total_value":     round(total_value, 2),
        "open_pnl_inr":   round(open_pnl, 2),
        "open_pnl_pct":   round(open_pnl / total_invested, 4) if total_invested else 0,
        "closed_trades":   closed_count,
        "closed_pnl_inr":  round(closed_pnl, 2),
        "total_pnl_inr":   round(open_pnl + closed_pnl, 2),
    }
