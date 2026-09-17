from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import AssetViewSet, metal_price

router = DefaultRouter()
router.register("assets", AssetViewSet, basename="asset")

urlpatterns = router.urls + [
    path("metal/", metal_price, name="metal-price"),
]
