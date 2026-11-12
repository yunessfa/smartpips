from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.alerts.models import WatchItem
from apps.prefs.models import MarketAccess


class FuturesOnlyFocus(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("fo", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(FUTURES_ONLY=True)
    def test_access_map_hides_metals_and_spot_without_touching_stored_flags(self):
        body = self.client.get("/api/prefs/market_access/").json()
        self.assertEqual(body, {"metals": False, "spot": False, "futures": True, "futures_only": True})
        row = MarketAccess.objects.get(user=self.user)
        self.assertTrue(row.allow_metals and row.allow_spot)

    @override_settings(FUTURES_ONLY=False)
    def test_switch_off_restores_the_stored_flags(self):
        self.assertEqual(self.client.get("/api/prefs/market_access/").json(),
                         {"metals": True, "spot": True, "futures": True})

    @override_settings(FUTURES_ONLY=True)
    def test_scalp_endpoint_only_serves_perps(self):
        for symbol in ("XAUUSD", "BTCUSDT"):
            res = self.client.post("/api/chat/scalp/", {"symbol": symbol, "price": 100, "timeframe": "5m"},
                                   format="json")
            self.assertEqual(res.status_code, 400, symbol)
            self.assertEqual(res.json()["code"], "futures_only")
        with patch("apps.chat.views.scalp_ai_signal", return_value={"signal": "wait"}, create=True), \
                patch("apps.strategy.decision.decide", return_value={"signal": "wait"}):
            res = self.client.post("/api/chat/scalp/", {"symbol": "BTCUSDT:PERP", "price": 100, "timeframe": "5m"},
                                   format="json")
        self.assertNotEqual(res.json().get("code"), "futures_only")

    @override_settings(FUTURES_ONLY=True)
    def test_assistant_chat_is_gone(self):
        res = self.client.post("/api/chat/send/", {"message": "hi"}, format="json")
        self.assertEqual(res.status_code, 410)
        self.assertEqual(res.json()["code"], "chat_removed")

    def _scan(self):
        from apps.alerts.management.commands import monitor_scalp
        seen = []
        with patch.object(monitor_scalp, "evaluate_and_alert", side_effect=lambda s, tf: seen.append(s) or 0), \
                patch.object(monitor_scalp, "vapid_configured", return_value=True):
            cmd = monitor_scalp.Command(stdout=StringIO(), stderr=StringIO())
            cmd._scan()
        return set(seen)

    @override_settings(FUTURES_ONLY=True)
    def test_alert_monitor_skips_gold_and_non_perp_watch_items(self):
        WatchItem.objects.create(user=self.user, symbol="XAUUSD")
        WatchItem.objects.create(user=self.user, symbol="ETHUSDT")
        WatchItem.objects.create(user=self.user, symbol="BTCUSDT:PERP")
        self.assertEqual(self._scan(), {"BTCUSDT:PERP"})

    @override_settings(FUTURES_ONLY=False)
    def test_alert_monitor_keeps_the_old_defaults_when_switched_off(self):
        WatchItem.objects.create(user=self.user, symbol="BTCUSDT:PERP")
        self.assertEqual(self._scan(), {"XAUUSD", "XAGUSD", "BTCUSDT:PERP"})
