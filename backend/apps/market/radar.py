"""Market radar: what is happening now, and why each coin has or has no signal.

Display only. Nothing here feeds the decision engine. On 12 coins (2021-2026) spike
entries lost after costs, and Fear & Greed / DVOL gave the playbook no consistent
edge. Funding, OI and Polymarket have not been tested as signals. Every source fails
on its own and keeps its last good value, so one dead API never blanks the page.
"""
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from . import futures_flow as ff

log = logging.getLogger("smartpips.market")

HEADERS = {"User-Agent": "market-radar/1.0", "Accept": "application/json"}
DEFAULT_SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "SUI", "BNB", "LTC", "AAVE"]
SPIKE_TFS = ("5m", "15m", "1h")
BOARD_TFS = ("5m", "15m", "1h")
SPIKE_RANGE_ATR = 3.0      # bar range vs the ATR before it
SPIKE_VOLUME_X = 3.0       # bar volume vs the 50-bar average before it
SPIKE_LOOKBACK = 6         # closed bars that still count as "recent"
WICK_SHARE = 0.6
LAST_GOOD_TTL = 6 * 3600


def _json(url, params=None, headers=None, timeout=8):
    r = requests.get(url, params=params or {}, headers={**HEADERS, **(headers or {})}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _cached(key, ttl, loader):
    """Fresh value, else the last good one flagged stale, else an unavailable marker."""
    hit = cache.get(f"radar:{key}")
    if hit is not None:
        return hit
    try:
        value = loader()
        if value is None:
            raise ValueError("empty response")
        value = {**value, "status": value.get("status", "ok"), "as_of": int(time.time())}
        cache.set(f"radar:{key}", value, ttl)
        if value["status"] == "ok":
            cache.set(f"radar:last:{key}", value, LAST_GOOD_TTL)
        return value
    except Exception as exc:
        log.warning("radar source %s failed: %s", key, type(exc).__name__)
        last = cache.get(f"radar:last:{key}")
        value = {**last, "status": "stale"} if last else {"status": "unavailable"}
        cache.set(f"radar:{key}", value, min(ttl, 60))
        return value


# ------------------------------------------------------------- market context
def fear_greed():
    rows = _json("https://api.alternative.me/fng/", {"limit": 8})["data"]
    return {"value": int(rows[0]["value"]), "label": rows[0]["value_classification"],
            "week_ago": int(rows[7]["value"]) if len(rows) > 7 else None}


def dvol():
    now = int(time.time() * 1000)
    rows = _json("https://www.deribit.com/api/v2/public/get_volatility_index_data",
                 {"currency": "BTC", "start_timestamp": now - 181 * 86400000, "end_timestamp": now,
                  "resolution": 86400})["result"]["data"]
    closes = [float(r[4]) for r in sorted(rows, key=lambda r: r[0])]
    if not closes:
        return None
    current = closes[-1]
    return {"value": round(current, 1), "day_change": round(current - closes[-2], 1) if len(closes) > 1 else None,
            "percentile_180d": round(sum(1 for c in closes if c <= current) / len(closes) * 100)}


def global_metrics():
    key = getattr(settings, "CMC_API_KEY", "")
    if key:
        d = _json("https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest",
                  headers={"X-CMC_PRO_API_KEY": key})["data"]
        q = d["quote"]["USD"]
        return {"source": "CoinMarketCap", "total_market_cap": q["total_market_cap"],
                "change_24h_pct": round(q["total_market_cap_yesterday_percentage_change"], 2),
                "btc_dominance": round(d["btc_dominance"], 2), "eth_dominance": round(d["eth_dominance"], 2)}
    d = _json("https://api.coingecko.com/api/v3/global")["data"]
    return {"source": "CoinGecko", "total_market_cap": d["total_market_cap"]["usd"],
            "change_24h_pct": round(d["market_cap_change_percentage_24h_usd"], 2),
            "btc_dominance": round(d["market_cap_percentage"]["btc"], 2),
            "eth_dominance": round(d["market_cap_percentage"]["eth"], 2)}


def parse_polymarket(events, max_events=5, max_markets=3):
    """Only live, still-uncertain questions: 99% / 1% markets tell a trader nothing."""
    out = []
    for e in events if isinstance(events, list) else []:
        title = str(e.get("title") or "")
        if not re.search(r"\b(bitcoin|btc|ethereum|eth|solana|xrp|crypto)\b", title, re.I):
            continue
        markets = []
        for m in e.get("markets") or []:
            if m.get("closed") or not m.get("active", True):
                continue
            try:
                outcomes = json.loads(m.get("outcomes") or "[]")
                prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                yes = prices[outcomes.index("Yes")]
            except (ValueError, TypeError, IndexError):
                continue
            if 0.05 <= yes <= 0.95:
                markets.append({"label": m.get("groupItemTitle") or m.get("question"),
                                "yes_pct": round(yes * 100, 1)})
        if not markets:
            continue
        markets.sort(key=lambda x: abs(x["yes_pct"] - 50))
        out.append({"title": title, "url": f"https://polymarket.com/event/{e.get('slug')}",
                    "volume_24h": float(e.get("volume24hr") or 0), "ends": e.get("endDate"),
                    "markets": markets[:max_markets]})
        if len(out) >= max_events:
            break
    return out


def polymarket():
    events = _json("https://gamma-api.polymarket.com/events",
                   {"tag_slug": "crypto", "closed": "false", "order": "volume24hr",
                    "ascending": "false", "limit": 40}, timeout=10)
    return {"events": parse_polymarket(events)}


def macro():
    key = getattr(settings, "POLYGON_API_KEY", "")
    if not key:
        return {"status": "needs_key", "rows": []}
    rows = []
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=10)  # spans weekends and market holidays
    for ticker in ("SPY", "QQQ"):
        bars = _json(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{today}",
                     {"adjusted": "true", "sort": "asc"},
                     headers={"Authorization": f"Bearer {key}"})["results"]
        last, previous = bars[-1], bars[-2]
        rows.append({"ticker": ticker, "close": last["c"],
                     "date": datetime.fromtimestamp(last["t"] / 1000, timezone.utc).date().isoformat(),
                     "change_pct": round((last["c"] / previous["c"] - 1) * 100, 2)})
    return {"source": "Polygon", "rows": rows}


def market_context():
    jobs = {"fear_greed": (fear_greed, 900), "dvol": (dvol, 600), "global": (global_metrics, 300),
            "polymarket": (polymarket, 180), "macro": (macro, 1800)}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {k: pool.submit(_cached, k, ttl, fn) for k, (fn, ttl) in jobs.items()}
    return {k: f.result() for k, f in futures.items()}


# ------------------------------------------------------------------- spikes
def find_spike(bars, timeframe, now=None):
    """Newest large-range, high-volume bar among the last closed bars, or None."""
    step = {"5m": 300, "15m": 900, "1h": 3600}[timeframe]
    now = now or time.time()
    closed = [b for b in bars if b["time"] + step <= now]
    if len(closed) < 66 or now - (closed[-1]["time"] + step) > 3 * step:
        return None  # too short, or a dead/delisted feed
    atr, prev_close, atrs = None, None, []
    for b in closed:
        tr = b["high"] - b["low"] if prev_close is None else max(
            b["high"] - b["low"], abs(b["high"] - prev_close), abs(b["low"] - prev_close))
        atr = tr if atr is None else tr / 14 + atr * 13 / 14
        atrs.append(atr)
        prev_close = b["close"]
    for i in range(len(closed) - 1, len(closed) - 1 - SPIKE_LOOKBACK, -1):
        b = closed[i]
        vols = [x["volume"] for x in closed[i - 50:i]]
        avg = sum(vols) / len(vols) if vols else 0
        rng = b["high"] - b["low"]
        if not avg or not atrs[i - 1] or rng <= 0:
            continue
        range_x, volume_x = rng / atrs[i - 1], b["volume"] / avg
        if range_x < SPIKE_RANGE_ATR or volume_x < SPIKE_VOLUME_X:
            continue
        lower = (min(b["open"], b["close"]) - b["low"]) / rng
        upper = (b["high"] - max(b["open"], b["close"])) / rng
        kind = ("wick_down" if lower >= WICK_SHARE else "wick_up" if upper >= WICK_SHARE
                else "impulse_up" if b["close"] >= b["open"] else "impulse_down")
        return {"timeframe": timeframe, "kind": kind, "range_atr": round(range_x, 1),
                "volume_x": round(volume_x, 1), "move_pct": round((b["close"] / b["open"] - 1) * 100, 2),
                "minutes_ago": max(0, int((now - (b["time"] + step)) / 60))}
    return None


def _coin_spikes(base):
    found = []
    for tf in SPIKE_TFS:
        try:
            spike = find_spike(ff.klines(base, tf, limit=90), tf)
        except ff.FlowError:
            continue
        if spike:
            found.append(spike)
    return found


def _oi_change(base):
    try:
        hist = ff.open_interest_hist(base, "1h", limit=25)
    except ff.FlowError:
        return None
    if len(hist) < 2 or not hist[0]["oi"]:
        return None
    return round((hist[-1]["oi"] / hist[0]["oi"] - 1) * 100, 1)


def _load_tape(bases):
    tickers = {t["symbol"]: t for t in ff._get("/fapi/v1/ticker/24hr")}
    premium = {p["symbol"]: p for p in ff._get("/fapi/v1/premiumIndex")}
    with ThreadPoolExecutor(max_workers=6) as pool:
        spikes = list(pool.map(_coin_spikes, bases))
        oi = list(pool.map(_oi_change, bases))
    rows = {}
    for base, sp, oi_pct in zip(bases, spikes, oi):
        t, p = tickers.get(base) or {}, premium.get(base) or {}
        funding = ff._f(p.get("lastFundingRate"))
        rows[base] = {"price": ff._f(t.get("lastPrice")), "change_24h_pct": ff._f(t.get("priceChangePercent")),
                      "quote_volume_24h": ff._f(t.get("quoteVolume")),
                      "funding_pct": round(funding * 100, 4) if funding is not None else None,
                      "oi_change_24h_pct": oi_pct, "spikes": sp}
    return {"rows": rows}


# ----------------------------------------------------------- playbook board
WAIT_PATTERNS = (
    ("no_trend", r"4h has no clear trend"),
    ("h1_conflict", r"1h trend does not agree"),
    ("not_stacked", r"not stacked"),
    ("no_push", r"price is only"),
    ("stop_too_small", r"stop is .* below"),
    ("stale", r"stale"),
    ("news", r"news"),
    ("muted", r"^muted"),
    ("low_score", r"below your minimum"),
)


def classify_wait(reason):
    for code, pattern in WAIT_PATTERNS:
        if re.search(pattern, reason or "", re.I):
            return code
    return "other"


def playbook_board(user, symbols):
    from apps.alerts.models import UserSignalState
    states = UserSignalState.objects.filter(user=user, symbol__in=symbols, timeframe__in=BOARD_TFS)
    board = {}
    for s in states:
        active = s.last_signal in ("buy", "sell")
        board.setdefault(s.symbol, {})[s.timeframe] = {
            "signal": s.last_signal if active else "wait",
            "code": None if active else classify_wait(s.last_reason),
            "checked": s.last_checked.isoformat() if s.last_checked else None}
    return board


def user_symbols(user):
    from apps.alerts.models import WatchItem
    from .crypto_symbols import SUPPORTED_CRYPTO
    watched = WatchItem.objects.filter(user=user, active=True, symbol__endswith=":PERP").values_list("symbol", flat=True)
    symbols = sorted(s for s in watched if ff.base_symbol(s) in SUPPORTED_CRYPTO)
    return symbols or [f"{b}USDT:PERP" for b in DEFAULT_SYMBOLS]


def snapshot(user):
    symbols = user_symbols(user)
    bases = sorted({ff.base_symbol(s) for s in symbols})
    tape = _cached("tape:" + ",".join(bases), 60, lambda: _load_tape(bases))
    board = playbook_board(user, symbols)
    rows = [{"symbol": s, "base": ff.base_symbol(s).replace("USDT", ""),
             **((tape.get("rows") or {}).get(ff.base_symbol(s)) or {}),
             "playbook": board.get(s, {})} for s in symbols]
    # Coins with a live setup first, then recent spikes, then by traded value.
    rows.sort(key=lambda r: (not any(v["signal"] != "wait" for v in r["playbook"].values()),
                             not r.get("spikes"), -(r.get("quote_volume_24h") or 0)))
    return {"context": market_context(), "tape_status": tape.get("status"), "as_of": tape.get("as_of"),
            "coins": rows, "display_only": True}
