"""
Resolve a live USD price for an arbitrary symbol the user mentions in chat, so the
assistant is never "blind" about something outside the watchlist.

- Crypto pairs (…USDT/USDC/…) -> Binance public REST.
- Metals (XAUUSD / XAGUSD)     -> metals service, now LBank-backed.
- Major FX/forex pairs         -> exchangerate.host (free, no key).
Everything is best-effort and cached briefly to avoid hammering the APIs.

2026-09-05: the Bitunix crypto branch is ACTIVE again (the shutdown was
rolled back). Binance remains the resilience fallback behind it.
"""
import logging
import re
import time

import requests

log = logging.getLogger("smartpips.market.quotes")

from .services import fetch_binance_quote
from .metals import fetch_metal_price

# Popular forex pairs we understand (base, quote).
FOREX_PAIRS = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"), "AUDUSD": ("AUD", "USD"), "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"), "EURJPY": ("EUR", "JPY"), "GBPJPY": ("GBP", "JPY"),
    "EURGBP": ("EUR", "GBP"),
}
METALS = {"XAUUSD", "XAGUSD"}

_CRYPTO_RE = re.compile(r"^[A-Z0-9]{2,15}(USDT|USDC|FDUSD|BUSD)$")

_cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, ts)
_TTL = 15  # seconds


def _cached(symbol):
    hit = _cache.get(symbol)
    if hit and time.time() - hit[1] < _TTL:
        return hit[0]
    return None


def _store(symbol, price):
    if price is not None:
        _cache[symbol] = (price, time.time())
    return price


def _forex_price(pair):
    base, quote = FOREX_PAIRS[pair]
    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": base, "symbols": quote},
            timeout=6,
        )
        r.raise_for_status()
        rate = r.json().get("rates", {}).get(quote)
        return float(rate) if rate else None
    except (requests.RequestException, ValueError, TypeError):
        return None


def live_price(symbol: str):
    """Return a float USD/quote price for one symbol, or None."""
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return None
    # crypto perpetual futures share the spot price for P&L purposes here
    base = symbol.replace(":PERP", "")
    cached = _cached(base)
    if cached is not None:
        return cached

    if base in METALS:
        return _store(base, fetch_metal_price(base))
    if base in FOREX_PAIRS:
        return _store(base, _forex_price(base))
    if _CRYPTO_RE.match(base):
        # SINGLE-SOURCE: crypto prices come from Bitunix (the execution
        # venue) first, so the tick the signal engine sees is the market the
        # order actually hits; Binance stays as a resilience fallback.
        p = _bitunix_price(base)
        if p is not None:
            return _store(base, p)
        q = fetch_binance_quote(base)
        return _store(base, q["price"] if q else None)
    # bare coin like "BTC" -> assume USDT pair
    if re.match(r"^[A-Z0-9]{2,10}$", base):
        p = _bitunix_price(base + "USDT")
        if p is not None:
            return _store(base, p)
        q = fetch_binance_quote(base + "USDT")
        return _store(base, q["price"] if q else None)
    return None


def _bitunix_price(pair):
    """Last price from Bitunix futures tickers; None on any failure or when
    the data source is switched back to binance via env."""
    try:
        from django.conf import settings as _st
        if getattr(_st, "CRYPTO_PERP_DATA_SOURCE", "bitunix") != "bitunix":
            return None
        from apps.bitunix.client import BitunixClient
        return BitunixClient().last_price(pair)
    except Exception:
        # Logging kept from 2026-09 — a silent None here looked identical to
        # "Bitunix has no price", which hid outages behind Binance numbers.
        log.exception("bitunix price lookup failed for %s", pair)
        return None


def live_prices(symbols) -> dict:
    out = {}
    for s in symbols:
        p = live_price(s)
        if p is not None:
            out[(s or "").upper()] = p
    return out
