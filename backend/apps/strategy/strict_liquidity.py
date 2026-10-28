"""Research-only sweep confirmation. Never substitutes for production V1 silently."""
import math


def confirmed_sweep(level, sweep_bar, confirmation_bar, atr, side, *, breach_atr=.05, rejection_atr=.15):
    """Prior level must be fixed before sweep_bar; separate later closed bar confirms.

    Caller is responsible for historical level provenance. Missing timestamps or
    confirmation cannot be upgraded to a confirmed sweep. Thresholds are
    structural hypotheses, not tuned to the supplied journal.
    """
    result = {"confirmed": False, "research_only": True, "side": side}
    try:
        values = [level, atr, sweep_bar["open"], sweep_bar["high"], sweep_bar["low"],
                  sweep_bar["close"], confirmation_bar["close"], sweep_bar["time"], confirmation_bar["time"]]
        if not all(math.isfinite(v) and v > 0 for v in values) or side not in ("buy", "sell"):
            return {**result, "reason": "INVALID_INPUT"}
        if confirmation_bar["time"] <= sweep_bar["time"]:
            return {**result, "reason": "FOLLOW_THROUGH_MISSING"}
        if side == "buy":
            breach = level - sweep_bar["low"] >= breach_atr * atr
            reject = sweep_bar["close"] - sweep_bar["low"] >= rejection_atr * atr
            close_back = sweep_bar["close"] > level
            follow = confirmation_bar["close"] > sweep_bar["high"]
        else:
            breach = sweep_bar["high"] - level >= breach_atr * atr
            reject = sweep_bar["high"] - sweep_bar["close"] >= rejection_atr * atr
            close_back = sweep_bar["close"] < level
            follow = confirmation_bar["close"] < sweep_bar["low"]
        checks = {"actual_breach": breach, "rejection": reject,
                  "close_back": close_back, "structure_follow_through": follow}
        return {**result, "confirmed": all(checks.values()), "checks": checks,
                "reason": "CONFIRMED" if all(checks.values()) else "SWEEP_UNCONFIRMED"}
    except (KeyError, TypeError, ValueError):
        return {**result, "reason": "MISSING_DATA"}


def regime_policy(state):
    policies = {
        "TREND_UP": ["trend_continuation_long", "pullback_long", "breakout_retest_long"],
        "TREND_DOWN": ["trend_continuation_short", "pullback_short", "breakout_retest_short"],
        "RANGE": ["liquidity_sweep_reversal", "range_edge_reversal"],
        "HIGH_VOLATILITY": [], "LOW_VOLATILITY": [], "TRANSITION": []}
    return {"state": state, "allowed_setups": policies.get(state, []),
            "research_only": True, "unknown_blocks": state not in policies,
            "requires": ["risk_verification", "closed_bar_confirmation"]}
