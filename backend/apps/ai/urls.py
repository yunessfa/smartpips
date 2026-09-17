from rest_framework.routers import DefaultRouter
from .views import AIProviderViewSet

router = DefaultRouter()
router.register("providers", AIProviderViewSet, basename="aiprovider")

urlpatterns = router.urls
