from datetime import timedelta
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from .models import Trade, TradeEvent
from .snapshots import issue_token, read_token
from .analytics import analyze, summarize

class SnapshotTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username="snapshot",password="x")
        self.trade=Trade.objects.create(user=self.user,symbol="BTCUSDT:PERP",entry_price=100,stop_loss=99,take_profit=102,size=10,leverage=2,source="bitunix_demo")
    def test_initial_snapshot(self):
        self.assertEqual(self.trade.entry_snapshot["context"]["stop_loss"],99)
        self.assertEqual(len(self.trade.entry_snapshot_hash),64)
        self.assertEqual(self.trade.events.count(),1)
        self.assertAlmostEqual(self.trade.entry_snapshot["initial_risk_quote"],.2)
    def test_trailing_preserves_snapshot(self):
        old=self.trade.entry_snapshot_hash;self.trade.stop_loss=100;self.trade.save();self.trade.refresh_from_db()
        self.assertEqual(self.trade.entry_snapshot_hash,old)
        self.assertEqual(self.trade.entry_snapshot["context"]["stop_loss"],99)
        self.assertEqual(self.trade.events.count(),2)
    def test_snapshot_model_guard(self):
        self.trade.entry_snapshot={"fake":True}
        with self.assertRaises(ValueError):self.trade.save()
    def test_snapshot_queryset_guard(self):
        with self.assertRaises(ValueError):Trade.objects.filter(pk=self.trade.pk).update(entry_snapshot={})
    def test_event_guard(self):
        event=self.trade.events.first();event.event="fake"
        with self.assertRaises(ValueError):event.save()
        with self.assertRaises(ValueError):TradeEvent.objects.all().update(event="fake")
    def test_close_idempotent(self):
        self.trade.close(102);n=self.trade.events.count();self.trade.close(200)
        self.assertEqual(self.trade.events.count(),n);self.assertEqual(self.trade.exit_price,102)
    def test_legacy_remains_unknown(self):
        from django.db import connection
        with connection.cursor() as c:c.execute("UPDATE trades_trade SET entry_snapshot = '{}', entry_snapshot_hash = '' WHERE id = %s",[self.trade.pk])
        self.trade.refresh_from_db();self.trade.notes="legacy";self.trade.save()
        self.assertEqual(self.trade.entry_snapshot,{})
    def test_signed_context(self):
        other=get_user_model().objects.create_user(username="other")
        token=issue_token(self.user,"BTCUSDT:PERP","5m",{"score":84})
        self.assertEqual(read_token(token,self.user,"BTCUSDT")["decision"]["score"],84)
        for bad,user,symbol in ((token,other,"BTCUSDT"),(token,self.user,"ETHUSDT"),(token+"x",self.user,"BTCUSDT")):
            with self.assertRaises(ValidationError):read_token(bad,user,symbol)
    def test_api_owner_scope(self):
        other=get_user_model().objects.create_user(username="other");client=APIClient();client.force_authenticate(other)
        self.assertEqual(client.get(f"/api/trades/{self.trade.pk}/audit_timeline/").status_code,404)
        self.assertEqual(client.get("/api/trades/analytics/").json()["overall"]["trades"],0)
    def test_no_fake_calibration(self):
        from .journal import calibrated_confidence
        out=calibrated_confidence(self.user,"A+",84,min_trades=0)
        self.assertFalse(out["calibrated"]);self.assertIsNone(out["historical_probability"]);self.assertEqual(out["value"],84)
    def test_overnight_source_scope(self):
        from apps.strategy.risk import daily_risk_guard
        Trade.objects.filter(pk=self.trade.pk).update(opened_at=timezone.now()-timedelta(days=2))
        self.trade.close(90)
        self.assertTrue(daily_risk_guard(self.user,balance=10,max_daily_loss_pct=1)["blocked"])
        self.assertFalse(daily_risk_guard(self.user,balance=10,max_daily_loss_pct=1,sources={"bitunix_real"})["blocked"])

class AnalyticsTests(SimpleTestCase):
    def rows(self):
        return [{"id":i,"status":"closed","pnl":p,"closed_at":f"2026-01-0{i+1}T12:00:00+00:00","opened_at":f"2026-01-0{i+1}T11:00:00+00:00","source":"manual"} for i,p in enumerate([2,-1,0,3,-2])]
    def test_zero_and_drawdown(self):
        v=summarize(self.rows());self.assertEqual((v["wins"],v["losses"],v["zeros"]),(2,2,1))
        self.assertEqual(v["total_reported_pnl"],2);self.assertAlmostEqual(v["profit_factor"],5/3)
        self.assertEqual(v["max_drawdown_reported_pnl"],2);self.assertIsNone(v["average_R"])
        self.assertIsNone(v["verified_net_pnl"]);self.assertEqual(v["holding_minutes"]["mean"],60)
    def test_segment_reconciliation(self):
        for dim,buckets in analyze(self.rows())["segments"].items():
            self.assertEqual(sum(b["trades"] for b in buckets),5,dim)
            self.assertEqual(sum(b["total_reported_pnl"] for b in buckets),2,dim)
    def test_empty_unknown(self):
        v=summarize([]);self.assertIsNone(v["win_rate"]);self.assertIsNone(v["profit_factor"])
    def test_immutable_R(self):
        rows=self.rows()[:1];rows[0].update(stop_loss=100,entry_snapshot={"initial_risk_quote":1,"context":{"entry":100,"stop_loss":99,"take_profit":102}})
        v=summarize(rows);self.assertEqual(v["average_R"],2);self.assertEqual(v["planned_R"]["mean"],2)
    def test_nonfinite_not_zero(self):
        rows=self.rows()[:1];rows[0]["pnl"]=float("nan")
        v=summarize(rows);self.assertEqual(v["pnl_sample"],0);self.assertIsNone(v["win_rate"])
