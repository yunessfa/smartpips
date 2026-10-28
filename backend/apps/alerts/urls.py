from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (vapid_key, subscribe, unsubscribe, status_view, test_push,
                    watchlist, watch_remove)
from .views_center import AlertRuleViewSet, NotificationViewSet, evaluate_now

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("rules", AlertRuleViewSet, basename="alert-rule")

urlpatterns = [
    # Web Push plumbing (unchanged)
    path("vapid/", vapid_key, name="vapid-key"),
    path("subscribe/", subscribe, name="push-subscribe"),
    path("unsubscribe/", unsubscribe, name="push-unsubscribe"),
    path("status/", status_view, name="push-status"),
    path("test/", test_push, name="push-test"),
    path("watchlist/", watchlist, name="watchlist"),
    path("watchlist/<str:symbol>/", watch_remove, name="watch-remove"),

    # Notification centre
    path("evaluate/", evaluate_now, name="alerts-evaluate"),
    path("", include(router.urls)),
]
