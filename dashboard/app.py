"""
Flask web dashboard for NSE Halal Algo Trading system.
Reads from SQLite paper trading database and today's signals CSV.

Run via:  python main.py dashboard
"""
import os
import csv
import sqlite3
import time
from datetime import date, datetime
from functools import lru_cache
from typing import Optional

from flask import Flask, render_template_string

# ── Project root (one level up from this file) ─────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "output", "paper_trades.db")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

app = Flask(__name__)

# ── Price cache (symbol -> (price, fetch_time)) ────────────────────────────
_price_cache: dict[str, tuple[float, float]] = {}
CACHE_TTL = 15 * 60  # 15 minutes


def _get_db() -> Optional[sqlite3.Connection]:
    if not os.path.exists(DB_PATH):
        return None
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_open_trades() -> list[dict]:
    con = _get_db()
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_date"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def get_closed_trades() -> list[dict]:
    con = _get_db()
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT * FROM trades WHERE status='CLOSED' ORDER BY exit_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def fetch_current_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch live prices via yfinance with 15-min cache."""
    now = time.time()
    prices = {}
    to_fetch = []

    for sym in symbols:
        cached = _price_cache.get(sym)
        if cached and (now - cached[1]) < CACHE_TTL:
            prices[sym] = cached[0]
        else:
            to_fetch.append(sym)

    if to_fetch:
        try:
            import yfinance as yf
            tickers = yf.Tickers(" ".join(to_fetch))
            for sym in to_fetch:
                try:
                    hist = tickers.tickers[sym].fast_info
                    price = getattr(hist, "last_price", None) or getattr(hist, "regularMarketPrice", None)
                    if price:
                        prices[sym] = float(price)
                        _price_cache[sym] = (float(price), now)
                except Exception:
                    pass
        except Exception:
            pass

    return prices


def read_today_signals() -> list[dict]:
    """Read today's signals CSV from output/signals_YYYY-MM-DD.csv."""
    today = date.today().isoformat()
    csv_path = os.path.join(OUTPUT_DIR, f"signals_{today}.csv")
    if not os.path.exists(csv_path):
        return []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def tier_badge(tier: str) -> str:
    tier = (tier or "").upper()
    if "STRONG" in tier:
        return '<span class="badge bg-success">STRONG BUY</span>'
    if tier == "BUY":
        return '<span class="badge bg-warning text-dark">BUY</span>'
    return '<span class="badge bg-info text-dark">WATCH</span>'


def pnl_class(value: float) -> str:
    return "text-success" if value >= 0 else "text-danger"


def pnl_sign(value: float) -> str:
    return f"+{value:.2f}" if value >= 0 else f"{value:.2f}"


def pnl_pct_fmt(value: float) -> str:
    pct = value * 100 if abs(value) < 10 else value  # handle both raw pct and 0-1
    if abs(pct) > 100:  # already in percentage form
        pct = value
    else:
        pct = value * 100 if abs(value) <= 1 else value
    return f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"


# ── Templates ─────────────────────────────────────────────────────────────
BASE_TEMPLATE = """
<!DOCTYPE html>
<html data-bs-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NSE Halal Algo Trader</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #0d1117; }
    .card { border: 1px solid #30363d; background-color: #161b22; }
    .card-header { background-color: #21262d; border-bottom: 1px solid #30363d; }
    .table { --bs-table-bg: transparent; }
    .navbar { background-color: #161b22 !important; border-bottom: 1px solid #30363d; }
    .hero-badge { font-size: 0.75rem; }
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg mb-4">
    <div class="container-fluid">
      <a class="navbar-brand fw-bold text-success" href="/">&#9787; NSE Halal Algo Trader</a>
      <div class="navbar-nav">
        <a class="nav-link {% if active == 'dashboard' %}active{% endif %}" href="/">Dashboard</a>
        <a class="nav-link {% if active == 'history' %}active{% endif %}" href="/history">Trade History</a>
      </div>
      <span class="navbar-text text-muted small">{{ now }}</span>
    </div>
  </nav>
  <div class="container-fluid px-4">
    {% block content %}{% endblock %}
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

DASHBOARD_TEMPLATE = BASE_TEMPLATE.replace(
    "{% block content %}{% endblock %}",
    """
<!-- Summary Cards -->
<div class="row g-3 mb-4">
  <div class="col-6 col-md-3">
    <div class="card text-center h-100">
      <div class="card-header small text-muted">Total Invested</div>
      <div class="card-body py-3">
        <div class="fs-4 fw-bold">&#8377;{{ "{:,.0f}".format(summary.total_invested) }}</div>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card text-center h-100">
      <div class="card-header small text-muted">Current Value</div>
      <div class="card-body py-3">
        <div class="fs-4 fw-bold">&#8377;{{ "{:,.0f}".format(summary.current_value) }}</div>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card text-center h-100">
      <div class="card-header small text-muted">Total P&amp;L</div>
      <div class="card-body py-3">
        <div class="fs-4 fw-bold {{ summary.pnl_class }}">
          &#8377;{{ summary.pnl_sign }}
          <span class="fs-6">({{ summary.pnl_pct }})</span>
        </div>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card text-center h-100">
      <div class="card-header small text-muted">Open Positions</div>
      <div class="card-body py-3">
        <div class="fs-4 fw-bold">{{ summary.open_count }}</div>
      </div>
    </div>
  </div>
</div>

<!-- Open Positions Table -->
<div class="card mb-4">
  <div class="card-header fw-semibold">Open Paper Positions</div>
  <div class="card-body p-0">
    {% if open_trades %}
    <div class="table-responsive">
      <table class="table table-striped table-hover mb-0">
        <thead class="table-dark">
          <tr>
            <th>Symbol</th>
            <th>Entry Date</th>
            <th>Entry Price</th>
            <th>Current Price</th>
            <th>Qty</th>
            <th>P&amp;L &#8377;</th>
            <th>P&amp;L %</th>
            <th>Signal Tier</th>
            <th>Days Held</th>
          </tr>
        </thead>
        <tbody>
          {% for t in open_trades %}
          <tr>
            <td class="fw-semibold">{{ t.symbol }}</td>
            <td>{{ t.entry_date }}</td>
            <td>&#8377;{{ "%.2f"|format(t.entry_price) }}</td>
            <td>
              {% if t.current_price %}
                &#8377;{{ "%.2f"|format(t.current_price) }}
              {% else %}
                <span class="text-muted">—</span>
              {% endif %}
            </td>
            <td>{{ "%.4f"|format(t.quantity) }}</td>
            <td class="{{ t.pnl_class }}">
              {% if t.current_price %}
                &#8377;{{ t.pnl_sign }}
              {% else %}
                <span class="text-muted">—</span>
              {% endif %}
            </td>
            <td class="{{ t.pnl_class }}">
              {% if t.current_price %}
                {{ t.pnl_pct }}
              {% else %}
                <span class="text-muted">—</span>
              {% endif %}
            </td>
            <td>{{ t.tier_badge|safe }}</td>
            <td>{{ t.days_held }}d</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="text-center text-muted py-5">
      <p class="mb-0">No paper trades yet — run a scan first with <code>python main.py scan</code></p>
    </div>
    {% endif %}
  </div>
</div>

<!-- Today's Signals -->
<div class="card mb-4">
  <div class="card-header fw-semibold">Today's Buy Signals <span class="text-muted small">({{ today }})</span></div>
  <div class="card-body p-0">
    {% if signals %}
    <div class="table-responsive">
      <table class="table table-striped table-hover mb-0">
        <thead class="table-dark">
          <tr>
            <th>Symbol</th>
            <th>Score</th>
            <th>Tier</th>
            <th>Sector</th>
            <th>Top Strength</th>
          </tr>
        </thead>
        <tbody>
          {% for s in signals %}
          <tr>
            <td class="fw-semibold">{{ s.symbol }}</td>
            <td>{{ s.score }}</td>
            <td>{{ s.tier_badge|safe }}</td>
            <td>{{ s.sector }}</td>
            <td class="text-muted small">{{ s.top_strength }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="text-center text-muted py-5">
      <p class="mb-0">No signals for today yet — run <code>python main.py scan --output csv</code></p>
    </div>
    {% endif %}
  </div>
</div>
"""
)

HISTORY_TEMPLATE = BASE_TEMPLATE.replace(
    "{% block content %}{% endblock %}",
    """
<div class="card mb-4">
  <div class="card-header fw-semibold">Closed Trade History</div>
  <div class="card-body p-0">
    {% if closed_trades %}
    <div class="table-responsive">
      <table class="table table-striped table-hover mb-0">
        <thead class="table-dark">
          <tr>
            <th>Symbol</th>
            <th>Entry Date</th>
            <th>Exit Date</th>
            <th>Entry Price</th>
            <th>Exit Price</th>
            <th>Qty</th>
            <th>P&amp;L &#8377;</th>
            <th>P&amp;L %</th>
            <th>Days Held</th>
            <th>Exit Reason</th>
          </tr>
        </thead>
        <tbody>
          {% for t in closed_trades %}
          <tr>
            <td class="fw-semibold">{{ t.symbol }}</td>
            <td>{{ t.entry_date }}</td>
            <td>{{ t.exit_date or "—" }}</td>
            <td>&#8377;{{ "%.2f"|format(t.entry_price) }}</td>
            <td>&#8377;{{ "%.2f"|format(t.exit_price) if t.exit_price else "—" }}</td>
            <td>{{ "%.4f"|format(t.quantity) }}</td>
            <td class="{{ t.pnl_class }}">&#8377;{{ t.pnl_sign }}</td>
            <td class="{{ t.pnl_class }}">{{ t.pnl_pct }}</td>
            <td>{{ t.hold_days or "—" }}d</td>
            <td class="text-muted small">{{ t.exit_reason or "—" }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="text-center text-muted py-5">
      <p class="mb-0">No closed trades yet.</p>
    </div>
    {% endif %}
  </div>
</div>
"""
)


# ── Route helpers ──────────────────────────────────────────────────────────

def _enrich_open_trades(trades: list[dict]) -> tuple[list[dict], dict]:
    """Add computed fields to open trades; return enriched list + summary."""
    symbols = [t["symbol"] for t in trades]
    prices = fetch_current_prices(symbols) if symbols else {}

    total_invested = 0.0
    total_value = 0.0

    enriched = []
    for t in trades:
        sym = t["symbol"]
        cp = prices.get(sym)

        entry = t["entry_price"]
        qty = t["quantity"]
        pos_inr = t.get("position_inr", entry * qty)
        total_invested += pos_inr

        if cp:
            cur_val = cp * qty
            total_value += cur_val
            pnl_inr = cur_val - pos_inr
            pnl_pct_raw = pnl_inr / pos_inr if pos_inr else 0.0
        else:
            total_value += pos_inr
            pnl_inr = None
            pnl_pct_raw = None

        entry_dt = datetime.fromisoformat(t["entry_date"])
        days_held = (datetime.now() - entry_dt).days

        t = dict(t)
        t["current_price"] = cp
        t["days_held"] = days_held
        t["tier_badge"] = tier_badge(t.get("signal_tier", ""))

        if pnl_inr is not None:
            t["pnl_class"] = pnl_class(pnl_inr)
            t["pnl_sign"] = pnl_sign(pnl_inr)
            raw_pct = pnl_pct_raw * 100
            t["pnl_pct"] = f"+{raw_pct:.2f}%" if raw_pct >= 0 else f"{raw_pct:.2f}%"
        else:
            t["pnl_class"] = ""
            t["pnl_sign"] = ""
            t["pnl_pct"] = ""

        enriched.append(t)

    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0

    summary = {
        "total_invested": total_invested,
        "current_value": total_value,
        "pnl_class": pnl_class(total_pnl),
        "pnl_sign": pnl_sign(total_pnl),
        "pnl_pct": f"+{total_pnl_pct:.2f}%" if total_pnl_pct >= 0 else f"{total_pnl_pct:.2f}%",
        "open_count": len(trades),
    }
    return enriched, summary


def _enrich_closed_trades(trades: list[dict]) -> list[dict]:
    enriched = []
    for t in [dict(r) for r in trades]:
        pnl = t.get("pnl_inr") or 0.0
        pnl_pct_raw = (t.get("pnl_pct") or 0.0) * 100
        t["pnl_class"] = pnl_class(pnl)
        t["pnl_sign"] = pnl_sign(pnl)
        t["pnl_pct"] = f"+{pnl_pct_raw:.2f}%" if pnl_pct_raw >= 0 else f"{pnl_pct_raw:.2f}%"
        enriched.append(t)
    return enriched


def _enrich_signals(raw: list[dict]) -> list[dict]:
    enriched = []
    for row in raw:
        tier = row.get("tier", row.get("Tier", "WATCH"))
        symbol = row.get("symbol", row.get("Symbol", ""))
        score = row.get("score", row.get("Score", ""))
        sector = row.get("sector", row.get("Sector", ""))

        # Top strength: first non-empty strengths field or any "strength" column
        top_strength = ""
        for key in ("strengths", "Strengths", "top_strength", "strength_1"):
            val = row.get(key, "")
            if val:
                # May be a pipe/comma separated list
                parts = [p.strip() for p in val.replace("|", ";").split(";") if p.strip()]
                top_strength = parts[0] if parts else val
                break

        enriched.append({
            "symbol": symbol,
            "score": score,
            "tier_badge": tier_badge(tier),
            "sector": sector,
            "top_strength": top_strength,
        })
    return enriched


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    open_trades_raw = get_open_trades()
    open_trades, summary = _enrich_open_trades(open_trades_raw)

    signals_raw = read_today_signals()
    signals = _enrich_signals(signals_raw)

    return render_template_string(
        DASHBOARD_TEMPLATE,
        active="dashboard",
        now=datetime.now().strftime("%d %b %Y  %H:%M"),
        today=date.today().isoformat(),
        open_trades=open_trades,
        summary=summary,
        signals=signals,
    )


@app.route("/history")
def history():
    closed_trades_raw = get_closed_trades()
    closed_trades = _enrich_closed_trades(closed_trades_raw)

    return render_template_string(
        HISTORY_TEMPLATE,
        active="history",
        now=datetime.now().strftime("%d %b %Y  %H:%M"),
        closed_trades=closed_trades,
    )
