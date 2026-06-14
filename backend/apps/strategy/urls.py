from rest_framework.routers import DefaultRouter
from .views import IndicatorViewSet, TelegramChannelViewSet

router = DefaultRouter()
router.register("indicators", IndicatorViewSet, basename="indicator")
router.register("telegram", TelegramChannelViewSet, basename="telegram")

urlpatterns = router.urls
