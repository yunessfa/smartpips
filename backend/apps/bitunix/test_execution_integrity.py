"""Execution-integrity regressions (2026-10 audit P0-01..P0-04). All exchange calls are mocks."""
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase as _TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.trades.models import Trade
from .demo_monitor import progress_pending, settle_demo
from .models import DemoPosition


class TestCase(_TestCase):
    """Order endpoints are throttled through the shared cache; never leak our
    request counts into other test modules (user pks are reused)."""
    def setUp(self):
        cache.clear()
        super().setUp()

    def tearDown(self):
        cache.clear()
        super().tearDown()


def mock_client(last=200.0, positions=None, available=10_000):
    c = Mock(configured=True)
    c.last_price.return_value = last
    c.account.return_value = {"available": available}
    c.place_order.return_value = {"orderId": "mock-ack"}
    c.pending_positions.return_value = positions if positions is not None else []
    c.flash_close_position.return_value = {"ok": True}
    return c


@override_settings(DEMO_RISK_V1_ENABLED=False)
class MarketPriceIsServerSideTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("exec-a")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    def post(self, client, **data):
        with patch("apps.bitunix.views._client", return_value=client):
            return self.api.post("/api/bitunix/order/", data, format="json")

    def test_demo_market_fills_at_server_quote_not_client_price(self):
        c = mock_client(last=200)
        r = self.post(c, mode="demo", symbol="BTCUSDT", side="BUY", orderType="MARKET", qty=1,
                      price=100, slPrice=190, tpPrice=220, leverage=2, demoBalance=1000)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(DemoPosition.objects.get().entry_price, 200)
        c.last_price.assert_called()
        c.place_order.assert_not_called()

    def test_tampered_client_price_cannot_flip_tp_sl_validation(self):
        # SL 150 is valid vs a fake price of 100?? no: with the real quote 200, TP 180 is on the wrong side
        c = mock_client(last=200)
        r = self.post(c, mode="demo", symbol="BTCUSDT", side="BUY", orderType="MARKET", qty=1,
                      price=170, slPrice=150, tpPrice=180, leverage=2, demoBalance=1000)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(DemoPosition.objects.exists())

    def test_market_without_public_quote_is_refused(self):
        c = mock_client(last=None)
        r = self.post(c, mode="demo", symbol="BTCUSDT", side="BUY", orderType="MARKET", qty=1,
                      price=100, slPrice=90, tpPrice=120, leverage=2, demoBalance=1000)
        self.assertEqual(r.status_code, 503)

    def test_real_market_never_forwards_client_price(self):
        c = mock_client(last=200, positions=[{"symbol": "BTCUSDT", "side": "LONG", "avgOpenPrice": "201.5",
                                              "positionId": "p-1"}])
        with patch("apps.prefs.models.RiskLimits.check_order", return_value=None):
            r = self.post(c, mode="real", confirm=True, symbol="BTCUSDT", side="BUY", orderType="MARKET",
                          qty=0.01, price=100, slPrice=190, tpPrice=220, leverage=2)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(c.place_order.call_args.kwargs.get("price"))
        self.assertTrue(r.json()["client_price_ignored"])


class AckIsNotFillTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("exec-b")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    def send(self, c, **extra):
        data = dict(mode="real", confirm=True, symbol="BTCUSDT", side="BUY", qty=0.01, leverage=2,
                    slPrice=190, tpPrice=220, orderType="MARKET")
        data.update(extra)
        with patch("apps.bitunix.views._client", return_value=c), \
                patch("apps.prefs.models.RiskLimits.check_order", return_value=None), \
                patch("apps.bitunix.views._verify_market_fill.__defaults__", (1, 0)):
            return self.api.post("/api/bitunix/order/", data, format="json")

    def test_verified_fill_records_exchange_average_price(self):
        c = mock_client(last=200, positions=[{"symbol": "BTCUSDT", "side": "LONG", "avgOpenPrice": "201.5",
                                              "positionId": "p-9"}])
        r = self.send(c)
        self.assertEqual(r.json()["fill_status"], "verified")
        t = Trade.objects.get(source="bitunix_real")
        self.assertEqual(t.entry_price, 201.5)
        self.assertIn("fill verified", t.notes)

    def test_unverified_ack_is_flagged_for_reconciliation(self):
        r = self.send(mock_client(last=200, positions=[]))
        self.assertEqual(r.json()["fill_status"], "unverified")
        self.assertIn("NOT verified", Trade.objects.get(source="bitunix_real").notes)

    def test_limit_ack_is_marked_pending_fill(self):
        r = self.send(mock_client(last=200), orderType="LIMIT", price=195)
        self.assertEqual(r.json()["fill_status"], "pending_limit")
        self.assertIn("PENDING FILL", Trade.objects.get(source="bitunix_real").notes)


class RealCloseMappingTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("exec-c")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    def close(self, c, **data):
        with patch("apps.bitunix.views._client", return_value=c):
            return self.api.post("/api/bitunix/close/", data, format="json")

    def mk(self, symbol, direction):
        return Trade.objects.create(user=self.user, symbol=symbol, direction=direction, entry_price=100,
                                    stop_loss=90 if direction == "long" else 110, source="bitunix_real",
                                    status="open", size=10, leverage=2)

    def test_closes_the_journal_row_of_that_position_not_newest_trade(self):
        eth = self.mk("ETHUSDT", "long")
        btc = self.mk("BTCUSDT", "short")   # newest open trade — the old code would have closed this
        c = mock_client(last=105, positions=[{"positionId": "pos-eth", "symbol": "ETHUSDT", "side": "LONG"}])
        r = self.close(c, mode="real", confirm=True, positionId="pos-eth")
        self.assertEqual(r.status_code, 200, r.content)
        eth.refresh_from_db(); btc.refresh_from_db()
        self.assertEqual(eth.status, "closed")
        self.assertEqual(btc.status, "open")

    def test_ambiguous_rows_are_left_for_reconciliation(self):
        self.mk("BTCUSDT", "long"); self.mk("BTCUSDT", "long")
        c = mock_client(positions=[{"positionId": "p", "symbol": "BTCUSDT", "side": "LONG"}])
        r = self.close(c, mode="real", confirm=True, positionId="p")
        self.assertEqual(r.json()["journal"], "ambiguous_needs_reconcile")
        self.assertEqual(Trade.objects.filter(status="open").count(), 2)

    def test_invalid_mode_and_missing_position_are_refused(self):
        c = mock_client(positions=[])
        self.assertEqual(self.close(c, mode="paper", confirm=True, positionId="x").status_code, 400)
        self.assertEqual(self.close(c, mode="real", confirm=True).status_code, 400)
        self.assertEqual(self.close(c, mode="real", confirm=True, positionId="gone").status_code, 404)
        c.flash_close_position.assert_not_called()


@override_settings(DEMO_RISK_V1_ENABLED=False)
class DemoLimitOrderTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("exec-d")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    def place(self, last, **extra):
        data = dict(mode="demo", symbol="BTCUSDT", side="BUY", orderType="LIMIT", price=190, qty=1,
                    slPrice=185, tpPrice=200, leverage=2, demoBalance=1000, expiryMinutes=30)
        data.update(extra)
        with patch("apps.bitunix.views._client", return_value=mock_client(last=last)):
            return self.api.post("/api/bitunix/order/", data, format="json")

    def test_resting_limit_is_not_a_position_until_touched(self):
        r = self.place(200)
        self.assertTrue(r.json()["pending"])
        p = DemoPosition.objects.get()
        self.assertTrue(p.is_pending)
        self.assertFalse(Trade.objects.exists())
        self.assertIsNone(p.check_tp_sl(150))           # no stop-out while only an order
        self.assertIsNone(progress_pending(p.pk, 195))  # not touched yet
        self.assertEqual(progress_pending(p.pk, 189.9), "filled")
        p.refresh_from_db()
        self.assertFalse(p.is_pending)
        self.assertTrue(Trade.objects.filter(source="bitunix_demo", status="open").exists())
        self.assertEqual(settle_demo(p.pk, 184)["reason"], "sl")

    def test_limit_expires_without_journal(self):
        self.place(200)
        p = DemoPosition.objects.get()
        self.assertEqual(progress_pending(p.pk, 199, now=timezone.now() + timedelta(minutes=31)), "expired")
        p.refresh_from_db()
        self.assertEqual(p.close_reason, "expired")
        self.assertFalse(Trade.objects.exists())

    def test_marketable_limit_fills_immediately(self):
        r = self.place(188)   # buy limit 190 above market 188
        self.assertTrue(r.json()["filled"])
        self.assertEqual(DemoPosition.objects.get().entry_price, 188)


class BrokerPathGuardTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("exec-e")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    def test_mt5_requires_confirm_stop_and_risk_gate(self):
        from apps.mt5.models import MT5Account, MT5Order
        MT5Account.objects.create()
        base = dict(symbol="XAUUSD", action="buy", volume=0.01, tp=4200)
        self.assertEqual(self.api.post("/api/mt5/order/", base, format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/mt5/order/", {**base, "confirm": True}, format="json").status_code, 400)
        with patch("apps.prefs.models.RiskLimits.check_order", return_value="Real trading is disabled"):
            r = self.api.post("/api/mt5/order/", {**base, "confirm": True, "sl": 4100}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(MT5Order.objects.exists())
        r = self.api.post("/api/mt5/order/", {**base, "confirm": True, "sl": 4100}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_lbank_respects_account_risk_gate(self):
        with patch("apps.prefs.models.RiskLimits.check_order", return_value="Daily loss limit reached"):
            r = self.api.post("/api/lbank/order/", dict(confirm=True, symbol="btc_usdt", type="buy",
                                                        price=100, amount=1), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Daily loss", r.json()["error"])
