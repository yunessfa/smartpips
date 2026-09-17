"""Gold & silver market data from LBank — the single venue for everything now.

Why this file exists
--------------------
LBank lists both metals as USDT-margined perpetuals in its "Metals" futures
category:

    GOLD(XAU)USDT Perp      <- our XAUUSD
    SILVER(XAG)USDT Perp    <- our XAGUSD

So gold/silver price AND candles can come from the same place as the rest of
the app instead of the old four-provider stack (cTrader/MT5 bridge ->
gold-api.com -> iTick -> Twelve Data). Those providers are NOT deleted; they
are commented out in `apps/market/metals.py` and `apps/market/candles.py` and
can be switched back on by un-commenting one block.

Two deliberate design choices, both about not lying to the trader
----------------------------------------------------------------
1. **No hardcoded contract symbol.** `resolve_symbol()` reads LBank's own
   `pub/instrument` list and matches on XAU/GOLD/XAG/SILVER. If LBank ever
   renames or delists the contract, we return None and the caller shows "no
   price" instead of a stale or invented number.
2. **No guessed kline endpoint.** LBank's contract docs are thin on klines, so
   `fetch_candles()` probes a small list of documented-looking candidates once,
   remembers the one that actually answered, and returns None if none do. A
   missing candle set makes the strategy engine sit out — which is correct —
   rather than run on fabricated bars.

Everything here is best-effort and logged. Nothing raises into a request.
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger("smartpips.market.lbank")

_BASE = getattr(settings, "LBANK_FUTURES_BASE_URL", "https://lbkperp.lbank.com").rstrip("/")
_PUB = "/cfd/openApi/v1/pub"
_PRODUCT_GROUP = "SwapU"          # USDT-margined perpetual
_TIMEOUT = 8

# Our internal symbol -> the tokens we accept in an LBank contract symbol.
# Matching is substring-based and case-insensitive, so "GOLDUSDT",
# "XAUUSDT" and "GOLD(XAU)USDT" all resolve for XAUUSD.
_MATCH = {
    "XAUUSD": ("XAU", "GOLD"),
    "XAGUSD": ("XAG", "SILVER"),
}

SUPPORTED = frozenset(_MATCH)

# Cache keys / TTLs. Symbol resolution barely ever changes, prices must not be
# stale, and the working kline endpoint is worth remembering for a whole day.
_SYMBOL_TTL = 6 * 60 * 60
_PRICE_TTL = 10
_ENDPOINT_TTL = 24 * 60 * 60
_CANDLE_TTL = {"1m": 45, "5m": 90, "15m": 180, "1h": 600, "4h": 1800}


def _get(path, params):
    """GET an LBank public endpoint. Returns parsed JSON or None. Never raises."""
    try:
        r = requests.get(f"{_BASE}{path}", params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("lbank GET %s failed: %s", path, exc)
        return None


def _rows(payload):
    """Unwrap LBank's {result, error_code, data:[...]} envelope."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    return payload if isinstance(payload, list) else []


def _num(v):
    try:
        f = float(v)
        return f if f == f else None      # reject NaN
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- symbols ----
def resolve_symbol(symbol):
    """Our "XAUUSD" -> LBank's actual contract symbol, or None if not listed.

    Reads the venue's instrument list rather than trusting a constant, so a
    rename on LBank's side degrades to "no data" instead of silent nonsense.
    """
    symbol = (symbol or "").upper().replace(":PERP", "")
    tokens = _MATCH.get(symbol)
    if not tokens:
        return None

    key = f"lbank:metal-symbol:{symbol}"
    hit = cache.get(key)
    if hit is not None:
        return hit or None                # "" is a cached negative

    rows = _rows(_get(f"{_PUB}/instrument", {"productGroup": _PRODUCT_GROUP}))
    found = ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = str(row.get("symbol") or "")
        haystack = f"{candidate} {row.get('symbolName') or ''}".upper()
        # Must look like a USDT quote AND mention gold/silver.
        if "USDT" in haystack and any(tok in haystack for tok in tokens):
            found = candidate
            break

    if found:
        log.info("lbank metals: %s -> %s", symbol, found)
    else:
        log.warning("lbank metals: %s not listed on LBank (%d instruments seen)",
                    symbol, len(rows))
    cache.set(key, found, _SYMBOL_TTL)
    return found or None


def available():
    """Which of XAUUSD / XAGUSD LBank can actually serve right now."""
    return {s: bool(resolve_symbol(s)) for s in sorted(SUPPORTED)}


# ----------------------------------------------------------------- price ----
def fetch_price(symbol):
    """Last traded price for XAUUSD / XAGUSD from LBank, or None."""
    symbol = (symbol or "").upper().replace(":PERP", "")
    if symbol not in SUPPORTED:
        return None

    key = f"lbank:metal-price:{symbol}"
    hit = cache.get(key)
    if hit is not None:
        return hit

    contract = resolve_symbol(symbol)
    if not contract:
        return None

    for row in _rows(_get(f"{_PUB}/marketData", {"productGroup": _PRODUCT_GROUP})):
        if not isinstance(row, dict) or row.get("symbol") != contract:
            continue
        # markedPrice is the fairer number for risk/PnL; lastPrice is the tape.
        price = _num(row.get("lastPrice")) or _num(row.get("markedPrice"))
        if price:
            cache.set(key, price, _PRICE_TTL)
            return price

    log.warning("lbank metals: no marketData row for %s (%s)", symbol, contract)
    return None


def fetch_prices(symbols=("XAUUSD", "XAGUSD")):
    out = {}
    for sym in symbols:
        price = fetch_price(sym)
        if price:
            out[sym.upper()] = price
    return out


# --------------------------------------------------------------- candles ----
# LBank's contract docs don't pin down the kline path/interval naming, so we
# probe instead of guessing once and failing forever. Each entry is
# (path, interval-map, param-name-for-limit).
_KLINE_ATTEMPTS = (
    (f"{_PUB}/getKline", {"1m": "1min", "5m": "5min", "15m": "15min",
                          "1h": "1hour", "4h": "4hour"}, "size"),
    (f"{_PUB}/getKline", {"1m": "1m", "5m": "5m", "15m": "15m",
                          "1h": "1h", "4h": "4h"}, "limit"),
    (f"{_PUB}/kline", {"1m": "1min", "5m": "5min", "15m": "15min",
                       "1h": "1hour", "4h": "4hour"}, "size"),
    (f"{_PUB}/marketKline", {"1m": "1min", "5m": "5min", "15m": "15min",
                             "1h": "1hour", "4h": "4hour"}, "size"),
)


def _parse_candles(payload):
    """Normalise whatever LBank returned into our {time,open,high,low,close,volume}.

    Accepts both dict rows and positional arrays, because kline endpoints on
    this venue are inconsistent about it. Returns [] when the shape is
    unrecognised — an empty list is honest, a half-parsed one is dangerous.
    """
    out = []
    for row in _rows(payload):
        try:
            if isinstance(row, dict):
                o = _num(row.get("open") or row.get("o"))
                h = _num(row.get("high") or row.get("h"))
                lo = _num(row.get("low") or row.get("l"))
                c = _num(row.get("close") or row.get("c"))
                v = _num(row.get("volume") or row.get("vol") or row.get("v")) or 1.0
                ts = _num(row.get("timestamp") or row.get("time") or row.get("t"))
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                # [time, open, high, low, close, volume?]
                ts, o, h, lo, c = (_num(row[0]), _num(row[1]), _num(row[2]),
                                   _num(row[3]), _num(row[4]))
                v = (_num(row[5]) if len(row) > 5 else None) or 1.0
            else:
                continue
            if None in (o, h, lo, c):
                continue
            if ts and ts > 1e11:          # milliseconds -> seconds
                ts = ts / 1000.0
            out.append({"time": int(ts) if ts else None, "open": o, "high": h,
                        "low": lo, "close": c, "volume": v})
        except (TypeError, ValueError, IndexError, KeyError):
            continue

    # oldest -> newest, which is what the strategy engine expects
    if len(out) >= 2 and out[0].get("time") and out[-1].get("time"):
        if out[0]["time"] > out[-1]["time"]:
            out.reverse()
    return out


def fetch_candles(symbol, timeframe="5m", limit=300):
    """OHLCV candles for XAUUSD / XAGUSD from LBank, or None if unavailable.

    Returning None (not []) matters: the caller can then decide to fall back,
    whereas [] would look like "the market has no bars".
    """
    symbol = (symbol or "").upper().replace(":PERP", "")
    if symbol not in SUPPORTED:
        return None

    cache_key = f"lbank:metal-candles:{symbol}:{timeframe}"
    hit = cache.get(cache_key)
    if hit:
        return hit

    contract = resolve_symbol(symbol)
    if not contract:
        return None

    # Try the endpoint that worked last time first.
    remembered = cache.get("lbank:kline-endpoint")
    attempts = list(_KLINE_ATTEMPTS)
    if remembered is not None and 0 <= remembered < len(attempts):
        attempts.insert(0, attempts.pop(remembered))

    for attempt in attempts:
        path, interval_map, limit_param = attempt
        interval = interval_map.get(timeframe)
        if not interval:
            continue
        payload = _get(path, {"symbol": contract, "type": interval,
                              "interval": interval, limit_param: min(limit, 500)})
        candles = _parse_candles(payload)
        if len(candles) >= 30:
            cache.set("lbank:kline-endpoint", _KLINE_ATTEMPTS.index(attempt),
                      _ENDPOINT_TTL)
            cache.set(cache_key, candles[-limit:],
                      _CANDLE_TTL.get(timeframe, 90))
            return candles[-limit:]

    log.warning("lbank metals: no kline endpoint answered for %s %s — strategy "
                "will sit this one out rather than run on synthetic bars",
                symbol, timeframe)
    return None
