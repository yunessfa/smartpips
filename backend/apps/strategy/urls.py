from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import IndicatorViewSet, TelegramChannelViewSet, backtest_view
from .config_views import StrategyViewSet, strategy_vocabulary

router = DefaultRouter()
router.register("indicators", IndicatorViewSet, basename="indicator")
router.register("telegram", TelegramChannelViewSet, basename="telegram")
# Configurable strategies layered on top of the existing engine. The engine's
# own /backtest/ endpoint below is untouched.
router.register("strategies", StrategyViewSet, basename="strategy")

urlpatterns = router.urls + [
    path("backtest/", backtest_view, name="strategy-backtest"),
    path("vocabulary/", strategy_vocabulary, name="strategy-vocabulary"),
]
