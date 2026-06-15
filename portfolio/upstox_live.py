"""
Upstox API v2 live portfolio integration.
Fetches real holdings once DMAT account is active and API keys are set.
"""
import config
from portfolio.csv_importer import Holding


def get_holdings() -> list[Holding]:
    """
    Fetches live holdings from Upstox API v2.
    Returns empty list if API keys not configured or account not activated.
    """
    if not config.UPSTOX_ACCESS_TOKEN:
        print("[upstox] No access token — skipping live holdings fetch")
        return []

    try:
        import upstox_client
        configuration = upstox_client.Configuration()
        configuration.access_token = config.UPSTOX_ACCESS_TOKEN

        api = upstox_client.PortfolioApi(upstox_client.ApiClient(configuration))
        response = api.get_holdings(api_version="2.0")

        holdings = []
        for item in response.data or []:
            isin = item.isin or ""
            sym  = (item.trading_symbol or "").replace("-EQ", "") + ".NS"
            holdings.append(Holding(
                symbol=sym,
                name=item.company_name or "",
                quantity=float(item.quantity or 0),
                avg_buy_price=float(item.average_price or 0),
                current_price=float(item.last_price or 0),
                broker="upstox",
            ))

        print(f"[upstox] Loaded {len(holdings)} live holdings")
        return holdings

    except ImportError:
        print("[upstox] upstox-python not installed — run: pip install upstox-python")
        return []
    except Exception as e:
        print(f"[upstox] Holdings fetch failed: {e}")
        return []
