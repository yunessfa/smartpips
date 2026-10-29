"""Trend-pullback playbook — the validated SmartPips setup (2026-10 research).

What it does (identical on 5m / 15m / 1h, only the target differs):

  1. Higher-timeframe trend: last CLOSED 4h bar has close > EMA200 and
     EMA50 > EMA200 (mirror for shorts). On 5m/15m the last closed 1h bar
     must agree too (EMA21 > EMA50 and close > EMA200).
  2. Local trend on the trading timeframe: EMA21 > EMA50 > EMA200.
  3. Price is stretched: close is more than 1 ATR above EMA21. We do NOT buy
     there — a LIMIT order waits at EMA21 (the pullback), valid 12 bars.
  4. Stop 1.5 ATR from the entry. If that stop is smaller than 0.4% of price
     the setup is skipped: round-trip fees + slippage (~0.1%) would eat a
     quarter of the risk unit. This single filter is the difference between a
     losing and a winning 5m scalp in the research.
  5. One fixed target: 3R on 1h, 2.5R on 5m/15m. Positions still open after
     72 bars are closed at market.

Evidence (BTC/USD 1-minute Bitstamp archive 2019-01 .. 2026-10, resampled;
taker 0.06%, maker 0.02%, slippage 0.02%, funding 0.01%/8h, stop-first on
ambiguous bars, limit fills on touch). Parameters were fixed on 2019-2022 and
then checked untouched on 2023-2024 and 2025-2026 — see RESEARCH below.
Past results do not guarantee future results; only BTC was available.
"""
import math

NAME = "trend_pullback"
VERSION = "trend-pullback-v1"
TIMEFRAMES = ("5m", "15m", "1h")
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}

STRETCH_ATR = 1.0          # close must be > 1 ATR from EMA21 to arm a pullback limit
STOP_ATR = 1.5
MIN_STOP_PCT = 0.40        # skip the setup when 1.5 ATR < 0.4% of price (fees vs risk)
LIMIT_VALID_BARS = 12
MAX_HOLD_BARS = 72
TARGET_R = {"5m": 2.5, "15m": 2.5, "1h": 3.0}
NEEDS_1H = {"5m": True, "15m": True, "1h": False}
MIN_BARS = 400             # EMA200 warm-up on the trading timeframe
MIN_HTF_BARS = 250         # EMA200 warm-up on 4h / 1h
LIVE_FETCH_BARS = 600      # what decide() requests so the EMAs are converged
COSTS = {"taker": 0.0006, "maker": 0.0002, "slippage": 0.0002}

# Multi-year research results (R per trade, net of costs). Kept with the code
# so the UI can show the evidence the parameters were chosen on.
RESEARCH = {
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
    "caveats": [
        "5m/15m edge mostly disappears if your real costs are about double the assumed ones.",
        "Limit entries assume a fill on touch; requiring a 0.02% trade-through lowers expectancy 10-20%.",
        "Only BTC was tested over multiple years; other symbols are untested.",
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
    return {"time": [c.get("time") for c in candles], "close": closes,
            "e21": ema_series(closes, 21), "e50": ema_series(closes, 50),
            "e200": ema_series(closes, 200), "atr": atr_series(candles)}


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
    if j is None or j + 1 < MIN_HTF_BARS:
        return None, "insufficient"
    ind = view.ind
    c, e21, e50, e200 = ind["close"][j], ind["e21"][j], ind["e50"][j], ind["e200"][j]
    if kind == "4h":
        if c > e200 and e50 > e200:
            return 1, "ok"
        if c < e200 and e50 < e200:
            return -1, "ok"
        return 0, "ok"
    if e21 > e50 and c > e200:
        return 1, "ok"
    if e21 < e50 and c < e200:
        return -1, "ok"
    return 0, "ok"


# ------------------------------------------------------------------- decision
def setup_at(i, ind, timeframe, h4_view, h1_view=None, symbol="BTCUSDT"):
    """Evaluate the playbook on CLOSED bar i. Returns a dict with `signal`.

    Pure and deterministic: the live engine calls it for the newest closed bar,
    the backtester for every bar of a long history (indicators computed once).
    """
    step = TF_SECONDS[timeframe]
    checks = {}
    waits = []

    def wait(code, message):
        waits.append({"code": code, "message": message})

    if timeframe not in TIMEFRAMES:
        wait("playbook_timeframe", f"trend pullback is validated on {', '.join(TIMEFRAMES)} only")
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
        wait("htf_no_trend", "4h has no clear trend (close/EMA50 vs EMA200 disagree)")
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

    local = 1 if (e21 > e50 > e200) else -1 if (e21 < e50 < e200) else 0
    checks["local_trend"] = local
    if direction and local != direction:
        wait("local_trend_conflict", f"{timeframe} EMAs (21/50/200) are not stacked with the 4h trend")
        direction = 0

    stretch = (close - e21) / a
    checks["stretch_atr"] = round(stretch, 2)
    if direction and stretch * direction <= STRETCH_ATR:
        wait("no_pullback_setup", f"price is only {stretch * direction:.2f} ATR from EMA21 — "
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

    entry = e21
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
        "bar_time": t,
    }


def _digits(symbol, price):
    base = symbol.upper().replace(":PERP", "")
    if base == "XAUUSD":
        return 2
    if base == "XAGUSD":
        return 3
    return max(2, min(12, 6 - math.floor(math.log10(price)))) if price > 0 else 6


def apply(decision, symbol, timeframe, tf_candles, htf_candles):
    """Overlay the playbook verdict on an engine decision dict (live path).

    `decision` keeps the engine's readings (indicators, rule_features, volume
    profile …) for display; signal, levels and wait reasons come only from
    the playbook. `htf_candles` = {"4h": [...], "1h": [...]} CLOSED bars.
    """
    symbol = symbol.upper()
    base = symbol.replace(":PERP", "")
    decision["signal_source"] = "playbook"
    decision["playbook"] = {"name": NAME, "version": VERSION, "timeframes": list(TIMEFRAMES)}
    decision["base_engine_signal"] = decision.get("signal")
    cleared = dict(entry=None, stop_loss=None, take_profit=None, tp_levels=None, entry_plan=None,
                   exit_plan=None, risk_reward=None, net_risk_reward=None, stop_pct=None,
                   est_round_trip_cost_pct=None, tp_source=None, grade=None)
    if base in ("XAUUSD", "XAGUSD"):
        decision.update(signal="wait", confidence="low", score=0, **cleared,
                        reason="Trend pullback playbook is validated on crypto (BTC) only.",
                        wait_reasons=[{"code": "playbook_market", "message": "not validated on metals"}])
        return decision
    if not tf_candles:
        decision.update(signal="wait", confidence="low", score=0, **cleared,
                        reason="No candles.", wait_reasons=[{"code": "insufficient_data", "message": "no candles"}])
        return decision
    ind = indicators(tf_candles)
    h4_view = HTFView((htf_candles or {}).get("4h") or [], TF_SECONDS["4h"])
    h1_view = HTFView((htf_candles or {}).get("1h") or [], TF_SECONDS["1h"]) if NEEDS_1H.get(timeframe) else None
    s = setup_at(len(tf_candles) - 1, ind, timeframe, h4_view, h1_view, symbol)
    decision["playbook"]["checks"] = s.get("checks")
    if s["signal"] not in ("buy", "sell"):
        first = (s["wait_reasons"] or [{"message": "conditions not met"}])[0]["message"]
        decision.update(signal="wait", confidence="low", score=0, **cleared,
                        reason=f"Trend pullback: {first}", wait_reasons=s["wait_reasons"])
        return decision
    d = _digits(symbol, s["entry"])
    rnd = lambda x: round(float(x), d)
    step_min = TF_SECONDS[timeframe] // 60
    tp_r = s["target_r"]
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
                    "reason": (f"price pushed {abs(s['checks']['stretch_atr']):.1f} ATR away from EMA21 in the "
                               "trend direction — buy the pullback at EMA21, never chase"),
                    "stretch_ema21_atr": s["checks"]["stretch_atr"]},
        exit_plan={"type": "fixed_target", "target_r": tp_r, "stop_atr": STOP_ATR,
                   "max_hold_bars": MAX_HOLD_BARS, "max_hold_minutes": MAX_HOLD_BARS * step_min,
                   "note": "close at market if neither stop nor target is hit within the time limit"},
        reason=(f"Trend pullback ({timeframe}): 4h trend {'up' if s['direction'] > 0 else 'down'}, "
                f"EMAs stacked, LIMIT at EMA21, stop {STOP_ATR} ATR ({s['stop_pct']:.2f}%), target {tp_r}R."),
        wait_reasons=[],
    )
    decision["playbook"]["evidence"] = RESEARCH["results"].get(timeframe)
    return decision


def series_decider(candles, timeframe, htf_candles, symbol="BTCUSDT"):
    """Backtest helper: indicators once, then a cheap per-bar decision."""
    ind = indicators(candles)
    h4_view = HTFView((htf_candles or {}).get("4h") or [], TF_SECONDS["4h"])
    h1_view = HTFView((htf_candles or {}).get("1h") or [], TF_SECONDS["1h"]) if NEEDS_1H.get(timeframe) else None

    def decide_at(i):
        return setup_at(i, ind, timeframe, h4_view, h1_view, symbol)
    return decide_at
