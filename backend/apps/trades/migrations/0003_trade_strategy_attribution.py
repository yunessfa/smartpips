import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Attach strategy attribution + entry context to journal rows.

    Every field is nullable/blank so existing trades migrate untouched; they
    simply report as "Unassigned" in strategy analytics.
    """

    dependencies = [
        ("strategy", "0002_strategy_config"),
        ("trades", "0002_fix_bitunix_mirror_size"),
    ]

    operations = [
        migrations.AddField(
            model_name="trade",
            name="strategy",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="trades", to="strategy.strategy"),
        ),
        migrations.AddField(
            model_name="trade",
            name="strategy_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="trade",
            name="strategy_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trade",
            name="timeframe",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="trade",
            name="confidence",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trade",
            name="exit_reason",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
