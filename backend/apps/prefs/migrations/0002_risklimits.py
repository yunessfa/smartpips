from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("prefs", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="RiskLimits",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("max_leverage", models.PositiveIntegerField(default=20)),
                ("max_position_usdt", models.FloatField(default=500)),
                ("max_open_positions", models.PositiveIntegerField(default=5)),
                ("daily_loss_limit_usdt", models.FloatField(default=100)),
                ("real_trading_enabled", models.BooleanField(default=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                              related_name="risk_limits",
                                              to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
