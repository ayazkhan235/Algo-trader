"""
SQLite/PostgreSQL paper trading engine.
Records virtual trades when buy/sell signals fire.
Tracks daily mark-to-market P&L and computes XIRR on exits.
"""
import os
from datetime import date, datetime
from typing import Optional
import config
from paper_trading.db import get_connection, placeholder, is_postgres

DB_PATH = os.path.join(config.OUTPUT_DIR, "paper_trades.db")


def _ensure_dir():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)


def init_db() -> None:
    con = get_connection()
    try:
        cur = con.cursor()
        if is_postgres():
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id            SERIAL PRIMARY KEY,
                symbol        TEXT NOT NULL,
                name          TEXT,
                entry_date    TEXT NOT NULL,
                entry_price   REAL NOT NULL,
                quantity      REAL NOT NULL,
                position_inr  REAL NOT NULL,
                signal_tier   TEXT NOT NULL,
                score         REAL,
                status        TEXT DEFAULT 'OPEN',
                exit_date     TEXT,
                exit_price    REAL,
                exit_reason   TEXT,
                pnl_inr       REAL,
                pnl_pct       REAL,
                hold_days     INTEGER
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_pnl (
                id          SERIAL PRIMARY KEY,
                date        TEXT NOT NULL,
                symbol      TEXT NOT NULL,
                trade_id    INTEGER,
                price       REAL,
                pnl_inr     REAL,
                pnl_pct     REAL
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id              SERIAL PRIMARY KEY,
                date            TEXT NOT NULL,
                total_invested  REAL,
                total_value     REAL,
                total_pnl       REAL,
                total_pnl_pct   REAL,
                open_positions  INTEGER,
                closed_trades   INTEGER
            )
            """)
        else:
            cur.executescript("""
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
        # Migration: add NIFTY benchmark column to snapshots if missing
        try:
            cur.execute("ALTER TABLE portfolio_snapshots ADD COLUMN nifty REAL")
        except Exception:  # noqa: BLE001 — column already exists
            pass
        # Migration: add news headline column to trades if missing
        try:
            cur.execute("ALTER TABLE trades ADD COLUMN news TEXT")
        except Exception:  # noqa: BLE001
            pass
        # Market-memory tables (30-day sentiment at 3 levels)
        cur.execute("""CREATE TABLE IF NOT EXISTS market_regime (
            date TEXT PRIMARY KEY, sentiment TEXT, score REAL,
            sp500 REAL, dow REAL, nasdaq REAL, nikkei REAL, hangseng REAL,
            india_vix REAL, fii_signal TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sector_sentiment (
            date TEXT, sector TEXT, score REAL, label TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS stock_news (
            date TEXT, symbol TEXT, score REAL, label TEXT, headline TEXT)""")
        con.commit()
    finally:
        con.close()


def open_trade(
    symbol: str,
    name: str,
    entry_price: float,
    signal_tier: str,
    score: float,
    position_size_inr: float = config.POSITION_SIZE_INR,
    news: str = None,
) -> int:
    """Records a new paper trade. Returns trade ID."""
    qty = round(position_size_inr / entry_price, 4)
    today = date.today().isoformat()
    ph = placeholder()

    con = get_connection()
    try:
        cur = con.cursor()
        if is_postgres():
            cur.execute(
                f"""INSERT INTO trades
                   (symbol, name, entry_date, entry_price, quantity, position_inr,
                    signal_tier, score, status, news)
                   VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'OPEN', {ph})
                   RETURNING id""",
                (symbol, name, today, entry_price, qty, qty * entry_price, signal_tier, score, news),
            )
            trade_id = cur.fetchone()[0]
        else:
            cur.execute(
                f"""INSERT INTO trades
                   (symbol, name, entry_date, entry_price, quantity, position_inr,
                    signal_tier, score, status, news)
                   VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'OPEN', {ph})""",
                (symbol, name, today, entry_price, qty, qty * entry_price, signal_tier, score, news),
            )
            trade_id = cur.lastrowid
        con.commit()
    finally:
        con.close()

    print(f"[paper] OPEN  {symbol} @ ₹{entry_price:.2f}  qty={qty:.4f}  "
          f"tier={signal_tier}  score={score:.0f}  id={trade_id}")
    return trade_id


def close_trade(trade_id: int, exit_price: float, reason: str) -> dict:
    """Closes an open trade and records P&L."""
    ph = placeholder()
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(f"SELECT * FROM trades WHERE id = {ph}", (trade_id,))
        row = cur.fetchone()
        if not row or row["status"] != "OPEN":
            raise ValueError(f"Trade {trade_id} not found or already closed")

        pnl_inr = (exit_price - row["entry_price"]) * row["quantity"]
        pnl_pct = (exit_price / row["entry_price"]) - 1
        today = date.today().isoformat()
        entry_dt = datetime.fromisoformat(row["entry_date"])
        hold_days = (datetime.now() - entry_dt).days

        cur.execute(
            f"""UPDATE trades
               SET status='CLOSED', exit_date={ph}, exit_price={ph}, exit_reason={ph},
                   pnl_inr={ph}, pnl_pct={ph}, hold_days={ph}
               WHERE id={ph}""",
            (today, exit_price, reason, pnl_inr, pnl_pct, hold_days, trade_id),
        )
        con.commit()
        symbol = row["symbol"]
    finally:
        con.close()

    print(f"[paper] CLOSE {symbol} @ ₹{exit_price:.2f}  "
          f"P&L={pnl_pct:.1%} (₹{pnl_inr:+.0f})  reason={reason}")
    return {"pnl_inr": pnl_inr, "pnl_pct": pnl_pct, "hold_days": hold_days}


def get_open_trades() -> list[dict]:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_date")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def get_all_trades() -> list[dict]:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM trades ORDER BY entry_date DESC")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def is_already_held(symbol: str) -> bool:
    ph = placeholder()
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(
            f"SELECT id FROM trades WHERE symbol={ph} AND status='OPEN'", (symbol,)
        )
        row = cur.fetchone()
        return row is not None
    finally:
        con.close()


def record_daily_prices(prices: dict[str, float]) -> None:
    """Update daily P&L for all open positions. prices = {symbol: current_price}"""
    today = date.today().isoformat()
    open_trades = get_open_trades()
    ph = placeholder()

    con = get_connection()
    try:
        cur = con.cursor()
        # Idempotent per day: clear today's rows before re-recording
        cur.execute(f"DELETE FROM daily_pnl WHERE date={ph}", (today,))
        for trade in open_trades:
            sym = trade["symbol"]
            price = prices.get(sym)
            if price is None:
                continue
            pnl_inr = (price - trade["entry_price"]) * trade["quantity"]
            pnl_pct = (price / trade["entry_price"]) - 1
            cur.execute(
                f"""INSERT INTO daily_pnl (date, symbol, trade_id, price, pnl_inr, pnl_pct)
                   VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                (today, sym, trade["id"], price, pnl_inr, pnl_pct),
            )
        con.commit()
    finally:
        con.close()


def save_snapshot(current_prices: dict[str, float] = None,
                  nifty_level: float = None) -> dict:
    """Upsert one portfolio snapshot row for today (idempotent per day).

    nifty_level: current NIFTY 50 index level, stored so the dashboard can show
    the portfolio's performance vs the index since inception.
    """
    s = portfolio_summary(current_prices)
    today = date.today().isoformat()
    ph = placeholder()
    total_pnl_pct = (s["total_pnl_inr"] / s["total_invested"]) if s["total_invested"] else 0.0

    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(f"DELETE FROM portfolio_snapshots WHERE date={ph}", (today,))
        cur.execute(
            f"""INSERT INTO portfolio_snapshots
               (date, total_invested, total_value, total_pnl, total_pnl_pct,
                open_positions, closed_trades, nifty)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (today, s["total_invested"], s["total_value"], s["total_pnl_inr"],
             round(total_pnl_pct, 4), s["open_positions"], s["closed_trades"],
             nifty_level),
        )
        con.commit()
    finally:
        con.close()
    return s


def get_all_daily_pnl() -> list[dict]:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM daily_pnl ORDER BY date, symbol")
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def get_all_snapshots() -> list[dict]:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM portfolio_snapshots ORDER BY date")
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


# ── Market memory (regime / sector / company news) ───────────────────────────
def save_market_regime(row: dict) -> None:
    """Upsert today's global-market regime row (idempotent per day)."""
    ph = placeholder()
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(f"DELETE FROM market_regime WHERE date={ph}", (row["date"],))
        cur.execute(
            f"""INSERT INTO market_regime
               (date, sentiment, score, sp500, dow, nasdaq, nikkei, hangseng,
                india_vix, fii_signal)
               VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (row["date"], row.get("sentiment"), row.get("score"), row.get("sp500"),
             row.get("dow"), row.get("nasdaq"), row.get("nikkei"), row.get("hangseng"),
             row.get("india_vix"), row.get("fii_signal")),
        )
        con.commit()
    finally:
        con.close()


def save_sector_sentiment(day: str, sectors: dict) -> None:
    """Replace today's sector sentiment rows. sectors = {sector: {avg,label}}."""
    ph = placeholder()
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(f"DELETE FROM sector_sentiment WHERE date={ph}", (day,))
        for sec, v in sectors.items():
            cur.execute(
                f"INSERT INTO sector_sentiment (date, sector, score, label) "
                f"VALUES ({ph},{ph},{ph},{ph})",
                (day, sec, v.get("avg"), v.get("label")),
            )
        con.commit()
    finally:
        con.close()


def save_stock_news(day: str, items: list[dict]) -> None:
    """Replace today's stock-news rows. items = [{symbol,score,label,headline}]."""
    ph = placeholder()
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(f"DELETE FROM stock_news WHERE date={ph}", (day,))
        for it in items:
            cur.execute(
                f"INSERT INTO stock_news (date, symbol, score, label, headline) "
                f"VALUES ({ph},{ph},{ph},{ph},{ph})",
                (day, it.get("symbol"), it.get("score"), it.get("label"), it.get("headline")),
            )
        con.commit()
    finally:
        con.close()


def _get_all(table: str) -> list[dict]:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(f"SELECT * FROM {table} ORDER BY date")
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def get_market_regime() -> list[dict]:
    return _get_all("market_regime")


def get_sector_sentiment() -> list[dict]:
    return _get_all("sector_sentiment")


def get_stock_news() -> list[dict]:
    return _get_all("stock_news")


def portfolio_summary(current_prices: dict[str, float] = None) -> dict:
    """Returns current portfolio summary."""
    open_trades = get_open_trades()
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(pnl_inr) FROM trades WHERE status='CLOSED'"
        )
        closed = cur.fetchone()
    finally:
        con.close()

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
