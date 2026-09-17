from rest_framework.routers import DefaultRouter
from .views import TradeViewSet

router = DefaultRouter()
router.register("", TradeViewSet, basename="trade")

urlpatterns = router.urls
