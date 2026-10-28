import importlib.util
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient
from .config_models import Strategy, StrategyVersion
from .config_serializers import has_trade_backtest
from .backtest_runner import run_selected, ResearchUnavailable
from apps.trades.models import Trade


def candles(n=100):
    return [dict(time=1700000040+i*60,open=100.,high=100.1,low=99.9,close=100.,
                 volume=10.) for i in range(n)]


class ResearchRoutingTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user("research-test")
        self.api=APIClient();self.api.force_authenticate(self.user)

    def test_native_remains_default(self):
        with patch("apps.strategy.backtest._decide_at",return_value=None):
            r=run_selected("BTCUSDT",candles(),timeframe="1m")
        self.assertEqual(r["engine"],"native")
        self.assertFalse(r["experimental"])
        self.assertIsNone(r["win_rate"])

    def test_research_result_never_unlocks_activation(self):
        from django.utils import timezone
        s=Strategy.objects.create(user=self.user,name="r")
        v=StrategyVersion.objects.create(strategy=s,version=1,
            backtest={"trades":10,"experimental":True},backtest_at=timezone.now())
        self.assertFalse(has_trade_backtest(v))

    def test_research_api_does_not_overwrite_native_result(self):
        s=Strategy.objects.create(user=self.user,name="r",market="crypto")
        v=StrategyVersion.objects.create(strategy=s,version=1,backtest={"trades":3})
        with patch("apps.strategy.backtest_data.historical_window",return_value=(candles(),{})), \
             patch("apps.strategy.backtest_runner.run_selected",
                   return_value={"trades":1,"experimental":True,"engine":"backtesting"}):
            r=self.api.post(f"/api/strategy/strategies/{s.pk}/backtest/",
                            {"engine":"backtesting","timeframe":"1m"},format="json")
        self.assertEqual(r.status_code,200,r.data)
        v.refresh_from_db();self.assertEqual(v.backtest,{"trades":3})

    def test_missing_optional_dependency_has_specific_503(self):
        import builtins
        real_import=builtins.__import__
        def block(name,*a,**kw):
            if name in ("pandas","backtesting") or name.startswith("backtesting."):
                raise ImportError("not installed")
            return real_import(name,*a,**kw)
        with patch("builtins.__import__",side_effect=block):
            with self.assertRaises(ResearchUnavailable):
                run_selected("BTCUSDT",candles(),timeframe="1m",source={"engine":"backtesting"})

    def test_analytics_separates_sources_and_versions(self):
        s=Strategy.objects.create(user=self.user,name="r")
        for source,version in [("manual",1),("bitunix_demo",1),("manual",2)]:
            t=Trade.objects.create(user=self.user,symbol="BTCUSDT",entry_price=100,
                size=10,strategy=s,strategy_name="r",strategy_version=version,source=source)
            t.close(101)
        r=self.api.get("/api/strategy/strategies/analytics/")
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(r.data["results"]),3)

    def test_holdout_no_pre_split_decisions(self):
        calls=[]
        def wait(symbol,prefix,**kw):
            calls.append(len(prefix));return None
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bars.json";path.write_text(json.dumps(candles(200)))
            out=io.StringIO()
            with patch("apps.strategy.backtest._decide_at",side_effect=wait):
                call_command("research_backtest",input=str(path),symbol="BTCUSDT:PERP",
                             timeframe="1m",engine="native",holdout=.3,stdout=out)
        result=json.loads(out.getvalue())
        self.assertEqual(result["split_index"],140)
        # Training starts with 61 bars; holdout starts only after the split.
        self.assertIn(141,calls)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["parameter_fitting"])


@__import__("unittest").skipUnless(importlib.util.find_spec("backtesting"),"Optional research dependency not installed")
class LibraryExecutionTests(SimpleTestCase):
    def test_prefix_only_and_fractional_trade(self):
        from .research_backtesting import run
        c=candles()
        c[64]["high"]=103
        seen=[]
        def decide(symbol,prefix,**kw):
            seen.append(len(prefix))
            return {"direction":"buy","entry":100,"stop":99,"target":102} if len(prefix)==61 else None
        with patch("apps.strategy.research_backtesting._decide_at",side_effect=decide):
            r=run("BTCUSDT",c,timeframe="1m")
        self.assertEqual(r["trades"],1)
        self.assertEqual(r["trade_list"][0]["entry_index"],61)
        self.assertEqual(r["trade_list"][0]["exit_index"],64)
        self.assertGreater(r["trade_list"][0]["r"],0)
        self.assertTrue(r["experimental"])
        self.assertFalse(r["activation_eligible"])
        self.assertEqual(seen[0],61)