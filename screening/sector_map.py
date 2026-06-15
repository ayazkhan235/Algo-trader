"""
Maps yfinance sector/industry strings to halal classification.
Based on AAOIFI Shariah Standard No. 21 + Nifty50 Shariah Index methodology.
"""

# ── Hard exclusion: these industry/sector substrings → HARAM ──────────────────
# Matched case-insensitively as substrings of yfinance industry or sector fields.
HARAM_KEYWORDS = {
    # Conventional finance (riba)
    "bank", "banking", "credit service", "mortgage", "capital market",
    "insurance", "financial service", "asset management", "brokerage",
    # Alcohol
    "wine", "winer", "distiller", "brewer", "brewery", "alcohol", "spirit",
    "beverage—alc",
    # Tobacco
    "tobacco", "cigarette",
    # Gambling
    "gambling", "casino", "gaming",
    # Defense / weapons
    "aerospace & defense", "defense", "weapon",
    # Adult entertainment
    "adult entertainment", "pornograph",
}

# ── Sectors that are blanket haram (yfinance sector field) ────────────────────
HARAM_SECTORS = {"financial services"}

# ── Manual blacklist: symbols always excluded regardless of sector ─────────────
# Add here conglomerates where yfinance sector doesn't reflect haram activity.
MANUAL_BLACKLIST = {
    "ITC.NS",       # Classified as Consumer Staples but primary revenue = tobacco
    "UNITEDSPRT.NS", # United Spirits — alcohol
    "RADICO.NS",    # Radico Khaitan — alcohol
    "MCDOWELL-N.NS",# McDowell's — alcohol
    "ABBINDIA.NS",  # ABB India — partly defense
    "BEL.NS",       # Bharat Electronics — defense
    "HAL.NS",       # Hindustan Aeronautics — defense
    "MFSL.NS",      # Max Financial — conventional insurance
    "CHOLAFIN.NS",  # Cholamandalam Finance — conventional NBFC
}

# ── Manual whitelist: symbols kept even if in a borderline sector ─────────────
# Islamic finance institutions, pure asset managers, halal-compliant NBFCs.
MANUAL_WHITELIST = {
    "HDFCAMC.NS",   # HDFC AMC — asset management (manages equity funds, not lender)
    "NIPPONLIFEIN.NS", # Nippon Life India AMC
    "ABSLAMC.NS",   # Aditya Birla Sun Life AMC
    "UTIAMC.NS",    # UTI AMC
}

# ── Sectors flagged for human review (not auto-rejected) ─────────────────────
REVIEW_KEYWORDS = {
    "entertainment", "hotel", "resort", "hospitality", "media",
    "advertising", "real estate", "reit", "meat", "packaged food",
}


def classify(symbol: str, sector: str, industry: str) -> tuple[str, str]:
    """
    Returns (classification, reason).
    classification: "halal" | "haram" | "review"
    """
    sym = symbol.upper()
    sec = (sector or "").lower()
    ind = (industry or "").lower()

    if sym in MANUAL_BLACKLIST:
        return "haram", f"Manual blacklist — {symbol}"

    if sym in MANUAL_WHITELIST:
        return "halal", f"Manual whitelist — {symbol}"

    for kw in HARAM_KEYWORDS:
        if kw in sec or kw in ind:
            return "haram", f"Haram keyword '{kw}' in sector/industry"

    if sec in HARAM_SECTORS:
        return "haram", f"Haram sector: {sector}"

    for kw in REVIEW_KEYWORDS:
        if kw in sec or kw in ind:
            return "review", f"Borderline keyword '{kw}' — manual review advised"

    return "halal", f"Sector '{sector}' / industry '{industry}' — no haram indicators"
