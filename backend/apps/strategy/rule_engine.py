"""Evaluate a validated strategy configuration against engine output.

This module is deliberately dumb: it reads numbers and strings out of the
dictionary that `apps.strategy.engine.run_strategy` already returns, compares
them to the user's rules, and produces a weighted confidence. It never touches
candles itself, so the deterministic engine remains the single source of truth
for what the market is doing --- a strategy only decides what to make of it.

Nothing user-supplied is executed. Operators are looked up in a fixed dict.
"""

from .rule_schema import BLOCKS

WAIT, BUY, SELL = "WAIT", "BUY", "SELL"


def _num(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bias(value):
    """Normalise the many ways the engine expresses a directional lean."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 0:
            return "bullish"
        if value < 0:
            return "bearish"
        return "neutral"
    text = str(value).strip().lower()
    if text in ("bull", "bullish", "long", "up", "buy"):
        return "bullish"
    if text in ("bear", "bearish", "short", "down", "sell"):
        return "bearish"
    if text in ("neutral", "flat", "none", "wait", ""):
        return "neutral"
    return text


def _first(source, *keys):
    """Read the first key that is present and not None.

    The engine has grown over time and reports some readings under more than
    one name depending on the code path; probing a few aliases keeps the rule
    layer working without having to modify the engine.
    """
    for key in keys:
        if isinstance(source, dict) and source.get(key) is not None:
            return source[key]
    return None


def extract_features(analysis):
    """Map raw engine output onto the rule vocabulary.

    Missing readings stay None. A rule against a reading the engine did not
    produce counts as "not met" rather than raising --- an incomplete data
    window should make a strategy quieter, never crash the scan.
    """
    analysis = analysis or {}
    detail = analysis.get("detail") if isinstance(analysis.get("detail"), dict) else {}

    def read(*keys):
        return _first(analysis, *keys) if _first(analysis, *keys) is not None \
            else _first(detail, *keys)

    features = {}

    features["market_structure"] = _bias(read("structure", "market_structure", "mss", "bias"))
    features["liquidity"] = _bias(read("liquidity", "liquidity_bias", "sweep_bias"))
    features["order_flow"] = _bias(read("order_flow", "orderflow", "of_bias", "delta_bias"))

    regime = read("regime", "market_regime")
    if isinstance(regime, dict):
        regime = _first(regime, "state", "name", "label", "regime")
    features["market_regime"] = str(regime).strip().lower() if regime is not None else None

    ema_fast = _num(read("ema_fast", "ema9", "ema_9"))
    ema_slow = _num(read("ema_slow", "ema50", "ema_50"))
    if ema_fast is not None and ema_slow is not None:
        features["ema_fast_vs_slow"] = "above" if ema_fast > ema_slow else "below"
    else:
        features["ema_fast_vs_slow"] = _bias(read("ema_bias")) and (
            "above" if _bias(read("ema_bias")) == "bullish" else "below")

    price = _num(read("price", "live_price", "close", "entry"))
    vwap = _num(read("vwap"))
    if price is not None and vwap is not None:
        features["price_vs_vwap"] = "above" if price > vwap else "below"
    else:
        features["price_vs_vwap"] = None

    features["rsi"] = _num(read("rsi", "rsi14", "rsi_14"))
    features["macd_hist"] = _num(read("macd_hist", "macd_histogram", "macdh"))
    features["engine_score"] = _num(read("score", "confidence"))

    atr = _num(read("atr", "atr14"))
    atr_pct = _num(read("atr_pct", "atr_percent"))
    if atr_pct is None and atr is not None and price:
        atr_pct = atr / price * 100
    features["atr_pct"] = atr_pct

    features["volume_ratio"] = _num(read("volume_ratio", "vol_ratio", "rvol"))

    rr = _num(read("rr", "risk_reward", "r_multiple"))
    if rr is None:
        entry = _num(read("entry", "price"))
        stop = _num(read("stop_loss", "sl"))
        target = _num(read("take_profit", "tp", "tp1"))
        if entry is not None and stop is not None and target is not None:
            risk = abs(entry - stop)
            if risk > 0:
                rr = abs(target - entry) / risk
    features["risk_reward"] = rr

    support = _num(read("support", "nearest_support"))
    resistance = _num(read("resistance", "nearest_resistance"))
    features["distance_to_support_pct"] = (
        abs(price - support) / price * 100 if price and support else None)
    features["distance_to_resistance_pct"] = (
        abs(resistance - price) / price * 100 if price and resistance else None)

    features["fib_retracement_pct"] = _num(read("fib_retracement", "fib_pct"))

    fvg = read("fvg", "fvg_present", "imbalance")
    features["fvg_present"] = None if fvg is None else bool(fvg)
    sweep = read("sweep", "liquidity_sweep", "swept")
    features["liquidity_sweep"] = None if sweep is None else bool(sweep)
    session = read("session", "session_active")
    if isinstance(session, str):
        features["session_active"] = session.strip().lower() not in ("", "dead", "off", "closed", "quiet")
    else:
        features["session_active"] = None if session is None else bool(session)

    return features


def _check(rule, features):
    """Return True / False / None (None = the reading is unavailable)."""
    block = rule["block"]
    meta = BLOCKS[block]
    actual = features.get(block)
    if actual is None:
        return None

    operator = rule["operator"]
    expected = rule.get("value")

    if meta["kind"] == "state":
        if operator == "is":
            return actual == expected
        return actual != expected

    if meta["kind"] == "number":
        if operator == "between":
            low, high = expected
            return low <= actual <= high
        return {
            "gt": actual > expected,
            "gte": actual >= expected,
            "lt": actual < expected,
            "lte": actual <= expected,
        }[operator]

    return actual is True if operator == "is_true" else actual is False


def _score_direction(rules, weights, features, direction):
    """Weighted pass rate for one direction, plus per-rule detail."""
    applicable = [r for r in rules if r["applies_to"] in ("both", direction)]
    if not applicable:
        return {"confidence": 0.0, "checks": [], "vetoed": False, "veto_reason": ""}

    total_weight = 0.0
    earned = 0.0
    checks = []
    vetoed = False
    veto_reason = ""

    for rule in applicable:
        group = BLOCKS[rule["block"]]["group"]
        # An unweighted group still counts, otherwise adding a rule the user
        # did not weight would silently do nothing.
        weight = float(weights.get(group, 0)) if weights else 0.0
        if not weight:
            weight = 100.0 / len(applicable)

        result = _check(rule, features)
        checks.append({
            "block": rule["block"],
            "label": BLOCKS[rule["block"]]["label"],
            "operator": rule["operator"],
            "value": rule.get("value"),
            "required": rule["required"],
            "actual": features.get(rule["block"]),
            "passed": result,
        })

        total_weight += weight
        if result is True:
            earned += weight
        elif rule["required"] and result is False:
            # A required rule that is definitively unmet kills the signal. A
            # required rule with NO data does not: absent data is not evidence
            # against, it just cannot contribute confidence.
            vetoed = True
            veto_reason = BLOCKS[rule["block"]]["label"]

    confidence = (earned / total_weight * 100) if total_weight else 0.0
    return {"confidence": round(confidence, 1), "checks": checks,
            "vetoed": vetoed, "veto_reason": veto_reason}


def evaluate(version, analysis):
    """Run one StrategyVersion against one engine analysis dict.

    Returns the decision plus the full reasoning, so the UI can show *why* a
    strategy said WAIT instead of only showing the verdict.
    """
    rules = version.rules or []
    weights = version.weights or {}
    strategy = version.strategy
    min_confidence = float(version.min_confidence or 0)

    features = extract_features(analysis)

    directions = []
    if strategy.direction in ("both", "long"):
        directions.append("long")
    if strategy.direction in ("both", "short"):
        directions.append("short")

    scored = {d: _score_direction(rules, weights, features, d) for d in directions}

    best_direction, best = None, None
    for direction, result in scored.items():
        if result["vetoed"]:
            continue
        if best is None or result["confidence"] > best["confidence"]:
            best_direction, best = direction, result

    if best is None:
        blocked = next((r["veto_reason"] for r in scored.values() if r["vetoed"]), "")
        return {
            "signal": WAIT,
            "direction": None,
            "confidence": 0.0,
            "min_confidence": min_confidence,
            "reason": f"Required condition not met: {blocked}" if blocked
                      else "No direction is enabled for this strategy.",
            "checks": [],
            "features": features,
            "strategy": strategy.name,
            "version": version.version,
        }

    meets = best["confidence"] >= min_confidence
    signal = (BUY if best_direction == "long" else SELL) if meets else WAIT
    if meets:
        reason = (f"{len([c for c in best['checks'] if c['passed'] is True])}"
                  f"/{len(best['checks'])} conditions met at "
                  f"{best['confidence']:g}% (needs {min_confidence:g}%).")
    else:
        reason = (f"Confidence {best['confidence']:g}% is below the "
                  f"{min_confidence:g}% required by this strategy.")

    return {
        "signal": signal,
        "direction": best_direction,
        "confidence": best["confidence"],
        "min_confidence": min_confidence,
        "reason": reason,
        "checks": best["checks"],
        "features": features,
        "strategy": strategy.name,
        "version": version.version,
    }
