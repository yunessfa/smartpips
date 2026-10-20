"""Server-generated entry context. Missing historical evidence stays missing."""
import hashlib
import json
from django.core import signing
from rest_framework.exceptions import ValidationError

SALT = "smartpips.decision.entry.v1"
FIELDS = "strategy_id strategy_name strategy_version engine_version timeframe higher_timeframe signal score conviction grade market_regime session setup_class entry stop_loss take_profit risk_reward atr ema9 ema50 ema200 vwap rsi macd stochastic market_structure liquidity_bias order_flow_bias order_block fvg premium_discount volume_ratio volume_profile reason_codes positive_factors negative_factors".split()


def digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def issue_token(user, symbol, timeframe, decision):
    return signing.dumps({"user": user.pk, "symbol": symbol, "timeframe": timeframe,
                          "decision": decision}, salt=SALT, compress=True)


def read_token(token, user, symbol):
    try:
        value = signing.loads(token, salt=SALT, max_age=180)
        if value["user"] != user.pk or value["symbol"].replace(":PERP", "") != symbol.upper().replace(":PERP", ""):
            raise ValueError("Wrong context")
        return value
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        raise ValidationError("Decision context invalid or expired. Request a fresh analysis.")


def build(trade, analysis=None):
    # No attempt to reconstruct historical indicators from today's active engine.
    context = {k: None for k in FIELDS}
    context.update(strategy_id=trade.strategy_id, strategy_name=trade.strategy_name or None,
                   strategy_version=trade.strategy_version, timeframe=trade.timeframe or None,
                   entry=trade.entry_price, stop_loss=trade.stop_loss, take_profit=trade.take_profit,
                   setup_class=trade.setup_class or None)
    if analysis:
        d = analysis["decision"]
        ind = d.get("indicators") or {}
        context.update({k: d.get(k) for k in ("engine_version", "signal", "score", "conviction", "grade",
            "market_regime", "session", "risk_reward", "atr", "volume_profile")})
        context["timeframe"] = analysis["timeframe"]
        context["higher_timeframe"] = d.get("htf_detail")
        for out, key in {"ema9":"EMA9", "ema50":"EMA50", "ema200":"EMA200", "vwap":"VWAP",
                         "rsi":"RSI", "macd":"MACD_hist", "stochastic":"Stoch", "market_structure":"SMC",
                         "order_flow_bias":"OrderFlow", "liquidity_bias":"LiquiditySweep",
                         "order_block":"OrderBlock", "fvg":"FVG_quality", "premium_discount":"PremiumDiscount"}.items():
            context[out] = ind.get(key)
        context["reason_codes"] = d.get("wait_reasons")
        context["positive_factors"] = d.get("reasons_plain")
        context["negative_factors"] = d.get("explanation_tree", {}).get("blocking_reasons")
    initial_risk = None
    if (trade.entry_price and trade.stop_loss and trade.size and trade.leverage and
            trade.symbol.upper().replace(":PERP", "").endswith("USDT")):
        distance = (trade.entry_price-trade.stop_loss) * (1 if trade.direction == "long" else -1)
        if distance > 0:
            initial_risk = trade.size * trade.leverage / trade.entry_price * distance
    return {"schema_version": 1, "context": context,
            "capture_quality": "server_signed_analysis" if analysis else "entry_fields_only",
            "initial_risk_quote": initial_risk, "initial_risk_basis": "planned_gross_stop_loss_excludes_costs",
            "execution_verified": False, "source": trade.source,
            "analysis_signal_is_not_execution": True}


def validate_binding(analysis, *, strategy_id, strategy_version, timeframe):
    """Client-selected attribution must match the signed server analysis."""
    d = analysis["decision"]
    if (strategy_id != d.get("strategy_id") or strategy_version != d.get("strategy_version")
            or timeframe != analysis.get("timeframe")):
        raise ValidationError("Entry attribution does not match signed analysis.")
