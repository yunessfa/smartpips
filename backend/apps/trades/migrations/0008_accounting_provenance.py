from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("trades", "0007_merge_20260812_1149")]
    operations = [
        migrations.AddField("trade", "fees_paid", models.FloatField(null=True, blank=True)),
        migrations.AddField("trade", "funding_paid", models.FloatField(null=True, blank=True)),
        migrations.AddField("trade", "costs_verified", models.BooleanField(default=False)),
        migrations.AddField("trade", "execution_verified", models.BooleanField(default=False)),
        migrations.AddField("trade", "external_order_id", models.CharField(max_length=80, blank=True)),
        migrations.AddField("trade", "external_position_id", models.CharField(max_length=80, blank=True)),
        migrations.AddField("trade", "execution_evidence", models.JSONField(default=dict, blank=True)),
    ]