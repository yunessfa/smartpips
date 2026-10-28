from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from .config_models import Strategy, StrategyVersion
from .rule_engine import evaluate, extract_features
from .rule_schema import validate_rules, validate_weights, validate_risk
from .selection import apply_strategy
from .presets import PRESETS
from .engine import run_strategy
from .backtest import backtest, _resample
from .volume_profile import volume_profile


def bars(n=100, price=100):
    return [{"open": price, "high": price * 1.02, "low": price * .98,
             "close": price * 1.001, "volume": 200 + i} for i in range(n)]


def config(rules, **kwargs):
    strategy = SimpleNamespace(name="test", direction="both", market="crypto", symbols=[], timeframes=[], pk=1)
    return SimpleNamespace(strategy=strategy, rules=validate_rules(rules), weights={}, min_confidence=60,
                           version=1, pk=1, risk={}, **kwargs)


class RuleRegressionTests(SimpleTestCase):
    def test_every_preset_validates(self):
        for p in PRESETS:
            validate_rules(p["rules"]); validate_weights(p["weights"]); validate_risk(p["risk"])

    def test_real_engine_features_have_numeric_readings(self):
        result = run_strategy("BTCUSDT", "5m", bars(), {})
        features = extract_features(result)
        for key in ("rsi", "macd_hist", "volume_ratio", "atr_pct"):
            self.assertIsInstance(features[key], (float, int), key)
        self.assertIn(features["market_regime"], ("trending", "ranging", "quiet", "volatile"))

    def test_missing_required_input_vetoes(self):
        v = config([{"block": "rsi", "operator": "gte", "value": 0},
                    {"block": "volume_ratio", "operator": "gte", "value": 1, "required": True}])
        self.assertEqual(evaluate(v, {"signal": "buy", "rsi": 55})["signal"], "WAIT")

    def test_configuration_changes_decision(self):
        a = config([{"block": "rsi", "operator": "gte", "value": 50, "applies_to": "long"}])
        b = config([{"block": "rsi", "operator": "lt", "value": 50, "applies_to": "long"}])
        self.assertEqual(evaluate(a, {"signal": "buy", "rsi": 60})["signal"], "BUY")
        self.assertEqual(evaluate(b, {"signal": "buy", "rsi": 60})["signal"], "WAIT")

    def test_rules_never_flip_existing_plan(self):
        v = config([{"block": "rsi", "operator": "gte", "value": 0, "applies_to": "short"}])
        d = {"signal": "buy", "rsi": 70, "entry": 100, "stop_loss": 99, "take_profit": 103}
        apply_strategy(d, v.strategy, v, "BTCUSDT", "5m")
        self.assertEqual(d["signal"], "wait")

    def test_incompatible_market_returns_wait(self):
        v = config([])
        d = {"signal": "buy"}
        apply_strategy(d, v.strategy, v, "XAUUSD", "5m")
        self.assertEqual(d["signal"], "wait")

    def test_zero_weight_is_not_fallback_weight(self):
        v = config([{"block": "rsi", "operator": "gte", "value": 0},
                    {"block": "volume_ratio", "operator": "gte", "value": 5}])
        v.weights = {"rsi": 100, "volume": 0}
        self.assertEqual(evaluate(v, {"signal": "buy", "rsi": 50, "volume_ratio": 1})["confidence"], 100)

    def test_same_group_rules_share_budget(self):
        v = config([{"block": "rsi", "operator": "gte", "value": 0},
                    {"block": "rsi", "operator": "lte", "value": 100},
                    {"block": "volume_ratio", "operator": "gte", "value": 5}])
        v.weights = {"rsi": 50, "volume": 50}
        self.assertEqual(evaluate(v, {"signal": "buy", "rsi": 50, "volume_ratio": 1})["confidence"], 50)

    def test_inactive_session_is_not_overridden_by_session_dict(self):
        f = extract_features({"session": {"name": "Asia"}, "rule_features": {"session_active": False}})
        self.assertFalse(f["session_active"])

    def test_no_rules_cannot_trade_with_zero_threshold(self):
        v = config([]); v.min_confidence = 0
        self.assertEqual(evaluate(v, {"signal": "buy"})["signal"], "WAIT")

    def test_low_price_crypto_levels_preserved(self):
        # Indicators must not round sub-cent readings to zero.
        result = run_strategy("SHIBUSDT", "5m", bars(price=.00001234), {})
        self.assertGreater(result["support"], 0)
        self.assertGreater(result["indicators"]["EMA9"], 0)

    def test_profile_bounds_and_missing_volume(self):
        p = volume_profile(bars())
        self.assertLessEqual(p["val"], p["poc"])
        self.assertLessEqual(p["poc"], p["vah"])
        self.assertIsNone(volume_profile([{**b, "volume": 0} for b in bars()]))


class BacktestRegressionTests(SimpleTestCase):
    @patch("apps.strategy.backtest._decide_at")
    def test_costs_subtracted_no_overlap_and_tf_forwarded(self, decide):
        decide.return_value = {"direction": "buy", "entry": 100, "stop": 99, "target": 101}
        result = backtest("BTCUSDT", bars(110), timeframe="1m")
        self.assertTrue(result["fees_deducted"])
        self.assertGreater(result["trades"], 0)
        for t in result["trade_list"]:
            self.assertLess(t["r"], t["gross_r"])
        for a, b in zip(result["trade_list"], result["trade_list"][1:]):
            self.assertGreater(b["entry_index"], a["exit_index"])
        self.assertEqual(decide.call_args.kwargs["timeframe"], "1m")
        self.assertEqual(result["trade_list"][0]["exit_reason"], "stop")

    def test_incomplete_htf_not_used(self):
        self.assertEqual(len(_resample(bars(8), 3)), 2)

    def test_tick_backtest_rejected(self):
        self.assertEqual(backtest("BTCUSDT", bars(), tick_mode=True)["trades"], 0)

    @patch("apps.strategy.engine.run_strategy", return_value={"signal": "wait"})
    def test_backtest_uses_historical_session(self, run):
        from .backtest import _decide_at
        data = [{**b, "time": 1700000000 + i * 60} for i, b in enumerate(bars())]
        _decide_at("BTCUSDT", data, timeframe="1m")
        self.assertEqual(run.call_args.args[1], "1m")
        self.assertEqual(int(run.call_args.kwargs["as_of"].timestamp()), data[-1]["time"] + 60)


class SelectionIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("strat", password="pass1234")
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def test_active_strategy_is_used_by_decide(self):
        strategy = Strategy.objects.create(user=self.user, name="Restrictive", market="crypto", is_active=True)
        StrategyVersion.objects.create(strategy=strategy, rules=validate_rules([
            {"block": "rsi", "operator": "gte", "value": 95, "required": True}]))
        # Live input must be timestamped, completed and fresh; do not bypass the gate.
        import time
        end = int(time.time() // 14400) * 14400 - 300
        valid_bars = [{**bar, "time": end - (99-i)*300} for i, bar in enumerate(bars())]
        with patch("time.time", return_value=end+301), \
             patch("apps.market.candles.fetch_candles", return_value=valid_bars), \
             patch("apps.strategy.engine.run_strategy", return_value={"signal": "buy", "rsi": 60, "score": 90}), \
             patch("apps.market.calendar_guard.high_impact_soon", return_value=(False, "")), \
             patch("apps.strategy.decision._apply_risk"):
            from .decision import decide
            result = decide("BTCUSDT", user=self.user)
        self.assertEqual(result["signal"], "wait")
        self.assertEqual(result["strategy_id"], strategy.pk)

    def test_activation_is_per_user_and_unique(self):
        other = User.objects.create_user("other")
        active = Strategy.objects.create(user=other, name="Other", is_active=True)
        response = self.client.get("/api/strategy/strategies/")
        preset = next(s for s in response.data if s["is_preset"])
        self.assertEqual(self.client.post(f"/api/strategy/strategies/{preset['id']}/activate/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/strategy/strategies/{preset['id']}/activate/").status_code, 200)
        self.assertEqual(Strategy.objects.filter(user=self.user, is_active=True).count(), 1)
        active.refresh_from_db(); self.assertTrue(active.is_active)

    def test_zero_trade_backtest_does_not_unlock_custom(self):
        from django.utils import timezone
        s = Strategy.objects.create(user=self.user, name="Empty")
        StrategyVersion.objects.create(strategy=s, backtest={"trades": 0}, backtest_at=timezone.now())
        self.assertEqual(self.client.post(f"/api/strategy/strategies/{s.pk}/activate/").status_code, 400)

    def test_non_admin_cannot_modify_global_indicators(self):
        response = self.client.post("/api/strategy/indicators/", {"label": "No", "key": "rsi"})
        self.assertEqual(response.status_code, 403)

    def test_chart_input_validation(self):
        self.assertEqual(self.client.get("/api/market/candles/?symbol=INVALID").status_code, 400)
        self.assertEqual(self.client.get("/api/market/candles/?timeframe=99m").status_code, 400)

    def test_invalid_signal_price_is_400(self):
        for price in ("nan", "-1", "oops"):
            r = self.client.post("/api/chat/scalp/", {"symbol": "BTCUSDT", "price": price}, format="json")
            self.assertEqual(r.status_code, 400)
