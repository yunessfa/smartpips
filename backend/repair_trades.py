"""REPAIR: restore every trade's P&L to the correct value.

Recomputes pnl/pnl_percent for every CLOSED trade from its own stored
entry/exit/size/leverage using the correct formula (pnl = size*leverage*move).
Works whether or not a stray `quantity` column still exists in the DB.

Run once:  python manage.py shell < repair_trades.py
"""
from apps.trades.models import Trade

repaired = 0
for t in Trade.objects.all():
    # clear any stray quantity so it can never interfere
    if hasattr(t, "quantity"):
        try:
            if getattr(t, "quantity", None) is not None:
                t.quantity = None
        except Exception:
            pass
    if t.status == "closed" and t.exit_price and t.entry_price:
        if t.direction == "long":
            move = (t.exit_price - t.entry_price) / t.entry_price
        else:
            move = (t.entry_price - t.exit_price) / t.entry_price
        pct = move * 100 * (t.leverage or 1)
        pnl = (t.size or 0) * (t.leverage or 1) * move
        t.pnl = round(pnl, 4)
        t.pnl_percent = round(pct, 4)
        t.save(update_fields=["pnl", "pnl_percent"])
        repaired += 1
        print("trade", t.id, t.symbol, "-> pnl", t.pnl, "(", t.pnl_percent, "% )")

print("\nrepaired", repaired, "closed trades OK")
