"""'My strategy decides' mode: user rules (e.g. volume profile) create the signal."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from .engine import run_strategy
from .rule_schema import RuleError, validate_risk, validate_rules
from .selection import apply_strategy
from .test_scalp_plan import trend_bars


def version(rules, source, direction="both"):
    strategy = SimpleNamespace(name="vp", direction=direction, market="crypto", symbols=[], timeframes=[], pk=7)
    return SimpleNamespace(strategy=strategy, rules=validate_rules(rules), weights={}, min_confidence=60,
                           version=1, pk=7, risk={"signal_source": source})


VP_LONG = [{"block": "price_vs_value_area", "operator": "is", "value": "above", "applies_to": "long", "required": True},
           {"block": "price_vs_value_area", "operator": "is", "value": "below", "applies_to": "short", "required": True}]


class SignalSourceTests(SimpleTestCase):
    def setUp(self):
        self.rows = trend_bars(300)
        self.base = run_strategy("BTCUSDT", "5m", self.rows, {}, live_price=self.rows[-1]["close"])

    def test_schema_accepts_only_known_sources(self):
        self.assertEqual(validate_risk({"signal_source": "strategy"})["signal_source"], "strategy")
        with self.assertRaises(RuleError):
            validate_risk({"signal_source": "anything"})

    def test_filter_mode_cannot_create_a_signal_from_engine_wait(self):
        d = dict(self.base, signal="wait")
        apply_strategy(d, *self._args("engine_filter"), candles=self.rows)
        self.assertEqual(d["signal"], "wait")
        self.assertEqual(d["signal_source"], "engine_filter")

    def test_strategy_mode_creates_signal_from_its_own_rules(self):
        d = dict(self.base, signal="wait")
        self.assertEqual(d["rule_features"]["price_vs_value_area"], "above")  # rising fixture
        apply_strategy(d, *self._args("strategy"), candles=self.rows)
        self.assertEqual(d["signal_source"], "strategy")
        if d["signal"] == "wait":   # only acceptable when the plan itself refused (fees/stop cap)
            self.assertIn("Strategy mode", d["reason"])
            return
        self.assertEqual(d["signal"], "buy")
        self.assertLess(d["stop_loss"], d["entry"])
        self.assertGreater(d["take_profit"], d["entry"])
        self.assertEqual(len(d["tp_levels"]), 3)
        self.assertEqual(d["base_engine_signal"], "wait")

    def test_strategy_mode_respects_unmet_rules_and_bad_data(self):
        short_only = version(VP_LONG, "strategy", direction="short")
        d = dict(self.base, signal="wait")
        apply_strategy(d, short_only.strategy, short_only, "BTCUSDT", "5m", candles=self.rows)
        self.assertEqual(d["signal"], "wait")
        d = dict(self.base, signal="buy", data_quality="stale")
        v = version(VP_LONG, "strategy")
        apply_strategy(d, v.strategy, v, "BTCUSDT", "5m", candles=self.rows)
        self.assertEqual(d["signal"], "wait")

    def _args(self, source):
        v = version(VP_LONG, source)
        return v.strategy, v, "BTCUSDT", "5m"
