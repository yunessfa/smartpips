"""SMART EXIT ENGINE.

Most trading systems put all their effort into the entry and use a fixed TP/SL.
But for scalping, *how you exit* usually matters more than the entry. This module
looks at a live open position and decides whether to:

  - move the stop up to lock in profit (trailing stop, ATR / swing based),
  - take partial profit because momentum is fading,
  - exit fully because the market structure flipped against the trade.

It returns a plain, explainable recommendation — it never closes anything by
itself; the caller (or the user) decides.
"""
from .engine import atr, swing_levels, _pivots
from .orderflow import order_flow, market_structure_shift, liquidity_sweep


def evaluate_exit(direction, entry_price, current_price, stop_loss, take_profit,
                  candles):
    """Decide what to do with an OPEN trade right now.

    direction: "long" or "short"
    Returns a dict:
      {
        action: "hold" | "trail" | "partial" | "exit",
        new_stop: float|None,        # suggested trailed stop (if action == trail)
        reasons: [str, ...],         # human-readable, localizable keys
        urgency: "low"|"medium"|"high",
        progress_pct: float,         # how far to TP (0-100), for the UI bar
      }
    """
    if not candles or len(candles) < 20 or not current_price or not entry_price:
        return {"action": "hold", "new_stop": None, "reasons": [],
                "urgency": "low", "progress_pct": 0.0}

    is_long = direction == "long"
    a = atr(candles, 14) or (current_price * 0.0008)
    reasons = []
    action = "hold"
    new_stop = None
    urgency = "low"

    # ---- progress toward target (for the UI progress bar) ----
    progress_pct = 0.0
    if take_profit and entry_price != take_profit:
        moved = (current_price - entry_price) if is_long else (entry_price - current_price)
        total = abs(take_profit - entry_price)
        progress_pct = max(0.0, min(100.0, (moved / total) * 100)) if total else 0.0

    # current profit in price terms and in R (risk units)
    profit = (current_price - entry_price) if is_long else (entry_price - current_price)
    risk = abs(entry_price - stop_loss) if stop_loss else a
    r_mult = (profit / risk) if risk else 0.0

    # ---- 1) MSS against the trade => strongest exit signal ----
    mss = market_structure_shift(candles)
    mss_dir = mss.get("mss")
    if mss_dir and ((is_long and mss_dir == "bearish") or (not is_long and mss_dir == "bullish")):
        return {"action": "exit", "new_stop": None,
                "reasons": ["mss_against"], "urgency": "high",
                "progress_pct": round(progress_pct, 1)}

    # ---- 2) Order flow flips/weakens against the trade ----
    flow = order_flow(candles)
    flow_bias = flow.get("bias") or 0
    want = 1 if is_long else -1
    if flow_bias == -want and r_mult > 0.3:
        # in profit but flow turned against us -> bank part of it
        action = "partial"
        urgency = "medium"
        reasons.append("flow_weakening")

    # ---- 3) Opposite-side liquidity swept => move likely exhausted ----
    sweep = liquidity_sweep(candles)
    if (sweep.get("bias") or 0) == -want and r_mult > 0.5:
        action = "exit" if action != "exit" else action
        urgency = "high"
        reasons.append("opp_liquidity_taken")

    # ---- 4) Trailing stop once the trade is meaningfully in profit ----
    #     Only ever tightens the stop in the trade's favour, never loosens it.
    if r_mult >= 1.0:
        highs_idx, lows_idx = _pivots(candles, k=2)
        if is_long and lows_idx:
            recent_low = min(candles[i]["low"] for i in lows_idx[-3:])
            trail = max(entry_price, recent_low - a * 0.3)  # never below break-even
            if stop_loss is None or trail > stop_loss:
                new_stop = trail
        elif (not is_long) and highs_idx:
            recent_high = max(candles[i]["high"] for i in highs_idx[-3:])
            trail = min(entry_price, recent_high + a * 0.3)
            if stop_loss is None or trail < stop_loss:
                new_stop = trail
        if new_stop is not None and action == "hold":
            action = "trail"
            reasons.append("trailing_to_lock_profit")

    # ---- 5) Near target: tighten and warn ----
    if progress_pct >= 80 and action == "hold":
        action = "trail"
        urgency = "medium"
        reasons.append("near_target")
        # pull stop to ~half the move to protect the gain
        half = entry_price + profit * 0.5 * (1 if is_long else -1)
        if is_long and (stop_loss is None or half > stop_loss):
            new_stop = half
        elif (not is_long) and (stop_loss is None or half < stop_loss):
            new_stop = half

    return {
        "action": action,
        "new_stop": round(new_stop, 3) if new_stop else None,
        "reasons": reasons,
        "urgency": urgency,
        "progress_pct": round(progress_pct, 1),
        "r_multiple": round(r_mult, 2),
    }
