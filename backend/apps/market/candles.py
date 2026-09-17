"""
Fetch recent OHLC candles so the strategy engine can compute REAL indicators on
real bars (not just the live tick stream).

2026-09 — metals moved to LBank
-------------------------------
Gold/silver bars now come from LBank (GOLD(XAU)USDT / SILVER(XAG)USDT perps),
the same venue as the price and the book. The previous metal sources are
commented out below rather than deleted:

  * MT5/cTrader bridge candles (MT5Candles)  -> _mt5_candles, still used for
    any non-metal broker symbol, but no longer consulted for XAU/XAG.
  * Twelve Data time_series (TWELVEDATA_KEY) -> _twelvedata_candles.

Set METALS_DATA_SOURCE=legacy to restore the old behaviour without editing
code.

Bitunix crypto candles are ACTIVE again (restored 2026-09-05). Binance stays
behind it as the fallback when Bitunix returns nothing.
"""
import logging
import os
import time

import requests

from .crypto_symbols import SUPPORTED_CRYPTO as _CRYPTO

log = logging.getLogger("smartpips.market.candles")

# Symbols served by LBank's Metals futures category.
_METALS = {"XAUUSD", "XAGUSD"}

# our symbol -> Twelve Data symbol
_TD = {"XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD"}
# timeframe label -> Twelve Data interval
_TD_INTERVAL = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}

_cache: dict = {}
# How long a fetched candle set stays fresh, per timeframe. A 5m bar doesn't change
# for 5 minutes, so caching ~90s slashes API calls without hurting accuracy.
_TTL_BY_TF = {"1m": 45, "5m": 90, "15m": 180, "1h": 600, "4h": 1800}


def _ttl_for(timeframe):
    return _TTL_BY_TF.get(timeframe, 90)


def _cache_get(key, timeframe="5m"):
    # Prefer the cross-worker Django cache; fall back to in-process dict.
    try:
        from django.core.cache import cache
        val = cache.get("candles:" + key)
        if val is not None:
            return val
    except Exception:
        pass
    hit = _cache.get(key)
    if hit and time.time() - hit[1] < _ttl_for(timeframe):
        return hit[0]
    return None


def _cache_put(key, val, timeframe="5m"):
    try:
        from django.core.cache import cache
        cache.set("candles:" + key, val, _ttl_for(timeframe))
    except Exception:
        pass
    _cache[key] = (val, time.time())
    return val


def _mt5_candles(symbol, timeframe, max_age=None):
    """Read fresh candles pushed by the MT5/cTrader bridge, if available and recent.
    Higher timeframes update less often, so allow them to be older before we
    consider them stale."""
    if max_age is None:
        max_age = {"5m": 180, "15m": 400, "1h": 1800, "4h": 5400}.get(timeframe, 180)
    try:
        from apps.mt5.models import MT5Candles
        from django.utils import timezone
        row = MT5Candles.objects.filter(symbol=symbol, timeframe=timeframe).first()
        if not row or not row.candles:
            return None
        if (timezone.now() - row.updated).total_seconds() > max_age:
            return None  # stale; fall back to other sources
        out = []
        for c in row.candles:
            try:
                out.append({
                    "open": float(c["open"]), "high": float(c["high"]),
                    "low": float(c["low"]), "close": float(c["close"]),
                    "volume": float(c.get("volume") or 1.0),
                })
            except (KeyError, TypeError, ValueError):
                continue
        return out or None
    except Exception:
        return None


_BINANCE_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"}



def _binance_candles(symbol, timeframe, limit):
    """Fetch real OHLCV candles from Binance. Spot by default; if the symbol ends
    with ':PERP' use the USD-M futures market (real volume + funding-driven moves)."""
    is_perp = symbol.endswith(":PERP")
    base = symbol.replace(":PERP", "")
    if base not in _CRYPTO:
        return None
    interval = _BINANCE_INTERVAL.get(timeframe, "5m")
    host = "https://fapi.binance.com/fapi/v1/klines" if is_perp \
        else "https://api.binance.com/api/v3/klines"
    try:
        r = requests.get(host, params={"symbol": base, "interval": interval,
                                       "limit": min(limit, 1000)}, timeout=8)
        r.raise_for_status()
        rows = r.json()
        # kline: [openTime, open, high, low, close, volume, closeTime, ...]
        return [{
            "time": int(k[0] // 1000),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        } for k in rows]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None


def _bitunix_candles(symbol, timeframe, limit):
    """Real OHLCV from Bitunix's OWN market for ':PERP' symbols — so the
    signal engine, the panel and the actual execution all share one venue
    (no Binance-vs-Bitunix basis mismatch on tight scalp stops)."""
    if not symbol.endswith(":PERP"):
        return None
    base = symbol.replace(":PERP", "")
    if base not in _CRYPTO:
        return None
    try:
        from apps.bitunix.client import BitunixClient
        c = BitunixClient()
        rows = (c.klines_paginated(base, timeframe, limit) if limit > 200
                else c.klines(base, timeframe, limit))
        return rows or None
    except Exception:
        # Kept the logging added in 2026-09: this used to fail silently, which
        # is why "crypto candles just stopped" was impossible to diagnose.
        log.exception("bitunix candles failed for %s %s", symbol, timeframe)
        return None


def _lbank_metal_candles(symbol, timeframe, limit):
    """ACTIVE metal bars: LBank GOLD(XAU)USDT / SILVER(XAG)USDT perps.

    Returns None (not []) when LBank has nothing, so the caller can tell
    "feed is down" apart from "market has no bars" and sit out instead of
    running the engine on synthetic data.
    """
    if symbol.replace(":PERP", "") not in _METALS:
        return None
    try:
        from apps.lbank.metals import fetch_candles
        return fetch_candles(symbol, timeframe, limit) or None
    except Exception:
        log.exception("lbank metal candles failed for %s %s", symbol, timeframe)
        return None


def _twelvedata_candles(symbol, timeframe, limit):
    """[LEGACY — Twelve Data] Metal bars, needs TWELVEDATA_KEY.

    Kept for rollback (METALS_DATA_SOURCE=legacy). Was the default metals
    source before LBank; its free tier rate-limits hard, which is one of the
    reasons for the move.
    """
    td_symbol = _TD.get(symbol)
    interval = _TD_INTERVAL.get(timeframe, "5min")
    token = os.getenv("TWELVEDATA_KEY")
    if not (td_symbol and token):
        return None
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": td_symbol, "interval": interval,
                    "outputsize": limit, "apikey": token, "order": "ASC"},
            timeout=8,
        )
        r.raise_for_status()
        values = (r.json() or {}).get("values") or []
        import calendar
        from datetime import datetime as _dt

        def _to_ts(s):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return calendar.timegm(_dt.strptime(s, fmt).timetuple())
                except (ValueError, TypeError):
                    continue
            return None

        candles = [{
            "open": float(v["open"]), "high": float(v["high"]),
            "low": float(v["low"]), "close": float(v["close"]),
            "volume": float(v["volume"]) if v.get("volume") else 1.0,
            "time": _to_ts(v.get("datetime", "")),
        } for v in values]
        return candles or None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        log.warning("legacy Twelve Data candles failed for %s %s", symbol, timeframe)
        return None


def fetch_candles(symbol: str, timeframe: str = "5m", limit: int = 200):
    """Return a list of {open,high,low,close} oldest->newest, or [] on failure.

    Source priority as of 2026-09:
      * metals (XAUUSD/XAGUSD) -> LBank only. No cross-venue fallback: a stop
        placed off another venue's print is worse than no signal at all.
      * crypto (spot & perps)  -> Bitunix klines first (the execution venue),
        then Binance public klines as the fallback.
      * anything else          -> fresh MT5/cTrader bridge candles.

    Set METALS_DATA_SOURCE=legacy to restore MT5-bridge -> Twelve Data for
    metals; both paths are still present, just not on the default route.
    """
    symbol = symbol.upper()
    key = f"{symbol}:{timeframe}"
    cached = _cache_get(key, timeframe)
    if cached is not None:
        return cached

    base = symbol.replace(":PERP", "")

    # ---------------------------------------------------------------- metals
    if base in _METALS:
        try:
            from django.conf import settings as _st
            metals_source = getattr(_st, "METALS_DATA_SOURCE", "lbank")
        except Exception:
            metals_source = "lbank"

        if metals_source == "legacy":
            # LEGACY PATH (kept, not deleted): broker bridge, then Twelve Data.
            mt5 = _mt5_candles(symbol, timeframe)
            if mt5:
                return _cache_put(key, mt5[-limit:], timeframe)
            td = _twelvedata_candles(symbol, timeframe, limit)
            if td:
                return _cache_put(key, td[-limit:], timeframe)
            return _cache_put(key, [], "1m")

        lb = _lbank_metal_candles(symbol, timeframe, limit)
        if lb:
            return _cache_put(key, lb[-limit:], timeframe)
        log.warning("no LBank candles for %s %s — engine will sit out",
                    symbol, timeframe)
        return _cache_put(key, [], "1m")

    # ---------------------------------------------------------------- crypto
    if base in _CRYPTO:
        # Bitunix first: same venue as execution, so scalp stops are measured
        # against the book the order actually hits.
        # NOTE: settings must be imported here. The metals branch above imports
        # `_st` inside its own scope, so it is NOT in scope at this point.
        try:
            from django.conf import settings as _st
            source = getattr(_st, "CRYPTO_PERP_DATA_SOURCE", "bitunix")
        except Exception:
            source = "bitunix"
        if source == "bitunix":
            bx = _bitunix_candles(symbol, timeframe, limit)
            if bx:
                return _cache_put(key, bx[-limit:], timeframe)
        bn = _binance_candles(symbol, timeframe, limit)
        if bn:
            return _cache_put(key, bn[-limit:], timeframe)
        log.warning("no Binance candles for %s %s", symbol, timeframe)
        return _cache_put(key, [], "1m")

    # ------------------------------------------------- other broker symbols
    mt5 = _mt5_candles(symbol, timeframe)
    if mt5:
        return _cache_put(key, mt5[-limit:], timeframe)

    return _cache_put(key, [], "1m")
