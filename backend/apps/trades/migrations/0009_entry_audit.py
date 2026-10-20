from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("trades", "0008_accounting_provenance")]
    operations = [
        migrations.AddField("trade", "entry_snapshot", models.JSONField(default=dict, blank=True, editable=False)),
        migrations.AddField("trade", "entry_snapshot_hash", models.CharField(max_length=64, blank=True, editable=False)),
        migrations.CreateModel(name="TradeEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("event", models.CharField(max_length=32)),
            ("details", models.JSONField(default=dict)),
            ("trade", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="trades.trade")),
        ], options={"ordering": ["created_at", "pk"]}),
    ]
