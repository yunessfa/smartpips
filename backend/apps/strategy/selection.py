"""Shared live/backtest configuration gate. It never bypasses base-engine safety."""
from .rule_engine import evaluate
from .rule_schema import validate_risk


def apply_strategy(decision, strategy, version, symbol, timeframe):
    decision["strategy_id"] = strategy.pk
    decision["strategy_version_id"] = version.pk if version else None
    decision["strategy_name"] = strategy.name
    decision["strategy_version"] = version.version if version else None
    market = "metals" if symbol in ("XAUUSD", "XAGUSD") else "crypto"
    mismatch = (not version or strategy.market != market
                or (strategy.symbols and symbol not in strategy.symbols)
                or (strategy.timeframes and timeframe not in strategy.timeframes))
    if mismatch:
        decision.update(signal="wait", confidence="low",
                        reason="Active strategy does not cover this market/symbol/timeframe.")
        return decision
    assessment = evaluate(version, decision)
    decision["strategy_evaluation"] = assessment
    if assessment.get("code") == "invalid_strategy_config":
        decision.update(signal="wait", confidence="low", reason=assessment["reason"])
        return decision
    risk = validate_risk(version.risk)
    if decision.get("signal") in ("buy", "sell"):
        if assessment["signal"].lower() != decision["signal"]:
            decision.update(signal="wait", confidence="low", reason=assessment["reason"])
        elif (decision.get("risk_reward") or 0) < risk.get("min_rr", 0):
            decision.update(signal="wait", confidence="low", reason="Below active strategy minimum R:R.")
    decision["strategy_risk"] = risk
    decision["strategy_policy"] = "Filter on the base engine; never bypasses its safety gates."
    decision["risk_settings_not_executed"] = [key for key in (
        "tp_method", "sl_method", "trailing_stop", "partial_tp", "max_daily_loss_usdt", "max_chase_pct")
        if key in risk]
    return decision
