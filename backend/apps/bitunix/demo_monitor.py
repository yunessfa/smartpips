"""Public-price polling only. No private exchange endpoints or real orders."""
import math
from django.db import transaction
from django.utils import timezone
from .models import DemoPosition


def settle_demo(position_id, price, observed_at=None):
    if price is None or not math.isfinite(float(price)) or price <= 0:
        return None
    from .views import _journal_close
    with transaction.atomic():
        p = DemoPosition.objects.select_for_update().filter(pk=position_id, closed_at__isnull=True).first()
        if p is None:
            return None
        hit = p.check_tp_sl(price)
        if not hit:
            return None
        p.closed_at = observed_at or timezone.now()
        # Fill at OBSERVED price, not an imaginary guaranteed stop/target fill.
        p.close_price = price
        p.close_reason = hit
        p.realized_pnl = p.gross_pnl(price)
        p.save()
        _journal_close(p.user, p.journal_trade_id, price,
                       note=f"closed by {hit}; demo observed polling price",
                       reason=hit)
        return {"id": p.pk, "reason": hit, "observed_price": price}


def sweep_demo(client):
    prices, closed, errors = {}, [], []
    rows = list(DemoPosition.objects.filter(closed_at__isnull=True).values("id", "symbol"))
    for row in rows:
        sym = row["symbol"]
        if sym not in prices:
            try:
                price = client.last_price(sym)
                if not price or not math.isfinite(float(price)) or price <= 0:
                    raise ValueError("Invalid public price")
                prices[sym] = price
            except Exception as exc:
                prices[sym] = None
                errors.append({"symbol": sym, "error_type": type(exc).__name__})
        try:
            result = settle_demo(row["id"], prices[sym])
            if result:
                closed.append(result)
        except Exception as exc:
            # One malformed legacy mirror must not starve every other position.
            errors.append({"position_id": row["id"], "error_type": type(exc).__name__})
    return {"checked": len(rows), "closed": closed, "errors": errors,
            "as_of": timezone.now().isoformat(), "scope": "demo_only",
            "limitations": "Sampled prices, not tick replay; touches between polls can be missed."}