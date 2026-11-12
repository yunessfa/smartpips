from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import AssetViewSet, metal_price, economic_calendar, chart_candles, futures_flow_view

router = DefaultRouter()
router.register("assets", AssetViewSet, basename="asset")

urlpatterns = router.urls + [
    path("calendar/", economic_calendar, name="economic-calendar"),
    path("candles/", chart_candles, name="chart-candles"),
    path("metal/", metal_price, name="metal-price"),
    path("flow/", futures_flow_view, name="futures-flow"),
]
