"""
Fully automated Upstox OAuth login using stored credentials.
Used by GitHub Actions to get a fresh access token daily.

Required environment variables (set as GitHub Secrets):
  UPSTOX_API_KEY       — from developer.upstox.com
  UPSTOX_API_SECRET    — from developer.upstox.com
  UPSTOX_MOBILE        — your registered mobile number (10 digits)
  UPSTOX_PASSWORD      — your Upstox account password
  UPSTOX_TOTP_SECRET   — TOTP seed from Upstox 2FA setup
                         (the text/QR code shown when you enabled 2FA)
  UPSTOX_PIN           — your 6-digit Upstox PIN
"""
import os
import json
import time
import urllib.parse
import requests
import pyotp
from pathlib import Path

_SANDBOX   = os.getenv("UPSTOX_SANDBOX", "true").lower() != "false"
_BASE      = "https://api-sandbox.upstox.com" if _SANDBOX else "https://api.upstox.com"
_AUTH_BASE = _BASE + "/v2/login/authorization"
_TOKEN_URL = _BASE + "/v2/login/authorization/token"
_TOKEN_FILE = Path(__file__).parent.parent / ".upstox_token.json"


def _get_totp() -> str:
    secret = os.environ["UPSTOX_TOTP_SECRET"].strip().replace(" ", "")
    return pyotp.TOTP(secret).now()


def get_fresh_token() -> str:
    """
    Fully automated login flow:
      1. Start OAuth session, get login page
      2. Submit mobile + password
      3. Submit TOTP code
      4. Submit PIN
      5. Extract auth code from redirect
      6. Exchange code for access token
    Returns access_token string.
    """
    api_key      = os.environ["UPSTOX_API_KEY"]
    api_secret   = os.environ["UPSTOX_API_SECRET"]
    mobile       = os.environ["UPSTOX_MOBILE"]
    password     = os.environ["UPSTOX_PASSWORD"]
    pin          = os.environ["UPSTOX_PIN"]
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8080/callback")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # ── Step 1: Load the auth dialog to get cookies/csrf ─────────────────────
    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     api_key,
        "redirect_uri":  redirect_uri,
    })
    auth_url = f"{_AUTH_BASE}/dialog?{auth_params}"
    r = session.get(auth_url, allow_redirects=True)
    print(f"[auto-login] Auth page: {r.status_code}")

    # ── Step 2: Submit mobile + password ─────────────────────────────────────
    login_payload = {
        "mobile":   mobile,
        "password": password,
    }
    r = session.post(
        f"{_AUTH_BASE}/dialog/mobile",
        json=login_payload,
        headers={"Content-Type": "application/json"},
    )
    print(f"[auto-login] Credentials submit: {r.status_code}")
    _check(r, "credential submission")

    # ── Step 3: Submit TOTP ───────────────────────────────────────────────────
    totp_code = _get_totp()
    print(f"[auto-login] TOTP generated: {totp_code[:2]}****")
    r = session.post(
        f"{_AUTH_BASE}/dialog/mobile/otp/validate",
        json={"otp": totp_code, "type": "TOTP"},
        headers={"Content-Type": "application/json"},
    )
    print(f"[auto-login] TOTP submit: {r.status_code}")
    _check(r, "TOTP validation")

    # ── Step 4: Submit PIN ────────────────────────────────────────────────────
    r = session.post(
        f"{_AUTH_BASE}/dialog/mobile/pin/validate",
        json={"pin": pin},
        headers={"Content-Type": "application/json"},
    )
    print(f"[auto-login] PIN submit: {r.status_code}")
    _check(r, "PIN validation")

    # ── Step 5: Extract auth code from redirect URL ───────────────────────────
    # After PIN, response contains the redirect URL with ?code=XXX
    try:
        data = r.json()
        redirect = data.get("redirectUrl") or data.get("redirect_url") or ""
    except Exception:
        redirect = r.headers.get("Location", "")

    if not redirect and r.history:
        redirect = r.history[-1].headers.get("Location", "")

    parsed = urllib.parse.urlparse(redirect)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if not code:
        raise RuntimeError(
            f"Could not extract auth code from redirect: {redirect}\n"
            f"Response body: {r.text[:500]}"
        )
    print(f"[auto-login] Auth code obtained: {code[:8]}...")

    # ── Step 6: Exchange code for access token ────────────────────────────────
    token_resp = requests.post(_TOKEN_URL, data={
        "code":          code,
        "client_id":     api_key,
        "client_secret": api_secret,
        "redirect_uri":  redirect_uri,
        "grant_type":    "authorization_code",
    }, headers={"Accept": "application/json"})
    token_resp.raise_for_status()

    token_data = token_resp.json()
    access_token = token_data["access_token"]
    print(f"[auto-login] Access token obtained: {access_token[:12]}...")

    # Save locally for this run
    _TOKEN_FILE.write_text(json.dumps(token_data, indent=2))

    return access_token


def _check(r: requests.Response, step: str):
    if r.status_code not in (200, 201, 302):
        raise RuntimeError(
            f"[auto-login] {step} failed ({r.status_code}): {r.text[:300]}"
        )


if __name__ == "__main__":
    print("[auto-login] Starting automated Upstox login...")
    token = get_fresh_token()
    # Print for GitHub Actions to capture as output
    print(f"::notice::Upstox token refreshed successfully")
    print(f"UPSTOX_ACCESS_TOKEN={token}")
