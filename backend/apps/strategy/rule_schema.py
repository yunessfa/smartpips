"""Closed vocabulary + validator for user-authored strategy rules.

Nothing here executes user input. A rule is three fields drawn from fixed
lists (`block`, `operator`) plus a bounded value, and the evaluator in
`rule_engine.py` does nothing but compare numbers and booleans. There is no
expression parser, no eval(), no import by name --- which is the whole reason
the rules are modelled as data rather than as a mini-language.

Every block maps onto something `apps.strategy.engine.run_strategy` already
computes, so a rule can never reference a signal the engine cannot produce.
"""

# ---------------------------------------------------------------- vocabulary

# kind:
#   "state" -> compare against one of `states`
#   "number" -> compare a numeric reading with gt/gte/lt/lte/between
#   "bool"  -> is true / is false
BLOCKS = {
    "market_structure": {
        "kind": "state",
        "label": "Market Structure",
        "states": ["bullish", "bearish", "neutral"],
        "group": "structure",
    },
    "liquidity": {
        "kind": "state",
        "label": "Liquidity",
        "states": ["bullish", "bearish", "neutral"],
        "group": "liquidity",
    },
    "order_flow": {
        "kind": "state",
        "label": "Order Flow",
        "states": ["bullish", "bearish", "neutral"],
        "group": "order_flow",
    },
    "market_regime": {
        "kind": "state",
        "label": "Market Regime",
        "states": ["trending", "ranging", "volatile", "quiet"],
        "group": "regime",
    },
    "ema_fast_vs_slow": {
        "kind": "state",
        "label": "EMA fast vs slow",
        "states": ["above", "below"],
        "group": "ema",
    },
    "price_vs_vwap": {
        "kind": "state",
        "label": "Price vs VWAP",
        "states": ["above", "below"],
        "group": "vwap",
    },
    "rsi": {"kind": "number", "label": "RSI", "min": 0, "max": 100, "group": "rsi"},
    "macd_hist": {"kind": "number", "label": "MACD histogram", "min": -1e6, "max": 1e6, "group": "macd"},
    "atr_pct": {"kind": "number", "label": "ATR % of price", "min": 0, "max": 100, "group": "atr"},
    "volume_ratio": {"kind": "number", "label": "Volume vs average", "min": 0, "max": 50, "group": "volume"},
    "risk_reward": {"kind": "number", "label": "Risk / Reward", "min": 0, "max": 100, "group": "risk"},
    "engine_score": {"kind": "number", "label": "Engine confluence score", "min": 0, "max": 100, "group": "structure"},
    "distance_to_support_pct": {
        "kind": "number", "label": "Distance to support (%)",
        "min": 0, "max": 100, "group": "support_resistance",
    },
    "distance_to_resistance_pct": {
        "kind": "number", "label": "Distance to resistance (%)",
        "min": 0, "max": 100, "group": "support_resistance",
    },
    "fib_retracement_pct": {
        "kind": "number", "label": "Fibonacci retracement (%)",
        "min": 0, "max": 200, "group": "fibonacci",
    },
    "fvg_present": {"kind": "bool", "label": "Fair value gap present", "group": "liquidity"},
    "liquidity_sweep": {"kind": "bool", "label": "Liquidity sweep", "group": "liquidity"},
    "session_active": {"kind": "bool", "label": "High-activity session", "group": "regime"},
}

STATE_OPERATORS = ["is", "is_not"]
NUMBER_OPERATORS = ["gt", "gte", "lt", "lte", "between"]
BOOL_OPERATORS = ["is_true", "is_false"]

# Weight groups the user can distribute 100% across. They intentionally mirror
# the engine's own layers so a weight always means something measurable.
WEIGHT_GROUPS = [
    "structure", "liquidity", "order_flow", "ema", "rsi", "macd", "vwap",
    "atr", "volume", "support_resistance", "fibonacci", "regime", "risk",
]

MAX_RULES = 24

RISK_FIELDS = {
    # field: (type, min, max)
    "risk_per_trade_pct": (float, 0.05, 10.0),
    "max_leverage": (int, 1, 125),
    "max_open_positions": (int, 1, 50),
    "max_daily_loss_usdt": (float, 0.0, 1_000_000.0),
    "min_rr": (float, 0.5, 20.0),
    "max_chase_pct": (float, 0.0, 10.0),
    "trailing_stop": (bool, None, None),
    "partial_tp": (bool, None, None),
}
TP_METHODS = ["fixed_rr", "atr", "structure", "levels"]
SL_METHODS = ["atr", "structure", "fixed_pct"]


class RuleError(ValueError):
    """Raised with a user-facing message when a rule set is malformed."""


# ----------------------------------------------------------------- helpers

def vocabulary():
    """Everything the builder UI needs, so the frontend hard-codes nothing."""
    return {
        "blocks": [
            {
                "key": key,
                "label": meta["label"],
                "kind": meta["kind"],
                "group": meta["group"],
                "states": meta.get("states", []),
                "min": meta.get("min"),
                "max": meta.get("max"),
                "operators": (
                    STATE_OPERATORS if meta["kind"] == "state"
                    else NUMBER_OPERATORS if meta["kind"] == "number"
                    else BOOL_OPERATORS
                ),
            }
            for key, meta in BLOCKS.items()
        ],
        "weight_groups": WEIGHT_GROUPS,
        "tp_methods": TP_METHODS,
        "sl_methods": SL_METHODS,
        "risk_fields": {
            name: {"type": typ.__name__, "min": lo, "max": hi}
            for name, (typ, lo, hi) in RISK_FIELDS.items()
        },
        "max_rules": MAX_RULES,
    }


def _number(value, meta, field):
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise RuleError(f"{field} must be a number.")
    lo, hi = meta.get("min"), meta.get("max")
    if lo is not None and num < lo:
        raise RuleError(f"{field} must be at least {lo}.")
    if hi is not None and num > hi:
        raise RuleError(f"{field} must be at most {hi}.")
    return num


def validate_rules(rules):
    """Return a normalised copy of `rules`, or raise RuleError.

    Unknown keys are dropped rather than stored, so a client cannot smuggle
    extra payload into the JSON column and have it round-trip.
    """
    if rules is None:
        return []
    if not isinstance(rules, list):
        raise RuleError("Rules must be a list.")
    if len(rules) > MAX_RULES:
        raise RuleError(f"A strategy may have at most {MAX_RULES} rules.")

    cleaned = []
    for index, raw in enumerate(rules, start=1):
        if not isinstance(raw, dict):
            raise RuleError(f"Rule {index} is not an object.")
        block = raw.get("block")
        meta = BLOCKS.get(block)
        if meta is None:
            raise RuleError(f"Rule {index}: unknown condition '{block}'.")

        operator = raw.get("operator")
        kind = meta["kind"]
        rule = {"block": block, "operator": operator}

        if kind == "state":
            if operator not in STATE_OPERATORS:
                raise RuleError(f"Rule {index}: operator must be one of {STATE_OPERATORS}.")
            value = raw.get("value")
            if value not in meta["states"]:
                raise RuleError(
                    f"Rule {index}: value must be one of {meta['states']}.")
            rule["value"] = value

        elif kind == "number":
            if operator not in NUMBER_OPERATORS:
                raise RuleError(f"Rule {index}: operator must be one of {NUMBER_OPERATORS}.")
            if operator == "between":
                pair = raw.get("value")
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise RuleError(f"Rule {index}: 'between' needs two values.")
                low = _number(pair[0], meta, f"Rule {index} lower bound")
                high = _number(pair[1], meta, f"Rule {index} upper bound")
                if low > high:
                    raise RuleError(f"Rule {index}: lower bound is above the upper bound.")
                rule["value"] = [low, high]
            else:
                rule["value"] = _number(raw.get("value"), meta, f"Rule {index} value")

        else:  # bool
            if operator not in BOOL_OPERATORS:
                raise RuleError(f"Rule {index}: operator must be one of {BOOL_OPERATORS}.")
            rule["value"] = None

        # Which direction this rule supports. "both" means it is a filter that
        # applies either way (e.g. "regime is trending").
        applies = raw.get("applies_to", "both")
        if applies not in ("both", "long", "short"):
            raise RuleError(f"Rule {index}: applies_to must be both/long/short.")
        rule["applies_to"] = applies

        # A required rule vetoes the signal when unmet, regardless of score.
        rule["required"] = bool(raw.get("required", False))
        cleaned.append(rule)

    return cleaned


def validate_weights(weights):
    """Normalise the weight map. Empty means 'weight every group equally'."""
    if not weights:
        return {}
    if not isinstance(weights, dict):
        raise RuleError("Weights must be an object.")
    cleaned = {}
    for group, value in weights.items():
        if group not in WEIGHT_GROUPS:
            raise RuleError(f"Unknown weight group '{group}'.")
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise RuleError(f"Weight for '{group}' must be a number.")
        if num < 0 or num > 100:
            raise RuleError(f"Weight for '{group}' must be between 0 and 100.")
        if num:
            cleaned[group] = num
    total = sum(cleaned.values())
    # A little slack so the UI's rounding does not reject a valid 99.9 split.
    if cleaned and not (95 <= total <= 105):
        raise RuleError(f"Weights must add up to about 100% (currently {total:g}%).")
    return cleaned


def validate_risk(risk):
    """Validate the strategy's risk block.

    These values are the strategy's *preference*. apps.prefs.RiskLimits is
    applied on top for real orders and always wins --- see
    `effective_risk()` below, which is what callers should use.
    """
    if not risk:
        return {}
    if not isinstance(risk, dict):
        raise RuleError("Risk settings must be an object.")
    cleaned = {}
    for field, value in risk.items():
        if field == "tp_method":
            if value not in TP_METHODS:
                raise RuleError(f"tp_method must be one of {TP_METHODS}.")
            cleaned[field] = value
            continue
        if field == "sl_method":
            if value not in SL_METHODS:
                raise RuleError(f"sl_method must be one of {SL_METHODS}.")
            cleaned[field] = value
            continue
        spec = RISK_FIELDS.get(field)
        if spec is None:
            raise RuleError(f"Unknown risk setting '{field}'.")
        typ, lo, hi = spec
        if typ is bool:
            cleaned[field] = bool(value)
            continue
        try:
            num = typ(value)
        except (TypeError, ValueError):
            raise RuleError(f"'{field}' must be a {typ.__name__}.")
        if lo is not None and num < lo:
            raise RuleError(f"'{field}' must be at least {lo}.")
        if hi is not None and num > hi:
            raise RuleError(f"'{field}' must be at most {hi}.")
        cleaned[field] = num
    return cleaned


def effective_risk(strategy_risk, limits):
    """Combine a strategy's risk preferences with the admin's hard limits.

    The admin ceiling always wins. A strategy asking for 50x when the account
    is capped at 20x gets 20x; a strategy asking for 5x keeps 5x. Returns the
    merged values plus a list of what was clamped, so the UI can be honest
    about why a setting is not being honoured.
    """
    merged = dict(strategy_risk or {})
    clamped = []
    if limits is None:
        return {"risk": merged, "clamped": clamped}

    def clamp(field, ceiling, label):
        value = merged.get(field)
        if value is not None and ceiling is not None and value > ceiling:
            merged[field] = ceiling
            clamped.append({"field": field, "requested": value,
                            "applied": ceiling, "reason": label})

    clamp("max_leverage", getattr(limits, "max_leverage", None), "account leverage limit")
    clamp("max_open_positions", getattr(limits, "max_open_positions", None),
          "account open-position limit")
    daily = getattr(limits, "daily_loss_limit_usdt", None)
    if daily:
        clamp("max_daily_loss_usdt", daily, "account daily loss limit")
    return {"risk": merged, "clamped": clamped}
