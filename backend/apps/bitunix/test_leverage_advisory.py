"""No network orders: internal leverage recommendation is warning-only."""
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.prefs.models import RiskLimits
from apps.trades.models import Trade
from .demo_risk import assess
from .models import DemoPosition

class LeverageAdvisoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('leverage-advisory')
        self.api = APIClient(); self.api.force_authenticate(self.user)
        self.limits = RiskLimits.for_user(self.user)
        self.limits.max_leverage = 10; self.limits.save()
        self.payload = dict(mode='real', confirm=True, symbol='BTCUSDT', side='BUY',
                            qty=.1, leverage=50)
        self.client = Mock(configured=True)
        self.client.last_price.return_value = 100
        self.client.account.return_value = {'available': 1000}
        self.client.place_order.return_value = {'orderId': 'mock-no-exchange-order'}

    def send(self, **overrides):
        with patch('apps.bitunix.views._client', return_value=self.client):
            return self.api.post('/api/bitunix/order/', {**self.payload, **overrides}, format='json')

    def test_high_leverage_is_warning_not_veto(self):
        response = self.send()
        self.assertEqual(response.status_code, 200, response.data)
        warning = response.data['warnings'][0]
        self.assertEqual(warning['code'], 'leverage_above_recommended')
        self.assertEqual(warning['recommended_max'], 10)
        self.assertEqual(warning['leverage'], 50)
        self.client.change_leverage.assert_called_once_with('BTCUSDT', 50)
        self.client.place_order.assert_called_once()
        self.assertIn('leverage_above_recommended', Trade.objects.get().notes)

    def test_at_recommendation_has_no_warning(self):
        response = self.send(leverage=10)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['warnings'], [])

    def test_account_disabled_is_not_bypassed(self):
        self.limits.real_trading_enabled = False; self.limits.save()
        self.assertEqual(self.send().status_code, 400)
        self.client.place_order.assert_not_called()

    def test_notional_limit_is_not_bypassed(self):
        self.limits.max_position_usdt = 1; self.limits.save()
        self.assertEqual(self.send().status_code, 400)
        self.client.place_order.assert_not_called()

    def test_daily_loss_limit_is_not_bypassed(self):
        with patch.object(RiskLimits, 'today_realized_loss', return_value=1000):
            self.assertEqual(self.send().status_code, 400)
        self.client.place_order.assert_not_called()

    def test_open_position_limit_is_not_bypassed(self):
        self.limits.max_open_positions = 0; self.limits.save()
        self.assertEqual(self.send().status_code, 400)
        self.client.place_order.assert_not_called()

    def test_exchange_leverage_rejection_still_blocks(self):
        from .client import BitunixError
        self.client.change_leverage.side_effect = BitunixError('exchange rejected')
        self.assertEqual(self.send().status_code, 502)
        self.client.place_order.assert_not_called()

    def test_insufficient_margin_still_blocks(self):
        self.client.account.return_value = {'available': 0}
        self.assertEqual(self.send().status_code, 400)
        self.client.place_order.assert_not_called()

    def test_order_confirmation_still_required(self):
        self.assertEqual(self.send(confirm=False).status_code, 400)
        self.client.place_order.assert_not_called()

    def test_invalid_leverage_is_not_advisory(self):
        for leverage in (-1, 0, 1.5, 'nan', 'invalid'):
            with self.subTest(leverage=leverage):
                self.assertEqual(self.send(leverage=leverage).status_code, 400)
        self.client.place_order.assert_not_called()

    @override_settings(DEMO_RISK_V1_ENABLED=True)
    def test_demo_above_recommendation_can_open(self):
        response = self.send(mode='demo', leverage=50, slPrice=99.9, demoBalance=1000)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['warnings'][0]['code'], 'leverage_above_recommended')
        self.assertEqual(DemoPosition.objects.get().leverage, 50)
        self.client.place_order.assert_not_called()

    def test_liquidation_stop_gate_remains_separate(self):
        result = assess(self.user, balance=1000, entry=100, stop=99,
                        qty=.1, leverage=125, side='BUY')
        self.assertIn('stop_too_close_to_or_beyond_estimated_liquidation', result['errors'])
        self.assertEqual(result['warnings'][0]['code'], 'leverage_above_recommended')
