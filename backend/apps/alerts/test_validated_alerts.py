from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.strategy.backtest import backtest
from apps.strategy.config_models import Strategy, StrategyVersion
from .models import Notification, WatchItem
from .signal_check import _alert_mode, evaluate_and_alert


def playbook(signal="buy", version=None):
    return dict(signal=signal, score=80, entry=60000, stop_loss=59000, take_profit=63000, risk_reward=3,
                signal_source="playbook", strategy_id=None, strategy_version_id=version, generated_at=1,
                exit_plan={"breakeven": {"trigger_price": 61000, "stop_price": 60100}})


@override_settings(ALERTS_VALIDATED_ONLY=True)
class ValidatedAlertTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("w")
        WatchItem.objects.create(user=self.user, symbol="BTCUSDT:PERP", min_score=60)
        for target in ("apps.alerts.signal_check.vapid_configured", "apps.alerts.gating.trade_alerts_muted"):
            p = patch(target, return_value=False); p.start(); self.addCleanup(p.stop)

    def strategy(self, source):
        s = Strategy.objects.create(user=self.user, name="s", market="crypto", is_active=True)
        v = StrategyVersion.objects.create(strategy=s, version=1, risk={"signal_source": source} if source else {})
        return s, v

    def test_no_strategy_and_unvalidated_strategy_use_the_playbook(self):
        self.assertEqual(_alert_mode(self.user), "trend")
        self.strategy("strategy")
        self.assertEqual(_alert_mode(self.user), "trend")

    def test_playbook_strategy_keeps_its_own_rules(self):
        self.strategy("playbook")
        self.assertEqual(_alert_mode(self.user), "safe")

    @override_settings(ALERTS_VALIDATED_ONLY=False)
    def test_switch_restores_previous_behaviour(self):
        self.assertEqual(_alert_mode(self.user), "safe")

    def test_flicker_inside_the_limit_window_is_one_alert(self):
        seq = [playbook(), playbook("wait"), playbook()]
        with patch("apps.strategy.decision.decide", side_effect=seq):
            for _ in seq:
                evaluate_and_alert("BTCUSDT:PERP", "1h")
        note = Notification.objects.get()
        self.assertIn("move SL to 60100", note.body)
        self.assertEqual(note.meta["mode"], "trend")

    def test_new_setup_after_the_window_alerts_again(self):
        with patch("apps.strategy.decision.decide", side_effect=[playbook(), playbook("wait"), playbook()]):
            evaluate_and_alert("BTCUSDT:PERP", "1h")
            evaluate_and_alert("BTCUSDT:PERP", "1h")
            Notification.objects.update(created=timezone.now() - timedelta(hours=13))
            evaluate_and_alert("BTCUSDT:PERP", "1h")
        self.assertEqual(Notification.objects.count(), 2)

    def test_opposite_side_is_not_suppressed(self):
        with patch("apps.strategy.decision.decide", side_effect=[playbook("buy"), playbook("sell")]):
            evaluate_and_alert("BTCUSDT:PERP", "1h")
            evaluate_and_alert("BTCUSDT:PERP", "1h")
        self.assertEqual(Notification.objects.count(), 2)


class BreakevenBacktestTests(TestCase):
    """Exit mechanics on a hand-built path (decider stubbed to one long trade)."""

    def run_path(self, closes, breakeven_r=1.0):
        path = [100.0] * 400 + closes
        candles = [{"time": 3600 * i, "open": path[max(i - 1, 0)], "close": c,
                    "high": max(c, path[max(i - 1, 0)]) + 0.1, "low": min(c, path[max(i - 1, 0)]) - 0.1, "volume": 1}
                   for i, c in enumerate(path)]
        fired = []
        def decider(*a, **k):
            def decide(i):
                if fired:
                    return None
                fired.append(i)
                return {"direction": "buy", "entry": 100.0, "stop": 98.0, "target": 106.0, "entry_type": "limit",
                        "expiry_bars": 12, "max_hold": 72, "breakeven_r": breakeven_r, "breakeven_lock_r": 0.1}
            return decide
        with patch("apps.strategy.backtest._playbook_decider", side_effect=decider):
            return backtest("BTCUSDT", candles, timeframe="1h", mode="trend", fee_rate=0, maker_fee_rate=0,
                            slippage_bps=0, funding_rate_8h=0)

    def test_stop_moves_after_a_close_at_1r(self):
        result = self.run_path([100.0, 102.5, 103.0, 100.0, 100.0])
        trade = result["trade_list"][0]
        self.assertEqual(trade["exit_reason"], "breakeven")
        self.assertAlmostEqual(trade["r"], 0.1)

    def test_without_the_trigger_the_full_stop_applies(self):
        trade = self.run_path([100.0, 101.0, 97.0, 97.0])["trade_list"][0]
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertAlmostEqual(trade["r"], -1.0)

    def test_trigger_bar_itself_cannot_be_stopped_at_breakeven(self):
        # Close reaches 1R but its low is below the would-be BE stop: still open.
        trade = self.run_path([100.0, 102.2, 106.5, 106.5])["trade_list"][0]
        self.assertEqual(trade["exit_reason"], "target")

    def test_plain_exit_when_breakeven_is_off(self):
        trade = self.run_path([100.0, 102.5, 100.0, 97.0], breakeven_r=None)["trade_list"][0]
        self.assertEqual(trade["exit_reason"], "stop")
