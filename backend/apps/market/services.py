"""
Market data services.

`get_quotes()` tries to pull live crypto prices from Binance's public REST API
(no API key required). If the network is unavailable, it falls back to
deterministic mock data so the dashboard always renders.
"""
import random
import requests

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"


def _mock_quote(symbol: str) -> dict:
    """Stable pseudo-random quote so the UI never looks broken offline."""
    rnd = random.Random(symbol)
    base = rnd.uniform(50, 70000)
    change = rnd.uniform(-6, 6)
    return {
        "symbol": symbol,
        "price": round(base, 2),
        "change_percent": round(change, 2),
        "high": round(base * 1.03, 2),
        "low": round(base * 0.97, 2),
        "volume": round(rnd.uniform(1_000, 5_000_000), 2),
        "source": "mock",
    }


def fetch_binance_quote(binance_symbol: str) -> dict | None:
    try:
        resp = requests.get(
            BINANCE_TICKER_URL,
            params={"symbol": binance_symbol},
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "price": float(data["lastPrice"]),
            "change_percent": float(data["priceChangePercent"]),
            "high": float(data["highPrice"]),
            "low": float(data["lowPrice"]),
            "volume": float(data["quoteVolume"]),
            "source": "binance",
        }
    except Exception:
        return None


def get_quotes(assets) -> list[dict]:
    """Return a list of quote dicts for the given Asset queryset/iterable."""
    quotes = []
    for asset in assets:
        quote = None
        if asset.binance_symbol:
            quote = fetch_binance_quote(asset.binance_symbol)
        if quote is None:
            quote = _mock_quote(asset.symbol)
        quote.update(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "category": asset.category,
                "tradingview_symbol": asset.tradingview_symbol or asset.symbol,
            }
        )
        quotes.append(quote)
    return quotes
