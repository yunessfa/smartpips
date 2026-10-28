"""'Why didn't I get an alert today?' — mute announcement, reasons, heartbeat."""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Notification, UserSignalState, WatchItem
from .signal_check import evaluate_and_alert
from .test_signal_pipeline import decision


class AlertDiagnosticsTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user('diag')
        WatchItem.objects.create(user=self.u, symbol='BTCUSDT', min_score=0)
        p = patch('apps.alerts.signal_check.vapid_configured', return_value=False)
        p.start(); self.addCleanup(p.stop)

    def run_pass(self, d, muted=False):
        with patch('apps.strategy.decision.decide', return_value=d), \
             patch('apps.alerts.gating.trade_alerts_muted', return_value=muted), \
             patch('apps.alerts.gating.loss_limit_state',
                   return_value={'blocked': muted, 'reason': '3 losses in a row today — take a break'}):
            evaluate_and_alert('BTCUSDT', '5m')

    def test_muted_day_is_announced_once_not_silent(self):
        for _ in range(3):
            self.run_pass(decision('buy'), muted=True)
        notes = Notification.objects.filter(user=self.u)
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.get().category, 'risk')
        self.assertIn('3 losses', notes.get().body)
        self.assertIn('muted', UserSignalState.objects.get().last_reason)

    def test_wait_reason_and_check_time_are_recorded(self):
        self.run_pass({**decision('wait'), 'wait_reasons': [{'code': 'low_score', 'message': 'confluence score 50 below 60'}]})
        st = UserSignalState.objects.get()
        self.assertIsNotNone(st.last_checked)
        self.assertIn('score 50', st.last_reason)
        self.run_pass(decision('buy'))
        self.assertIn('notified', UserSignalState.objects.get().last_reason)
        self.run_pass(decision('buy'))
        self.assertIn('already notified', UserSignalState.objects.get().last_reason)

    def test_status_endpoint_explains_monitor_mute_and_pairs(self):
        with patch('apps.strategy.decision.decide', return_value=decision('wait')), \
             patch('apps.alerts.gating.trade_alerts_muted', return_value=False):
            call_command('monitor_scalp', stdout=StringIO())
        api = APIClient(); api.force_authenticate(self.u)
        r = api.get('/api/alerts/status/').json()
        self.assertTrue(r['monitor']['healthy'])
        self.assertIn('BTCUSDT', r['watching'])
        self.assertTrue(any(p['symbol'] == 'BTCUSDT' for p in r['pairs']))
        self.assertIn('blocked', r['muted'])
