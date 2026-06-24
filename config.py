import os
from dotenv import load_dotenv

load_dotenv()

# ── HALAL SCREENING ────────────────────────────────────────────────────────────
SCREENING_MODE = "STANDARD"  # "STANDARD" (AAOIFI) or "STRICT_INDIA" (Nifty50 Shariah)

# STANDARD mode — AAOIFI / DJIM thresholds
DEBT_TO_ASSETS_MAX = 0.30
DEBT_TO_MARKET_CAP_MAX = 0.33
CASH_SECURITIES_TO_ASSETS_MAX = 0.30
RECEIVABLES_TO_ASSETS_MAX = 0.49
INTEREST_INCOME_TO_REVENUE_MAX = 0.05
NON_PERMISSIBLE_INCOME_MAX = 0.05
FIXED_ASSETS_FLOOR = 0.20           # Zamzam Capital (India) requirement

# STRICT_INDIA overrides — Nifty50 Shariah / NSE (applied when SCREENING_MODE = "STRICT_INDIA")
STRICT_DEBT_TO_ASSETS_MAX = 0.25
STRICT_INTEREST_INCOME_MAX = 0.025

def get_debt_threshold() -> float:
    return STRICT_DEBT_TO_ASSETS_MAX if SCREENING_MODE == "STRICT_INDIA" else DEBT_TO_ASSETS_MAX

def get_interest_income_threshold() -> float:
    return STRICT_INTEREST_INCOME_MAX if SCREENING_MODE == "STRICT_INDIA" else INTEREST_INCOME_TO_REVENUE_MAX

def fixed_assets_floor_enabled() -> bool:
    return SCREENING_MODE == "STRICT_INDIA"

# ── FUNDAMENTAL HARD GATES ─────────────────────────────────────────────────────
MIN_ROE = 0.10
MIN_INTEREST_COVERAGE = 3.0
MAX_PE = 40
MIN_PIOTROSKI_SCORE = 4
MIN_ALTMAN_Z = 1.81
BENEISH_M_THRESHOLD = -1.78
MAX_PROMOTER_PLEDGE_PCT = 40.0

# ── CONVICTION SCORING WEIGHTS ─────────────────────────────────────────────────
WEIGHTS = {
    "valuation":     0.20,
    "profitability": 0.25,
    "growth":        0.15,
    "quality":       0.15,
    "health":        0.15,
    "india":         0.10,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# ── SIGNAL TIERS ───────────────────────────────────────────────────────────────
STRONG_BUY_THRESHOLD = 75
BUY_THRESHOLD = 60
WATCH_THRESHOLD = 50

# ── BUY / SELL RULES ──────────────────────────────────────────────────────────
MIN_HOLD_YEARS = 1
SELL_SCORE_FLOOR = 40
SELL_ROE_FLOOR = 0.10
SELL_DRAWDOWN_STOP = -0.30
MAX_PE_SELL = 60
POSITION_SIZE_INR = 10_000          # (legacy) per-trade size, fallback only
# Paper trading mirrors the real plan: a fresh MONTHLY_BUDGET_INR is deployed
# each calendar month (accumulating), in whole shares, so paper results predict
# what the real ₹7k/month portfolio would actually do.
MONTHLY_BUDGET_INR = 7_000          # Cash invested each month (paper = real plan)
MAX_NEW_PER_MONTH = 3              # Max new positions opened per month
MAX_POSITIONS = 24                 # Max total concurrent holdings (accumulates over time)
REAL_MONTHLY_BUDGET_INR = 7_000     # Real-money monthly budget (backtest default / live)
LIVE_POSITION_SIZE_INR = 5_000      # Real money per trade via Upstox
LIVE_TRADING = False                # Set True via --live flag; never commit True

# ── DATA ───────────────────────────────────────────────────────────────────────
NSE_UNIVERSE = "nifty500"           # nifty50 | nifty200 | nifty500
CACHE_TTL_HOURS = 24
MAX_WORKERS = 10

# ── OUTPUT ─────────────────────────────────────────────────────────────────────
TOP_N_RECOMMENDATIONS = 20
OUTPUT_DIR = "output"

# ── API KEYS ──────────────────────────────────────────────────────────────────
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET", "")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8080")

ZERODHA_API_KEY = os.getenv("ZERODHA_API_KEY", "")
ZERODHA_API_SECRET = os.getenv("ZERODHA_API_SECRET", "")
ZERODHA_ACCESS_TOKEN = os.getenv("ZERODHA_ACCESS_TOKEN", "")

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
REPORT_EMAIL_TO = os.getenv("REPORT_EMAIL_TO", "")
