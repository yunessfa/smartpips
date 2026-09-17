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


# our symbol -> Yahoo Finance ticker. Spot tickers (XAUUSD=X) 404, so these are
# the COMEX front futures. They track spot closely but carry a small basis,
# which is why Yahoo sits below Twelve Data in the chain.
_YF = {"XAUUSD": "GC=F", "XAGUSD": "SI=F"}
_YF_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "60m"}
_YF_RANGE = {"1m": "1d", "5m": "5d", "15m": "1mo", "1h": "3mo"}

# How many lower-timeframe bars make one higher-timeframe bar. Building 15m/1h/4h
# locally from 5m bars means ONE upstream request feeds every timeframe, which is
# what keeps us inside Twelve Data's free-tier rate limit.
_DERIVE_FROM_5M = {"15m": 3, "1h": 12, "4h": 48}

_TD_MIN_GAP = 9            # seconds between two Twelve Data requests
_STALE_TTL = 6 * 60 * 60   # keep the last good bar set for emergencies
_SECONDS_PER_TF = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}

# Which source last served a given "SYMBOL:tf". Diagnostics only (metals_probe
# reads it so it can report the truth instead of re-running the chain and
# possibly picking a different source the second time).
LAST_SOURCE: dict = {}


def _ttl_for(timeframe):
    return _TTL_BY_TF.get(timeframe, 90)


def _stale_put(key, val):
    """Remember the last GOOD bar set for hours, as a last-resort source."""
    if not val:
        return val
    try:
        from django.core.cache import cache
        cache.set("candles:stale:" + key, val, _STALE_TTL)
    except Exception:
        pass
    return val


def _stale_get(key):
    try:
        from django.core.cache import cache
        return cache.get("candles:stale:" + key)
    except Exception:
        return None


def _sane_bars(candles, symbol, timeframe, source):
    """Reject a bar set whose newest timestamp lies in the future.

    Why this exists: Twelve Data returns `datetime` strings in the FEED's local
    timezone, not UTC. Parsing them as UTC stamped gold bars ~10 hours ahead of
    now (the probe showed age=-35793s). Bars from the future poison every
    freshness check, make charts from two sources impossible to merge, and can
    make a stale feed look live. We fix the offset at the source below; this is
    the safety net for any provider that still hands us nonsense.
    """
    if not candles:
        return None
    newest = candles[-1].get("time")
    if not newest:
        return candles          # no timestamps at all: order is all we need
    drift = newest - time.time()
    if drift <= 120:
        return candles
    step = _SECONDS_PER_TF.get(timeframe, 300)
    log.warning("%s bars for %s %s are %d min in the future - rejecting this "
                "source (timezone bug upstream)", source, symbol, timeframe,
                int(drift // 60))
    # Tolerate at most one bar of clock skew; anything more is not skew.
    return None if drift > step else candles


def _aggregate(candles, factor):
    """Roll N lower-timeframe bars into one higher-timeframe bar.

    open = first open, close = last close, high/low = extremes, volume = sum.
    That is exactly how an exchange builds the higher timeframe, so these are
    real bars, not synthetic ones. Incomplete trailing groups are dropped.
    """
    if not candles or factor < 2:
        return candles or []
    out = []
    usable = len(candles) - (len(candles) % factor)
    for i in range(0, usable, factor):
        chunk = candles[i:i + factor]
        try:
            out.append({
                "time": chunk[0].get("time"),
                "open": chunk[0]["open"],
                "high": max(c["high"] for c in chunk),
                "low": min(c["low"] for c in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(c.get("volume") or 0 for c in chunk) or 1.0,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _yahoo_candles(symbol, timeframe, limit):
    """Free, keyless metal bars from Yahoo Finance (COMEX front futures).

    No API key and no quota worth worrying about, which is exactly what we need
    when Twelve Data's free allowance is spent. 4h is not offered; the caller
    derives it from 5m.
    """
    ticker = _YF.get(symbol.replace(":PERP", ""))
    interval = _YF_INTERVAL.get(timeframe)
    if not (ticker and interval):
        return None
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker,
            params={"interval": interval,
                    "range": _YF_RANGE.get(timeframe, "5d"),
                    "includePrePost": "false"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
        )
        if r.status_code != 200:
            log.warning("yahoo %s (%s %s) -> HTTP %s", ticker, symbol,
                        timeframe, r.status_code)
            return None
        result = ((r.json() or {}).get("chart") or {}).get("result") or []
        if not result:
            return None
        res = result[0]
        stamps = res.get("timestamp") or []
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        out = []
        for i, ts in enumerate(stamps):
            try:
                o, h, lo, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                v = (q.get("volume") or [None] * len(stamps))[i]
            except (KeyError, IndexError, TypeError):
                continue
            if None in (o, h, lo, c):
                continue            # Yahoo pads market gaps with nulls
            out.append({"time": int(ts), "open": float(o), "high": float(h),
                        "low": float(lo), "close": float(c),
                        "volume": float(v or 1.0)})
        return out[-limit:] or None
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("yahoo candles failed for %s %s: %s", symbol, timeframe, exc)
        return None


def _metal_fallback_candles(symbol, timeframe, limit):
    """Metal bars from anywhere but LBank, in order of trustworthiness.

    LBank publishes metal PRICES but refuses its public contract kline paths
    (HTTP 403 from their WAF, while /instrument and /marketData answer 200), so
    candles have to come from somewhere else:

    1. MT5/cTrader bridge - a real broker feed, when the bridge is running
    2. Twelve Data        - spot XAU/USD, but a hard free-tier quota
    3. Yahoo COMEX futures - keyless and unlimited; this is what fixes silver
    4. Derived locally from 5m bars - one request feeds every higher timeframe
    5. The last good set we ever saw, marked stale

    Every candidate goes through _sane_bars first. Returns (candles, source).
    """
    mt5 = _sane_bars(_mt5_candles(symbol, timeframe), symbol, timeframe, "mt5-bridge")
    if mt5:
        return mt5, "mt5-bridge"

    td = _sane_bars(_twelvedata_candles(symbol, timeframe, limit),
                    symbol, timeframe, "twelvedata")
    if td and len(td) >= 30:
        return td, "twelvedata"

    yf = _sane_bars(_yahoo_candles(symbol, timeframe, limit),
                    symbol, timeframe, "yahoo")
    if yf and len(yf) >= 30:
        return yf, "yahoo"

    factor = _DERIVE_FROM_5M.get(timeframe)
    if factor:
        base_5m = fetch_candles(symbol, "5m", min(limit * factor, 1000))
        derived = _aggregate(base_5m, factor)
        if derived and len(derived) >= 30:
            return derived, "derived-from-5m(x%d)" % factor

    stale = _stale_get("%s:%s" % (symbol, timeframe))
    if stale:
        return stale, "stale-cache"

    return None, None


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


def _td_utc_shift(meta):
    """Seconds to SUBTRACT from a Twelve Data timestamp to reach real UTC.

    Their `meta.exchange_timezone` says which clock the `datetime` strings are
    on. Returns 0 when it is already UTC or cannot be resolved (the caller's
    sanity check then catches anything still wrong).
    """
    tz_name = (meta or {}).get("exchange_timezone") or (meta or {}).get("timezone")
    if not tz_name or str(tz_name).upper() in ("UTC", "ETC/UTC", "GMT"):
        return 0
    try:
        from datetime import datetime, timezone as _tz
        from zoneinfo import ZoneInfo
        offset = datetime.now(_tz.utc).astimezone(ZoneInfo(str(tz_name))).utcoffset()
        return int(offset.total_seconds()) if offset else 0
    except Exception:
        log.warning("unknown Twelve Data timezone %r - leaving timestamps as-is",
                    tz_name)
        return 0


def _shift(ts, seconds):
    return (ts - seconds) if (ts and seconds) else ts


def _twelvedata_candles(symbol, timeframe, limit):
    """[LEGACY — Twelve Data] Metal bars, needs TWELVEDATA_KEY.

    Kept for rollback (METALS_DATA_SOURCE=legacy). Was the default metals
    source before LBank; its free tier rate-limits hard, which is one of the
    reasons for the move.
    """
    td_symbol = _TD.get(symbol.replace(":PERP", ""))
    interval = _TD_INTERVAL.get(timeframe, "5min")
    token = os.getenv("TWELVEDATA_KEY")
    if not (td_symbol and token):
        return None

    # THROTTLE: the free tier allows ~8 requests/minute and 800 credits/day.
    # Two symbols x four timeframes on a per-minute cron blew through that
    # before noon, which is why gold answered and silver came back empty. If we
    # spoke to them moments ago, skip and let the caller fall through to Yahoo
    # or to locally derived bars.
    try:
        from django.core.cache import cache
        if cache.get("td:cooldown"):
            log.info("twelve data skipped for %s %s (rate-limit cooldown)",
                     symbol, timeframe)
            return None
        cache.set("td:cooldown", True, _TD_MIN_GAP)
    except Exception:
        pass

    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": td_symbol, "interval": interval,
                    "outputsize": limit, "apikey": token, "order": "ASC"},
            timeout=8,
        )
        r.raise_for_status()
        payload = r.json() or {}
        values = payload.get("values") or []
        # Twelve Data timestamps are in the FEED's timezone, not UTC. Parsing
        # them as UTC is what stamped gold bars ~10 hours into the future.
        tz_shift = _td_utc_shift(payload.get("meta") or {})
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
            "time": _shift(_to_ts(v.get("datetime", "")), tz_shift),
        } for v in values]
        return candles or None
    except requests.RequestException as exc:
        # Never log the response body: on 429 Twelve Data echoes the request
        # URL back, API key included.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 429:
            try:
                from django.core.cache import cache
                cache.set("td:cooldown", True, 120)      # back off 2 minutes
            except Exception:
                pass
        log.warning("Twelve Data candles failed for %s %s (HTTP %s)",
                    symbol, timeframe, status or "n/a")
        return None
    except (ValueError, KeyError, TypeError):
        log.warning("Twelve Data candles unparseable for %s %s", symbol, timeframe)
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
            LAST_SOURCE[key] = "lbank"
            _stale_put(key, lb[-limit:])
            return _cache_put(key, lb[-limit:], timeframe)

        # LBank serves metal prices but refuses its public kline paths (403).
        # "Sit out forever" would mean "no metal signals, ever", so unless
        # METALS_STRICT_SOURCE=1 we take the best available substitute and name
        # it in the log. Those bars come from a different book, so exact levels
        # deserve a little tolerance.
        strict = str(os.getenv("METALS_STRICT_SOURCE", "")).lower() in ("1", "true", "yes")
        if not strict:
            bars, source = _metal_fallback_candles(symbol, timeframe, limit)
            if bars:
                LAST_SOURCE[key] = source
                log.warning("metals fallback: %s %s bars from %s "
                            "(LBank klines unavailable)", symbol, timeframe, source)
                if source != "stale-cache":
                    _stale_put(key, bars[-limit:])
                return _cache_put(key, bars[-limit:], timeframe)

        LAST_SOURCE[key] = None
        log.warning("no metal candles at all for %s %s — engine will sit out",
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
