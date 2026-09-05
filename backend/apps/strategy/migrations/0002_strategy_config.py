import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("strategy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Strategy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("preset_key", models.CharField(blank=True, db_index=True, max_length=40)),
                ("name", models.CharField(max_length=80)),
                ("description", models.TextField(blank=True)),
                ("market", models.CharField(
                    choices=[("crypto", "Crypto"), ("forex", "Forex"), ("metals", "Metals")],
                    default="crypto", max_length=8)),
                ("symbols", models.JSONField(blank=True, default=list)),
                ("timeframes", models.JSONField(blank=True, default=list)),
                ("direction", models.CharField(
                    choices=[("both", "Both"), ("long", "Long only"), ("short", "Short only")],
                    default="both", max_length=6)),
                ("is_active", models.BooleanField(default=False)),
                ("archived", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="strategies", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-is_active", "name"]},
        ),
        migrations.CreateModel(
            name="StrategyVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField(default=1)),
                ("rules", models.JSONField(blank=True, default=list)),
                ("weights", models.JSONField(blank=True, default=dict)),
                ("min_confidence", models.FloatField(default=70)),
                ("risk", models.JSONField(blank=True, default=dict)),
                ("backtest", models.JSONField(blank=True, default=dict)),
                ("backtest_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("strategy", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="versions", to="strategy.strategy")),
            ],
            options={"ordering": ["-version"],
                     "unique_together": {("strategy", "version")}},
        ),
        migrations.AddIndex(
            model_name="strategy",
            index=models.Index(fields=["user", "is_active"], name="strat_user_active_idx"),
        ),
    ]
