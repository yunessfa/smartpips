"""
Key daily/session liquidity levels for gold: Previous Day High/Low (PDH/PDL) and
Asian session High/Low (AH/AL). Stop hunts cluster around these, so price tagging
one and reversing is a high-quality signal.

Works from the candle timestamps (`time` = unix seconds, which MT5/cTrader send).
If candles have no timestamps we return None gracefully (no effect on the score).
All bucketing is done in UTC. Asian session = 00:00-07:00 UTC.
"""
from datetime import datetime, timezone


def _ts(c):
    t = c.get("time")
    if not t:
        return None
    try:
        return datetime.fromtimestamp(int(t), tz=timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def key_levels(candles):
    """Return {PDH,PDL,AH,AL} from candle history, or {} if timestamps are missing."""
    stamped = [(c, _ts(c)) for c in candles]
    stamped = [(c, d) for c, d in stamped if d is not None]
    if len(stamped) < 20:
        return {}

    today = stamped[-1][1].date()
    prev_day_highs, prev_day_lows = [], []
    asian_highs, asian_lows = [], []

    # find the most recent FULL previous day
    days = sorted({d.date() for _, d in stamped})
    prev_day = days[-2] if len(days) >= 2 else None

    for c, d in stamped:
        if prev_day and d.date() == prev_day:
            prev_day_highs.append(c["high"])
            prev_day_lows.append(c["low"])
        # Asian session of the CURRENT day (00:00-07:00 UTC)
        if d.date() == today and d.hour < 7:
            asian_highs.append(c["high"])
            asian_lows.append(c["low"])

    out = {}
    if prev_day_highs:
        out["PDH"] = max(prev_day_highs)
        out["PDL"] = min(prev_day_lows)
    if asian_highs:
        out["AH"] = max(asian_highs)
        out["AL"] = min(asian_lows)
    return out


def level_interaction(candles, atr=None):
    """Did price just sweep one of the key levels and reverse? Returns bias + which.

    Bullish = swept below PDL/AL and closed back above (sell-side liquidity grab).
    Bearish = swept above PDH/AH and closed back below.
    """
    out = {"bias": 0, "level": None, "levels": {}}
    levels = key_levels(candles)
    if not levels:
        return out
    if not atr:
        # cheap ATR proxy from recent candle ranges
        recent = candles[-15:]
        atr = sum(c["high"] - c["low"] for c in recent) / len(recent) if recent else 0
    if not atr:
        return out
    out["levels"] = {k: round(v, 3) for k, v in levels.items()}

    price = candles[-1]["close"]
    recent = candles[-3:]
    rlow = min(c["low"] for c in recent)
    rhigh = max(c["high"] for c in recent)
    tol = atr * 0.6

    for name in ("PDL", "AL"):
        lvl = levels.get(name)
        if lvl and rlow <= lvl + tol and price > lvl:
            out["bias"] = 1
            out["level"] = f"{name} sweep"
            return out
    for name in ("PDH", "AH"):
        lvl = levels.get(name)
        if lvl and rhigh >= lvl - tol and price < lvl:
            out["bias"] = -1
            out["level"] = f"{name} sweep"
            return out
    return out
