"""Tests for the Bitunix integration.

Run:  python manage.py test apps.bitunix

Covers the three places a bug costs real money:
  1. the signature formula (exactly per the official sign doc),
  2. the demo fill / TP-SL engine,
  3. the REAL-order guards (mode+confirm required, TP/SL side sanity,
     margin hard-cap) — with the network mocked so no test can ever
     reach the live exchange.
"""
import hashlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .client import BitunixClient, _query_concat, sign_request
from django.core.cache import cache


def _lift_limits(user, **over):
    """Give a user generous risk limits so a specific non-risk guard can be
    exercised without the risk cap firing first."""
    from apps.prefs.models import RiskLimits
    lim = RiskLimits.for_user(user)
    lim.max_leverage = over.get("max_leverage", 125)
    lim.max_position_usdt = over.get("max_position_usdt", 10_000_000)
    lim.max_open_positions = over.get("max_open_positions", 1000)
    lim.daily_loss_limit_usdt = over.get("daily_loss_limit_usdt", 0)
    lim.real_trading_enabled = over.get("real_trading_enabled", True)
    lim.save()
    return lim

from .models import DemoPosition


class SigningTests(TestCase):
    def test_query_concat_sorted_no_separators(self):
        q = _query_concat({"symbol": "BTCUSDT", "limit": "5", "interval": "1m"})
        # ascending by key: interval, limit, symbol — key+value, no '=' or '&'
        self.assertEqual(q, "interval1mlimit5symbolBTCUSDT")

    def test_sign_matches_documented_double_sha256(self):
        api_key, secret = "test-key", "test-secret"
        params = {"marginCoin": "USDT"}
        body = ""
        headers, nonce, ts = sign_request(api_key, secret, params, body,
                                          nonce="n" * 32, timestamp="1700000000000")
        digest = hashlib.sha256(
            f"{'n'*32}1700000000000{api_key}marginCoinUSDT{body}".encode()
        ).hexdigest()
        expected = hashlib.sha256((digest + secret).encode()).hexdigest()
        self.assertEqual(headers["sign"], expected)
        self.assertEqual(headers["api-key"], api_key)
        self.assertEqual(headers["timestamp"], "1700000000000")
        self.assertEqual(len(headers["nonce"]), 32)

    def test_post_body_participates_in_signature(self):
        h1, _, _ = sign_request("k", "s", None, '{"symbol":"BTCUSDT"}',
                                nonce="n" * 32, timestamp="1")
        h2, _, _ = sign_request("k", "s", None, '{"symbol":"ETHUSDT"}',
                                nonce="n" * 32, timestamp="1")
        self.assertNotEqual(h1["sign"], h2["sign"])


class ClientGuardTests(TestCase):
    def test_place_order_validates_inputs_before_network(self):
        c = BitunixClient(api_key="k", secret_key="s")
        with self.assertRaises(Exception):
            c.place_order("BTCUSDT", "HOLD", 1)          # bad side
        with self.assertRaises(Exception):
            c.place_order("BTCUSDT", "BUY", 1, order_type="LIMIT")  # no price

    @mock.patch("apps.bitunix.client.requests.request")
    def test_error_envelope_raises(self, req):
        req.return_value.json.return_value = {"code": 20001, "msg": "boom"}
        c = BitunixClient(api_key="k", secret_key="s")
        with self.assertRaises(Exception) as cm:
            c.account()
        self.assertIn("20001", str(cm.exception))


class DemoEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u", password="p")

    def test_long_pnl_and_tp(self):
        p = DemoPosition.objects.create(user=self.user, symbol="BTCUSDT",
                                        side="LONG", qty=0.01, entry_price=100000,
                                        leverage=5, tp_price=101000, sl_price=99000)
        self.assertAlmostEqual(p.unrealized_pnl(100500), 3.797, places=3)  # 5 gross - fee
        self.assertIsNone(p.check_tp_sl(100500))
        self.assertEqual(p.check_tp_sl(101200), "tp")
        self.assertEqual(p.check_tp_sl(98900), "sl")

    def test_short_mirrors(self):
        p = DemoPosition.objects.create(user=self.user, symbol="ETHUSDT",
                                        side="SHORT", qty=0.5, entry_price=4000,
                                        leverage=3, tp_price=3900, sl_price=4100)
        self.assertAlmostEqual(p.unrealized_pnl(3950), 22.615, places=3)  # 25 gross - fee
        self.assertEqual(p.check_tp_sl(3890), "tp")
        self.assertEqual(p.check_tp_sl(4110), "sl")


class OrderViewGuardTests(TestCase):
    """The rules that keep a demo click from ever becoming a real trade."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("u2", password="p")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        cache.clear()
        _lift_limits(self.user)

    def test_mode_is_mandatory(self):
        r = self.api.post("/api/bitunix/order/",
                          {"symbol": "BTCUSDT", "side": "BUY", "qty": 0.01},
                          format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("mode", r.json()["error"])

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    def test_demo_fills_locally_at_live_price(self, _lp):
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                           "qty": 0.01, "leverage": 5,
                           "tpPrice": 101000, "slPrice": 99000}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["filled"])
        pos = DemoPosition.objects.get(user=self.user)
        self.assertEqual(pos.entry_price, 100000.0)
        self.assertAlmostEqual(pos.margin, 0.01 * 100000 / 5, places=2)

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    def test_real_requires_confirm(self, _lp):
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "real", "symbol": "BTCUSDT", "side": "BUY",
                           "qty": 0.01}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("confirm", r.json()["error"])

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    def test_tp_sl_side_sanity(self, _lp):
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                           "qty": 0.01, "tpPrice": 99000}, format="json")  # TP below entry on BUY
        self.assertEqual(r.status_code, 400)

    @mock.patch("apps.bitunix.views.BitunixClient.account",
                return_value=[{"available": "50"}])
    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    @mock.patch("apps.bitunix.views.BitunixClient.configured",
                new_callable=mock.PropertyMock, return_value=True)
    def test_real_margin_hard_cap(self, _cfg, _lp, _acct):
        # 0.01 BTC * 100k / 1x = 1000 USDT margin needed; only 50 available.
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "real", "confirm": True, "symbol": "BTCUSDT",
                           "side": "BUY", "qty": 0.01, "leverage": 1}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("insufficient margin", r.json()["error"])


class DemoLiquidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u3", password="p")

    def test_liq_price_and_priority(self):
        p = DemoPosition.objects.create(user=self.user, symbol="BTCUSDT",
                                        side="LONG", qty=0.01, entry_price=100000,
                                        leverage=10, margin=100,
                                        sl_price=89000)  # SL below liq on purpose
        self.assertAlmostEqual(p.liq_price, 100000 * (1 - 0.095), places=2)  # 90500
        # price at 90000: below liq (90500) AND below SL? SL=89000 not hit;
        # liq must fire first
        self.assertEqual(p.check_tp_sl(90400), "liq")

    def test_short_liq_side(self):
        p = DemoPosition.objects.create(user=self.user, symbol="ETHUSDT",
                                        side="SHORT", qty=1, entry_price=4000,
                                        leverage=20, margin=200)
        self.assertAlmostEqual(p.liq_price, 4000 * (1 + 0.0475), places=2)
        self.assertEqual(p.check_tp_sl(4200), "liq")


class DemoBalanceCapTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u4", password="p")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        cache.clear()
        _lift_limits(self.user)

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    def test_demo_rejects_over_top_balance(self, _lp):
        # need 0.01*100000/5 = 200 USDT margin; top balance only 75.83
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                           "qty": 0.01, "leverage": 5, "demoBalance": 75.83},
                          format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("insufficient demo balance", r.json()["error"])

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    def test_demo_counts_open_margins(self, _lp):
        DemoPosition.objects.create(user=self.user, symbol="BTCUSDT", side="LONG",
                                    qty=0.004, entry_price=100000, leverage=5,
                                    margin=80)
        # free = 100 - 80 = 20; need 40 -> reject
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                           "qty": 0.002, "leverage": 5, "demoBalance": 100},
                          format="json")
        self.assertEqual(r.status_code, 400)
        # free 20, need 20 -> accept
        r2 = self.api.post("/api/bitunix/order/",
                           {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                            "qty": 0.001, "leverage": 5, "demoBalance": 100},
                           format="json")
        self.assertEqual(r2.status_code, 200, r2.content)


class KlinePaginationTests(TestCase):
    def test_paginates_past_200_bar_cap(self):
        c = BitunixClient(api_key="k", secret_key="s")
        def fake_klines(symbol, interval="5m", limit=200, kline_type="LAST_PRICE",
                        end_time=None):
            # two pages: newest 200 bars t=200..399, older 200 bars t=0..199
            if end_time is None:
                return [{"time": t, "open": 1, "high": 1, "low": 1, "close": 1,
                         "volume": 1} for t in range(200, 400)]
            return [{"time": t, "open": 1, "high": 1, "low": 1, "close": 1,
                     "volume": 1} for t in range(0, 200)]
        with mock.patch.object(BitunixClient, "klines", side_effect=fake_klines):
            out = c.klines_paginated("BTCUSDT", "5m", 500)
        self.assertEqual(len(out), 400)              # all available bars
        self.assertEqual(out[0]["time"], 0)          # chronological
        self.assertEqual(out[-1]["time"], 399)


class DepthViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u5", password="p")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        cache.clear()
        _lift_limits(self.user)

    @mock.patch("apps.bitunix.views.BitunixClient.depth")
    def test_clamps_to_allowed_levels(self, depth):
        depth.return_value = {"asks": [{"price": 1, "qty": 1}], "bids": [{"price": 0.9, "qty": 1}]}
        r = self.api.get("/api/bitunix/depth/?symbol=BNBUSDT:PERP&depth=16")
        self.assertEqual(r.status_code, 200)
        depth.assert_called_with("BNBUSDT", 50)     # 16 -> next allowed level
        self.assertEqual(r.json()["depth"], 50)

    @mock.patch("apps.bitunix.views.BitunixClient.depth")
    def test_falls_back_to_5_when_empty(self, depth):
        depth.side_effect = [{"asks": [], "bids": []},
                             {"asks": [{"price": 1, "qty": 2}], "bids": [{"price": 0.9, "qty": 2}]}]
        r = self.api.get("/api/bitunix/depth/?symbol=ADAUSDT&depth=15")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(depth.call_count, 2)
        self.assertEqual(depth.call_args_list[1].args, ("ADAUSDT", 5))
        self.assertTrue(r.json()["book"]["bids"])


class JournalMirrorTests(TestCase):
    """Every Bitunix trade (demo or real) must land in the main journal."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("u6", password="p")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        cache.clear()
        _lift_limits(self.user)

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    def test_demo_open_creates_journal_row(self, _lp):
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                           "qty": 0.001, "leverage": 5, "demoBalance": 1000,
                           "tpPrice": 101000, "slPrice": 99000}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        from apps.trades.models import Trade
        t = Trade.objects.get(user=self.user, source="bitunix_demo")
        self.assertEqual(t.direction, "long")
        self.assertEqual(t.entry_price, 100000.0)
        self.assertEqual(t.status, "open")
        pos = DemoPosition.objects.get(user=self.user)
        self.assertEqual(pos.journal_trade_id, t.id)

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100500.0)
    def test_demo_manual_close_closes_journal(self, _lp):
        # open (at 100500 via mocked live price)
        self.api.post("/api/bitunix/order/",
                      {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                       "qty": 0.001, "leverage": 5, "demoBalance": 1000},
                      format="json")
        pos = DemoPosition.objects.get(user=self.user)
        r = self.api.post("/api/bitunix/close/",
                          {"mode": "demo", "positionId": pos.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        from apps.trades.models import Trade
        t = Trade.objects.get(pk=pos.journal_trade_id)
        self.assertEqual(t.status, "closed")
        self.assertIsNotNone(t.exit_price)
        self.assertIsNotNone(t.pnl)

    @mock.patch("apps.bitunix.views.BitunixClient.last_price")
    def test_demo_tp_close_closes_journal(self, lp):
        lp.return_value = 100000.0
        self.api.post("/api/bitunix/order/",
                      {"mode": "demo", "symbol": "BTCUSDT", "side": "BUY",
                       "qty": 0.001, "leverage": 5, "demoBalance": 1000,
                       "tpPrice": 101000}, format="json")
        pos = DemoPosition.objects.get(user=self.user)
        lp.return_value = 101500.0          # TP crossed
        self.api.get("/api/bitunix/positions/?mode=demo")
        from apps.trades.models import Trade
        t = Trade.objects.get(pk=pos.journal_trade_id)
        self.assertEqual(t.status, "closed")
        self.assertEqual(t.exit_price, 101000.0)
        self.assertIn("tp", t.notes)

    @mock.patch("apps.bitunix.views.BitunixClient.place_order",
                return_value={"orderId": "ox1"})
    @mock.patch("apps.bitunix.views.BitunixClient.account",
                return_value=[{"available": "5000"}])
    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    @mock.patch("apps.bitunix.views.BitunixClient.configured",
                new_callable=mock.PropertyMock, return_value=True)
    def test_real_order_creates_journal_row(self, *_):
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "real", "confirm": True, "symbol": "ETHUSDT",
                           "side": "SELL", "qty": 0.1, "leverage": 3}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        from apps.trades.models import Trade
        t = Trade.objects.get(user=self.user, source="bitunix_real")
        self.assertEqual(t.direction, "short")
        self.assertIn("ox1", t.notes)


class FeeAndThrottleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u7", password="p")

    def test_demo_pnl_nets_round_trip_fee(self):
        p = DemoPosition.objects.create(user=self.user, symbol="BTCUSDT",
                                        side="LONG", qty=1, entry_price=100,
                                        leverage=1, margin=100)
        # gross move +10 → 10; fee = (100+110)*0.0006 = 0.126 → net 9.874
        self.assertAlmostEqual(p.unrealized_pnl(110), 9.874, places=3)


class RiskLimitEnforcementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u8", password="p")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        cache.clear()
        _lift_limits(self.user)

    @mock.patch("apps.bitunix.views.BitunixClient.account", return_value=[{"available": "100000"}])
    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    @mock.patch("apps.bitunix.views.BitunixClient.configured",
                new_callable=mock.PropertyMock, return_value=True)
    def test_leverage_cap_blocks_real_order(self, *_):
        from apps.prefs.models import RiskLimits
        lim = RiskLimits.for_user(self.user)
        lim.max_leverage = 10; lim.save()
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "real", "confirm": True, "symbol": "BTCUSDT",
                           "side": "BUY", "qty": 0.001, "leverage": 50}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Leverage", r.json()["error"])

    @mock.patch("apps.bitunix.views.BitunixClient.account", return_value=[{"available": "100000"}])
    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=100000.0)
    @mock.patch("apps.bitunix.views.BitunixClient.configured",
                new_callable=mock.PropertyMock, return_value=True)
    def test_real_trading_disabled_blocks(self, *_):
        from apps.prefs.models import RiskLimits
        lim = RiskLimits.for_user(self.user)
        lim.real_trading_enabled = False; lim.save()
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "real", "confirm": True, "symbol": "BTCUSDT",
                           "side": "BUY", "qty": 0.001, "leverage": 5}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("disabled", r.json()["error"].lower())


class JournalSizeConventionTests(TestCase):
    """Regression: mirrored Trade.size must be MARGIN (USD), not coin qty —
    otherwise the in-app account panel inflates value/qty by ~leverage."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("u9", password="p")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        cache.clear(); _lift_limits(self.user)

    @mock.patch("apps.bitunix.views.BitunixClient.last_price", return_value=7.961)
    def test_demo_journal_size_equals_margin(self, _lp):
        # margin 375 @ 15x on LINK: qty ≈ 706.5, but size stored must be 375
        r = self.api.post("/api/bitunix/order/",
                          {"mode": "demo", "symbol": "LINKUSDT", "side": "BUY",
                           "qty": 706.5, "leverage": 15, "demoBalance": 1000},
                          format="json")
        self.assertEqual(r.status_code, 200, r.content)
        from apps.trades.models import Trade
        t = Trade.objects.get(user=self.user, source="bitunix_demo")
        expected_margin = 706.5 * 7.961 / 15
        self.assertAlmostEqual(t.size, expected_margin, places=1)   # ≈ 375, NOT 706
        # and the app's derivation reproduces the original qty
        notional = t.size * t.leverage
        derived_qty = notional / t.entry_price
        self.assertAlmostEqual(derived_qty, 706.5, places=1)
