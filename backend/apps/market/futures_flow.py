"""Real futures order-flow data (Binance USD-M public endpoints, no API key).

Why a second venue: orders are executed on Bitunix, but Bitunix publishes neither
taker buy / sell volume nor open-interest history. Binance USD-M is the deepest
BTC / alt perp market and publishes both, so it is used as the REFERENCE market
for flow. Every payload below says so (`venue`), and nothing here feeds a
decision: the 2026-10 indicator study could not test these inputs because no
history had been collected. Collect first (`record_flow`, `backfill_flow`), test
second, wire into the engine only if a study says so.

What is real and what is not:
  * taker buy / sell volume per bar  - real aggressor volume (exchange reported)
  * open interest, funding, mark     - real
  * order book                       - real resting orders at the moment of the
                                       request; they can be pulled before trading
  * liquidations (websocket only)    - a SAMPLE: the exchange pushes at most the
                                       largest liquidation per symbol per second
"""
import logging
import os
import time

import requests

log = logging.getLogger("smartpips.flow")

VENUE = "binance_usdm"
BASE_URL = os.getenv("BINANCE_FAPI_URL", "https://fapi.binance.com").rstrip("/")
# Since 2026-04 market streams must use a routed path; forceOrder lives under /market.
WS_MARKET_URL = os.getenv("BINANCE_FSTREAM_MARKET_URL", "wss://fstream.binance.com/market").rstrip("/")
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
OI_PERIODS = ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")
DEPTH_LIMITS = (5, 10, 20, 50, 100, 500, 1000)


class FlowError(Exception):
    """Feed problem. The message is safe to log; callers show a generic one."""


def base_symbol(symbol):
    return (symbol or "").upper().replace(":PERP", "").replace("/", "").strip()


def _get(path, params=None, timeout=8, session=None):
    try:
        r = (session or requests).get(f"{BASE_URL}{path}", params=params or {}, timeout=timeout,
                                      headers={"User-Agent": "SmartPips/flow"})
    except requests.RequestException as exc:
        raise FlowError(f"network error on {path}: {type(exc).__name__}") from exc
    if r.status_code in (418, 429):
        raise FlowError(f"rate limited on {path} (HTTP {r.status_code}, retry-after={r.headers.get('Retry-After')})")
    if r.status_code == 451:
        raise FlowError(f"{path} is not served to this server's region (HTTP 451)")
    if r.status_code != 200:
        raise FlowError(f"HTTP {r.status_code} on {path}: {r.text[:120]}")
    try:
        return r.json()
    except ValueError as exc:
        raise FlowError(f"non-JSON response on {path}") from exc


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


# ------------------------------------------------------------------ parsers --
def parse_kline(k):
    """[openTime, o, h, l, c, volume, closeTime, quoteVol, trades, takerBuyBase, takerBuyQuote, _]"""
    try:
        vol, buy = float(k[5]), float(k[9])
        return {"time": int(k[0]) // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                "close": float(k[4]), "volume": vol, "quote_volume": float(k[7]), "trades": int(k[8]),
                "taker_buy": buy, "taker_sell": max(vol - buy, 0.0), "delta": 2 * buy - vol}
    except (IndexError, TypeError, ValueError):
        return None


def parse_depth(d):
    def side(rows):
        out = []
        for r in rows or []:
            if not isinstance(r, (list, tuple)) or len(r) < 2:
                continue
            p, q = _f(r[0]), _f(r[1])
            if p is not None and q is not None and p > 0 and q > 0:
                out.append([p, q])
        return out
    if not isinstance(d, dict):
        return None
    bids, asks = side(d.get("bids")), side(d.get("asks"))
    if not bids or not asks:
        return None
    bids.sort(key=lambda r: -r[0])
    asks.sort(key=lambda r: r[0])
    t = d.get("T") or d.get("E")
    return {"time": int(t) / 1000.0 if t else time.time(), "last_update_id": d.get("lastUpdateId"),
            "bids": bids, "asks": asks}


def parse_force_order(msg):
    """Liquidation event from <symbol>@forceOrder (raw or combined-stream envelope)."""
    if not isinstance(msg, dict):
        return None
    data = msg.get("data") if "data" in msg else msg
    o = (data or {}).get("o") if isinstance(data, dict) else None
    if not isinstance(o, dict) or data.get("e") != "forceOrder":
        return None
    price = _f(o.get("ap")) or _f(o.get("p"))
    qty = _f(o.get("z")) or _f(o.get("q"))
    side = str(o.get("S") or "").upper()
    if not price or not qty or side not in ("BUY", "SELL"):
        return None
    # A SELL liquidation order closes a LONG; a BUY closes a SHORT.
    return {"time": int(o.get("T") or data.get("E") or 0) / 1000.0, "symbol": str(o.get("s") or "").upper(),
            "side": side, "liquidated": "long" if side == "SELL" else "short",
            "price": price, "qty": qty, "notional": price * qty}


# --------------------------------------------------------------------- REST --
def klines(symbol, interval="5m", limit=500, start_ms=None, end_ms=None, session=None):
    """Bars with real taker buy / sell volume. `limit` max 1500."""
    params = {"symbol": base_symbol(symbol), "interval": interval, "limit": max(1, min(int(limit), 1500))}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    if end_ms is not None:
        params["endTime"] = int(end_ms)
    rows = _get("/fapi/v1/klines", params, session=session)
    out = [b for b in (parse_kline(k) for k in rows if isinstance(k, list)) if b]
    out.sort(key=lambda b: b["time"])
    return out


def open_interest(symbol, session=None):
    d = _get("/fapi/v1/openInterest", {"symbol": base_symbol(symbol)}, session=session)
    oi = _f(d.get("openInterest")) if isinstance(d, dict) else None
    if oi is None:
        raise FlowError("open interest missing in response")
    return {"time": int(d.get("time") or time.time() * 1000) / 1000.0, "oi": oi}


def open_interest_hist(symbol, period="5m", limit=288, start_ms=None, end_ms=None, session=None):
    """Open-interest history. The exchange only keeps the latest month; max 500 per call."""
    if period not in OI_PERIODS:
        raise FlowError(f"unsupported OI period {period}")
    params = {"symbol": base_symbol(symbol), "period": period, "limit": max(1, min(int(limit), 500))}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    if end_ms is not None:
        params["endTime"] = int(end_ms)
    rows = _get("/futures/data/openInterestHist", params, session=session)
    out = []
    for r in rows if isinstance(rows, list) else []:
        oi, t = _f(r.get("sumOpenInterest")), r.get("timestamp")
        if oi is not None and t is not None:
            out.append({"time": int(t) // 1000, "oi": oi, "oi_value": _f(r.get("sumOpenInterestValue"))})
    out.sort(key=lambda r: r["time"])
    return out


def premium_index(symbol, session=None):
    d = _get("/fapi/v1/premiumIndex", {"symbol": base_symbol(symbol)}, session=session)
    if not isinstance(d, dict) or _f(d.get("markPrice")) is None:
        raise FlowError("premium index missing in response")
    nft = d.get("nextFundingTime")
    return {"time": int(d.get("time") or time.time() * 1000) / 1000.0, "mark": _f(d.get("markPrice")),
            "index": _f(d.get("indexPrice")), "funding_rate": _f(d.get("lastFundingRate")),
            "next_funding_time": int(nft) / 1000.0 if nft else None}


def funding_history(symbol, start_ms=None, end_ms=None, limit=1000, session=None):
    params = {"symbol": base_symbol(symbol), "limit": max(1, min(int(limit), 1000))}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    if end_ms is not None:
        params["endTime"] = int(end_ms)
    rows = _get("/fapi/v1/fundingRate", params, session=session)
    out = []
    for r in rows if isinstance(rows, list) else []:
        rate, t = _f(r.get("fundingRate")), r.get("fundingTime")
        if rate is not None and t is not None:
            out.append({"time": int(t) // 1000, "rate": rate, "mark": _f(r.get("markPrice"))})
    out.sort(key=lambda r: r["time"])
    return out


def depth(symbol, limit=100, session=None):
    limit = next((x for x in DEPTH_LIMITS if x >= int(limit)), 1000)
    book = parse_depth(_get("/fapi/v1/depth", {"symbol": base_symbol(symbol), "limit": limit}, session=session))
    if book is None:
        raise FlowError("empty order book")
    return book


# ----------------------------------------------------------------- features --
def book_imbalance(book, bands=(0.1, 0.25, 0.5, 1.0)):
    """Resting size within +/- band % of mid. imbalance = (bid - ask) / (bid + ask), in [-1, 1]."""
    best_bid, best_ask = book["bids"][0][0], book["asks"][0][0]
    mid = (best_bid + best_ask) / 2
    out = {"mid": mid, "spread_bps": round((best_ask - best_bid) / mid * 1e4, 3), "bands": []}
    lo_seen, hi_seen = book["bids"][-1][0], book["asks"][-1][0]
    for band in bands:
        lo, hi = mid * (1 - band / 100), mid * (1 + band / 100)
        bid = sum(q for p, q in book["bids"] if p >= lo)
        ask = sum(q for p, q in book["asks"] if p <= hi)
        out["bands"].append({"band_pct": band, "bid_qty": round(bid, 6), "ask_qty": round(ask, 6),
                             "imbalance": round((bid - ask) / (bid + ask), 4) if bid + ask > 0 else None,
                             # False when the fetched depth does not reach the band edge on both sides
                             "complete": lo_seen <= lo and hi_seen >= hi})
    return out


def delta_summary(bars, windows=(1, 6, 24)):
    """Real taker delta over the last N CLOSED bars, plus a CVD series for the sparkline."""
    if not bars:
        return {"bars": 0, "windows": [], "cvd": []}
    cvd, run = [], 0.0
    for b in bars:
        run += b["delta"]
        cvd.append(round(run, 6))
    out = {"bars": len(bars), "windows": [], "cvd": cvd[-120:], "last_bar_time": bars[-1]["time"]}
    for n in windows:
        seg = bars[-n:]
        vol = sum(b["volume"] for b in seg)
        dlt = sum(b["delta"] for b in seg)
        move = (seg[-1]["close"] - seg[0]["open"]) / seg[0]["open"] * 100 if seg[0]["open"] else None
        out["windows"].append({"bars": len(seg), "volume": round(vol, 6), "delta": round(dlt, 6),
                               "delta_pct": round(dlt / vol * 100, 2) if vol > 0 else None,
                               "price_change_pct": round(move, 3) if move is not None else None})
    return out


def oi_summary(hist, now_oi=None):
    """OI change over 1h / 4h / 24h from 5m history (percent)."""
    if not hist:
        return {"oi": now_oi, "changes": []}
    last = now_oi if now_oi is not None else hist[-1]["oi"]
    t_last = hist[-1]["time"]
    out = {"oi": last, "changes": []}
    for label, sec in (("1h", 3600), ("4h", 14400), ("24h", 86400)):
        past = next((r for r in reversed(hist) if r["time"] <= t_last - sec), None)
        if past and past["oi"] > 0:
            out["changes"].append({"window": label, "change_pct": round((last - past["oi"]) / past["oi"] * 100, 3)})
    return out


def snapshot(symbol, timeframe="5m", bars=96):
    """Everything the flow panel shows, in one call. Sections fail independently."""
    if timeframe not in TF_SECONDS:
        raise FlowError(f"unsupported timeframe {timeframe}")
    out = {"symbol": base_symbol(symbol), "venue": VENUE, "timeframe": timeframe,
           "generated_at": time.time(), "errors": [], "role": "context_only"}
    step = TF_SECONDS[timeframe]
    try:
        rows = klines(symbol, timeframe, bars + 1)
        closed = [b for b in rows if b["time"] + step <= time.time()]       # never the forming bar
        out["delta"] = delta_summary(closed)
    except FlowError as exc:
        log.warning("flow klines failed: %s", exc)
        out["errors"].append("delta")
    try:
        hist = open_interest_hist(symbol, "5m", 300)
        out["open_interest"] = oi_summary(hist)
    except FlowError as exc:
        log.warning("flow OI failed: %s", exc)
        out["errors"].append("open_interest")
    try:
        p = premium_index(symbol)
        rate = p["funding_rate"]
        out["funding"] = {**p, "rate_pct": round(rate * 100, 4) if rate is not None else None,
                          "basis_bps": round((p["mark"] - p["index"]) / p["index"] * 1e4, 2)
                          if p.get("index") else None}
    except FlowError as exc:
        log.warning("flow funding failed: %s", exc)
        out["errors"].append("funding")
    try:
        out["book"] = book_imbalance(depth(symbol, 500))
    except FlowError as exc:
        log.warning("flow depth failed: %s", exc)
        out["errors"].append("book")
    out["status"] = "ok" if not out["errors"] else "partial" if len(out["errors"]) < 4 else "unavailable"
    return out
