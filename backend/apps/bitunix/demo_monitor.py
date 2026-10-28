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


def progress_pending(position_id, price, now=None):
    """Fill or expire a resting demo LIMIT order. Returns 'filled'|'expired'|None."""
    from .views import _journal_open
    now = now or timezone.now()
    with transaction.atomic():
        p = DemoPosition.objects.select_for_update().filter(
            pk=position_id, closed_at__isnull=True, order_type="LIMIT", filled_at__isnull=True).first()
        if p is None:
            return None
        if p.expires_at and now >= p.expires_at:
            p.closed_at, p.close_reason, p.realized_pnl = now, "expired", 0.0
            p.save()
            return "expired"
        if price is None or not math.isfinite(float(price)) or not p.limit_touched(price):
            return None
        p.filled_at = now
        p.journal_trade_id = _journal_open(
            p.user, symbol=p.symbol, side="BUY" if p.side == "LONG" else "SELL", qty=p.qty,
            entry=p.entry_price, leverage=p.leverage, tp=p.tp_price, sl=p.sl_price,
            source="bitunix_demo", note="demo LIMIT filled (observed polling price)")
        p.save()
        return "filled"


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
            state = progress_pending(row["id"], prices[sym])
            if state:
                closed.append({"id": row["id"], "reason": f"limit_{state}"})
                if state == "expired":
                    continue
            result = settle_demo(row["id"], prices[sym])
            if result:
                closed.append(result)
        except Exception as exc:
            # One malformed legacy mirror must not starve every other position.
            errors.append({"position_id": row["id"], "error_type": type(exc).__name__})
    return {"checked": len(rows), "closed": closed, "errors": errors,
            "as_of": timezone.now().isoformat(), "scope": "demo_only",
            "limitations": "Sampled prices, not tick replay; touches between polls can be missed."}