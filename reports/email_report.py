"""
Sends daily morning brief + signal summary via Gmail API.
Uses OAuth2 refresh token (set up once, runs forever).

Setup instructions:
1. Go to Google Cloud Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Desktop app)
3. Download credentials.json
4. Run: python -c "from reports.email_report import setup_gmail; setup_gmail()"
5. Copy the refresh token into your .env file as GMAIL_REFRESH_TOKEN
"""
import os
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import Optional

import config


def _get_gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=config.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GMAIL_CLIENT_ID,
        client_secret=config.GMAIL_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def setup_gmail() -> None:
    """One-time OAuth setup to get refresh token. Run this manually once."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    creds = flow.run_local_server(port=0)
    print(f"\nAdd this to your .env file:\nGMAIL_REFRESH_TOKEN={creds.refresh_token}")


def _build_html(brief: dict, signals: list, paper_summary: dict) -> str:
    today = date.today().strftime("%A, %d %b %Y")
    sentiment = brief.get("overall_sentiment", "UNKNOWN")
    colour = {"BULLISH": "#27ae60", "BEARISH": "#e74c3c", "NEUTRAL": "#f39c12"}.get(sentiment, "#999")

    global_rows = ""
    for name, data in list(brief.get("global", {}).items())[:8]:
        chg = data["change_pct"]
        chg_col = "#27ae60" if chg > 0 else "#e74c3c"
        global_rows += f"<tr><td>{name}</td><td>{data['price']:,.2f}</td><td style='color:{chg_col}'>{chg:+.1%}</td></tr>"

    signal_rows = ""
    for s in signals[:10]:
        tier_col = {"STRONG BUY": "#27ae60", "BUY": "#f39c12"}.get(s.tier, "#3498db")
        signal_rows += (
            f"<tr><td><b>{s.symbol.replace('.NS','')}</b></td>"
            f"<td style='color:{tier_col}'>{s.tier}</td>"
            f"<td>{s.score:.0f}</td>"
            f"<td>{s.metrics.get('trailing_pe', '—'):.1f}</td>"
            f"<td>{s.metrics.get('roe', 0)*100:.1f}%</td>"
            f"<td>{s.sector}</td></tr>"
        )

    crypto = brief.get("crypto", {})
    btc = crypto.get("prices", {}).get("BTC", {})
    fg = crypto.get("fear_greed", {})
    crypto_line = f"BTC ${btc.get('price_usd', 0):,.0f} ({btc.get('change_24h', 0):+.1%}) | Fear & Greed: {fg.get('value', '?')} ({fg.get('label', '?')})" if btc else ""

    paper_line = ""
    if paper_summary:
        paper_line = (
            f"Open: {paper_summary.get('open_positions', 0)} | "
            f"Invested: ₹{paper_summary.get('total_invested', 0):,.0f} | "
            f"P&L: ₹{paper_summary.get('open_pnl_inr', 0):+,.0f} "
            f"({paper_summary.get('open_pnl_pct', 0):+.1%})"
        )

    events = brief.get("upcoming_events", [])
    event_html = "".join(f"<li>{'In ' + str(e['days_away']) + 'd' if e['days_away'] else 'TODAY'}: {e['event']}</li>" for e in events[:3])

    return f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #222;">
    <h2 style="border-left: 4px solid {colour}; padding-left: 10px;">
      NSE Halal Algo Trader — {today}
      <span style="font-size:0.8em; color:{colour}"> {sentiment}</span>
    </h2>

    <h3>🌏 Global Pre-Market</h3>
    <table border="0" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%">
      <tr style="background:#f5f5f5"><th align="left">Indicator</th><th>Price</th><th>Change</th></tr>
      {global_rows}
    </table>

    <p>₿ {crypto_line}</p>

    {f'<h3>📅 Upcoming Events</h3><ul>{event_html}</ul>' if events else ''}

    <h3>📊 Top Buy Signals Today</h3>
    {"<p><i>No signals meeting criteria today.</i></p>" if not signal_rows else f'''
    <table border="0" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%">
      <tr style="background:#f5f5f5"><th>Symbol</th><th>Signal</th><th>Score</th><th>P/E</th><th>ROE</th><th>Sector</th></tr>
      {signal_rows}
    </table>'''}

    {f'<h3>📋 Paper Portfolio</h3><p>{paper_line}</p>' if paper_line else ''}

    <hr style="margin-top:24px"/>
    <p style="font-size:0.75em; color:#999">
      This is an automated report from your NSE Halal Algo Trader.
      All signals are for informational purposes only. DYOR.
    </p>
    </body></html>
    """


def _build_trade_html(executed: list, brief: dict, paper_summary: dict) -> str:
    today = date.today().strftime("%A, %d %b %Y")
    sentiment = (brief or {}).get("overall_sentiment", "UNKNOWN")
    colour = {"BULLISH": "#27ae60", "BEARISH": "#e74c3c", "NEUTRAL": "#f39c12"}.get(sentiment, "#999")

    # External market / global context
    context_items = "".join(f"<li>{line}</li>" for line in (brief or {}).get("summary_lines", []))
    context_block = (
        f"<h3>🌏 Market &amp; Global Context</h3><ul>{context_items}</ul>"
        if context_items else ""
    )

    # Per-trade cards with the "why"
    cards = ""
    for t in executed:
        why = "".join(f"<li>{s}</li>" for s in t.get("strengths", [])) or "<li>Passed halal + quality screens</li>"
        tier_col = {"STRONG BUY": "#27ae60", "BUY": "#f39c12"}.get(t["tier"], "#3498db")
        cards += f"""
        <div style="border:1px solid #eee; border-left:4px solid {tier_col}; padding:10px 14px; margin:10px 0; border-radius:4px;">
          <b>{t['symbol'].replace('.NS','')}</b> — {t.get('name','')}
          <span style="color:{tier_col}; font-weight:bold;"> {t['tier']}</span>
          &nbsp;<span style="color:#888;">score {t['score']:.0f} · {t.get('sector','')}</span><br/>
          Invested ₹{t.get('invested',0):,.0f} · {t.get('qty',0)} sh @ ₹{t['price']:,.2f}
          <div style="margin-top:6px; color:#444;"><i>Why picked:</i><ul style="margin:4px 0;">{why}</ul></div>
        </div>"""

    paper_line = ""
    if paper_summary:
        paper_line = (
            f"Open: {paper_summary.get('open_positions', 0)} | "
            f"Invested: ₹{paper_summary.get('total_invested', 0):,.0f} | "
            f"P&L: ₹{paper_summary.get('open_pnl_inr', 0):+,.0f} "
            f"({paper_summary.get('open_pnl_pct', 0):+.1%})"
        )

    return f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #222;">
    <h2 style="border-left: 4px solid {colour}; padding-left: 10px;">
      Paper Trades Executed — {today}
      <span style="font-size:0.8em; color:{colour}"> {sentiment}</span>
    </h2>
    <p>{len(executed)} new position(s) opened within your ₹{config.MONTHLY_BUDGET_INR:,.0f} budget.</p>
    {context_block}
    <h3>🛒 What was bought &amp; why</h3>
    {cards}
    {f'<h3>📋 Paper Portfolio</h3><p>{paper_line}</p>' if paper_line else ''}
    <hr style="margin-top:24px"/>
    <p style="font-size:0.75em; color:#999">
      Automated paper-trade notification. Informational only — not investment advice. DYOR.
    </p>
    </body></html>
    """


def send_trade_notification(
    executed: list,
    brief: dict = None,
    paper_summary: dict = None,
    to_email: str = None,
) -> bool:
    """Email a short summary of the trades just executed and why."""
    if not executed:
        return False
    to = to_email or config.REPORT_EMAIL_TO
    if not to:
        print("[email] No recipient configured — set REPORT_EMAIL_TO in .env")
        return False
    if not config.GMAIL_REFRESH_TOKEN:
        print("[email] Gmail not configured — set GMAIL_REFRESH_TOKEN in .env")
        return False

    try:
        service = _get_gmail_service()
        html = _build_trade_html(executed, brief or {}, paper_summary or {})

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Paper Trades — {date.today().strftime('%d %b')} — {len(executed)} new position(s)"
        msg["From"]    = "me"
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[email] Trade notification sent to {to}")
        return True
    except Exception as e:
        print(f"[email] Failed to send trade notification: {e}")
        return False


def send_daily_report(
    brief: dict,
    signals: list,
    paper_summary: dict = None,
    to_email: str = None,
) -> bool:
    to = to_email or config.REPORT_EMAIL_TO
    if not to:
        print("[email] No recipient configured — set REPORT_EMAIL_TO in .env")
        return False
    if not config.GMAIL_REFRESH_TOKEN:
        print("[email] Gmail not configured — set GMAIL_REFRESH_TOKEN in .env")
        return False

    try:
        service = _get_gmail_service()
        html = _build_html(brief, signals, paper_summary or {})

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"NSE Halal Signals — {date.today().strftime('%d %b')} — {brief.get('overall_sentiment', '')}"
        msg["From"]    = "me"
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[email] Daily report sent to {to}")
        return True
    except Exception as e:
        print(f"[email] Failed to send: {e}")
        return False
