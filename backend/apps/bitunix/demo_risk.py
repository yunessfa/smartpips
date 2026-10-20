"""Research-only profile. Never used by the REAL order path."""
import math
from django.utils import timezone
from .models import DemoPosition, FEE_RATE

PROFILE = {"name": "demo-conservative-v1", "risk_per_trade_pct": .5,
           "max_daily_loss_pct": 2, "max_leverage": 10,
           "max_open_positions": 3, "max_total_stop_risk_pct": 1.5,
           "liquidation_buffer_fraction": .8}


def assess(user, *, balance, entry, stop, qty, leverage, side):
    errors = []
    warnings = []
    vals = (balance, entry, stop, qty, leverage)
    if any(v is None or not math.isfinite(float(v)) or v <= 0 for v in vals):
        return {"allowed": False, "errors": ["demo_balance_and_valid_stop_required"],
                "profile": PROFILE}
    if side not in ("BUY", "SELL") or (stop >= entry if side == "BUY" else stop <= entry):
        errors.append("invalid_stop_side")
    if leverage > PROFILE["max_leverage"]:
        warnings.append({"code": "leverage_above_recommended", "severity": "warning",
                         "leverage": leverage, "recommended_max": PROFILE["max_leverage"],
                         "message": "Leverage exceeds the demo recommendation; order remains allowed if other checks pass."})
    # Include estimated round-trip fees in sizing; adverse gap/slippage can still exceed this.
    loss_per_coin = abs(entry-stop) + (entry+stop)*FEE_RATE
    budget = balance * PROFILE["risk_per_trade_pct"] / 100
    suggested_qty = budget / loss_per_coin
    proposed = qty * loss_per_coin
    if proposed > budget * 1.001:
        errors.append("demo_trade_risk_cap")
    if abs(entry-stop)/entry * leverage > .95 * PROFILE["liquidation_buffer_fraction"]:
        errors.append("stop_too_close_to_or_beyond_estimated_liquidation")
    open_positions = list(DemoPosition.objects.filter(user=user, closed_at__isnull=True))
    if len(open_positions) >= PROFILE["max_open_positions"]:
        errors.append("demo_open_position_cap")
    existing_risk = 0
    for p in open_positions:
        if not p.sl_price or (p.sl_price >= p.entry_price if p.side == "LONG" else p.sl_price <= p.entry_price):
            errors.append("existing_demo_stop_missing_or_invalid")
            continue
        existing_risk += p.qty * (abs(p.entry_price-p.sl_price) + (p.entry_price+p.sl_price)*FEE_RATE)
    if existing_risk+proposed > balance*PROFILE["max_total_stop_risk_pct"]/100 * 1.001:
        errors.append("demo_total_stop_risk_cap")
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Gross historical demo PnL is conservative only after estimated fees.
    day_net = sum((p.gross_pnl(p.close_price) or 0)-p.round_trip_fee(p.close_price)
                  for p in DemoPosition.objects.filter(user=user, closed_at__gte=start))
    if day_net <= -balance*PROFILE["max_daily_loss_pct"]/100:
        errors.append("demo_daily_loss_cap")
    used = sum(p.margin for p in open_positions)
    if qty*entry/leverage > balance-used:
        errors.append("demo_available_margin")
    return {"allowed": not errors, "errors": sorted(set(errors)), "warnings": warnings, "profile": PROFILE,
            "suggested_qty": suggested_qty, "estimated_stop_loss_usdt": proposed,
            "estimated_total_stop_risk_usdt": existing_risk+proposed,
            "daily_net_estimate_usdt": day_net, "balance_basis": "user_supplied_demo_balance",
            "limitations": "Polling gaps, slippage and unrealized losses can exceed these budgets."}