from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai.models import AIProvider
from apps.ai.providers import chat_completion, AIClientError

from .models import Conversation, Message
from .serializers import (
    ConversationSerializer,
    ConversationListSerializer,
    MessageSerializer,
)
from .services import build_system_prompt, parse_assistant_reply


class ConversationViewSet(viewsets.ModelViewSet):
    """Conversations are scoped to the logged-in user."""

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "list":
            return ConversationListSerializer
        return ConversationSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat(request):
    """Main chat endpoint.

    Body: { "conversation_id": <int|null>, "message": "<text>" }
    """
    user_text = (request.data.get("message") or "").strip()
    if not user_text:
        return Response(
            {"error": "Message is empty."}, status=status.HTTP_400_BAD_REQUEST
        )

    provider = AIProvider.objects.filter(is_active=True).first()
    if provider is None:
        return Response(
            {"error": "No active AI provider. Configure one on the AI page."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation_id = request.data.get("conversation_id")
    if conversation_id:
        conversation = Conversation.objects.filter(
            pk=conversation_id, user=request.user
        ).first()
        if conversation is None:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        title = user_text[:60] + ("…" if len(user_text) > 60 else "")
        conversation = Conversation.objects.create(user=request.user, title=title)

    Message.objects.create(conversation=conversation, role="user", content=user_text)

    messages = [{"role": "system", "content": build_system_prompt(request.user)}]
    for msg in conversation.messages.all():
        messages.append({"role": msg.role, "content": msg.content})

    try:
        raw_reply = chat_completion(provider, messages)
    except AIClientError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    parsed = parse_assistant_reply(raw_reply)
    assistant_message = Message.objects.create(
        conversation=conversation,
        role="assistant",
        content=parsed.get("reply", ""),
        recommendations=parsed.get("recommendations", []),
        news_used=parsed.get("news_used", []),
    )
    conversation.save()  # bump updated_at

    return Response(
        {
            "conversation_id": conversation.id,
            "message": MessageSerializer(assistant_message).data,
        }
    )
