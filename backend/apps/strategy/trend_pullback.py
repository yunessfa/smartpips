"""Trend-pullback playbook — the validated SmartPips setup.

Two variants share one function (`setup_at`):

  "trend" (default, trend-pullback-v2), 5m / 15m / 1h:
    1. 4h trend from PRICE: the last CLOSED 4h bar closed above the middle of
       the 4h high-low range of the last 50 bars (below it for shorts).
    2. Local trend on the trading timeframe: EMA21 > EMA50 > EMA200.
    3. Price is stretched more than 1 ATR from EMA21 -> a LIMIT order waits
       at EMA21 (the pullback), valid 12 bars. We never chase.
  "price" (price-pullback-v1, no moving averages), 1h only:
    2. Local trend: middle of the last 20 bars' high-low range above the
       middle of the last 100 bars' range.
    3. Price stretched more than 1 ATR from that 20-bar middle -> LIMIT there.

  Both: stop 1.5 ATR, skipped when that is under 0.4% of price (fees). One
  target: 3R on 1h, 2.5R on 5m/15m; close at market after 72 bars. The "trend"
  variant moves the 1h stop to breakeven after a bar closes 1R in profit.

v1 also required a 4h EMA50/EMA200 trend and, on 5m/15m, 1h agreement. On 12
coins (2021-2026) the price-range trend gave the same expectancy with ~40% more
setups, and the 1h filter added nothing. Evidence: RESEARCH / PRICE_RESEARCH.
Past results do not guarantee future results.
"""
import math

NAME = "trend_pullback"
VERSION = "trend-pullback-v2"
PRICE_NAME = "price_pullback"
PRICE_VERSION = "price-pullback-v1"
PRICE_TIMEFRAMES = ("1h",)
VARIANTS = ("trend", "price")
TIMEFRAMES = ("5m", "15m", "1h")
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}

STRETCH_ATR = 1.0          # close must be > 1 ATR from EMA21 to arm a pullback limit
STOP_ATR = 1.5
MIN_STOP_PCT = 0.40        # skip the setup when 1.5 ATR < 0.4% of price (fees vs risk)
LIMIT_VALID_BARS = 12
MAX_HOLD_BARS = 72
TARGET_R = {"5m": 2.5, "15m": 2.5, "1h": 3.0}
NEEDS_1H = {"5m": False, "15m": False, "1h": False}  # v1 needed 1h agreement; it added nothing on 12 coins
HTF_RANGE_BARS = 50       # 4h trend = close vs the middle of this many bars' high-low range
PRICE_FAST, PRICE_SLOW = 20, 100
# Once a bar CLOSES this many R in profit the stop moves to entry + BREAKEVEN_LOCK_R.
# 1h only: on 12 coins it kept expectancy and cut the portfolio drawdown by a quarter.
# On 15m it did not help, and 5m was not tested, so those keep the plain exit.
BREAKEVEN_R = {"1h": 1.0}  # "trend" variant only; it lowered expectancy on the price variant
BREAKEVEN_LOCK_R = 0.1
MIN_BARS = 400             # EMA200 warm-up on the trading timeframe
MIN_HTF_BARS = 250         # EMA200 warm-up on 4h / 1h
LIVE_FETCH_BARS = 600      # what decide() requests so the EMAs are converged
COSTS = {"taker": 0.0006, "maker": 0.0002, "slippage": 0.0002}

# Multi-year research results (R per trade, net of costs). Kept with the code
# so the UI can show the evidence the parameters were chosen on.
RESEARCH = {
    "version": VERSION,
    "data": "Binance USD-M 5m, 12 coins (BTC ETH SOL XRP DOGE ADA AVAX LINK SUI BNB LTC AAVE), 2021-01 .. 2026-10, resampled",
    "costs": ("limit entry maker 0.02%; stop AND target exit as market: taker 0.06% + slippage 0.02%; "
              "funding 0.01% per 8h held"),
    "periods": {"train": "2021-2023", "validation": "2024", "holdout": "2025-2026"},
    "results": {
    "1h": {
        "trades_per_year": 155,
        "win_rate_pct": 48.9,
        "expectancy_r": {
            "train": 0.282,
            "validation": 0.219,
            "holdout": 0.185
        },
        "profit_factor": {
            "train": 1.6,
            "validation": 1.44,
            "holdout": 1.36
        },
        "r_by_year": {
            "2021": 39.1,
            "2022": 45.4,
            "2023": 39.1,
            "2024": 34.9,
            "2025": 29.9,
            "2026": 25.4
        },
        "positive_years": "6/6",
        "positive_months_pct": 89,
        "max_drawdown_r": -67.0,
        "expectancy_95ci": [
            0.208,
            0.268
        ],
        "per": "coin-year (12 coins); drawdown is for all 12 coins together"
    },
    "15m": {
        "trades_per_year": 472,
        "win_rate_pct": 39.0,
        "expectancy_r": {
            "train": 0.212,
            "validation": 0.22,
            "holdout": 0.193
        },
        "profit_factor": {
            "train": 1.32,
            "validation": 1.33,
            "holdout": 1.28
        },
        "r_by_year": {
            "2021": 133.9,
            "2022": 100.3,
            "2023": 54.5,
            "2024": 110.0,
            "2025": 91.6,
            "2026": 78.3
        },
        "positive_years": "6/6",
        "positive_months_pct": 89,
        "max_drawdown_r": -161.3,
        "expectancy_95ci": [
            0.189,
            0.225
        ],
        "per": "coin-year (12 coins); drawdown is for all 12 coins together"
    },
    "5m": {
        "trades_per_year": 836,
        "win_rate_pct": 38.4,
        "expectancy_r": {
            "train": 0.155,
            "validation": 0.132,
            "holdout": 0.129
        },
        "profit_factor": {
            "train": 1.22,
            "validation": 1.19,
            "holdout": 1.18
        },
        "r_by_year": {
            "2021": 226.4,
            "2022": 129.3,
            "2023": 46.2,
            "2024": 114.8,
            "2025": 129.1,
            "2026": 50.5
        },
        "positive_years": "6/6",
        "positive_months_pct": 84,
        "max_drawdown_r": -183.6,
        "expectancy_95ci": [
            0.13,
            0.157
        ],
        "per": "coin-year (12 coins); drawdown is for all 12 coins together"
    }
},
    "stress": {"double_costs_expectancy_r": {"1h": 0.176, "15m": 0.093, "5m": -0.012}},
    "caveats": [
        "Trades per year are per coin; the drawdown is for all 12 coins traded together at 1R each.",
        "5m loses its edge if your real costs are about double the assumed ones; 15m keeps about half.",
        "Limit entries assume a fill on touch; requiring a 0.02% trade-through lowers expectancy 10-20%.",
        "The 12 coins are ones that survived to 2026, which flatters any multi-coin result.",
        "The 1h-filter and breakeven choices were read on all periods, so the holdout is not clean for them.",
        "Past results do not guarantee future results.",
    ],
}

RESEARCH_V1_EMA_TREND = {
    "data": "BTC/USD Bitstamp 1m, 2019-01-01 .. 2026-10-27 (resampled); no other symbol available offline",
    "costs": ("limit entry maker 0.02%; stop AND target exit as market: taker 0.06% + slippage 0.02%; "
              "funding 0.01% per 8h held"),
    "periods": {"train": "2019-2022", "validation": "2023-2024", "holdout": "2025-2026"},
    "results": {
        "1h": {"trades_per_year": 108, "win_rate_pct": 36.7,
               "expectancy_r": {"train": 0.345, "validation": 0.138, "holdout": 0.265},
               "profit_factor": {"train": 1.51, "validation": 1.19, "holdout": 1.37},
               "r_by_year": {"2019": 64.9, "2020": 47.4, "2021": 21.2, "2022": 18.6, "2023": 24.4,
                             "2024": 4.9, "2025": 32.8, "2026": 17.2},
               "positive_years": "8/8", "positive_months_pct": 65, "max_drawdown_r": -26.2,
               "monte_carlo_drawdown_r_p95": -35.6, "expectancy_95ci": [0.15, 0.40]},
        "15m": {"trades_per_year": 261, "win_rate_pct": 38.6,
                "expectancy_r": {"train": 0.167, "validation": 0.118, "holdout": 0.148},
                "profit_factor": {"train": 1.24, "validation": 1.17, "holdout": 1.21},
                "r_by_year": {"2019": 48.7, "2020": 69.8, "2021": 72.0, "2022": 19.5, "2023": 29.6,
                              "2024": 20.1, "2025": 19.1, "2026": 34.6},
                "positive_years": "8/8", "positive_months_pct": 61, "max_drawdown_r": -26.2,
                "monte_carlo_drawdown_r_p95": -54.5, "expectancy_95ci": [0.082, 0.226]},
        "5m": {"trades_per_year": 284, "win_rate_pct": 41.3,
               "expectancy_r": {"train": 0.182, "validation": 0.097, "holdout": 0.334},
               "profit_factor": {"train": 1.27, "validation": 1.14, "holdout": 1.53},
               "r_by_year": {"2019": 69.0, "2020": 103.1, "2021": 98.4, "2022": 25.5, "2023": 11.9,
                             "2024": 18.5, "2025": 58.2, "2026": 25.8},
               "positive_years": "8/8", "positive_months_pct": 64, "max_drawdown_r": -23.5,
               "monte_carlo_drawdown_r_p95": -47.9, "expectancy_95ci": [0.118, 0.256]},
        "5m_without_min_stop_filter": {"expectancy_r": {"train": 0.068, "validation": -0.15, "holdout": -0.167},
                                       "positive_years": "3/8"},
    },
    "stress": {
        "limit_must_trade_through_0.02pct": {"1h": 0.25, "15m": 0.123, "5m": 0.26},
        "double_costs_holdout_expectancy_r": {"1h": 0.193, "15m": 0.047, "5m": 0.238},
        "parameter_neighbourhood_1h": "107 of 108 nearby parameter sets positive in train, validation and holdout",
    },
    # Same rules, no re-tuning, on Binance USD-M 5m data 2021-01 .. 2026-10.
    "multi_symbol": {
        "symbols": ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "SUI", "BNB", "LTC", "AAVE"],
        "periods": {"train": "2021-2023", "validation": "2024", "holdout": "2025-2026"},
        "expectancy_r": {"1h": {"train": 0.303, "validation": 0.178, "holdout": 0.200},
                         "15m": {"train": 0.224, "validation": 0.201, "holdout": 0.203},
                         "5m": {"train": 0.173, "validation": 0.134, "holdout": 0.147}},
        "win_rate_pct": {"1h": 35.2, "15m": 39.1, "5m": 38.8},
        "with_1h_breakeven": {"win_rate_pct": 49.3, "expectancy_r": 0.249, "portfolio_max_drawdown_r": -48.6,
                              "without_breakeven_max_drawdown_r": -64.7, "wins_below_0_3r_pct": 48},
    },
    "caveats": [
        "5m/15m edge mostly disappears if your real costs are about double the assumed ones.",
        "Limit entries assume a fill on touch; requiring a 0.02% trade-through lowers expectancy 10-20%.",
        "Coins move together: 12 symbols had a -13R worst day, so size each trade for that.",
        "The 12 coins are ones that survived to 2026, which flatters any multi-coin result.",
        "Past results do not guarantee future results.",
    ],
}

PRICE_RESEARCH = {
    "version": PRICE_VERSION,
    "data": RESEARCH["data"], "costs": RESEARCH["costs"], "periods": RESEARCH["periods"],
    "results": {
    "1h": {
        "trades_per_year": 159,
        "win_rate_pct": 33.6,
        "expectancy_r": {
            "train": 0.209,
            "validation": 0.245,
            "holdout": 0.139
        },
        "profit_factor": {
            "train": 1.3,
            "validation": 1.35,
            "holdout": 1.19
        },
        "r_by_year": {
            "2021": 35.5,
            "2022": 28.7,
            "2023": 29.4,
            "2024": 40.6,
            "2025": 35.0,
            "2026": 7.9
        },
        "positive_years": "6/6",
        "positive_months_pct": 79,
        "max_drawdown_r": -89.5,
        "expectancy_95ci": [
            0.158,
            0.226
        ],
        "per": "coin-year (12 coins); drawdown is for all 12 coins together"
    }
},
    "stress": {"double_costs_expectancy_r": {"1h": 0.130}},
    "caveats": [
        "No moving averages. About 22% less profit per trade than the default variant on the same data.",
        "On 15m this variant nearly vanished with double costs, so it is offered on 1h only.",
        "Trades per year are per coin; the drawdown is for all 12 coins traded together at 1R each.",
        "Past results do not guarantee future results.",
    ],
}



# ----------------------------------------------------------------- indicators
def ema_series(values, period):
    """pandas ewm(span=period, adjust=False) seeded with the first value."""
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(float(v) * k + out[-1] * (1 - k))
    return out


def atr_series(candles, period=14):
    """Wilder ATR (ewm alpha=1/period, adjust=False); first TR = high-low."""
    out = []
    prev_close = None
    a = None
    alpha = 1.0 / period
    for c in candles:
        h, l = float(c["high"]), float(c["low"])
        tr = h - l if prev_close is None else max(h - l, abs(h - prev_close), abs(l - prev_close))
        a = tr if a is None else tr * alpha + a * (1 - alpha)
        out.append(a)
        prev_close = float(c["close"])
    return out


def indicators(candles):
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    return {"time": [c.get("time") for c in candles], "close": closes,
            "e21": ema_series(closes, 21), "e50": ema_series(closes, 50),
            "e200": ema_series(closes, 200), "atr": atr_series(candles),
            "mid20": range_mid_series(highs, lows, PRICE_FAST),
            "mid50": range_mid_series(highs, lows, HTF_RANGE_BARS),
            "mid100": range_mid_series(highs, lows, PRICE_SLOW)}


def range_mid_series(highs, lows, n):
    """Middle of the high-low range of the last n bars (None until n bars exist)."""
    from collections import deque
    out, qh, ql = [], deque(), deque()
    for i, (h, l) in enumerate(zip(highs, lows)):
        while qh and highs[qh[-1]] <= h:
            qh.pop()
        while ql and lows[ql[-1]] >= l:
            ql.pop()
        qh.append(i); ql.append(i)
        if qh[0] <= i - n:
            qh.popleft()
        if ql[0] <= i - n:
            ql.popleft()
        out.append((highs[qh[0]] + lows[ql[0]]) / 2 if i + 1 >= n else None)
    return out


class HTFView:
    """Closed-bar view of a higher-timeframe series (no look-ahead).

    `at(decision_close_time)` returns the index of the newest HTF bar whose
    close time (time + step) is <= the moment the trading bar closed.
    """

    def __init__(self, candles, step):
        self.step = step
        self.ind = indicators(candles) if candles else None
        self.times = [float(c["time"]) for c in candles] if candles else []

    def at(self, close_time):
        if not self.times:
            return None
        lo, hi = 0, len(self.times) - 1
        if self.times[0] + self.step > close_time:
            return None
        while lo < hi:  # last index with time + step <= close_time
            mid = (lo + hi + 1) // 2
            if self.times[mid] + self.step <= close_time:
                lo = mid
            else:
                hi = mid - 1
        return lo


def _htf_trend(view, close_time, kind):
    """+1 / -1 / 0 trend on the HTF bar that was closed at `close_time`."""
    if view is None or view.ind is None:
        return None, "missing"
    j = view.at(close_time)
    ind = view.ind
    if kind == "4h":
        # Price-only trend: close vs the middle of the last 50 bars' high-low range.
        if j is None or j + 1 < HTF_RANGE_BARS or ind["mid50"][j] is None:
            return None, "insufficient"
        c, mid = ind["close"][j], ind["mid50"][j]
        return (1 if c > mid else -1 if c < mid else 0), "ok"
    if j is None or j + 1 < MIN_HTF_BARS:
        return None, "insufficient"
    c, e21, e50, e200 = ind["close"][j], ind["e21"][j], ind["e50"][j], ind["e200"][j]
    if e21 > e50 and c > e200:
        return 1, "ok"
    if e21 < e50 and c < e200:
        return -1, "ok"
    return 0, "ok"


# ------------------------------------------------------------------- decision
def setup_at(i, ind, timeframe, h4_view, h1_view=None, symbol="BTCUSDT", variant="trend"):
    """Evaluate the playbook on CLOSED bar i. Returns a dict with `signal`.

    Pure and deterministic: the live engine calls it for the newest closed bar,
    the backtester for every bar of a long history (indicators computed once).
    """
    step = TF_SECONDS[timeframe]
    checks = {}
    waits = []

    def wait(code, message):
        waits.append({"code": code, "message": message})

    allowed = PRICE_TIMEFRAMES if variant == "price" else TIMEFRAMES
    if timeframe not in allowed:
        name = "price-action pullback" if variant == "price" else "trend pullback"
        wait("playbook_timeframe", f"{name} is validated on {', '.join(allowed)} only")
        return {"signal": "wait", "checks": checks, "wait_reasons": waits}
    if i + 1 < MIN_BARS:
        wait("insufficient_history", f"needs {MIN_BARS} closed {timeframe} bars for EMA200 (have {i + 1})")
        return {"signal": "wait", "checks": checks, "wait_reasons": waits}

    close, e21, e50, e200, a = (ind["close"][i], ind["e21"][i], ind["e50"][i], ind["e200"][i], ind["atr"][i])
    t = ind["time"][i]
    if t is None or not a or a <= 0 or not close:
        wait("insufficient_data", "bar time/ATR unavailable")
        return {"signal": "wait", "checks": checks, "wait_reasons": waits}
    close_time = float(t) + step

    h4, h4_state = _htf_trend(h4_view, close_time, "4h")
    checks["h4_trend"] = h4
    if h4 is None:
        wait("htf_unavailable", f"4h trend unavailable ({h4_state}) — no signal without it")
        return {"signal": "wait", "checks": checks, "wait_reasons": waits}
    direction = h4
    if direction == 0:
        wait("htf_no_trend", "4h has no clear trend (close is at the middle of its 50-bar range)")
    h1 = None
    if NEEDS_1H.get(timeframe):
        h1, h1_state = _htf_trend(h1_view, close_time, "1h")
        checks["h1_trend"] = h1
        if h1 is None:
            wait("htf_unavailable", f"1h trend unavailable ({h1_state})")
            return {"signal": "wait", "checks": checks, "wait_reasons": waits}
        if direction and h1 != direction:
            wait("h1_conflict", "1h trend does not agree with 4h")
            direction = 0

    if variant == "price":
        fast, slow = ind["mid20"][i], ind["mid100"][i]
        if fast is None or slow is None:
            wait("insufficient_history", f"needs {PRICE_SLOW} closed {timeframe} bars for the price ranges")
            return {"signal": "wait", "checks": checks, "wait_reasons": waits}
        local = 1 if fast > slow else -1 if fast < slow else 0
        anchor, anchor_name = fast, "the 20-bar range middle"
        stack_msg = f"{timeframe} 20-bar and 100-bar range middles are not stacked with the 4h trend"
    else:
        local = 1 if (e21 > e50 > e200) else -1 if (e21 < e50 < e200) else 0
        anchor, anchor_name = e21, "EMA21"
        stack_msg = f"{timeframe} EMAs (21/50/200) are not stacked with the 4h trend"
    checks["local_trend"] = local
    if direction and local != direction:
        wait("local_trend_conflict", stack_msg)
        direction = 0

    stretch = (close - anchor) / a
    checks["stretch_atr"] = round(stretch, 2)
    if direction and stretch * direction <= STRETCH_ATR:
        wait("no_pullback_setup", f"price is only {stretch * direction:.2f} ATR from {anchor_name} — "
                                  f"wait for a > {STRETCH_ATR} ATR push, then buy the pullback")
        direction = 0

    stop_dist = STOP_ATR * a
    stop_pct = stop_dist / close * 100
    checks["stop_pct"] = round(stop_pct, 3)
    if stop_pct < MIN_STOP_PCT:
        wait("stop_below_cost_floor", f"1.5 ATR stop is {stop_pct:.2f}% — below {MIN_STOP_PCT}%; "
                                      "fees would eat the edge on this volatility")
        direction = 0

    if not direction:
        return {"signal": "wait", "checks": checks, "wait_reasons": waits}

    entry = anchor
    target_r = TARGET_R[timeframe]
    stop = entry - direction * stop_dist
    target = entry + direction * stop_dist * target_r
    cost_win = entry * (COSTS["maker"] * 2)                       # limit in, TP limit out
    cost_loss = entry * (COSTS["maker"] + COSTS["taker"] + COSTS["slippage"])
    net_rr = (stop_dist * target_r - cost_win) / (stop_dist + cost_loss)
    return {
        "signal": "buy" if direction > 0 else "sell",
        "direction": direction, "entry": entry, "stop": stop, "target": target,
        "stop_dist": stop_dist, "stop_pct": stop_pct, "target_r": target_r, "net_rr": net_rr,
        "atr": a, "close": close, "checks": checks, "wait_reasons": [],
        "bar_time": t, "breakeven_r": BREAKEVEN_R.get(timeframe) if variant == "trend" else None,
        "anchor_name": anchor_name,
    }


def _digits(symbol, price):
    base = symbol.upper().replace(":PERP", "")
    if base == "XAUUSD":
        return 2
    if base == "XAGUSD":
        return 3
    return max(2, min(12, 6 - math.floor(math.log10(price)))) if price > 0 else 6


def apply(decision, symbol, timeframe, tf_candles, htf_candles, variant="trend"):
    """Overlay the playbook verdict on an engine decision dict (live path).

    `decision` keeps the engine's readings (indicators, rule_features, volume
    profile …) for display; signal, levels and wait reasons come only from
    the playbook. `htf_candles` = {"4h": [...], "1h": [...]} CLOSED bars.
    """
    symbol = symbol.upper()
    base = symbol.replace(":PERP", "")
    decision["signal_source"] = "playbook"
    price = variant == "price"
    decision["playbook"] = {"name": PRICE_NAME if price else NAME, "version": PRICE_VERSION if price else VERSION,
                            "variant": variant, "timeframes": list(PRICE_TIMEFRAMES if price else TIMEFRAMES)}
    label = "Price-action pullback" if price else "Trend pullback"
    decision["base_engine_signal"] = decision.get("signal")
    cleared = dict(entry=None, stop_loss=None, take_profit=None, tp_levels=None, entry_plan=None,
                   exit_plan=None, risk_reward=None, net_risk_reward=None, stop_pct=None,
                   est_round_trip_cost_pct=None, tp_source=None, grade=None)
    if base in ("XAUUSD", "XAGUSD"):
        decision.update(signal="wait", confidence="low", score=0, **cleared,
                        reason="Trend pullback playbook is validated on crypto only.",
                        wait_reasons=[{"code": "playbook_market", "message": "not validated on metals"}])
        return decision
    if not tf_candles:
        decision.update(signal="wait", confidence="low", score=0, **cleared,
                        reason="No candles.", wait_reasons=[{"code": "insufficient_data", "message": "no candles"}])
        return decision
    ind = indicators(tf_candles)
    h4_view = HTFView((htf_candles or {}).get("4h") or [], TF_SECONDS["4h"])
    h1_view = HTFView((htf_candles or {}).get("1h") or [], TF_SECONDS["1h"]) if NEEDS_1H.get(timeframe) else None
    s = setup_at(len(tf_candles) - 1, ind, timeframe, h4_view, h1_view, symbol, variant)
    decision["playbook"]["checks"] = s.get("checks")
    if s["signal"] not in ("buy", "sell"):
        first = (s["wait_reasons"] or [{"message": "conditions not met"}])[0]["message"]
        decision.update(signal="wait", confidence="low", score=0, **cleared,
                        reason=f"{label}: {first}", wait_reasons=s["wait_reasons"])
        return decision
    d = _digits(symbol, s["entry"])
    rnd = lambda x: round(float(x), d)
    step_min = TF_SECONDS[timeframe] // 60
    tp_r = s["target_r"]
    breakeven = None
    if s.get("breakeven_r"):
        trigger_r = BREAKEVEN_R[timeframe]
        breakeven = {"trigger_r": trigger_r, "lock_r": BREAKEVEN_LOCK_R,
                     "trigger_price": rnd(s["entry"] + s["direction"] * s["stop_dist"] * trigger_r),
                     "stop_price": rnd(s["entry"] + s["direction"] * s["stop_dist"] * BREAKEVEN_LOCK_R),
                     "note": "manual: after a bar closes past the trigger, move the stop to stop_price"}
    decision.update(
        signal=s["signal"], confidence="high", score=80, grade="A",
        entry=rnd(s["entry"]), stop_loss=rnd(s["stop"]), take_profit=rnd(s["target"]),
        risk_reward=tp_r, net_risk_reward=round(s["net_rr"], 2), stop_pct=round(s["stop_pct"], 3),
        est_round_trip_cost_pct=round((COSTS["maker"] + COSTS["taker"] + COSTS["slippage"]) * 100, 3),
        tp_source="r_multiple",
        # Single validated target. The ladder below only splits the SAME exit
        # for display: everything closes at the playbook target.
        tp_levels=[{"price": rnd(s["target"]), "pct": 100, "r": tp_r}],
        entry_plan={"type": "limit", "price": rnd(s["entry"]), "expiry_bars": LIMIT_VALID_BARS,
                    "valid_for_bars": LIMIT_VALID_BARS, "valid_for_minutes": LIMIT_VALID_BARS * step_min,
                    "reason": (f"price pushed {abs(s['checks']['stretch_atr']):.1f} ATR away from {s['anchor_name']} in the "
                               f"trend direction — buy the pullback at {s['anchor_name']}, never chase"),
                    "stretch_ema21_atr": s["checks"]["stretch_atr"]},
        exit_plan={"type": "fixed_target", "target_r": tp_r, "stop_atr": STOP_ATR,
                   "max_hold_bars": MAX_HOLD_BARS, "max_hold_minutes": MAX_HOLD_BARS * step_min,
                   "breakeven": breakeven,
                   "note": "close at market if neither stop nor target is hit within the time limit"},
        reason=(f"{label} ({timeframe}): 4h trend {'up' if s['direction'] > 0 else 'down'}, "
                f"{'range middles' if price else 'EMAs'} stacked, LIMIT at {s['anchor_name']}, "
                f"stop {STOP_ATR} ATR ({s['stop_pct']:.2f}%), target {tp_r}R."),
        wait_reasons=[],
    )
    decision["playbook"]["evidence"] = (PRICE_RESEARCH if price else RESEARCH)["results"].get(timeframe)
    return decision


def series_decider(candles, timeframe, htf_candles, symbol="BTCUSDT", variant="trend"):
    """Backtest helper: indicators once, then a cheap per-bar decision."""
    ind = indicators(candles)
    h4_view = HTFView((htf_candles or {}).get("4h") or [], TF_SECONDS["4h"])
    h1_view = HTFView((htf_candles or {}).get("1h") or [], TF_SECONDS["1h"]) if NEEDS_1H.get(timeframe) else None

    def decide_at(i):
        return setup_at(i, ind, timeframe, h4_view, h1_view, symbol, variant)
    return decide_at


def research_for(variant="trend"):
    return PRICE_RESEARCH if variant == "price" else RESEARCH


def variant_for(mode=None, version=None):
    """'price' when asked for explicitly or when the active playbook strategy is the price one."""
    if mode == "price":
        return "price"
    risk = getattr(version, "risk", None) or {}
    return "price" if risk.get("playbook") == PRICE_NAME else "trend"
