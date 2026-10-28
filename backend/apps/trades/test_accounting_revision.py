import io
import json
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Trade
from .serializers import TradeSerializer
from apps.strategy.config_models import Strategy, StrategyVersion


class AccountingRevisionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("accounting")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def trade(self, **kw):
        return Trade.objects.create(user=self.user, symbol="BTCUSDT", entry_price=100,
                                    size=100, leverage=1, **kw)

    def test_partial_then_close_counts_only_remainder(self):
        t = self.trade()
        self.assertEqual(t.close_partial(110, 40, "tp1_done"), 4)
        t.close(120)
        self.assertEqual(t.pnl, 16)
        self.assertEqual(t.pnl_percent, 16)
        self.assertEqual(t.remaining_pct, 0)
        self.assertEqual(t.exit_reason, "manual")

    def test_three_partials_no_final_double_count(self):
        t = self.trade()
        t.close_partial(110,40,"tp1_done")
        t.close_partial(120,35,"tp2_done")
        t.close_partial(130,25,"tp3_done")
        self.assertEqual(t.pnl,18.5)
        self.assertEqual(t.status,"closed")
        self.assertEqual(t.remaining_pct,0)

    def test_partial_then_stop_short(self):
        t = self.trade(direction="short")
        t.close_partial(90,40,"tp1_done")
        t.close(105,reason="sl")
        self.assertEqual(t.pnl,1)
        self.assertEqual(t.exit_reason,"sl")

    def test_stale_duplicate_partial_is_idempotent(self):
        t = self.trade()
        stale = Trade.objects.get(pk=t.pk)
        t.close_partial(110,40,"tp1_done")
        self.assertEqual(stale.close_partial(110,40,"tp1_done"),0)
        self.assertEqual(stale.realized_pnl,4)

    def test_closed_trade_never_repriced(self):
        t = self.trade()
        t.close(110)
        first = t.closed_at
        t.close(90)
        self.assertEqual(t.pnl,10)
        self.assertEqual(t.closed_at,first)

    def test_partial_clamped_and_invalid_rejected(self):
        t = self.trade()
        t.close_partial(110,200,"tp1_done")
        self.assertEqual(t.pnl,10)
        with self.assertRaises(ValueError):
            t.close_partial(110,10,"pnl")

    def test_unknown_costs_are_null_not_zero(self):
        t = self.trade(source="bitunix_real")
        t.close(110)
        d = TradeSerializer(t).data
        self.assertIsNone(d["net_pnl"])
        self.assertEqual(d["pnl_basis"],"estimated_unverified")

    def test_signed_funding_cost_and_verified_fees(self):
        t = self.trade(fees_paid=1,funding_paid=-2,costs_verified=True)
        t.close(110)
        self.assertEqual(t.net_pnl,11)

    def test_forged_verification_not_writable(self):
        r=self.api.post("/api/trades/",{"symbol":"BTCUSDT","entry_price":100,"size":10,
                                       "costs_verified":True,"execution_verified":True},format="json")
        self.assertEqual(r.status_code,201)
        self.assertFalse(r.data["costs_verified"])

    def test_invalid_exit_rejected(self):
        t=self.trade()
        for v in (0,-1,"NaN","Infinity"):
            r=self.api.post(f"/api/trades/{t.pk}/close/",{"exit_price":v},format="json")
            self.assertEqual(r.status_code,400)

    def test_strategy_snapshot_survives_rename(self):
        s=Strategy.objects.create(user=self.user,name="Before")
        StrategyVersion.objects.create(strategy=s,version=1)
        r=self.api.post("/api/trades/",{"symbol":"BTCUSDT","entry_price":100,
            "strategy":s.pk,"timeframe":"5m","confidence":62},format="json")
        self.assertEqual(r.status_code,201,r.data)
        s.name="After";s.save()
        t=Trade.objects.get(pk=r.data["id"])
        self.assertEqual(t.strategy_name,"Before")
        self.assertEqual(t.strategy_version,1)
        self.assertEqual(TradeSerializer(t).data["confidence"],62)

    def test_audit_does_not_repair_legacy_pnl(self):
        t=self.trade(status="closed",pnl=214,realized_pnl=15,remaining_pct=60)
        out=io.StringIO()
        call_command("audit_trade_accounting",stdout=out)
        self.assertTrue(json.loads(out.getvalue())["read_only"])
        t.refresh_from_db()
        self.assertEqual(t.pnl,214)

    def test_autoclose_never_closes_real_or_demo_mirror(self):
        self.trade(source="bitunix_real",stop_loss=99)
        self.trade(source="bitunix_demo",stop_loss=99)
        from unittest.mock import patch
        with patch("apps.market.quotes_resolver.live_price",return_value=90) as lp:
            r=self.api.post("/api/trades/auto_close/")
        self.assertEqual(r.status_code,200)
        lp.assert_not_called()
        self.assertEqual(Trade.objects.filter(status="open").count(),2)
    def test_explicit_entry_version_preserves_signal_snapshot(self):
        s=Strategy.objects.create(user=self.user,name="Versioned")
        StrategyVersion.objects.create(strategy=s,version=1)
        StrategyVersion.objects.create(strategy=s,version=2)
        r=self.api.post("/api/trades/",{"symbol":"BTCUSDT","entry_price":100,
            "strategy":s.pk,"entry_strategy_version":1},format="json")
        self.assertEqual(r.status_code,201,r.data)
        self.assertEqual(r.data["strategy_version"],1)
        bad=self.api.post("/api/trades/",{"symbol":"BTCUSDT","entry_price":100,
            "strategy":s.pk,"entry_strategy_version":999},format="json")
        self.assertEqual(bad.status_code,400)
