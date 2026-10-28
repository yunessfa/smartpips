from unittest.mock import patch
from django.test import SimpleTestCase
from .risk import position_size
from .evidence import bounded_family_model, enrich_explanation
from .strict_liquidity import confirmed_sweep, regime_policy
from .evaluation import split_plan, evaluate

class FoundationTests(SimpleTestCase):
    def test_floor_sizing(self):
        p=position_size("BTCUSDT:PERP",100,.5,10000,9940,leverage=5);self.assertLessEqual(p["quantity"]*60,.5)
    def test_minimum_lot_overbudget_rejected(self):
        self.assertIsNone(position_size("XAUUSD",100,.1,2000,1900))
    def test_unknown_contract_rejected(self):
        self.assertIsNone(position_size("EURUSD",1000,1,1.1,1.09))
    def test_nonfinite_rejected(self):
        for v in (float("nan"),float("inf"),-1,0):self.assertIsNone(position_size("BTCUSDT",v,1,100,99))
    def test_family_budget(self):
        a=bounded_family_model({"MOMENTUM":[1]});b=bounded_family_model({"MOMENTUM":[1,1,1]})
        self.assertEqual(a["directional_balance"],b["directional_balance"]);self.assertIsNone(a["probability"]);self.assertEqual(a["coverage"],1/9)
    def test_final_wait_retained(self):
        d=enrich_explanation({"signal":"wait","score":110,"reason":"scope mismatch"})
        self.assertEqual(d["signal_strength"],100);self.assertEqual(d["score"],110)
        self.assertEqual(d["explanation_tree"]["blocking_reasons"][-1]["message"],"scope mismatch")
    def test_sweep_requires_breach_and_followthrough(self):
        bar={"time":1000,"open":101,"high":102,"low":100.1,"close":101};confirm={"time":1060,"close":103}
        self.assertFalse(confirmed_sweep(100,bar,confirm,1,"buy")["confirmed"])
        bar["low"]=99;self.assertTrue(confirmed_sweep(100,bar,confirm,1,"buy")["confirmed"])
        confirm["close"]=101;self.assertFalse(confirmed_sweep(100,bar,confirm,1,"buy")["confirmed"])
    def test_separate_confirmation(self):
        b={"time":1000,"open":101,"high":102,"low":99,"close":101}
        self.assertFalse(confirmed_sweep(100,b,{"time":1000,"close":103},1,"buy")["confirmed"])
    def test_regime_policy(self):
        self.assertEqual(regime_policy("TRANSITION")["allowed_setups"],[]);self.assertTrue(regime_policy("other")["unknown_blocks"])
    def test_split_bounds(self):
        self.assertEqual(split_plan(1000),{"train":[0,700],"validation":[700,850],"holdout":[850,1000]})
        with self.assertRaises(ValueError):split_plan(100)
    @patch("apps.strategy.evaluation.run_selected",return_value={"trades":0,"diagnostics":{"bars_evaluated":10,"base_engine_wait":10}})
    def test_prefix_and_holdout_sealed(self,run):
        out=evaluate("BTCUSDT",[{"time":i} for i in range(1000)])
        self.assertEqual(out["holdout"]["status"],"not_accessed")
        self.assertEqual([len(c.args[1]) for c in run.call_args_list],[700,850,550,700,850]);self.assertFalse(out["parameter_fitting"])

class LiveDataQualityTests(SimpleTestCase):
    def inspect(self,rows):
        from .data_quality import inspect_bars
        return inspect_bars(rows,60,10000)
    def bar(self,t=1000):return {"time":t,"open":100,"high":102,"low":98,"close":101,"volume":10}
    def test_valid(self):self.assertTrue(self.inspect([self.bar(),self.bar(1060)])[1]["valid"])
    def test_duplicate(self):self.assertFalse(self.inspect([self.bar(),self.bar()])[1]["valid"])
    def test_gap(self):self.assertFalse(self.inspect([self.bar(),self.bar(1120)])[1]["valid"])
    def test_nonfinite(self):
        b=self.bar();b["close"]=float("nan");self.assertFalse(self.inspect([b])[1]["valid"])
    def test_high_low_invalid(self):
        b=self.bar();b["high"]=99;self.assertFalse(self.inspect([b])[1]["valid"])
    def test_forming_removed(self):self.assertFalse(self.inspect([self.bar(9990)])[1]["valid"])
    def test_missing_timestamp(self):
        b=self.bar();del b["time"];self.assertFalse(self.inspect([b])[1]["valid"])
