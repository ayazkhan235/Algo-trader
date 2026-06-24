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


# Plain-English explanation for each market indicator (matched by keyword)
MARKET_GLOSSARY = [
    ("sentiment", "The bot's overall read of today's global mood."),
    ("s&p 500", "US stock market. Rising = healthy global appetite for risk, usually good for Indian stocks too."),
    ("vix", "India's ‘fear gauge’. Below 15 = calm, good for buying; above 20 = nervous, jumpy markets."),
    ("fii", "Foreign investor money flow. Net BUYING lifts Indian stocks; net SELLING is a caution sign."),
    ("crude", "Oil price. India imports most of its oil, so FALLING crude is good (less inflation, stronger rupee)."),
    ("usd/inr", "Rupee per US dollar. A HIGHER number = weaker rupee (helps IT/exporters, hurts importers)."),
    ("btc", "Crypto + Fear/Greed gauge. ‘Extreme Fear’ means investors are panicking — a global risk-off signal."),
    ("risk-off", "Investors worldwide are avoiding risk — expect caution and possible foreign selling in India."),
    ("risk-on", "Investors worldwide are embracing risk — a supportive backdrop for stocks."),
]


def _explain_line(line: str) -> str:
    low = line.lower()
    for key, exp in MARKET_GLOSSARY:
        if key in low:
            return exp
    return ""


def _market_context_html(brief: dict) -> str:
    """Market cues with a plain-English explanation under each line."""
    lines = (brief or {}).get("summary_lines", [])
    if not lines:
        return ""
    rows = ""
    for ln in lines:
        exp = _explain_line(ln)
        exp_html = (f"<div style='color:#777; font-size:0.9em; margin:0 0 8px 14px'>↳ {exp}</div>"
                    if exp else "")
        rows += f"<li style='margin-bottom:2px'><b>{ln}</b>{exp_html}</li>"
    return ("<h3>🌏 What's happening in the markets (plain English)</h3>"
            "<ul style='list-style:none; padding-left:0'>" + rows + "</ul>")


def _build_trade_html(executed: list, brief: dict, paper_summary: dict, closed: list = None) -> str:
    today = date.today().strftime("%A, %d %b %Y")
    sentiment = (brief or {}).get("overall_sentiment", "UNKNOWN")
    colour = {"BULLISH": "#27ae60", "BEARISH": "#e74c3c", "NEUTRAL": "#f39c12"}.get(sentiment, "#999")

    context_block = _market_context_html(brief)

    # Sold positions (if any)
    sold = ""
    for c in (closed or []):
        pcol = "#27ae60" if (c.get("pnl_inr", 0) or 0) >= 0 else "#e74c3c"
        sold += (f"<div style='border:1px solid #eee; border-left:4px solid #e67e22; "
                 f"padding:10px 14px; margin:10px 0; border-radius:4px;'>"
                 f"<b>{c['symbol'].replace('.NS','')}</b> "
                 f"<span style='color:#e67e22; font-weight:bold;'>SOLD</span> — {c.get('reason','')}"
                 f"<br/><span style='color:{pcol}'>Realized P&L ₹{c.get('pnl_inr',0):+,.0f} "
                 f"({c.get('pnl_pct',0):+.1%})</span> · held {c.get('hold_days','?')} days</div>")
    sold_block = f"<h3>📤 Sold today</h3>{sold}" if sold else ""

    # Per-trade cards with the "why"
    cards = ""
    for t in executed:
        why = "".join(f"<li>{s}</li>" for s in t.get("strengths", [])) or "<li>Passed halal + quality screens</li>"
        tier_col = {"STRONG BUY": "#27ae60", "BUY": "#f39c12"}.get(t["tier"], "#3498db")
        headline = t.get("news_headline")
        news_col = {"POSITIVE": "#27ae60", "NEGATIVE": "#e74c3c"}.get(t.get("news_label"), "#888")
        news_block = (
            f'<div style="margin-top:6px; color:{news_col};">📰 <i>In the news '
            f'({t.get("news_label","").title()}):</i> "{headline}"</div>'
            if headline else ""
        )
        cards += f"""
        <div style="border:1px solid #eee; border-left:4px solid {tier_col}; padding:10px 14px; margin:10px 0; border-radius:4px;">
          <b>{t['symbol'].replace('.NS','')}</b> — {t.get('name','')}
          <span style="color:{tier_col}; font-weight:bold;"> {t['tier']}</span>
          &nbsp;<span style="color:#888;">score {t['score']:.0f} · {t.get('sector','')}</span><br/>
          Invested ₹{t.get('invested',0):,.0f} · {t.get('qty',0)} sh @ ₹{t['price']:,.2f}
          <div style="margin-top:6px; color:#444;"><i>Why picked:</i><ul style="margin:4px 0;">{why}</ul></div>
          {news_block}
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
    <p>{len(executed)} new buy(s) · {len(closed or [])} sell(s) this run (budget ₹{config.MONTHLY_BUDGET_INR:,.0f}/month).</p>
    {sold_block}
    {f'<h3>🛒 What was bought &amp; why</h3>{cards}' if cards else ''}
    {context_block}
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
    closed: list = None,
) -> bool:
    """Email a summary of the buys and/or sells just executed and why."""
    executed = executed or []
    closed = closed or []
    if not executed and not closed:
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
        html = _build_trade_html(executed, brief or {}, paper_summary or {}, closed=closed)

        bits = []
        if executed:
            bits.append(f"{len(executed)} buy")
        if closed:
            bits.append(f"{len(closed)} sell")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Paper Trades — {date.today().strftime('%d %b')} — {' · '.join(bits)}"
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


def _build_digest_html(holdings: list, summary: dict, brief: dict,
                       nifty_return, executed: list, closed: list = None) -> str:
    closed = closed or []
    today = date.today().strftime("%A, %d %b %Y")
    sentiment = (brief or {}).get("overall_sentiment", "UNKNOWN")
    colour = {"BULLISH": "#27ae60", "BEARISH": "#e74c3c", "NEUTRAL": "#f39c12"}.get(sentiment, "#999")

    total_pct = summary.get("open_pnl_pct", 0) or 0
    pct_col = "#27ae60" if total_pct >= 0 else "#e74c3c"
    vs_nifty = ""
    if nifty_return is not None:
        edge = total_pct - nifty_return
        ec = "#27ae60" if edge >= 0 else "#e74c3c"
        vs_nifty = (f"<p>NIFTY 50 since inception: {nifty_return:+.1%} &nbsp;|&nbsp; "
                    f"<b style='color:{ec}'>Strategy vs NIFTY: {edge:+.1%}</b></p>")

    rows = ""
    for h in sorted(holdings, key=lambda x: x.get("pct", 0), reverse=True):
        c = "#27ae60" if h.get("pct", 0) >= 0 else "#e74c3c"
        rows += (
            f"<tr><td><b>{h['symbol'].replace('.NS','')}</b></td>"
            f"<td align='right'>{h['qty']:.0f}</td>"
            f"<td align='right'>₹{h['entry']:,.2f}</td>"
            f"<td align='right'>₹{h['price']:,.2f}</td>"
            f"<td align='right' style='color:{c}'>{h['pct']:+.1%}</td>"
            f"<td align='right'>₹{h['value']:,.0f}</td></tr>"
        )

    new_block = ""
    if executed:
        names = ", ".join(t["symbol"].replace(".NS", "") for t in executed)
        new_block += f"<p>🛒 <b>Bought today:</b> {len(executed)} — {names}</p>"
    if closed:
        snames = ", ".join(c["symbol"].replace(".NS", "") for c in closed)
        new_block += f"<p>📤 <b>Sold today:</b> {len(closed)} — {snames}</p>"

    context_block = _market_context_html(brief)

    return f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 720px; margin: 0 auto; color: #222;">
    <h2 style="border-left: 4px solid {colour}; padding-left: 10px;">
      Paper Portfolio — {today}
      <span style="font-size:0.8em; color:{colour}"> {sentiment}</span>
    </h2>
    <p>
      Invested ₹{summary.get('total_invested', 0):,.0f} &nbsp;→&nbsp;
      Value ₹{summary.get('total_value', 0):,.0f} &nbsp;|&nbsp;
      <b style="color:{pct_col}">{total_pct:+.1%}</b>
      (₹{summary.get('open_pnl_inr', 0):+,.0f})
    </p>
    {vs_nifty}
    {new_block}
    <h3>📊 Current Holdings ({len(holdings)})</h3>
    <table border="0" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%">
      <tr style="background:#f5f5f5"><th align="left">Symbol</th><th>Qty</th><th>Entry</th><th>Now</th><th>% Change</th><th>Value</th></tr>
      {rows or '<tr><td colspan=6><i>No open positions.</i></td></tr>'}
    </table>
    {context_block}
    <hr style="margin-top:24px"/>
    <p style="font-size:0.75em; color:#999">Automated daily paper-portfolio digest. Informational only — not investment advice. DYOR.</p>
    </body></html>
    """


def send_portfolio_digest(holdings: list, summary: dict, brief: dict = None,
                          nifty_return=None, executed: list = None,
                          to_email: str = None, closed: list = None) -> bool:
    """Daily email of ALL current holdings + % change + vs NIFTY (sends every run)."""
    to = to_email or config.REPORT_EMAIL_TO
    if not to or not config.GMAIL_REFRESH_TOKEN:
        print("[email] Gmail not configured — skipping daily digest")
        return False
    try:
        service = _get_gmail_service()
        html = _build_digest_html(holdings, summary or {}, brief or {}, nifty_return,
                                  executed or [], closed=closed or [])
        pct = (summary or {}).get("open_pnl_pct", 0) or 0
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (f"Paper Portfolio — {date.today().strftime('%d %b')} — "
                          f"{len(holdings)} holdings ({pct:+.1%})")
        msg["From"] = "me"
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[email] Daily portfolio digest sent to {to}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[email] Failed to send daily digest: {e}")
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
