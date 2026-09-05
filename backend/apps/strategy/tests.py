from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.strategy.models import Indicator, TelegramChannel


class StrategyTests(APITestCase):
    def setUp(self):
        User.objects.create_user("u", password="pass1234")
        login = self.client.post(
            reverse("login"), {"username": "u", "password": "pass1234"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")

    def test_create_indicator(self):
        res = self.client.post(
            "/api/strategy/indicators/",
            {"label": "RSI 14", "key": "rsi", "settings": "length 14"},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Indicator.objects.count(), 1)

    def test_username_is_normalised(self):
        res = self.client.post(
            "/api/strategy/telegram/", {"username": "@whalepool"}
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["username"], "whalepool")

    @patch(
        "apps.strategy.views.fetch_channel_messages",
        return_value=[{"channel": "x", "text": "BTC pumping"}],
    )
    def test_channel_preview(self, _mock):
        ch = TelegramChannel.objects.create(username="x")
        res = self.client.post(f"/api/strategy/telegram/{ch.id}/preview/")
        self.assertTrue(res.data["ok"])
        self.assertEqual(len(res.data["messages"]), 1)
