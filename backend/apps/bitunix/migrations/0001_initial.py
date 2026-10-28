from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="DemoPosition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=24)),
                ("side", models.CharField(choices=[("LONG", "LONG"), ("SHORT", "SHORT")],
                                          max_length=8)),
                ("qty", models.FloatField()),
                ("entry_price", models.FloatField()),
                ("leverage", models.PositiveIntegerField(default=1)),
                ("margin", models.FloatField(default=0)),
                ("tp_price", models.FloatField(blank=True, null=True)),
                ("sl_price", models.FloatField(blank=True, null=True)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("close_price", models.FloatField(blank=True, null=True)),
                ("close_reason", models.CharField(blank=True, max_length=16)),
                ("realized_pnl", models.FloatField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name="bitunix_demo_positions",
                                           to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-opened_at"]},
        ),
    ]
