from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import DemoPosition
from .demo_risk import assess
from .demo_monitor import sweep_demo, settle_demo
from apps.trades.models import Trade
from .management.commands.reconcile_bitunix import preview


@override_settings(DEMO_RISK_V1_ENABLED=True)
class DemoRevisionTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user("demo-research")
        self.api=APIClient();self.api.force_authenticate(self.user)
        self.kw=dict(balance=1000,entry=100,stop=99,qty=.1,leverage=5,side="BUY")

    def test_safe_order_allowed(self):
        self.assertTrue(assess(self.user,**self.kw)["allowed"])

    def test_unknown_balance_stop_and_nonfinite_fail_closed(self):
        for key in ("balance","stop","qty","entry"):
            self.assertFalse(assess(self.user,**{**self.kw,key:None})["allowed"])
        self.assertFalse(assess(self.user,**{**self.kw,"qty":float("nan")})["allowed"])

    def test_risk_and_leverage_caps(self):
        r=assess(self.user,**{**self.kw,"qty":20,"leverage":125})
        self.assertIn("demo_trade_risk_cap",r["errors"])
        self.assertNotIn("demo_leverage_cap",r["errors"])
        self.assertEqual(r["warnings"][0]["code"], "leverage_above_recommended")
        self.assertLess(r["suggested_qty"],5)

    def test_existing_unknown_stop_blocks_aggregate_risk(self):
        DemoPosition.objects.create(user=self.user,symbol="BTCUSDT",side="LONG",
            qty=1,entry_price=100,leverage=5,margin=20)
        self.assertIn("existing_demo_stop_missing_or_invalid",
                      assess(self.user,**self.kw)["errors"])

    def test_other_user_risk_not_counted(self):
        other=get_user_model().objects.create_user("other-demo")
        DemoPosition.objects.create(user=other,symbol="BTCUSDT",side="LONG",
            qty=100,entry_price=100,leverage=5,margin=2000)
        self.assertTrue(assess(self.user,**self.kw)["allowed"])

    @patch("apps.bitunix.views.BitunixClient.last_price",return_value=100)
    def test_api_enforces_demo_not_just_ui(self, lp):
        r=self.api.post("/api/bitunix/order/",{"mode":"demo","symbol":"BTCUSDT",
            "side":"BUY","qty":10,"leverage":50,"slPrice":99,"demoBalance":1000},format="json")
        self.assertEqual(r.status_code,400)
        self.assertEqual(r.data["code"],"demo_risk_blocked")
        self.assertFalse(DemoPosition.objects.exists())

    @patch("apps.bitunix.views.BitunixClient.last_price",return_value=100)
    def test_valid_demo_creates_margin_mirror(self, lp):
        r=self.api.post("/api/bitunix/order/",{"mode":"demo","symbol":"BTCUSDT",
            "side":"BUY","qty":.1,"leverage":5,"slPrice":99,"demoBalance":1000,
            "timeframe":"5m","confidence":71},format="json")
        self.assertEqual(r.status_code,200,r.data)
        t=Trade.objects.get()
        self.assertEqual(t.size,2)
        self.assertEqual(t.confidence,71)
        self.assertEqual(t.timeframe,"5m")

    @patch("apps.bitunix.views.BitunixClient.last_price",return_value=100)
    def test_limit_demo_not_falsely_filled(self,lp):
        # Demo LIMIT is now a resting order (pullback entries): it must NOT be
        # filled at the live price, and it must not create a journal trade.
        r=self.api.post("/api/bitunix/order/",{"mode":"demo","symbol":"BTCUSDT",
            "side":"BUY","qty":.1,"orderType":"LIMIT","price":95,"slPrice":94,
            "demoBalance":1000,"leverage":5},format="json")
        self.assertEqual(r.status_code,200,r.data)
        self.assertTrue(r.data["pending"])
        self.assertFalse(r.data["filled"])
        p=DemoPosition.objects.get()
        self.assertTrue(p.is_pending)
        self.assertEqual(p.entry_price,95)
        self.assertFalse(Trade.objects.filter(source="bitunix_demo").exists())

    def test_monitor_independent_and_idempotent_observed_gap_price(self):
        t=Trade.objects.create(user=self.user,symbol="BTCUSDT",entry_price=100,
                               size=20,leverage=5,source="bitunix_demo")
        p=DemoPosition.objects.create(user=self.user,symbol="BTCUSDT",side="LONG",
            qty=1,entry_price=100,leverage=5,margin=20,sl_price=99,journal_trade_id=t.pk)
        c=Mock();c.last_price.return_value=98
        self.assertEqual(len(sweep_demo(c)["closed"]),1)
        self.assertIsNone(settle_demo(p.pk,97))
        t.refresh_from_db();p.refresh_from_db()
        self.assertEqual(t.exit_price,98)
        self.assertEqual(t.pnl,-2)
        self.assertEqual(t.pnl,p.realized_pnl)
        self.assertEqual(t.exit_reason,"sl")

    def test_unavailable_price_does_not_settle(self):
        p=DemoPosition.objects.create(user=self.user,symbol="BTCUSDT",side="LONG",
            qty=1,entry_price=100,leverage=5,margin=20,sl_price=99)
        c=Mock();c.last_price.side_effect=RuntimeError("down")
        r=sweep_demo(c)
        self.assertTrue(r["errors"])
        p.refresh_from_db();self.assertIsNone(p.closed_at)

    def test_reconcile_requires_exact_identity_and_is_preview_only(self):
        t=Trade.objects.create(user=self.user,symbol="BTCUSDT",entry_price=100,
                               size=20,source="bitunix_real")
        row=dict(positionId="p1",symbol="BTCUSDT",side="LONG",entryPrice="100",
                 closePrice="110",realizedPNL="10",fee="1",funding="-1")
        r=preview(t,{"positionList":[row]},"p1")
        self.assertIsNone(r["net_pnl"]);self.assertTrue(r["read_only"])
        with self.assertRaises(ValueError):
            preview(t,{"positionList":[row]},"p2")
        with self.assertRaises(ValueError):
            preview(t,{"positionList":[row,row]},"p1")
    @patch("apps.bitunix.views._journal_open",return_value=None)
    @patch("apps.bitunix.views.BitunixClient.last_price",return_value=100)
    def test_failed_demo_journal_rolls_back_position(self,lp,journal):
        r=self.api.post("/api/bitunix/order/",{"mode":"demo","symbol":"BTCUSDT",
            "side":"BUY","qty":.1,"leverage":5,"slPrice":99,"demoBalance":1000},format="json")
        self.assertEqual(r.status_code,503)
        self.assertFalse(DemoPosition.objects.exists())

    def test_daily_loss_blocks_new_demo(self):
        from django.utils import timezone
        DemoPosition.objects.create(user=self.user,symbol="BTCUSDT",side="LONG",
            qty=1,entry_price=100,leverage=5,margin=20,closed_at=timezone.now(),
            close_price=75,realized_pnl=-25)
        self.assertIn("demo_daily_loss_cap",assess(self.user,**self.kw)["errors"])
