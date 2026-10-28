import math
from rest_framework.exceptions import ValidationError
from apps.strategy.config_models import Strategy


def order_context(user, data, symbol):
    context = {}
    if data.get("decision_token"):
        from .snapshots import read_token
        context["_entry_analysis_context"] = read_token(data["decision_token"], user, symbol)
    tf = data.get("timeframe")
    if tf:
        from apps.strategy.backtest import TF_SECONDS
        if tf not in TF_SECONDS:
            raise ValidationError("Invalid entry timeframe.")
        context["timeframe"] = tf
    score = data.get("confidence")
    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise ValidationError("Invalid entry score.")
        if not math.isfinite(score) or not 0 <= score <= 100:
            raise ValidationError("Invalid entry score.")
        context["confidence"] = score
    sid = data.get("strategy_id")
    if not sid:
        if context.get("_entry_analysis_context"):
            from .snapshots import validate_binding
            validate_binding(context["_entry_analysis_context"], strategy_id=None, strategy_version=None, timeframe=tf)
        return context
    try:
        strategy = Strategy.objects.filter(pk=int(sid), archived=False).first()
    except (ValueError, TypeError):
        raise ValidationError("Invalid strategy.")
    if not strategy or strategy.user_id not in (None, user.pk):
        raise ValidationError("Unknown strategy.")
    number = data.get("strategy_version")
    try:
        version = (strategy.versions.filter(version=int(number)).first()
                   if number is not None else strategy.current_version())
    except (ValueError, TypeError):
        raise ValidationError("Invalid strategy version.")
    analysis_symbol = data.get("analysis_symbol") or symbol
    if (not isinstance(analysis_symbol, str)
            or analysis_symbol.replace(":PERP", "") != symbol.replace(":PERP", "")
            or strategy.market != ("metals" if symbol in ("XAUUSD","XAGUSD") else "crypto")
            or not version or (strategy.symbols and analysis_symbol not in strategy.symbols)
            or (strategy.timeframes and tf not in strategy.timeframes)):
        raise ValidationError("Strategy does not cover this symbol/timeframe/version.")
    context.update(strategy=strategy, strategy_name=strategy.name,
                   strategy_version=version.version)
    if context.get("_entry_analysis_context"):
        from .snapshots import validate_binding
        validate_binding(context["_entry_analysis_context"], strategy_id=strategy.pk, strategy_version=version.version, timeframe=tf)
    return context