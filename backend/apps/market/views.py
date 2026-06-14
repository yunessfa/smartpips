from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Asset
from .serializers import AssetSerializer
from .services import get_quotes


class AssetViewSet(viewsets.ModelViewSet):
    """CRUD for tracked assets + a /quotes/ action with live prices."""

    queryset = Asset.objects.all()
    serializer_class = AssetSerializer

    @action(detail=False, methods=["get"])
    def quotes(self, request):
        watched = self.get_queryset().filter(is_watched=True)
        return Response(get_quotes(watched))
