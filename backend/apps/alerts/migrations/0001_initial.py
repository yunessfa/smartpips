"""Initial migration for the alerts app.

The app previously shipped without any migration files, so its tables were
created ad hoc by running `makemigrations alerts` on the machine. Production
deploys only run `migrate`, which meant new alert tables could never reach the
server. This file pins the three original models so the app is now versioned
like every other app.

If your database ALREADY contains these three tables (because you ran
`makemigrations alerts` locally at some point), record this migration as
applied instead of running it:

    python manage.py migrate alerts 0001 --fake
    python manage.py migrate alerts
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("endpoint", models.URLField(max_length=600, unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="push_subscriptions",
                    to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SignalState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=20)),
                ("timeframe", models.CharField(max_length=8)),
                ("last_signal", models.CharField(default="wait", max_length=8)),
                ("last_score", models.IntegerField(default=0)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={"unique_together": {("symbol", "timeframe")}},
        ),
        migrations.CreateModel(
            name="WatchItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=20)),
                ("min_score", models.IntegerField(default=68)),
                ("active", models.BooleanField(default=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="watchlist",
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("user", "symbol")}},
        ),
    ]
