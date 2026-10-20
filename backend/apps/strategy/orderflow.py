"""
Order-flow & liquidity layer derived from OHLC candles (no Level-2 needed).

This is the pragmatic "~40% of order flow" the review described: from candle
direction, body strength, range expansion and momentum we estimate buy/sell
pressure, plus structural events (liquidity sweeps, order blocks) that matter a
lot for XAUUSD. When real Bid/Ask tick data is available (cTrader) the same
fields can be fed more accurately, but this works on candles alone.
"""


def order_flow(candles, lookback=20):
    """Estimate buy/sell pressure, delta, velocity and acceleration from candles.

    Returns a dict with a directional bias in [-1, +1] and component values.
    """
    if len(candles) < lookback + 5:
        return {"bias": 0, "buy_pressure": 0.0, "sell_pressure": 0.0,
                "delta": 0.0, "velocity": 0.0, "acceleration": 0.0}

    window = candles[-lookback:]
    up = down = 0.0
    for c in window:
        rng = max(c["high"] - c["low"], 1e-9)
        body = c["close"] - c["open"]
        # where the close sits in the bar's range (0=low,1=high) → aggression proxy
        close_pos = (c["close"] - c["low"]) / rng
        vol = c.get("volume") or 1.0
        if body >= 0:
            up += close_pos * vol
        else:
            down += (1 - close_pos) * vol

    total = up + down or 1.0
    buy_pressure = round(up / total, 3)
    sell_pressure = round(down / total, 3)
    delta = round(buy_pressure - sell_pressure, 3)

    # velocity = recent average signed move; acceleration = change in velocity
    closes = [c["close"] for c in candles]
    def avg_move(seq):
        diffs = [seq[i] - seq[i - 1] for i in range(1, len(seq))]
        return sum(diffs) / len(diffs) if diffs else 0.0
    recent = avg_move(closes[-6:])
    prior = avg_move(closes[-12:-6]) if len(closes) >= 12 else 0.0
    px = closes[-1] or 1.0
    velocity = round(recent / px, 6)
    acceleration = round((recent - prior) / px, 6)

    bias = 0
    if delta > 0.15 and velocity >= 0:
        bias = 1
    elif delta < -0.15 and velocity <= 0:
        bias = -1

    return {"bias": bias, "buy_pressure": buy_pressure, "sell_pressure": sell_pressure,
            "delta": delta, "velocity": velocity, "acceleration": acceleration}


def liquidity_sweep(candles, lookback=40, tol_factor=3e-4):
    """Detect a recent sweep of equal highs/lows (stop hunt) that then reversed.

    A bullish sweep = price dipped below a prior equal-low cluster and closed back
    above (sell-side liquidity taken → bullish). Bearish = mirror. Returns dict.
    """
    out = {"side": None, "reversed": False, "bias": 0}
    if len(candles) < lookback + 3:
        return out
    window = candles[-lookback:]
    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]
    price = candles[-1]["close"]
    tol = price * tol_factor

    prior_high = max(highs[:-2])
    prior_low = min(lows[:-2])
    last_high = max(highs[-2:])
    last_low = min(lows[-2:])

    # swept above prior highs but closed back below → sell-side setup
    if last_high > prior_high + tol and price < prior_high:
        out.update({"side": "buy_side_taken", "reversed": True, "bias": -1})
    # swept below prior lows but closed back above → buy-side setup
    elif last_low < prior_low - tol and price > prior_low:
        out.update({"side": "sell_side_taken", "reversed": True, "bias": 1})
    return out


def order_blocks(candles, lookback=30):
    """Find the most recent bullish/bearish order block (last opposite candle before
    a strong impulsive move). Returns the nearest OB zone + a directional bias when
    price is reacting from a block."""
    out = {"bullish": None, "bearish": None, "bias": 0}
    if len(candles) < 6:
        return out
    window = candles[-lookback:] if len(candles) > lookback else candles
    atr_like = sum(c["high"] - c["low"] for c in window) / len(window) or 1e-9
    price = candles[-1]["close"]

    for i in range(len(window) - 3, 1, -1):
        c0, c1 = window[i], window[i + 1]
        move = c1["close"] - c1["open"]
        # strong bullish impulse preceded by a down candle => bullish OB
        if move > atr_like * 1.2 and c0["close"] < c0["open"] and out["bullish"] is None:
            out["bullish"] = {"top": c0["high"], "bottom": c0["low"]}
        # strong bearish impulse preceded by an up candle => bearish OB
        if -move > atr_like * 1.2 and c0["close"] > c0["open"] and out["bearish"] is None:
            out["bearish"] = {"top": c0["high"], "bottom": c0["low"]}
        if out["bullish"] and out["bearish"]:
            break

    # bias: price tapping into a bullish OB from above = bullish, mirror for bearish
    tol = atr_like * 0.5
    if out["bullish"] and (out["bullish"]["bottom"] - tol) <= price <= (out["bullish"]["top"] + tol):
        out["bias"] = 1
    elif out["bearish"] and (out["bearish"]["bottom"] - tol) <= price <= (out["bearish"]["top"] + tol):
        out["bias"] = -1
    return out


def premium_discount(candles, lookback=50):
    """Where is price within the current dealing range? ICT-style: the range is the
    last swing high to last swing low (the active leg), not a flat window. Smart
    money buys in 'discount' (lower half) and sells in 'premium' (upper half)."""
    if len(candles) < 10:
        return {"zone": "equilibrium", "pct": 50.0, "bias": 0}

    # find the most recent swing high and swing low (fractal, k=2)
    k = 2
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    swing_hi = swing_lo = None
    for i in range(len(candles) - k - 1, k - 1, -1):
        if swing_hi is None and highs[i] == max(highs[i - k:i + k + 1]):
            swing_hi = highs[i]
        if swing_lo is None and lows[i] == min(lows[i - k:i + k + 1]):
            swing_lo = lows[i]
        if swing_hi is not None and swing_lo is not None:
            break

    # fall back to the window extremes if no clean swings found
    window = candles[-lookback:] if len(candles) > lookback else candles
    hi = swing_hi if swing_hi is not None else max(c["high"] for c in window)
    lo = swing_lo if swing_lo is not None else min(c["low"] for c in window)
    if hi <= lo:
        return {"zone": "equilibrium", "pct": 50.0, "bias": 0}

    price = candles[-1]["close"]
    pct = (price - lo) / (hi - lo) * 100
    pct = max(0.0, min(100.0, pct))
    if pct <= 38:
        return {"zone": "discount", "pct": round(pct, 1), "bias": 1}
    if pct >= 62:
        return {"zone": "premium", "pct": round(pct, 1), "bias": -1}
    return {"zone": "equilibrium", "pct": round(pct, 1), "bias": 0}


def market_structure_shift(candles, k=2):
    """Detect a Market Structure Shift: a break of swing structure opposite to the
    prior leg (stronger signal than a plain BOS)."""
    if len(candles) < 12:
        return {"mss": None}
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    sh, sl = [], []
    for i in range(k, len(candles) - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            sh.append(i)
        if lows[i] == min(lows[i - k:i + k + 1]):
            sl.append(i)
    price = candles[-1]["close"]
    if len(sh) >= 2 and len(sl) >= 2:
        downtrend = highs[sh[-1]] < highs[sh[-2]] and lows[sl[-1]] < lows[sl[-2]]
        uptrend = highs[sh[-1]] > highs[sh[-2]] and lows[sl[-1]] > lows[sl[-2]]
        if downtrend and price > highs[sh[-1]]:
            return {"mss": "bullish"}
        if uptrend and price < lows[sl[-1]]:
            return {"mss": "bearish"}
    return {"mss": None}


def fvg_quality(candles):
    """Richer FVG: size, age and fill% of the most recent unfilled gap.

    Returns {direction, size, age, fill_pct} or None.
    """
    if len(candles) < 4:
        return None
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price = candles[-1]["close"]
    # scan back for the most recent 3-candle gap
    for i in range(len(candles) - 1, 2, -1):
        # bullish gap: low[i] > high[i-2]
        if lows[i] > highs[i - 2]:
            gap = lows[i] - highs[i - 2]
            mid = (lows[i] + highs[i - 2]) / 2
            filled = max(0.0, min(1.0, (lows[i] - price) / gap)) if gap else 0.0
            return {"direction": "bullish", "size": round(gap, 3),
                    "age": len(candles) - 1 - i, "fill_pct": round(filled * 100, 1),
                    "mid": round(mid, 3)}
        if highs[i] < lows[i - 2]:
            gap = lows[i - 2] - highs[i]
            mid = (lows[i - 2] + highs[i]) / 2
            filled = max(0.0, min(1.0, (price - highs[i]) / gap)) if gap else 0.0
            return {"direction": "bearish", "size": round(gap, 3),
                    "age": len(candles) - 1 - i, "fill_pct": round(filled * 100, 1),
                    "mid": round(mid, 3)}
    return None
