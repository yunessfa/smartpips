"""MARKET REGIME DETECTION.

Before deciding *which* setup to look for, a good trader first reads *what kind of
market* this is. The same indicators mean different things in a trend vs a range.
This module classifies the current tape into one regime and returns rules the
engine can use to allow/deny whole families of setups.

Regimes:
  - "trending"        : clean directional move (EMA stack aligned, ADX-ish strong)
  - "ranging"         : price oscillating between levels, no clear direction
  - "high_volatility" : large ATR / wide bars — moves are real but risky
  - "quiet"           : ATR too small to scalp profitably (spread eats the edge)

The engine uses this to e.g. skip trend setups in a range, or stand aside when
the tape is quiet.
"""


def _ema(values, period):
    if not values:
        return None
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _atr(candles, period=14):
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:] if len(trs) > period else trs
    return sum(window) / len(window) if window else 0.0


def detect_regime(candles, symbol="XAUUSD"):
    """Classify the market. Returns a dict the engine can act on."""
    if not candles or len(candles) < 30:
        return {"regime": "quiet", "strength": 0.0, "allow_trend": False,
                "allow_range": False, "note": "not enough data"}

    closes = [c["close"] for c in candles]
    price = closes[-1]
    a = _atr(candles, 14)
    atr_pct = (a / price) if price else 0

    base = symbol.upper().replace(":PERP", "")
    is_crypto = base.endswith("USDT")

    # 1) Quiet check first — too small to scalp.
    quiet_floor = 6e-4 if is_crypto else 9e-5
    if atr_pct < quiet_floor:
        return {"regime": "quiet", "strength": 0.0, "allow_trend": False,
                "allow_range": False, "atr_pct": round(atr_pct, 6),
                "note": "volatility too low to scalp"}

    # 2) Trend strength from EMA separation + directional persistence.
    ema_fast = _ema(closes[-50:], 9)
    ema_mid = _ema(closes[-50:], 21)
    ema_slow = _ema(closes[-100:], 50) if len(closes) >= 50 else _ema(closes, 50)
    stacked_up = ema_fast > ema_mid > ema_slow
    stacked_dn = ema_fast < ema_mid < ema_slow
    # how far price has travelled vs how much it wiggled (efficiency ratio)
    window = closes[-20:]
    net = abs(window[-1] - window[0])
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window))) or 1e-9
    efficiency = net / path  # ~1 = clean trend, ~0 = choppy/range

    # 3) High-volatility check — needs BOTH large ATR *and* directionless bars.
    #    A normal-ATR choppy tape is a range, not high-volatility.
    hi_vol_bar = 5e-3 if is_crypto else 7e-4

    if atr_pct > hi_vol_bar and efficiency < 0.30:
        # genuinely large bars but no direction => dangerous chop
        return {"regime": "high_volatility", "strength": round(efficiency, 2),
                "allow_trend": False, "allow_range": False,
                "atr_pct": round(atr_pct, 6), "efficiency": round(efficiency, 2),
                "note": "wide, directionless bars — stand aside"}

    if (stacked_up or stacked_dn) and efficiency >= 0.40:
        return {"regime": "trending",
                "direction": "up" if stacked_up else "down",
                "strength": round(efficiency, 2),
                "allow_trend": True, "allow_range": False,
                "atr_pct": round(atr_pct, 6), "efficiency": round(efficiency, 2),
                "note": "clean directional trend"}

    # 4) Otherwise it's a range.
    return {"regime": "ranging", "strength": round(efficiency, 2),
            "allow_trend": False, "allow_range": True,
            "atr_pct": round(atr_pct, 6), "efficiency": round(efficiency, 2),
            "note": "oscillating range — trend setups disabled"}


# Session quality stars (suggestion #4). London/NY = best liquidity.
SESSION_QUALITY = {
    "London/NY overlap": 5, "London open": 5, "New York": 5, "NY open": 5,
    "London": 4, "London close": 4,
    "Asia": 2, "Off-hours": 1, "Off": 1,
}


def session_stars(session_name):
    """Return 1-5 quality stars for a session name."""
    return SESSION_QUALITY.get(session_name, 3)


def classify_setup(direction, tf, htf_bias, regime):
    """SETUP CLASSIFICATION (suggestion #2): name the type of trade so the user
    instantly understands *why* this signal appeared."""
    flow = tf.get("flow") or {}
    sweep = tf.get("sweep") or {}
    smc = tf.get("smc") or {}
    mss = tf.get("mss") or {}
    want = 1 if direction == "buy" else -1

    swept = (sweep.get("bias") or 0) == want
    bos = smc.get("bos") == ("bullish" if want > 0 else "bearish")
    structure_flip = mss.get("mss") in ("bullish", "bearish")

    # Liquidity reversal: a stop-hunt swept the opposite side, then we go the other way
    if swept and (structure_flip or bos):
        return {"class": "liquidity_reversal", "emoji": "🟠"}
    # Breakout: structure broke in a trending regime
    if bos and regime.get("regime") == "trending":
        return {"class": "breakout", "emoji": "🔵"}
    # Trend continuation: aligned with a trending regime, no fresh break needed
    if regime.get("regime") == "trending" and htf_bias == want:
        return {"class": "trend_continuation", "emoji": "🟢"}
    # Range scalp: we're in a range and fading an edge
    if regime.get("regime") == "ranging":
        return {"class": "range_scalp", "emoji": "🟣"}
    return {"class": "momentum", "emoji": "⚪"}
