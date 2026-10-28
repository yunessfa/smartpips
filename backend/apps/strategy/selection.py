"""Shared live/backtest configuration gate.

Two modes (version.risk["signal_source"]):
  * engine_filter (default) — the base engine proposes BUY/SELL and the active
    strategy may only confirm or veto it. User rules can never create a signal.
  * strategy — the strategy's own rules choose the direction. The engine still
    supplies every reading (volume profile, VWAP, structure…), the data-quality
    gate, the news guard and risk sizing (applied in decide()), and the
    timeframe-sized scalp plan (stop/targets/fee gate) for that direction. The
    base engine's score/conviction/HTF gates do NOT apply in this mode.
"""
from .rule_engine import evaluate
from .rule_schema import validate_risk


def _mismatch(strategy, version, symbol, timeframe):
    market = "metals" if symbol.replace(":PERP", "") in ("XAUUSD", "XAGUSD") else "crypto"
    return (not version or strategy.market != market
            or (strategy.symbols and symbol not in strategy.symbols)
            or (strategy.timeframes and timeframe not in strategy.timeframes))


def _stamp(decision, strategy, version):
    decision["strategy_id"] = strategy.pk
    decision["strategy_version_id"] = version.pk if version else None
    decision["strategy_name"] = strategy.name
    decision["strategy_version"] = version.version if version else None


def _finish(decision, risk):
    decision["strategy_risk"] = risk
    decision["risk_settings_not_executed"] = [key for key in (
        "tp_method", "sl_method", "trailing_stop", "partial_tp", "max_daily_loss_usdt", "max_chase_pct")
        if key in risk]
    return decision


def apply_strategy(decision, strategy, version, symbol, timeframe, candles=None):
    _stamp(decision, strategy, version)
    if _mismatch(strategy, version, symbol, timeframe):
        decision.update(signal="wait", confidence="low",
                        reason="Active strategy does not cover this market/symbol/timeframe.")
        return decision
    try:
        risk = validate_risk(version.risk)
    except Exception as exc:  # invalid stored config fails closed
        decision.update(signal="wait", confidence="low", reason=f"Invalid strategy configuration: {exc}")
        return decision
    if risk.get("signal_source") == "strategy":
        return _finish(_standalone(decision, version, symbol, timeframe, candles, risk), risk)

    assessment = evaluate(version, decision)
    decision["strategy_evaluation"] = assessment
    decision["signal_source"] = "engine_filter"
    if assessment.get("code") == "invalid_strategy_config":
        decision.update(signal="wait", confidence="low", reason=assessment["reason"])
        return decision
    if decision.get("signal") in ("buy", "sell"):
        if assessment["signal"].lower() != decision["signal"]:
            decision.update(signal="wait", confidence="low", reason=assessment["reason"])
        elif (decision.get("risk_reward") or 0) < risk.get("min_rr", 0):
            decision.update(signal="wait", confidence="low", reason="Below active strategy minimum R:R.")
    decision["strategy_policy"] = "Filter on the base engine; never bypasses its safety gates."
    return _finish(decision, risk)


def _standalone(decision, version, symbol, timeframe, candles, risk):
    """The user's rules decide the direction; the engine supplies the plan."""
    from .scalp_plan import build_plan

    decision["signal_source"] = "strategy"
    decision["strategy_policy"] = ("Your strategy's rules choose the direction. Data-quality, news and "
                                   "account-risk gates and the timeframe-sized plan still apply.")
    base_signal = decision.get("signal")
    decision["base_engine_signal"] = base_signal
    features = decision.get("rule_features") or {}
    price = features.get("price") or decision.get("price_at_signal")
    atr = decision.get("atr")
    if decision.get("data_quality") in ("invalid", "stale", "none", "ticks", "insufficient", "price_mismatch") \
            or not features or not candles or not price or not atr:
        decision.update(signal="wait", confidence="low",
                        reason="Strategy mode: market readings unavailable; no signal.")
        return decision

    want = {"both": ("buy", "sell"), "long": ("buy",), "short": ("sell",)}[version.strategy.direction]
    best = None
    for side in want:
        plan = build_plan(side, symbol, timeframe, candles, price, atr,
                          key_levels=((decision.get("indicators") or {}).get("KeyLevels") or None))
        if "reject" in plan:
            continue
        candidate = {**decision, "signal": side, "entry": plan["entry"], "stop_loss": plan["stop"],
                     "take_profit": plan["take_profit"], "risk_reward": plan["risk_reward"]}
        assessment = evaluate(version, candidate)
        if assessment.get("signal", "").lower() == side and plan["risk_reward"] >= risk.get("min_rr", 0):
            if best is None or assessment["confidence"] > best[2]["confidence"]:
                best = (side, plan, assessment)
            elif assessment["confidence"] == best[2]["confidence"]:
                best = ("tie", None, assessment)
    if best is None or best[0] == "tie":
        probe = evaluate(version, {**decision, "signal": "wait"})
        decision["strategy_evaluation"] = probe
        decision.update(signal="wait", confidence="low", entry=None, stop_loss=None, take_profit=None,
                        tp_levels=None, entry_plan=None,
                        reason=("Strategy mode: both directions qualify equally — no signal."
                                if best else f"Strategy mode: {probe.get('reason') or 'conditions not met'}"))
        return decision

    side, plan, assessment = best
    rnd = lambda x: float(f"{x:.10g}")
    decision.update(
        signal=side, strategy_evaluation=assessment,
        confidence="high" if assessment["confidence"] >= 85 else "medium",
        entry=rnd(plan["entry"]), stop_loss=rnd(plan["stop"]), take_profit=rnd(plan["take_profit"]),
        risk_reward=plan["risk_reward"], net_risk_reward=plan["net_rr"], stop_pct=plan["stop_pct"],
        est_round_trip_cost_pct=plan["est_round_trip_cost_pct"], tp_source=plan["tp_source"],
        entry_plan={**plan["entry_plan"], "price": rnd(plan["entry_plan"]["price"])},
        tp_levels=[{"price": rnd(p), "pct": pct, "r": r}
                   for p, pct, r in zip(plan["tp_prices"], (40, 35, 25), plan["tp_r"])],
        reason=f"Strategy mode: {assessment['reason']}",
        wait_reasons=[],
    )
    return decision
