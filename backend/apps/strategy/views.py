from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Indicator, TelegramChannel
from .serializers import IndicatorSerializer, TelegramChannelSerializer
from .services import fetch_channel_messages


class IndicatorViewSet(viewsets.ModelViewSet):
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer


class TelegramChannelViewSet(viewsets.ModelViewSet):
    queryset = TelegramChannel.objects.all()
    serializer_class = TelegramChannelSerializer

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Fetch a few recent posts to confirm the channel is readable."""
        channel = self.get_object()
        messages = fetch_channel_messages(channel.username, limit=3)
        return Response({"ok": bool(messages), "messages": messages})
