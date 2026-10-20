"""Data fix: earlier the Bitunix journal mirror stored Trade.size as the coin
QTY instead of the committed MARGIN (USD). The in-app account panel assumes
size = margin, so those rows showed value/qty inflated by ~leverage×.

For every OPEN trade created by the Bitunix mirror, convert the stored qty
back to margin:  margin = qty * entry_price / leverage.
Idempotent-ish: only touches bitunix_* sources; safe to run once.
"""
from django.db import migrations


def fix_size(apps, schema_editor):
    Trade = apps.get_model("trades", "Trade")
    for t in Trade.objects.filter(source__in=["bitunix_demo", "bitunix_real"],
                                  status="open"):
        if t.entry_price and t.leverage:
            # old size was qty (coins); new size is the USD margin
            t.size = round((t.size * t.entry_price) / t.leverage, 6)
            t.save(update_fields=["size"])


def noop(apps, schema_editor):
    # not reversible with confidence; leave as-is on downgrade
    pass


class Migration(migrations.Migration):
    dependencies = [("trades", "0001_initial")]
    operations = [migrations.RunPython(fix_size, noop)]
