from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.ai.models import AIProvider
from apps.chat.models import Conversation, Message

FAKE_REPLY = (
    '{"reply": "BTC looks strong.", "news_used": [], '
    '"recommendations": [{"symbol": "BTCUSDT", "action": "buy", '
    '"entry": "60000", "take_profit": "65000", "stop_loss": "58000", '
    '"timeframe": "4h", "confidence": "medium", "rationale": "uptrend"}]}'
)


class ChatFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("trader", password="pass1234")
        login = self.client.post(
            reverse("login"), {"username": "trader", "password": "pass1234"}
        )
        self.token = login.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        AIProvider.objects.create(
            label="Test", provider_type="deepseek", api_key="x", is_active=True
        )

    @patch("apps.chat.views.chat_completion", return_value=FAKE_REPLY)
    def test_send_creates_conversation_and_saves_messages(self, _mock):
        res = self.client.post("/api/chat/send/", {"message": "How is BTC?"})
        self.assertEqual(res.status_code, 200)
        conv_id = res.data["conversation_id"]
        self.assertEqual(Conversation.objects.count(), 1)
        # one user message + one assistant message
        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 2)
        self.assertEqual(len(res.data["message"]["recommendations"]), 1)

    @patch("apps.chat.views.chat_completion", return_value=FAKE_REPLY)
    def test_history_is_persisted_and_listable(self, _mock):
        first = self.client.post("/api/chat/send/", {"message": "hi"})
        conv_id = first.data["conversation_id"]
        # follow-up message reuses the same conversation
        self.client.post(
            "/api/chat/send/", {"message": "and ETH?", "conversation_id": conv_id}
        )
        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 4)

        listing = self.client.get("/api/chat/conversations/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 1)

        detail = self.client.get(f"/api/chat/conversations/{conv_id}/")
        self.assertEqual(len(detail.data["messages"]), 4)

    @patch("apps.chat.views.chat_completion", return_value=FAKE_REPLY)
    def test_conversations_are_isolated_per_user(self, _mock):
        self.client.post("/api/chat/send/", {"message": "mine"})
        other = User.objects.create_user("other", password="pass1234")
        login = self.client.post(
            reverse("login"), {"username": "other", "password": "pass1234"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        listing = self.client.get("/api/chat/conversations/")
        self.assertEqual(len(listing.data), 0)

    def test_chat_requires_authentication(self):
        self.client.credentials()  # drop the token
        res = self.client.post("/api/chat/send/", {"message": "hi"})
        self.assertEqual(res.status_code, 401)
