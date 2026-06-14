from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/market/", include("apps.market.urls")),
    path("api/sources/", include("apps.sources.urls")),
    path("api/strategy/", include("apps.strategy.urls")),
    path("api/trades/", include("apps.trades.urls")),
    path("api/ai/", include("apps.ai.urls")),
    path("api/chat/", include("apps.chat.urls")),
]
