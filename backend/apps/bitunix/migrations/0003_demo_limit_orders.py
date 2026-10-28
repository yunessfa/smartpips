from django.db import migrations, models


def backfill_filled_at(apps, schema_editor):
    DemoPosition = apps.get_model("bitunix", "DemoPosition")
    # Every pre-existing demo row was an immediate MARKET fill.
    DemoPosition.objects.filter(filled_at__isnull=True).update(filled_at=models.F("opened_at"))


class Migration(migrations.Migration):
    dependencies = [("bitunix", "0002_demoposition_journal_trade_id")]
    operations = [
        migrations.AddField(model_name="demoposition", name="order_type",
                            field=models.CharField(default="MARKET", max_length=8)),
        migrations.AddField(model_name="demoposition", name="filled_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="demoposition", name="expires_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(backfill_filled_at, migrations.RunPython.noop),
    ]
