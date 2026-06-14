from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.trades.models import Trade


class TradeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("trader", password="pass1234")
        login = self.client.post(
            reverse("login"), {"username": "trader", "password": "pass1234"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")

    def test_create_and_list_trade(self):
        res = self.client.post(
            "/api/trades/",
            {
                "symbol": "BTCUSDT", "direction": "long",
                "entry_price": 60000, "size": 100, "leverage": 5,
            },
        )
        self.assertEqual(res.status_code, 201)
        listing = self.client.get("/api/trades/")
        self.assertEqual(len(listing.data), 1)

    def test_long_pnl_is_computed_on_close(self):
        trade = Trade.objects.create(
            user=self.user, symbol="BTCUSDT", direction="long",
            entry_price=100, size=200, leverage=2,
        )
        # +10% move, 2x leverage -> +20% on margin, notional = 400 -> pnl = 40
        res = self.client.post(f"/api/trades/{trade.id}/close/", {"exit_price": 110})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "closed")
        self.assertAlmostEqual(res.data["pnl_percent"], 20.0, places=2)
        self.assertAlmostEqual(res.data["pnl"], 40.0, places=2)

    def test_short_pnl_direction(self):
        trade = Trade.objects.create(
            user=self.user, symbol="ETHUSDT", direction="short",
            entry_price=100, size=100, leverage=1,
        )
        # price falls to 90 -> short gains +10%
        trade.close(90)
        self.assertAlmostEqual(trade.pnl_percent, 10.0, places=2)
        self.assertGreater(trade.pnl, 0)

    def test_stats_endpoint(self):
        Trade.objects.create(user=self.user, symbol="A", entry_price=10, size=10).close(11)
        Trade.objects.create(user=self.user, symbol="B", entry_price=10, size=10).close(9)
        res = self.client.get("/api/trades/stats/")
        self.assertEqual(res.data["closed"], 2)
        self.assertEqual(res.data["wins"], 1)
        self.assertEqual(res.data["win_rate"], 50.0)

    def test_trades_isolated_per_user(self):
        Trade.objects.create(user=self.user, symbol="X", entry_price=1, size=1)
        other = User.objects.create_user("other", password="pass1234")
        login = self.client.post(
            reverse("login"), {"username": "other", "password": "pass1234"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        res = self.client.get("/api/trades/")
        self.assertEqual(len(res.data), 0)
