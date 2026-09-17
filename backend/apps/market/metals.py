"""
Live spot prices for metals (gold/silver).

2026-09 — SINGLE SOURCE: LBank
------------------------------
LBank lists both metals as USDT-margined perpetuals in its "Metals" futures
category (GOLD(XAU)USDT Perp / SILVER(XAG)USDT Perp), so gold and silver now
come from the same venue as everything else. That removes three separate
failure modes at once: two API keys we didn't control, and a basis mismatch
between the price we quoted and the book we executed on.

The OLD provider chain is preserved verbatim below, commented out, NOT
deleted:

  1. cTrader / MT5 bridge (MT5Quote)   -> _from_ctrader
  2. gold-api.com (free, no key)       -> _from_gold_api
  3. iTick (needs ITICK_TOKEN)         -> _from_itick

To roll back, set METALS_DATA_SOURCE=legacy in the environment — the legacy
chain is still wired up behind that flag, so no code edit is needed.

All calls stay best-effort: any failure returns None for that symbol and the
caller refuses to quote a price rather than inventing one.
"""
import logging
import os

import requests
from django.conf import settings

log = logging.getLogger("smartpips.market.metals")

# Our symbol -> the code each provider expects.
GOLD_API = {"XAUUSD": "XAU", "XAGUSD": "XAG"}

_HEADERS = {"User-Agent": "SmartPips/1.0"}


# ===========================================================================
# ACTIVE: LBank
# ===========================================================================
def _from_lbank(symbol: str):
    """Last price for XAUUSD / XAGUSD from LBank futures.

    apps.lbank.metals resolves the real contract symbol from LBank's own
    instrument list, so a rename/delisting on their side surfaces as None
    here instead of a silently wrong number.
    """
    try:
        from apps.lbank.metals import fetch_price
        return fetch_price(symbol)
    except Exception:
        # Logged, not swallowed — this is exactly the class of silent failure
        # the technical review flagged (T-2).
        log.exception("lbank metal price failed for %s", symbol)
        return None


# ===========================================================================
# LEGACY PROVIDERS — commented out 2026-09, kept for rollback.
# Reachable only when METALS_DATA_SOURCE=legacy (see fetch_metal_price).
# ===========================================================================
def _from_gold_api(symbol: str):
    """[LEGACY — gold-api.com] Free USD spot, no API key."""
    code = GOLD_API.get(symbol)
    if not code:
        return None
    try:
        r = requests.get(f"https://api.gold-api.com/price/{code}",
                         timeout=6, headers=_HEADERS)
        r.raise_for_status()
        price = r.json().get("price")
        return float(price) if price else None
    except (requests.RequestException, ValueError, TypeError):
        log.warning("legacy gold-api lookup failed for %s", symbol)
        return None


def _from_itick(symbol: str):
    """[LEGACY — iTick] Needs ITICK_TOKEN in the environment."""
    token = os.getenv("ITICK_TOKEN")
    if not token:
        return None
    try:
        r = requests.get(
            "https://api.itick.org/forex/quote",
            params={"region": "gb", "code": symbol},
            headers={"token": token, **_HEADERS},
            timeout=6,
        )
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data", payload) or {}
        # iTick field names vary; try the common ones for "last price".
        for key in ("ld", "last", "price", "c", "lastPrice", "p"):
            if data.get(key):
                return float(data[key])
    except (requests.RequestException, ValueError, TypeError, KeyError):
        log.warning("legacy iTick lookup failed for %s", symbol)
        return None
    return None


def _from_ctrader(symbol):
    """[LEGACY — cTrader/MT5 bridge] Live mid-price from MT5Quote, if fresh."""
    try:
        from apps.mt5.models import MT5Quote
        from django.utils import timezone
        q = MT5Quote.objects.filter(symbol=symbol.upper()).first()
        if q and q.bid and q.ask:
            if (timezone.now() - q.updated).total_seconds() < 60:
                return round((q.bid + q.ask) / 2.0, 3)
    except Exception:
        log.exception("legacy cTrader/MT5 quote lookup failed for %s", symbol)
    return None


def _legacy_chain(symbol: str):
    """The pre-2026-09 waterfall, kept intact behind METALS_DATA_SOURCE=legacy."""
    return _from_ctrader(symbol) or _from_gold_api(symbol) or _from_itick(symbol)


# ===========================================================================
def fetch_metal_price(symbol: str):
    """Return a float USD price for XAUUSD / XAGUSD, or None.

    Default path is LBank only — one venue, one number, no disagreement
    between the price shown and the book traded. Setting
    METALS_DATA_SOURCE=legacy restores the old cTrader -> gold-api -> iTick
    waterfall without touching this file.
    """
    source = getattr(settings, "METALS_DATA_SOURCE", "lbank")

    if source == "legacy":
        return _legacy_chain(symbol)

    price = _from_lbank(symbol)
    if price:
        return price

    # Intentionally NO silent fallback to the legacy feeds here. Mixing venues
    # is how you end up stopped out on a price that never printed where you
    # trade. If LBank is down we say "no price" and the engine sits out.
    log.warning("no LBank price for %s — refusing to quote from another venue",
                symbol)
    return None


def fetch_metal_prices(symbols=("XAUUSD", "XAGUSD")) -> dict:
    out = {}
    for sym in symbols:
        price = fetch_metal_price(sym)
        if price:
            out[sym] = price
    return out
