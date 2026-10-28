from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from apps.strategy.config_models import Strategy, StrategyVersion
from apps.strategy.test_hotfix import historical_bars
from .models import WatchItem, Notification, UserSignalState
from .signal_check import evaluate_and_alert


def decision(signal='buy', version=1):
    return dict(signal=signal, score=80, entry=60000, stop_loss=59000,
                take_profit=62000, risk_reward=2, strategy_id=1,
                strategy_version_id=version, strategy_name='Fixture', generated_at=123)


class AlertPipelineTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user('watcher-a')
        self.b = User.objects.create_user('watcher-b')
        for u in (self.a, self.b):
            WatchItem.objects.create(user=u, symbol='BTCUSDT', min_score=70)
        self.patches = [patch('apps.alerts.gating.trade_alerts_muted', return_value=False),
                        patch('apps.alerts.gating.notify_allowed', return_value=True),
                        patch('apps.alerts.signal_check.vapid_configured', return_value=False)]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def test_user_specific_decisions_no_global_broadcast_and_dedup(self):
        def choose(*args, user, **kw):
            return decision('buy' if user.pk == self.a.pk else 'wait')
        with patch('apps.strategy.decision.decide', side_effect=choose) as decide, \
             patch('apps.alerts.signal_check.broadcast') as push:
            evaluate_and_alert('BTCUSDT','1m'); evaluate_and_alert('BTCUSDT','1m')
        self.assertEqual(Notification.objects.count(),1)
        note=Notification.objects.get(); self.assertEqual(note.user,self.a)
        self.assertEqual(note.meta['strategy_version_id'],1)
        self.assertEqual(note.meta['mode'],'safe')
        self.assertEqual(decide.call_count,4); push.assert_not_called()
        self.assertEqual(UserSignalState.objects.count(),2)

    def test_push_recipient_is_only_the_owner_of_final_buy(self):
        with patch('apps.strategy.decision.decide', side_effect=lambda *a,user,**kw: decision('buy' if user==self.a else 'wait')), \
             patch('apps.alerts.signal_check.vapid_configured',return_value=True), \
             patch('apps.alerts.signal_check.broadcast',return_value=1) as push:
            self.assertEqual(evaluate_and_alert('BTCUSDT','5m'),1)
        self.assertEqual(push.call_args.kwargs['users'],[self.a])

    def test_below_score_or_risk_muted_does_not_latch_buy(self):
        WatchItem.objects.filter(user=self.a).update(min_score=90)
        with patch('apps.strategy.decision.decide', return_value=decision()), \
             patch('apps.alerts.gating.trade_alerts_muted',side_effect=lambda u:u==self.b):
            evaluate_and_alert('BTCUSDT','1m')
        # no trade signal; the muted user only gets the one-per-day "alerts paused" notice
        self.assertEqual(Notification.objects.filter(category='signal').count(),0)
        self.assertEqual(list(Notification.objects.values_list('user','category')),[(self.b.pk,'risk')])
        self.assertFalse(UserSignalState.objects.exclude(last_signal='wait').exists())

    def test_strategy_version_change_and_wait_transition_are_user_scoped(self):
        WatchItem.objects.filter(user=self.b).update(active=False)
        for sig,version in [('buy',1),('buy',1),('buy',2),('wait',2),('buy',2)]:
            with patch('apps.strategy.decision.decide',return_value=decision(sig,version)):
                evaluate_and_alert('BTCUSDT','1m')
        self.assertEqual(Notification.objects.count(),3)

    def test_one_user_error_does_not_stop_other_users(self):
        def choose(*a,user,**kw):
            if user==self.a: raise RuntimeError('isolated fixture error')
            return decision()
        with patch('apps.strategy.decision.decide',side_effect=choose), \
             self.assertLogs('smartpips.alerts',level='ERROR'):
            evaluate_and_alert('BTCUSDT','5m')
        self.assertEqual(Notification.objects.get().user,self.b)

    def test_monitor_includes_one_minute_even_without_vapid(self):
        with patch('apps.alerts.management.commands.monitor_scalp.vapid_configured',return_value=False), \
             patch('apps.alerts.management.commands.monitor_scalp.evaluate_and_alert',return_value=0) as evaluate:
            call_command('monitor_scalp',stdout=StringIO())
        self.assertIn(('BTCUSDT','1m'),[c.args for c in evaluate.call_args_list])

    def test_real_decide_applies_each_users_selected_strategy(self):
        # Mock external data/engine only; real strategy selector/evaluator and
        # final alert persistence run. Opposite required RSI gates must differ.
        for u,value in ((self.a,50),(self.b,90)):
            s=Strategy.objects.create(user=u,name=f'RSI-{value}',market='crypto',
                                      timeframes=['1m'],is_active=True)
            StrategyVersion.objects.create(strategy=s,version=1,min_confidence=70,
                rules=[{'block':'rsi','operator':'gte','value':value,'required':True}],weights={'rsi':100})
        base={**decision(),'indicators':{'RSI':60},'rule_features':{'rsi':60}}
        with patch('apps.market.candles.fetch_candles',side_effect=lambda symbol,tf,limit=300: historical_bars(tf,limit)), \
             patch('apps.strategy.engine.run_strategy',side_effect=lambda *a,**kw:dict(base)), \
             patch('apps.market.calendar_guard.high_impact_soon',return_value=(False,'')), \
             patch('apps.strategy.decision._apply_risk'):
            evaluate_and_alert('BTCUSDT','1m')
        self.assertEqual(Notification.objects.count(),1)
        note=Notification.objects.get();self.assertEqual(note.user,self.a)
        self.assertEqual(note.meta['strategy_name'],'RSI-50')

    def test_news_guard_in_shared_pipeline_blocks_alerts(self):
        with patch('apps.market.candles.fetch_candles',side_effect=lambda symbol,tf,limit=300: historical_bars(tf,limit)), \
             patch('apps.strategy.engine.run_strategy',side_effect=lambda *a,**kw:decision()), \
             patch('apps.market.calendar_guard.high_impact_soon',return_value=(True,'fixture high-impact event')), \
             patch('apps.strategy.decision._apply_risk'):
            evaluate_and_alert('BTCUSDT','1m')
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(UserSignalState.objects.exclude(last_signal='wait').exists())

    def test_last_moment_risk_suppression_does_not_mark_alert_as_emitted(self):
        with patch('apps.strategy.decision.decide',return_value=decision()), \
             patch('apps.alerts.gating.notify_allowed',return_value=False):
            evaluate_and_alert('BTCUSDT','1m')
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(UserSignalState.objects.exclude(last_signal='wait').exists())
