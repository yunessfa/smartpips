"""Scalp trade geometry: entry plan, stop, targets — sized to the timeframe.

Why this exists (2026-10 audit, measured on real BTC 1m data, 2025):
  * The old geometry used a fixed 0.8% crypto stop floor on EVERY timeframe,
    widened stops to the 40-bar extreme, and multiplied targets by 3R whenever
    ATR% > 0.035% (i.e. practically always for crypto). On 5m BTC that meant a
    median ~1.2% stop and ~3.7% target: targets were hit 1.8% of the time and
    81% of trades just timed out after four hours.
  * Signals fired a median 4.8 ATR away from the 20-bar extreme — i.e. after
    most of the move — and the "over-extended" gate (2.2 ATR from EMA9)
    almost never triggered.

This module replaces that block with:
  * timeframe-aware stop floors/caps (in ATR and %), with a FEE floor so
    commissions never eat most of the risk unit;
  * the stop placed behind the nearest swing pivot, never the window extreme;
    when structure needs a stop wider than the cap, the setup is rejected
    instead of silently widening risk;
  * anti-chase: when price is already stretched from EMA21 / the leg origin, the
    plan becomes a LIMIT entry at the pullback level with an expiry, instead of
    a market entry at the top of the move;
  * targets at the nearest opposing liquidity (swing high/low, PDH/PDL, Asia
    high/low) between 1.2R and 2R, otherwise 1.5R; TP1 = 1R; TP3 capped 2.5R;
  * a cost gate: the main target must still be >= 1R AFTER estimated
    round-trip fees and slippage.

It does NOT claim profitability. Measured edge is reported separately by the
backtests; this module only makes the plan executable and honest.
"""
import math

# per-timeframe parameters
TF_PARAMS = {
    #       min stop (ATR), max stop (ATR), crypto fee-floor %, metal floor %, limit expiry (bars)
    "1m": dict(min_atr=1.2, max_atr=4.0, crypto_floor=0.25, xau_floor=0.06, xag_floor=0.09, expiry=10),
    "5m": dict(min_atr=1.0, max_atr=3.0, crypto_floor=0.35, xau_floor=0.10, xag_floor=0.14, expiry=6),
    "15m": dict(min_atr=1.0, max_atr=2.8, crypto_floor=0.50, xau_floor=0.15, xag_floor=0.20, expiry=4),
    "1h": dict(min_atr=1.0, max_atr=2.5, crypto_floor=0.80, xau_floor=0.25, xag_floor=0.35, expiry=3),
    "4h": dict(min_atr=1.0, max_atr=2.5, crypto_floor=1.20, xau_floor=0.40, xag_floor=0.55, expiry=2),
}
# Cost assumptions per round trip.
#   crypto  — Bitunix futures VIP0: taker 0.06%, maker 0.02%, + 0.02% slippage.
#   metals  — broker/CFD spread-style costs (MT5/cTrader): ~0.015% per side,
#             + 0.01% slippage. NOT validated on historical gold data (none was
#             available to this audit) — re-check against your broker's spread.
TAKER_FEE = 0.0006
MAKER_FEE = 0.0002
SLIPPAGE = 0.0002
COSTS = {
    "crypto": dict(taker=TAKER_FEE, maker=MAKER_FEE, slip=SLIPPAGE),
    "metal": dict(taker=0.00015, maker=0.00015, slip=0.0001),
}
CHASE_EMA_ATR = 1.5        # price further than this from EMA21 (ATR) = stretched
CHASE_LEG_ATR = 3.0        # or the move from the 20-bar extreme is larger than this
MIN_NET_RR = 1.0           # main target must still pay >= 1R after costs
TP_MIN_R, TP_MAX_R, TP_DEFAULT_R = 1.2, 2.0, 1.5


def _pivots(candles, k=2):
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    sh, sl = [], []
    for i in range(k, len(candles) - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            sh.append(highs[i])
        if lows[i] == min(lows[i - k:i + k + 1]):
            sl.append(lows[i])
    return sh, sl


def _ema(values, period):
    if not values:
        return None
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _floor_pct(symbol, timeframe):
    p = TF_PARAMS.get(timeframe, TF_PARAMS["5m"])
    base = symbol.upper().replace(":PERP", "")
    if base == "XAUUSD":
        return p["xau_floor"] / 100
    if base == "XAGUSD":
        return p["xag_floor"] / 100
    return p["crypto_floor"] / 100


def build_plan(direction, symbol, timeframe, candles, price, atr, key_levels=None):
    """Return a plan dict or {"reject": (code, message)}.

    direction: "buy" | "sell"; candles: CLOSED bars of the trading timeframe;
    price: reference (live) price; atr: ATR of the trading timeframe.
    """
    p = TF_PARAMS.get(timeframe, TF_PARAMS["5m"])
    want = 1 if direction == "buy" else -1
    if not candles or not price or not atr or atr <= 0:
        return {"reject": ("plan_unavailable", "not enough data to place stop/targets")}
    closes = [c["close"] for c in candles]
    e21 = _ema(closes[-120:], 21)
    window = candles[-20:]
    lo20 = min(c["low"] for c in window)
    hi20 = max(c["high"] for c in window)

    # ---- 1) anti-chase: market entry only near value, else pullback limit ----
    stretch_ema = ((price - e21) * want) / atr if e21 else 0.0
    stretch_leg = ((price - lo20) if want > 0 else (hi20 - price)) / atr
    chasing = stretch_ema > CHASE_EMA_ATR or stretch_leg > CHASE_LEG_ATR
    entry_type = "market"
    entry = price
    entry_reason = "price is near value (EMA21) — market entry acceptable"
    if chasing:
        leg_mid = (hi20 + lo20) / 2
        # pullback level: the nearer of EMA21 and the 50% of the 20-bar leg,
        # but never closer than 0.5 ATR from price (otherwise it is not a pullback)
        cands = [x for x in (e21, leg_mid) if x and (price - x) * want >= 0.5 * atr]
        if not cands:
            return {"reject": ("chasing", "move already extended and no clean pullback level — wait")}
        entry = max(cands) if want > 0 else min(cands)
        entry_type = "limit"
        entry_reason = (f"price already {stretch_ema:.1f} ATR from EMA21 / {stretch_leg:.1f} ATR into the leg — "
                        "do not chase; limit at pullback")

    # ---- 2) stop behind the nearest swing pivot, bounded by TF floor/cap ----
    sh, sl_piv = _pivots(candles[-60:], 2)
    buf = 0.3 * atr
    if want > 0:
        below = [x for x in sl_piv if x < entry - 0.25 * atr]
        struct = (entry - (max(below) - buf)) if below else None
    else:
        above = [x for x in sh if x > entry + 0.25 * atr]
        struct = ((min(above) + buf) - entry) if above else None
    floor_dist = max(p["min_atr"] * atr, entry * _floor_pct(symbol, timeframe))
    cap_dist = max(p["max_atr"] * atr, floor_dist * 1.25)
    stop_dist = max(struct or 0.0, floor_dist)
    if struct and struct > cap_dist:
        return {"reject": ("stop_too_wide", f"structure needs a {struct / entry * 100:.2f}% stop — too wide for a "
                                            f"{timeframe} scalp; wait for a tighter setup")}
    stop = entry - want * stop_dist

    # ---- 3) costs: what R must the target reach to still pay >= 1R net? ----
    k = COSTS["metal" if symbol.upper().replace(":PERP", "") in ("XAUUSD", "XAGUSD") else "crypto"]
    fee_in = k["maker"] if entry_type == "limit" else k["taker"]
    cost = entry * (fee_in + k["maker"] + k["slip"])          # winner path (TP is a resting order)
    cost_stop = entry * (fee_in + k["taker"] + k["slip"])     # loser path (stop = market)
    r_needed = (MIN_NET_RR * (stop_dist + cost_stop) + cost) / stop_dist
    lo_r = max(TP_MIN_R, r_needed)
    if lo_r > TP_MAX_R:
        return {"reject": ("fees_vs_target", f"fees need a {r_needed:.2f}R target — beyond a {timeframe} "
                                             "scalp's reach; not worth it")}

    # ---- 4) targets at nearby opposing liquidity ----
    levels = []
    if want > 0:
        levels += [x for x in sh if x > entry]
        levels += [v for k, v in (key_levels or {}).items() if k in ("PDH", "AH") and v and v > entry]
    else:
        levels += [x for x in sl_piv if x < entry]
        levels += [v for k, v in (key_levels or {}).items() if k in ("PDL", "AL") and v and v < entry]
    r_of = lambda lv: abs(lv - entry) / stop_dist
    in_band = sorted((r_of(lv), lv) for lv in levels if lo_r <= r_of(lv) <= TP_MAX_R)
    if in_band:
        main_r, tp_source = in_band[0][0], "liquidity"
    else:
        main_r, tp_source = max(TP_DEFAULT_R, lo_r), "r_multiple"
    tp_main = entry + want * stop_dist * main_r
    r1, r3 = 1.0, min(TP_MAX_R + 0.5, max(main_r * 1.5, main_r + 0.5))
    tps = [entry + want * stop_dist * r for r in (r1, main_r, r3)]
    net_rr = (abs(tp_main - entry) - cost) / (stop_dist + cost_stop)

    expiry = p["expiry"] if entry_type == "limit" else 0
    return {
        "entry": entry, "stop": stop, "take_profit": tp_main, "tp_prices": tps,
        "tp_r": [round(r1, 2), round(main_r, 2), round(r3, 2)],
        "risk_reward": round(main_r, 2), "net_rr": round(net_rr, 2),
        "stop_pct": round(stop_dist / entry * 100, 3),
        "est_round_trip_cost_pct": round((fee_in + k["taker"] + k["slip"]) * 100, 3),
        "tp_source": tp_source,
        "entry_plan": {
            "type": entry_type, "price": entry, "expiry_bars": expiry,
            "reason": entry_reason,
            "stretch_ema21_atr": round(stretch_ema, 2), "stretch_leg_atr": round(stretch_leg, 2),
            "valid_for_bars": expiry,
        },
    }
