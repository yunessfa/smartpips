"""
SmartPips Strategy Engine — the DECISION maker.

This is the core change recommended in the review: the *engine* decides buy/sell/
wait from real indicators on real candles, computes a transparent confidence score,
and sizes the trade with a risk manager. GPT is NOT asked to decide — it only
explains the engine's decision afterwards.

Indicators are computed on OHLC candles (via apps.market.candles). When candle data
isn't available, the caller may pass a tick series as a fallback; quality is lower
and the engine flags that.
"""
from statistics import mean


# ----------------------------- indicator math -----------------------------
def ema(values, period):
    if not values:
        return None
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def ema_series(values, period):
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(len(values) - period, len(values)):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if gains + losses == 0:
        return 50.0
    rs = gains / (losses or 1e-9)
    return 100 - 100 / (1 + rs)


def macd(values, fast=12, slow=26, signal=9):
    if len(values) < slow + signal:
        return None
    ef, es = ema_series(values, fast), ema_series(values, slow)
    macd_line = [a - b for a, b in zip(ef, es)]
    sig = ema_series(macd_line, signal)
    return {"macd": macd_line[-1], "signal": sig[-1], "hist": macd_line[-1] - sig[-1]}


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs[-period:]) if trs else None


def vwap(candles):
    """Volume-weighted average price.

    Uses real volume when the candle carries it (MT5/cTrader send tick_volume),
    and falls back to a flat unit weight for spot feeds that have no volume — in
    which case VWAP degrades gracefully to an average typical price.
    """
    if not candles:
        return None
    num = den = 0.0
    has_real_vol = any((c.get("volume") or 0) > 1 for c in candles)
    for c in candles:
        tp = (c["high"] + c["low"] + c["close"]) / 3
        vol = (c.get("volume") or 1.0) if has_real_vol else 1.0
        num += tp * vol
        den += vol
    return num / den if den else None


def stochastic(closes, highs, lows, k_period=9, d_period=3):
    if len(closes) < k_period + d_period:
        return None
    ks = []
    for i in range(k_period - 1, len(closes)):
        hi = max(highs[i - k_period + 1:i + 1])
        lo = min(lows[i - k_period + 1:i + 1])
        ks.append(50.0 if hi == lo else (closes[i] - lo) / (hi - lo) * 100)
    if len(ks) < d_period:
        return None
    return {"k": ks[-1], "d": mean(ks[-d_period:])}


def swing_levels(candles, lookback=40):
    """Nearest support/resistance from recent swing highs/lows."""
    window = candles[-lookback:] if len(candles) > lookback else candles
    if not window:
        return None, None
    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]
    return min(lows), max(highs)  # support, resistance


# ----------------------------- Smart-Money / liquidity -----------------------------
def _pivots(candles, k=2):
    """Return indices of swing highs and lows (fractal-style, k bars each side)."""
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    sh, sl = [], []
    for i in range(k, len(candles) - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            sh.append(i)
        if lows[i] == min(lows[i - k:i + k + 1]):
            sl.append(i)
    return sh, sl


def smc_structure(candles):
    """Detect BOS / CHOCH / FVG / equal highs-lows from candles.

    Returns a dict with a directional bias (+1 bull / -1 bear / 0) plus flags that
    the explanation layer can cite. Pure price-structure — no extra data needed.
    """
    out = {"bias": 0, "bos": None, "choch": None, "fvg": None,
           "equal_high": False, "equal_low": False}
    if len(candles) < 12:
        return out
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price = closes[-1]
    sh, sl = _pivots(candles, k=2)

    # Break of structure: did price close beyond the last swing high/low?
    last_sh = highs[sh[-1]] if sh else None
    last_sl = lows[sl[-1]] if sl else None
    if last_sh is not None and price > last_sh:
        out["bos"] = "bullish"
        out["bias"] += 1
    elif last_sl is not None and price < last_sl:
        out["bos"] = "bearish"
        out["bias"] -= 1

    # Change of character: previous structure broke the other way.
    if len(sh) >= 2 and len(sl) >= 2:
        rising_highs = highs[sh[-1]] > highs[sh[-2]]
        rising_lows = lows[sl[-1]] > lows[sl[-2]]
        if out["bos"] == "bullish" and not rising_highs and not rising_lows:
            out["choch"] = "bullish"
        elif out["bos"] == "bearish" and rising_highs and rising_lows:
            out["choch"] = "bearish"

    # Fair value gap on the last 3 candles.
    if len(candles) >= 3:
        if lows[-1] > highs[-3]:
            out["fvg"] = "bullish"
            out["bias"] += 1
        elif highs[-1] < lows[-3]:
            out["fvg"] = "bearish"
            out["bias"] -= 1

    # Equal highs/lows = resting liquidity (within a small tolerance).
    tol = price * 3e-4 if price else 0
    if len(sh) >= 2 and abs(highs[sh[-1]] - highs[sh[-2]]) <= tol:
        out["equal_high"] = True
    if len(sl) >= 2 and abs(lows[sl[-1]] - lows[sl[-2]]) <= tol:
        out["equal_low"] = True

    out["bias"] = 1 if out["bias"] > 0 else -1 if out["bias"] < 0 else 0
    return out


# ----------------------------- single-timeframe read -----------------------------
def analyse_timeframe(candles):
    """Compute indicators + a directional bias (+1/0/-1) for one timeframe."""
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    if len(closes) < 30:
        return None

    e9, e50 = ema(closes[-60:], 9), ema(closes[-150:], 50)
    e200 = ema(closes, 200) if len(closes) >= 200 else None
    price = closes[-1]
    r = rsi(closes, 14)
    m = macd(closes)
    st = stochastic(closes, highs, lows, 9, 3)
    vw = vwap(candles)
    smc = smc_structure(candles)
    from .orderflow import (order_flow, liquidity_sweep, order_blocks, fvg_quality,
                            premium_discount, market_structure_shift)
    flow = order_flow(candles)
    sweep = liquidity_sweep(candles)
    obs = order_blocks(candles)
    fvg = fvg_quality(candles)
    pd_zone = premium_discount(candles)
    mss = market_structure_shift(candles)
    from .levels import level_interaction
    klevels = level_interaction(candles)

    bias = 0
    if e9 is not None and e50 is not None:
        bias += 1 if e9 > e50 else -1
    if e200 is not None:
        bias += 1 if price > e200 else -1
    if vw is not None:
        bias += 1 if price > vw else -1
    bias += smc["bias"]
    bias += flow["bias"]
    bias += sweep["bias"]
    bias += obs["bias"]
    bias += klevels["bias"]

    return {
        "price": price, "ema9": e9, "ema50": e50, "ema200": e200,
        "rsi": r, "macd": m, "stoch": st, "vwap": vw, "smc": smc,
        "flow": flow, "sweep": sweep, "order_blocks": obs, "fvg_q": fvg,
        "premium_discount": pd_zone, "mss": mss, "key_levels": klevels,
        "bias": 1 if bias > 0 else -1 if bias < 0 else 0,
    }


# ----------------------------- weighted confidence -----------------------------
# Transparent weights (sum 100) — confidence is computed here, NOT by GPT.
WEIGHTS = {"htf_trend": 15, "ema": 11, "vwap": 9, "rsi": 7, "macd": 7,
           "stoch": 3, "smc": 10, "orderflow": 13, "liquidity": 8,
           "orderblock": 7, "premium_discount": 4, "key_levels": 6}


def _score_direction(tf, htf_bias):
    """Return (direction, score 0-100, breakdown) for the trading timeframe."""
    price = tf["price"]
    long_pts = short_pts = 0
    bd = {}

    def award(key, cond_long, cond_short):
        nonlocal long_pts, short_pts
        w = WEIGHTS[key]
        if cond_long:
            long_pts += w
            bd[key] = +w
        elif cond_short:
            short_pts += w
            bd[key] = -w
        else:
            bd[key] = 0

    award("htf_trend", htf_bias > 0, htf_bias < 0)
    if tf["ema9"] is not None and tf["ema50"] is not None:
        award("ema", tf["ema9"] > tf["ema50"], tf["ema9"] < tf["ema50"])
    if tf["vwap"] is not None:
        award("vwap", price > tf["vwap"], price < tf["vwap"])
    if tf["rsi"] is not None:
        award("rsi", 50 < tf["rsi"] < 78, 22 < tf["rsi"] < 50)
    if tf["macd"] is not None:
        award("macd", tf["macd"]["hist"] > 0, tf["macd"]["hist"] < 0)
    if tf["stoch"] is not None:
        award("stoch", tf["stoch"]["k"] > tf["stoch"]["d"] and tf["stoch"]["k"] < 85,
              tf["stoch"]["k"] < tf["stoch"]["d"] and tf["stoch"]["k"] > 15)
    if tf.get("smc") is not None:
        award("smc", tf["smc"]["bias"] > 0, tf["smc"]["bias"] < 0)
    if tf.get("flow") is not None:
        award("orderflow", tf["flow"]["bias"] > 0, tf["flow"]["bias"] < 0)
    if tf.get("sweep") is not None:
        award("liquidity", tf["sweep"]["bias"] > 0, tf["sweep"]["bias"] < 0)
    if tf.get("order_blocks") is not None:
        award("orderblock", tf["order_blocks"]["bias"] > 0, tf["order_blocks"]["bias"] < 0)
    if tf.get("premium_discount") is not None:
        award("premium_discount", tf["premium_discount"]["bias"] > 0, tf["premium_discount"]["bias"] < 0)
    if tf.get("key_levels") is not None:
        award("key_levels", tf["key_levels"]["bias"] > 0, tf["key_levels"]["bias"] < 0)

    total = long_pts + short_pts
    if total <= 0:
        return "buy", 0, bd, 0

    # CONVICTION = how strongly the winning side dominates (0-100).
    # This is the real signal quality. A 62-vs-58 split is a coin-flip (low
    # conviction) even though the winner's raw points look "high". Scalping into
    # a near-tie is exactly how you bleed — so we score by dominance, not by the
    # winning side's absolute points.
    if long_pts >= short_pts:
        conviction = round((long_pts - short_pts) / total * 100)
        return "buy", long_pts, bd, conviction
    conviction = round((short_pts - long_pts) / total * 100)
    return "sell", short_pts, bd, conviction


def _confidence_label(score):
    if score >= 80:
        return "high"
    if score >= 65:
        return "medium"
    return "low"


def _plain_reasons(tf, direction):
    """Turn raw engine flags into short, human-readable confirmation/risk keys
    (the frontend localises them). Returns {pros, cons} lists of keys."""
    pros, cons = [], []
    want = 1 if direction == "buy" else -1

    def agree(b):
        return None if not b else ((b > 0) == (want > 0))

    smc = tf.get("smc") or {}
    if smc.get("bos") == ("bullish" if want > 0 else "bearish"):
        pros.append("bos_aligned")
    if tf.get("mss") and tf["mss"].get("mss") == ("bullish" if want > 0 else "bearish"):
        pros.append("mss_shift")
    flow = tf.get("flow") or {}
    if agree(flow.get("bias")) is True:
        pros.append("smart_money_flow")
    elif agree(flow.get("bias")) is False:
        cons.append("flow_against")
    sweep = tf.get("sweep") or {}
    if agree(sweep.get("bias")) is True:
        pros.append("liquidity_grabbed")
    ob = tf.get("order_blocks") or {}
    if agree(ob.get("bias")) is True:
        pros.append("order_block")
    pd = tf.get("premium_discount") or {}
    if pd.get("zone") == "discount" and want > 0:
        pros.append("discount_zone")
    elif pd.get("zone") == "premium" and want < 0:
        pros.append("premium_zone")
    elif pd.get("zone") == "premium" and want > 0:
        cons.append("buying_in_premium")
    elif pd.get("zone") == "discount" and want < 0:
        cons.append("selling_in_discount")
    kl = tf.get("key_levels") or {}
    if kl.get("level"):
        pros.append("key_level_sweep")
    fvg = tf.get("fvg_q")
    if fvg and fvg.get("direction") == ("bullish" if want > 0 else "bearish"):
        pros.append("fvg_present")
    return {"pros": pros, "cons": cons}


def _signal_grade(score, signal):
    """Customer-friendly A+/A/B/C grade + 0-5 star meter from the score."""
    if signal == "wait":
        return {"grade": "—", "stars": 0, "strength": "no-trade"}
    if score >= 90:
        return {"grade": "A+", "stars": 5, "strength": "very-strong"}
    if score >= 80:
        return {"grade": "A", "stars": 4, "strength": "strong"}
    if score >= 68:
        return {"grade": "B", "stars": 3, "strength": "moderate"}
    if score >= 58:
        return {"grade": "C", "stars": 2, "strength": "weak"}
    return {"grade": "C", "stars": 1, "strength": "weak"}
    if score >= 60:
        return "medium"
    return "low"


# ----------------------------- the engine -----------------------------
def _validate_setup(direction, tf, htf_bias, session, mode="safe"):
    """SETUP VALIDATION ENGINE.

    Checks named conditions for a scalp entry and decides if the setup is allowed,
    plus produces a human-readable checklist and a quality grade (A+/A/B/C).

    Conditions checked (each is a "confluence"):
      1. HTF trend agrees with the trade direction
      2. MSS or BOS confirmed in the trade direction (structure break)
      3. Liquidity sweep in the trade direction (stop-hunt done)
      4. Price reacting from an Order Block OR a quality FVG
      5. Order Flow pressure agrees with the trade direction
      6. Session is London or New York (real liquidity)

    'mode':
      - "safe":       require the trend + structure essentials, ≥4 of 6 total.
      - "aggressive": looser — ≥3 of 6, structure OR sweep is enough.
    """
    want = 1 if direction == "buy" else -1
    bull = want > 0

    flow = tf.get("flow") or {}
    sweep = tf.get("sweep") or {}
    obs = tf.get("order_blocks") or {}
    mss = tf.get("mss") or {}
    smc = tf.get("smc") or {}
    fvg_q = tf.get("fvg_q") or {}

    # individual condition booleans
    c_htf = (htf_bias > 0) if bull else (htf_bias < 0)
    c_struct = (mss.get("mss") == ("bullish" if bull else "bearish")) or \
               (smc.get("bos") == ("bullish" if bull else "bearish"))
    c_sweep = (sweep.get("bias") or 0) == want
    fvg_dir = fvg_q.get("direction")
    c_fvg = fvg_dir == ("bullish" if bull else "bearish")
    c_zone = ((obs.get("bias") or 0) == want) or c_fvg
    c_flow = (flow.get("bias") or 0) == want
    sess_name = (session or {}).get("name", "")
    c_session = sess_name in ("London", "New York", "London/NY overlap",
                              "London open", "NY open", "London close")

    checks = [
        ("trend_aligned", c_htf),
        ("structure_break", c_struct),
        ("liquidity_sweep", c_sweep),
        ("order_block_fvg", c_zone),
        ("order_flow", c_flow),
        ("active_session", c_session),
    ]
    passed = sum(1 for _, ok in checks if ok)

    if mode == "aggressive":
        # looser: need 3 of 6, and at least structure OR sweep
        ok = passed >= 3 and (c_struct or c_sweep)
        min_needed = 3
    else:
        # safe: trend + structure are essential, plus ≥4 of 6 overall
        ok = c_htf and c_struct and passed >= 4
        min_needed = 4

    # quality grade from how many confluences lined up
    if passed >= 6:
        grade = "A+"
    elif passed == 5:
        grade = "A"
    elif passed == 4:
        grade = "B"
    elif passed == 3:
        grade = "C"
    else:
        grade = "D"

    # build a reject reason naming what's missing (most important first)
    reject_reason = ""
    if not ok:
        if not c_htf:
            reject_reason = "setup rejected: higher-timeframe trend not aligned"
        elif not c_struct:
            reject_reason = "setup rejected: no confirmed MSS/BOS in trade direction"
        else:
            missing = [name for name, v in checks if not v]
            reject_reason = f"setup rejected: only {passed}/{min_needed} key conditions ({', '.join(missing)} missing)"

    return {
        "pass": ok,
        "grade": grade,
        "passed": passed,
        "total": len(checks),
        "checks": dict(checks),
        "reject_reason": reject_reason,
    }


def run_strategy(symbol, timeframe, tf_candles, htf_candles_map, live_price=None,
                 mode="safe"):
    """
    Decide buy/sell/wait from REAL indicators + multi-timeframe agreement.

    tf_candles: candles for the trading timeframe.
    htf_candles_map: {label: candles} for higher timeframes to confirm.
    Returns a dict the API/GPT can consume.
    """
    tf = analyse_timeframe(tf_candles)
    if tf is None:
        return {"signal": "wait", "confidence": "low", "score": 0,
                "reason": "not enough candle data", "data_quality": "insufficient"}

    # REAL ORDER FLOW: for metals, if the cTrader bridge has streamed enough live
    # ticks, use true tick-based buy/sell pressure instead of the candle-derived
    # approximation. Crypto already has real volume from Binance.
    _base = symbol.upper().replace(":PERP", "")
    if _base in ("XAUUSD", "XAGUSD"):
        try:
            from apps.market.tick_flow import real_order_flow
            rof = real_order_flow(_base)
            if rof and tf.get("flow"):
                tf["flow"]["bias"] = rof["bias"]
                tf["flow"]["buy_pressure"] = rof["buy_pressure"]
                tf["flow"]["sell_pressure"] = rof["sell_pressure"]
                tf["flow"]["delta"] = rof["delta"]
                tf["flow"]["source"] = "ctrader_ticks"
        except Exception:
            pass

    # Multi-timeframe: collect higher-timeframe biases.
    htf_biases = {}
    for label, candles in (htf_candles_map or {}).items():
        a = analyse_timeframe(candles)
        if a:
            htf_biases[label] = a["bias"]
    htf_bias = 0
    if htf_biases:
        s = sum(htf_biases.values())
        htf_bias = 1 if s > 0 else -1 if s < 0 else 0

    direction, score, breakdown, conviction = _score_direction(tf, htf_bias)

    price = live_price or tf["price"]
    a = atr(tf_candles, 14) or (price * 0.0008)
    support, resistance = swing_levels(tf_candles)

    # ----- decision gates -----
    reasons = []
    signal = direction

    # 0) MARKET REGIME DETECTION — read what kind of market this is BEFORE
    #    deciding. Different regimes allow different setups; a quiet or
    #    directionless tape means stand aside entirely.
    from .regime import detect_regime, session_stars, classify_setup
    regime_info = detect_regime(tf_candles, symbol)
    market_regime = regime_info["regime"]

    if market_regime == "quiet":
        signal = "wait"
        reasons.append("market too quiet to scalp (low volatility)")
    elif market_regime == "high_volatility":
        signal = "wait"
        reasons.append("wide, directionless bars — too risky")

    # 1) Higher-timeframe alignment. A counter-trend scalp is the #1 way to bleed,
    #    so we don't just block conflicts — for the trade to stand, the higher
    #    timeframe must AGREE (or at least the trade's own EMA structure must).
    if htf_bias != 0 and ((direction == "buy" and htf_bias < 0) or
                          (direction == "sell" and htf_bias > 0)):
        signal = "wait"
        reasons.append("higher timeframe conflicts with the setup")

    # 1b) Don't fight the local trend: EMA50/200 must not point the other way.
    e50, e200 = tf.get("ema50"), tf.get("ema200")
    if e50 is not None and e200 is not None:
        local_up = e50 > e200
        if direction == "sell" and local_up and htf_bias >= 0:
            signal = "wait"
            reasons.append("shorting into an up-trend (EMA50>EMA200)")
        elif direction == "buy" and not local_up and htf_bias <= 0:
            signal = "wait"
            reasons.append("buying into a down-trend (EMA50<EMA200)")

    # 2) CONVICTION GATE — the single most important filter. If the two sides are
    #    nearly tied, the market has no real direction and this is a coin-flip.
    #    Requiring strong dominance is what stops the engine from, e.g., shorting
    #    into an uptrend just because short edged out long by a few points.
    from apps.market.sessions import current_session
    session = current_session()
    sess_stars = session_stars(session.get("name", ""))

    # adaptive: ranging markets & poor sessions demand MORE conviction
    min_conviction = 34
    if market_regime == "ranging":
        min_conviction = 50
    if sess_stars <= 2:
        min_conviction += 8
    if conviction < min_conviction:
        signal = "wait"
        reasons.append(f"weak conviction {conviction}% (both directions close) "
                       f"— need {min_conviction}%")

    # 2a) Weak absolute score => no trade. Adaptive by regime/session.
    min_score = 60 if session["score"] >= 6 else 66
    if market_regime == "ranging":
        min_score = max(min_score, 68)   # #4 adaptive threshold: stricter in range
    if score < min_score:
        signal = "wait"
        reasons.append(f"confluence score {score} below {min_score} "
                       f"({session['name']} session)")

    # 2b) SETUP VALIDATION ENGINE — the core quality gate for scalping.
    #     Instead of "score is high enough", we check named conditions and require
    #     a minimum number of the IMPORTANT ones. This is what lifts the win-rate:
    #     fewer trades, but each one has real structural backing.
    setup = None
    if signal in ("buy", "sell"):
        setup = _validate_setup(signal, tf, htf_bias, session, mode=mode)
        if not setup["pass"]:
            signal = "wait"
            reasons.append(setup["reject_reason"])

    # 2b-2) REGIME RULES — in a ranging market, block trend-continuation entries
    #       (they get chopped up). Only allow reversal/range setups there.
    setup_class = None
    if signal in ("buy", "sell"):
        setup_class = classify_setup(signal, tf, htf_bias, regime_info)
        if market_regime == "ranging" and setup_class["class"] in ("trend_continuation", "breakout"):
            signal = "wait"
            reasons.append("trend setup blocked in a ranging market")

    # 2c) PULLBACK CONFIRMATION — don't chase. After a structure break, the best
    #     entries come on a pullback toward the breakout level, not at the extreme.
    #     In "safe" mode we require price to NOT be over-extended from EMA9.
    if signal in ("buy", "sell") and mode == "safe":
        ema9 = tf.get("ema9")
        if ema9 and a:
            # distance from the fast EMA in ATR units; chasing if too far
            ext = (price - ema9) / a if signal == "buy" else (ema9 - price) / a
            if ext > 2.2:
                signal = "wait"
                reasons.append("over-extended from EMA9 — wait for a pullback")

    # ----- risk manager: structure-based stop, volatility-adaptive R:R -----
    entry = price
    take_profit = stop_loss = risk_reward = tp_levels = None
    # Volatility regime sets the reward multiple.
    atr_pct = (a / price) if price else 0
    if atr_pct < 1.2e-4:
        tp_mult, regime = 1.5, "low"
    elif atr_pct > 3.5e-4:
        tp_mult, regime = 3.0, "high"
    else:
        tp_mult, regime = 2.0, "normal"

    # Minimum stop as a % of price. These were FAR too tight before, which is why
    # almost every trade hit SL on normal market noise. Widened substantially:
    #   - gold moves several dollars per minute, so 0.15% (~$6 on $4150) was suicide.
    #   - crypto is even noisier and needs the most room.
    base = symbol.upper().replace(":PERP", "")
    is_crypto = base.endswith("USDT")
    if is_crypto:
        min_stop_pct = 0.008          # 0.8% for crypto
    elif base == "XAUUSD":
        min_stop_pct = 0.0035         # ~0.35% (~$14 on $4150) — survives normal noise
    elif base == "XAGUSD":
        min_stop_pct = 0.0045         # silver is whippier than gold
    else:
        min_stop_pct = 0.0025

    if signal in ("buy", "sell"):
        # stop = the LARGER of (ATR-based, now 2.2x) and (min % of price).
        stop_dist = max(a * 2.2, price * min_stop_pct)
        if signal == "buy":
            atr_stop = entry - stop_dist
            # structure stop only if it gives MORE room (further from entry), never less
            stop_loss = min(atr_stop, support - a * 0.5) if (support and support < atr_stop) else atr_stop
            risk = entry - stop_loss
            take_profit = entry + risk * tp_mult
        else:
            atr_stop = entry + stop_dist
            stop_loss = max(atr_stop, resistance + a * 0.5) if (resistance and resistance > atr_stop) else atr_stop
            risk = stop_loss - entry
            take_profit = entry - risk * tp_mult
        if risk and risk > 0:
            risk_reward = round(abs(take_profit - entry) / risk, 2)
        if not risk_reward or risk_reward < 1.5:
            signal = "wait"
            reasons.append("could not place a stop with acceptable R:R")

        # THREE-LEVEL PARTIAL TAKE-PROFIT — instead of one all-or-nothing target,
        # split the position into 3 exits so a runner can be managed even if the
        # user isn't watching: TP1 (close 40%) banks something fast, TP2 (35%) is
        # the original target, TP3 (25%) lets a strong move run further.
        tp_levels = None
        if signal in ("buy", "sell") and risk and risk > 0:
            r1, r2, r3 = 1.0, tp_mult, tp_mult * 1.6
            if signal == "buy":
                lv = [entry + risk * r1, entry + risk * r2, entry + risk * r3]
            else:
                lv = [entry - risk * r1, entry - risk * r2, entry - risk * r3]
            tp_levels = [
                {"price": round(lv[0], 5), "pct": 40, "r": round(r1, 2)},
                {"price": round(lv[1], 5), "pct": 35, "r": round(r2, 2)},
                {"price": round(lv[2], 5), "pct": 25, "r": round(r3, 2)},
            ]

        # MINIMUM EXPECTED MOVE — if the target is tiny relative to volatility,
        # the trade isn't worth the spread/risk. A 6-dollar TP when ATR is 20 is
        # noise. Require the reward to be a meaningful fraction of ATR.
        if signal in ("buy", "sell") and take_profit and a:
            tp_dist = abs(take_profit - entry)
            if tp_dist < a * 0.8:
                signal = "wait"
                reasons.append("expected move too small vs volatility — not worth it")

    digits = 2 if symbol == "XAUUSD" else 3
    rnd = lambda x: round(x, digits) if isinstance(x, (int, float)) else x

    return {
        "signal": signal,
        "confidence": _confidence_label(score) if signal != "wait" else "low",
        "score": score,
        "conviction": conviction,
        "grade": _signal_grade(score, signal),
        "setup": setup,
        "setup_mode": mode,
        "setup_class": setup_class,
        "market_regime": regime_info,
        "session_quality": {"name": session.get("name"),
                            "stars": session_stars(session.get("name", ""))},
        "reasons_plain": _plain_reasons(tf, direction) if signal != "wait" else {"pros": [], "cons": []},
        "score_breakdown": breakdown,
        "htf_bias": htf_bias,
        "htf_detail": htf_biases,
        "entry": rnd(entry) if signal != "wait" else None,
        "take_profit": rnd(take_profit) if take_profit else None,
        "stop_loss": rnd(stop_loss) if stop_loss else None,
        "tp_levels": tp_levels,
        "risk_reward": risk_reward,
        "atr": rnd(a),
        "support": rnd(support) if support else None,
        "resistance": rnd(resistance) if resistance else None,
        "indicators": {
            "EMA9": rnd(tf["ema9"]) if tf["ema9"] else None,
            "EMA50": rnd(tf["ema50"]) if tf["ema50"] else None,
            "EMA200": rnd(tf["ema200"]) if tf["ema200"] else None,
            "RSI": round(tf["rsi"], 1) if tf["rsi"] else None,
            "MACD_hist": round(tf["macd"]["hist"], 4) if tf["macd"] else None,
            "Stoch": {"k": round(tf["stoch"]["k"], 1), "d": round(tf["stoch"]["d"], 1)} if tf["stoch"] else None,
            "VWAP": rnd(tf["vwap"]) if tf["vwap"] else None,
            "SMC": (lambda s: {
                "bias": s["bias"], "BOS": s["bos"], "CHOCH": s["choch"],
                "FVG": s["fvg"], "equal_high": s["equal_high"], "equal_low": s["equal_low"],
            })(tf["smc"]) if tf.get("smc") else None,
            "OrderFlow": (lambda f: {
                "delta": f["delta"], "buy_pressure": f["buy_pressure"],
                "sell_pressure": f["sell_pressure"], "velocity": f["velocity"],
                "acceleration": f["acceleration"],
            })(tf["flow"]) if tf.get("flow") else None,
            "LiquiditySweep": tf["sweep"]["side"] if tf.get("sweep") else None,
            "FVG_quality": tf.get("fvg_q"),
            "PremiumDiscount": tf.get("premium_discount"),
            "MSS": tf["mss"]["mss"] if tf.get("mss") else None,
            "OrderBlock": (lambda o: "bullish" if o["bias"] > 0 else "bearish" if o["bias"] < 0 else None)(tf["order_blocks"]) if tf.get("order_blocks") else None,
            "KeyLevels": tf["key_levels"]["levels"] if tf.get("key_levels") else {},
            "LevelSweep": tf["key_levels"]["level"] if tf.get("key_levels") else None,
        },
        "regime": regime,
        "reason": "; ".join(reasons) if reasons else "all layers aligned",
        "session": {"name": session["name"], "score": session["score"],
                    "quality": session["quality"]},
        "data_quality": "candles",
    }
