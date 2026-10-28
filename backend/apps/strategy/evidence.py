"""Shadow evidence: bounded correlated families; not calibrated probability.

V1 execution thresholds/weights remain untouched until prospective/OOS testing.
Every absent family is unknown, not a manufactured neutral/positive vote.
"""
import math
ENGINE_VERSION = "smartpips-v1+audit-foundation-1"
FAMILIES = ("TREND", "STRUCTURE", "LIQUIDITY", "ORDER_FLOW", "MOMENTUM",
            "LOCATION", "VOLATILITY", "SESSION", "RISK")


def bounded_family_model(votes):
    families = {}
    for family in FAMILIES:
        values = [float(v) for v in votes.get(family, [])
                  if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
        # Multiple correlated votes share ONE family budget, not independent weights.
        contribution = max(-1., min(1., sum(values) / len(values))) if values else None
        families[family] = {"value": contribution, "observations": len(values), "budget": 1}
    available = [v["value"] for v in families.values() if v["value"] is not None]
    return {"families": families, "coverage": len(available) / len(FAMILIES),
            "directional_balance": sum(available) / len(available) if available else None,
            "probability": None, "mode": "shadow_only", "production_gate": False}


def enrich_explanation(decision):
    decision["engine_version"] = ENGINE_VERSION
    score = decision.get("score")
    decision["signal_strength"] = min(100, max(0, score)) if isinstance(score, (float, int)) else None
    decision["model_confidence"] = {"label": "unvalidated", "probability": None,
                                    "historical_status": "Historical probability unavailable"}
    ind = decision.get("indicators") or {}
    flow = ind.get("OrderFlow")
    if isinstance(flow, dict):
        flow["mode"] = "ESTIMATED_ORDER_FLOW"
        flow.setdefault("source", "ohlcv_proxy_or_tick_direction_unresolved")
        flow["aggressor_flow_verified"] = False
    # Only demonstrably available evidence is populated. No inferred pass states.
    votes = {}
    htf = decision.get("htf_bias")
    if isinstance(htf, (int, float)):
        votes["TREND"] = [htf]
    if isinstance(flow, dict) and isinstance(flow.get("delta"), (int, float)):
        delta = flow["delta"]
        # Don't silently rescale an unresolved tick count as a normalized delta.
        if -1 <= delta <= 1 and flow.get("source") == "ohlcv_estimate":
            votes["ORDER_FLOW"] = [delta]
    decision["evidence_model"] = bounded_family_model(votes)
    reasons = list(decision.get("wait_reasons") or [])
    if decision.get("signal") == "wait" and decision.get("reason"):
        if not any(x.get("message") == decision["reason"] for x in reasons if isinstance(x, dict)):
            reasons.append({"code": "FINAL_GATE", "message": decision["reason"]})
    decision["explanation_tree"] = {
        "decision": decision.get("signal", "wait"),
        "status": "WAIT" if decision.get("signal") == "wait" else "SETUP_DETECTED",
        "entry_confirmed": False,  # A model plan is not an exchange execution confirmation.
        "positive_factors": decision.get("reasons_plain") or [],
        "blocking_reasons": reasons, "risk_block": decision.get("risk_block"),
        "invalidation": decision.get("stop_loss"),
        "next_event": None, "next_event_status": "not_recorded_not_invented",
        "news_status": decision.get("news_status", "unavailable"),
        "execution_risk_verified": False}
    return decision
