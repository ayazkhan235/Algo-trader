"""
Crypto market pulse — BTC/ETH prices and Fear & Greed Index.
Uses CoinGecko (free, no API key) and alternative.me.
Crypto is used as a global risk-appetite indicator, not as a buy signal.
"""
import requests
from data import cache

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


def fetch_crypto_prices() -> dict:
    cache_key = "crypto_prices"
    cached = cache.get(cache_key, ttl_hours=1)
    if cached:
        return cached

    try:
        resp = requests.get(
            COINGECKO_URL,
            params={"ids": "bitcoin,ethereum", "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        result = {
            "BTC": {
                "price_usd":    data["bitcoin"]["usd"],
                "change_24h":   data["bitcoin"].get("usd_24h_change", 0) / 100,
            },
            "ETH": {
                "price_usd":    data["ethereum"]["usd"],
                "change_24h":   data["ethereum"].get("usd_24h_change", 0) / 100,
            },
        }
        cache.set(cache_key, result)
        return result
    except Exception as e:
        print(f"[crypto] Price fetch failed: {e}")
        return {}


def fetch_fear_greed() -> dict:
    cache_key = "fear_greed"
    cached = cache.get(cache_key, ttl_hours=12)
    if cached:
        return cached

    try:
        resp = requests.get(FEAR_GREED_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"][0]
        result = {
            "value":      int(data["value"]),
            "label":      data["value_classification"],
            "timestamp":  data["timestamp"],
        }
        cache.set(cache_key, result)
        return result
    except Exception as e:
        print(f"[crypto] Fear & Greed fetch failed: {e}")
        return {}


def crypto_market_signal(prices: dict, fg: dict) -> str:
    """
    Returns a plain-English signal for Indian market context.
    BTC tracks Nasdaq risk-on/off sentiment.
    """
    btc_chg = prices.get("BTC", {}).get("change_24h", 0)
    fg_val  = fg.get("value", 50)

    if btc_chg < -0.07 or fg_val <= 20:
        return "RISK-OFF: Crypto crash — global risk-off likely, watch for FII selling in NSE"
    if btc_chg < -0.03 or fg_val <= 35:
        return "CAUTION: Crypto weakness — mild risk-off signal for equities"
    if btc_chg > 0.05 and fg_val >= 70:
        return "RISK-ON: Crypto strength — global risk appetite high, positive for NSE"
    return "NEUTRAL: Crypto not sending a strong directional signal"
