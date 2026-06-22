"""
Google Sheets sync for paper trading.

Mirrors the paper-trading DB into a Google Spreadsheet so the portfolio can be
reviewed from anywhere, with a live Dashboard tab showing % change.

Tabs written (rebuilt from the DB on every sync, so they are always current):
  • Trades      — one row per position (entry, live price, unrealized %, exit, realized %)
  • Daily P&L   — time series of mark-to-market P&L per open position
  • Snapshots   — portfolio-level history (total value, total % change)
  • Dashboard   — formula-driven summary + charts on top of the tabs above

Auth: a Google service account. Set one of:
  GOOGLE_SERVICE_ACCOUNT_JSON  → raw JSON string, or a path to the key file
  GOOGLE_APPLICATION_CREDENTIALS → path to the key file (standard Google env var)

On first run (no GOOGLE_SHEET_ID set) a new spreadsheet is created, shared with
GSHEET_SHARE_EMAIL / REPORT_EMAIL_TO, and its ID saved to output/gsheet_id.txt.
Put that ID in GOOGLE_SHEET_ID to reuse the same sheet next time.
"""
import json
import os
from datetime import date

import config
from paper_trading.sqlite_engine import (
    init_db, get_all_trades, get_all_daily_pnl, get_all_snapshots, save_snapshot,
    record_daily_prices,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_ID_FILE = os.path.join(config.OUTPUT_DIR, "gsheet_id.txt")

TRADES_TAB = "Trades"
DAILY_TAB = "Daily P&L"
SNAP_TAB = "Snapshots"
DASH_TAB = "Dashboard"

TRADES_HEADER = [
    "Trade ID", "Symbol", "Name", "Entry Date", "Entry Price", "Quantity",
    "Invested (INR)", "Tier", "Score", "Current Price", "Current Value (INR)",
    "Unrealized P&L (INR)", "% Change", "Status", "Exit Date", "Exit Price",
    "Exit Reason", "Realized P&L (INR)", "Realized %", "Hold Days",
]
DAILY_HEADER = ["Date", "Symbol", "Trade ID", "Price", "P&L (INR)", "P&L %"]
SNAP_HEADER = [
    "Date", "Total Invested", "Total Value", "Total P&L (INR)", "Total P&L %",
    "Open Positions", "Closed Trades", "NIFTY 50",
]


# ─────────────────────────────────────────────────────────────────────────────
# Auth / service handles
# ─────────────────────────────────────────────────────────────────────────────
def _credentials():
    from google.oauth2 import service_account

    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        if raw.startswith("{"):
            info = json.loads(raw)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        if os.path.exists(raw):
            return service_account.Credentials.from_service_account_file(raw, scopes=SCOPES)
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON or a readable path")

    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path and os.path.exists(path):
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    raise RuntimeError(
        "No Google credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON "
        "(raw JSON or path) or GOOGLE_APPLICATION_CREDENTIALS."
    )


def is_configured() -> bool:
    """True if Sheets sync can run (credentials are present)."""
    return bool(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    )


def _services():
    from googleapiclient.discovery import build

    creds = _credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return sheets, drive


# ─────────────────────────────────────────────────────────────────────────────
# Spreadsheet provisioning
# ─────────────────────────────────────────────────────────────────────────────
def _saved_sheet_id() -> str:
    env = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if env:
        return env
    if os.path.exists(SHEET_ID_FILE):
        with open(SHEET_ID_FILE) as f:
            return f.read().strip()
    return ""


def _persist_sheet_id(sheet_id: str) -> None:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    with open(SHEET_ID_FILE, "w") as f:
        f.write(sheet_id)


def _share(drive, sheet_id: str) -> None:
    email = os.getenv("GSHEET_SHARE_EMAIL", "").strip() or os.getenv("REPORT_EMAIL_TO", "").strip()
    if not email:
        print("[gsheets] No GSHEET_SHARE_EMAIL/REPORT_EMAIL_TO set — sheet stays "
              "private to the service account. Set one to get edit access.")
        return
    try:
        drive.permissions().create(
            fileId=sheet_id,
            body={"type": "user", "role": "writer", "emailAddress": email},
            sendNotificationEmail=True,
        ).execute()
        print(f"[gsheets] Shared spreadsheet with {email}")
    except Exception as e:  # noqa: BLE001
        print(f"[gsheets] Could not share sheet with {email}: {e}")


def _is_valid_sheet(sheets, sheet_id: str) -> bool:
    try:
        sheets.spreadsheets().get(
            spreadsheetId=sheet_id, fields="spreadsheetId"
        ).execute()
        return True
    except Exception:  # noqa: BLE001 — 404 / permission / bad id
        return False


def _ensure_spreadsheet(sheets, drive) -> str:
    # Try the configured id (env first, then the persisted file). If a
    # candidate is missing/invalid (e.g. a stale GOOGLE_SHEET_ID secret), skip
    # it and fall through to creating a fresh spreadsheet.
    candidates = []
    env_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if env_id:
        candidates.append(env_id)
    if os.path.exists(SHEET_ID_FILE):
        with open(SHEET_ID_FILE) as f:
            file_id = f.read().strip()
        if file_id and file_id not in candidates:
            candidates.append(file_id)

    for sid in candidates:
        if _is_valid_sheet(sheets, sid):
            _persist_sheet_id(sid)
            return sid
        print(f"[gsheets] Configured sheet '{sid}' not found/accessible — creating a new one.")

    body = {
        "properties": {"title": "Algo-Trader Paper Trades"},
        "sheets": [
            {"properties": {"title": DASH_TAB}},
            {"properties": {"title": TRADES_TAB}},
            {"properties": {"title": DAILY_TAB}},
            {"properties": {"title": SNAP_TAB}},
        ],
    }
    try:
        ss = sheets.spreadsheets().create(body=body).execute()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "Could not create a spreadsheet. Service accounts have no personal "
            "Google Drive, so auto-create often fails with a 403. Instead, create "
            "a blank Google Sheet yourself, share it (Editor) with the service "
            "account email, and set GOOGLE_SHEET_ID to that sheet's id. "
            f"Original error: {e}"
        ) from e
    sheet_id = ss["spreadsheetId"]
    _persist_sheet_id(sheet_id)
    _share(drive, sheet_id)
    print(f"[gsheets] Created spreadsheet: https://docs.google.com/spreadsheets/d/{sheet_id}")
    return sheet_id


def _ensure_tabs(sheets, sheet_id: str) -> dict:
    """Make sure all required tabs exist. Returns {title: sheetId}."""
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    requests = [
        {"addSheet": {"properties": {"title": t}}}
        for t in (DASH_TAB, TRADES_TAB, DAILY_TAB, SNAP_TAB) if t not in existing
    ]
    if requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id, body={"requests": requests}
        ).execute()
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Row building (pure functions — unit-testable without network)
# ─────────────────────────────────────────────────────────────────────────────
def _num(v):
    return v if isinstance(v, (int, float)) else None


def build_trade_rows(trades: list[dict], prices: dict[str, float]) -> list[list]:
    rows = [TRADES_HEADER]
    for t in trades:
        entry = t["entry_price"]
        qty = t["quantity"]
        if t["status"] == "OPEN":
            cur = prices.get(t["symbol"], entry)
            cur_val = round(cur * qty, 2)
            unreal = round((cur - entry) * qty, 2)
            pct = round((cur / entry) - 1, 4) if entry else 0
        else:
            cur, cur_val, unreal, pct = "", "", "", ""
        rows.append([
            t["id"], t["symbol"], t.get("name") or "", t["entry_date"],
            round(entry, 2), qty, round(t["position_inr"], 2), t["signal_tier"],
            _num(t.get("score")), cur, cur_val, unreal, pct, t["status"],
            t.get("exit_date") or "", _num(t.get("exit_price")),
            t.get("exit_reason") or "", _num(t.get("pnl_inr")),
            _num(t.get("pnl_pct")), _num(t.get("hold_days")),
        ])
    return rows


def build_daily_rows(daily: list[dict]) -> list[list]:
    rows = [DAILY_HEADER]
    for d in daily:
        rows.append([
            d["date"], d["symbol"], d.get("trade_id"),
            round(d["price"], 2) if d.get("price") is not None else "",
            round(d["pnl_inr"], 2) if d.get("pnl_inr") is not None else "",
            round(d["pnl_pct"], 4) if d.get("pnl_pct") is not None else "",
        ])
    return rows


def build_snapshot_rows(snaps: list[dict]) -> list[list]:
    rows = [SNAP_HEADER]
    for s in snaps:
        rows.append([
            s["date"], _num(s.get("total_invested")), _num(s.get("total_value")),
            _num(s.get("total_pnl")), _num(s.get("total_pnl_pct")),
            _num(s.get("open_positions")), _num(s.get("closed_trades")),
            _num(s.get("nifty")),
        ])
    return rows


def benchmark_return(snaps: list[dict]) -> float:
    """NIFTY 50 return since inception, from the first/last stored index level."""
    levels = [_num(s.get("nifty")) for s in snaps if _num(s.get("nifty"))]
    if len(levels) >= 1 and levels[0]:
        return round((levels[-1] / levels[0]) - 1, 4)
    return None


def fetch_nifty_level() -> float:
    """Latest NIFTY 50 index level (best-effort, needs network)."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^NSEI").history(period="5d")["Close"].dropna()
        return float(hist.iloc[-1]) if len(hist) else None
    except Exception as e:  # noqa: BLE001
        print(f"[gsheets] NIFTY level fetch failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────
def _rewrite_tab(sheets, sheet_id: str, tab: str, rows: list[list]) -> None:
    sheets.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"'{tab}'"
    ).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()


def _write_dashboard(sheets, sheet_id: str, tab_ids: dict, nifty_return=None) -> None:
    """Formula-driven dashboard referencing the data tabs."""
    t = f"'{TRADES_TAB}'"
    nifty_cell = nifty_return if nifty_return is not None else ""
    rows = [
        ["ALGO-TRADER PAPER PORTFOLIO", "", f"Updated: {date.today().isoformat()}"],
        [],
        ["Total Invested (INR)", f"=SUM({t}!G2:G)"],
        ["Current Value (INR)",
         f"=SUMIF({t}!N2:N,\"OPEN\",{t}!K2:K)+SUM({t}!G2:G)-SUMIF({t}!N2:N,\"OPEN\",{t}!G2:G)"],
        ["Open Unrealized P&L (INR)", f"=SUMIF({t}!N2:N,\"OPEN\",{t}!L2:L)"],
        ["Realized P&L (INR)", f"=SUM({t}!R2:R)"],
        ["Total P&L (INR)", "=B5+B6"],
        ["Total % Change", "=IFERROR(B7/B3,0)"],
        ["NIFTY 50 since inception", nifty_cell],
        ["Strategy vs NIFTY", "=IF(ISNUMBER(B9),B8-B9,\"awaiting data\")"],
        ["Open Positions", f"=COUNTIF({t}!N2:N,\"OPEN\")"],
        ["Closed Trades", f"=COUNTIF({t}!N2:N,\"CLOSED\")"],
        ["Win Rate (closed)",
         f"=IFERROR(COUNTIFS({t}!N2:N,\"CLOSED\",{t}!R2:R,\">0\")/COUNTIF({t}!N2:N,\"CLOSED\"),0)"],
        ["Avg Open % Change", f"=IFERROR(AVERAGEIF({t}!N2:N,\"OPEN\",{t}!M2:M),0)"],
        [],
        ["TOP MOVERS (open positions, by % change)"],
        ["Symbol", "% Change", "Unrealized P&L (INR)"],
        [f"=IFERROR(SORT(FILTER({{{t}!B2:B,{t}!M2:M,{t}!L2:L}},{t}!N2:N=\"OPEN\"),2,FALSE),\"\")"],
    ]
    sheets.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"'{DASH_TAB}'"
    ).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{DASH_TAB}'!A1",
        valueInputOption="USER_ENTERED",  # so formulas evaluate
        body={"values": rows},
    ).execute()

    # Percentage formatting + bold header; charts. Best-effort.
    try:
        _format_dashboard(sheets, sheet_id, tab_ids)
    except Exception as e:  # noqa: BLE001
        print(f"[gsheets] Dashboard formatting/charts skipped: {e}")


def _format_dashboard(sheets, sheet_id: str, tab_ids: dict) -> None:
    dash = tab_ids[DASH_TAB]
    snap = tab_ids[SNAP_TAB]
    pct_fmt = {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}
    requests = [
        # Bold title
        {"repeatCell": {
            "range": {"sheetId": dash, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}},
            "fields": "userEnteredFormat.textFormat"}},
        # % cells: B8 Total %, B9 NIFTY %, B10 Strategy vs NIFTY
        {"repeatCell": {
            "range": {"sheetId": dash, "startRowIndex": 7, "endRowIndex": 10,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": pct_fmt},
            "fields": "userEnteredFormat.numberFormat"}},
        # % cells: B13 Win Rate, B14 Avg Open %
        {"repeatCell": {
            "range": {"sheetId": dash, "startRowIndex": 12, "endRowIndex": 14,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": pct_fmt},
            "fields": "userEnteredFormat.numberFormat"}},
        # Equity curve: Snapshots Total P&L % over time
        {"addChart": {"chart": {
            "spec": {
                "title": "Portfolio % Change Over Time",
                "basicChart": {
                    "chartType": "LINE", "legendPosition": "BOTTOM_LEGEND",
                    "domains": [{"domain": {"sourceRange": {"sources": [
                        {"sheetId": snap, "startRowIndex": 0,
                         "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
                    "series": [{"series": {"sourceRange": {"sources": [
                        {"sheetId": snap, "startRowIndex": 0,
                         "startColumnIndex": 4, "endColumnIndex": 5}]}}}],
                    "headerCount": 1,
                },
            },
            "position": {"overlayPosition": {"anchorCell": {
                "sheetId": dash, "rowIndex": 1, "columnIndex": 4}}},
        }}},
    ]
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": requests}
    ).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def sync(current_prices: dict[str, float] = None) -> str:
    """
    Record today's marks + snapshot in the DB, then rebuild the Google Sheet.
    Returns the spreadsheet URL.
    """
    current_prices = current_prices or {}
    init_db()
    record_daily_prices(current_prices)
    save_snapshot(current_prices, nifty_level=fetch_nifty_level())

    sheets, drive = _services()
    sheet_id = _ensure_spreadsheet(sheets, drive)
    tab_ids = _ensure_tabs(sheets, sheet_id)

    snaps = get_all_snapshots()
    _rewrite_tab(sheets, sheet_id, TRADES_TAB,
                 build_trade_rows(get_all_trades(), current_prices))
    _rewrite_tab(sheets, sheet_id, DAILY_TAB, build_daily_rows(get_all_daily_pnl()))
    _rewrite_tab(sheets, sheet_id, SNAP_TAB, build_snapshot_rows(snaps))
    _write_dashboard(sheets, sheet_id, tab_ids, nifty_return=benchmark_return(snaps))

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    print(f"[gsheets] Synced to {url}")
    return url
