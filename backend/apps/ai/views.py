from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AIProvider
from .serializers import AIProviderSerializer
from .providers import chat_completion, AIClientError


class AIProviderViewSet(viewsets.ModelViewSet):
    queryset = AIProvider.objects.all()
    serializer_class = AIProviderSerializer

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        provider = self.get_object()
        provider.is_active = True
        provider.save()
        return Response(self.get_serializer(provider).data)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Send a tiny ping to verify the key/model actually work."""
        provider = self.get_object()
        try:
            reply = chat_completion(
                provider,
                [{"role": "user", "content": "Reply with the single word: OK"}],
            )
            return Response({"ok": True, "reply": reply.strip()})
        except AIClientError as exc:
            return Response(
                {"ok": False, "error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
