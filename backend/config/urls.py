from django.contrib import admin
from django.urls import path, include

from .health import health_view, health_deep_view, logs_view, logs_test_view

urlpatterns = [
    path("admin/", admin.site.urls),

    # ---- observability (T-2) ----
    # /api/health/ is deliberately public and minimal so an uptime monitor or
    # a systemd/docker healthcheck can call it without credentials.
    path("api/health/", health_view, name="health"),
    path("api/health/deep/", health_deep_view, name="health-deep"),
    path("api/logs/", logs_view, name="logs"),
    path("api/logs/test/", logs_test_view, name="logs-test"),

    path("api/auth/", include("apps.accounts.urls")),
    path("api/market/", include("apps.market.urls")),
    path("api/sources/", include("apps.sources.urls")),
    path("api/strategy/", include("apps.strategy.urls")),
    path("api/trades/", include("apps.trades.urls")),
    path("api/ai/", include("apps.ai.urls")),
    path("api/chat/", include("apps.chat.urls")),
    path("api/alerts/", include("apps.alerts.urls")),
    path("api/mt5/", include("apps.mt5.urls")),
    path("api/ctrader/", include("apps.ctrader.urls")),
    path("api/lbank/", include("apps.lbank.urls")),

    path("api/bitunix/", include("apps.bitunix.urls")),

    path("api/prefs/", include("apps.prefs.urls")),
]
