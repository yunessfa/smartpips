"""Notification centre: internal notifications + user-defined alert rules.

AlertRule is created before Notification because Notification carries a
nullable FK back to it.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0001_initial"),
        ("trades", "0002_fix_bitunix_mirror_size"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=80)),
                ("scope", models.CharField(
                    choices=[("any", "Any open trade"),
                             ("symbol", "A specific symbol"),
                             ("trade", "One specific trade")],
                    default="any", max_length=8)),
                ("symbol", models.CharField(blank=True, max_length=20)),
                ("condition", models.CharField(
                    choices=[("pnl_above", "PnL at or above (USDT)"),
                             ("pnl_below", "PnL at or below (USDT)"),
                             ("pnl_pct_above", "PnL % at or above"),
                             ("pnl_pct_below", "PnL % at or below"),
                             ("price_above", "Price at or above"),
                             ("price_below", "Price at or below"),
                             ("reaches_tp", "Price reaches take profit"),
                             ("reaches_sl", "Price reaches stop loss"),
                             ("move_pct_from_entry", "Price moved % from entry"),
                             ("open_longer_than", "Trade open longer than (minutes)")],
                    default="pnl_above", max_length=24)),
                ("threshold", models.FloatField(default=0)),
                ("enabled", models.BooleanField(default=True)),
                ("push", models.BooleanField(default=True)),
                ("once_per_crossing", models.BooleanField(default=True)),
                ("trigger_count", models.PositiveIntegerField(default=0)),
                ("last_triggered_at", models.DateTimeField(blank=True, null=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("trade", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alert_rules", to="trades.trade")),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alert_rules", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("category", models.CharField(
                    choices=[("system", "System"), ("trading", "Trading"),
                             ("pnl", "PnL"), ("signal", "Signal"),
                             ("position", "Position"), ("risk", "Risk")],
                    default="system", max_length=12)),
                ("level", models.CharField(
                    choices=[("info", "Info"), ("success", "Success"),
                             ("warning", "Warning"), ("danger", "Danger")],
                    default="info", max_length=8)),
                ("title", models.CharField(max_length=140)),
                ("body", models.TextField(blank=True)),
                ("url", models.CharField(blank=True, max_length=300)),
                ("symbol", models.CharField(blank=True, max_length=20)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("read", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("rule", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notifications", to="alerts.alertrule")),
                ("trade", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notifications", to="trades.trade")),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created"]},
        ),
        migrations.CreateModel(
            name="AlertRuleState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("latched", models.BooleanField(default=False)),
                ("last_value", models.FloatField(blank=True, null=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("rule", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="states", to="alerts.alertrule")),
                ("trade", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alert_states", to="trades.trade")),
            ],
            options={"unique_together": {("rule", "trade")}},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "read"],
                               name="alerts_note_user_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "category"],
                               name="alerts_note_user_cat_idx"),
        ),
    ]
