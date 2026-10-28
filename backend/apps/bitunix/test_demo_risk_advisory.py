"""Demo stop budgets are advisory; real orders and hard checks are unchanged."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.trades.models import Trade
from .demo_risk import assess, PROFILE
from .models import DemoPosition, FEE_RATE


@override_settings(DEMO_RISK_V1_ENABLED=True)
class DemoStopAdvisoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('stop-advisory')
        self.api = APIClient(); self.api.force_authenticate(self.user)
        self.kw = dict(balance=1000, entry=.9857, stop=.993888,
                       qty=3804.403, leverage=75, side='SELL')

    def position(self, **overrides):
        return DemoPosition.objects.create(**dict(dict(user=self.user, symbol='BTCUSDT',
            side='LONG', qty=10, entry_price=100, sl_price=99, leverage=5, margin=200), **overrides))

    def test_screenshot_both_budgets_warn_without_block(self):
        r = assess(self.user, **self.kw)
        self.assertTrue(r['allowed'], r)
        self.assertEqual(r['errors'], [])
        warnings = {w['code']: w for w in r['warnings']}
        self.assertEqual(set(warnings), {'leverage_above_recommended', 'demo_trade_risk_cap', 'demo_total_stop_risk_cap'})
        expected = self.kw['qty'] * (.993888 - .9857 + (.993888 + .9857) * FEE_RATE)
        self.assertAlmostEqual(warnings['demo_trade_risk_cap']['estimated_risk_usdt'], expected)
        self.assertAlmostEqual(warnings['demo_total_stop_risk_cap']['estimated_risk_usdt'], expected)
        self.assertEqual(warnings['demo_trade_risk_cap']['recommended_max_usdt'], 5)
        self.assertEqual(warnings['demo_total_stop_risk_cap']['recommended_max_usdt'], 15)
        self.assertEqual(r['profile']['stop_risk_policy'], 'warning_only')

    @patch('apps.bitunix.views.BitunixClient.place_order')
    @patch('apps.bitunix.views.BitunixClient.last_price', return_value=.9857)
    def test_screenshot_api_opens_demo_and_journal_without_exchange_order(self, price, place):
        r = self.api.post('/api/bitunix/order/', dict(mode='demo', symbol='SUIUSDT',
            side='SELL', qty=3804.403, leverage=75, slPrice=.993888,
            tpPrice=.962336, demoBalance=1000), format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data['warnings']), 3)
        self.assertEqual(DemoPosition.objects.count(), 1)
        self.assertEqual(Trade.objects.filter(source='bitunix_demo').count(), 1)
        self.assertAlmostEqual(DemoPosition.objects.get().margin, 50, places=4)
        place.assert_not_called()

    def test_aggregate_warning_includes_existing_positions(self):
        self.position()
        r = assess(self.user, **self.kw)
        self.assertTrue(r['allowed'], r)
        self.assertGreater(r['estimated_total_stop_risk_usdt'], r['estimated_stop_loss_usdt'])

    def test_below_recommendations_has_no_budget_warning(self):
        r = assess(self.user, **{**self.kw, 'qty': .1, 'leverage': 5})
        self.assertTrue(r['allowed']); self.assertEqual(r['warnings'], [])

    def test_boundary_includes_round_trip_fees(self):
        per_coin = abs(self.kw['entry']-self.kw['stop']) + (self.kw['entry']+self.kw['stop'])*FEE_RATE
        r = assess(self.user, **{**self.kw, 'qty': 5/per_coin, 'leverage': 5})
        self.assertTrue(r['allowed']); self.assertEqual(r['warnings'], [])

    def test_available_margin_still_blocks_and_preserves_warnings(self):
        r = assess(self.user, **{**self.kw, 'qty': 100000})
        self.assertFalse(r['allowed']); self.assertIn('demo_available_margin', r['errors'])
        self.assertIn('demo_trade_risk_cap', [w['code'] for w in r['warnings']])

    def test_liquidation_distance_still_blocks(self):
        r = assess(self.user, **{**self.kw, 'leverage': 125})
        self.assertFalse(r['allowed'])
        self.assertIn('stop_too_close_to_or_beyond_estimated_liquidation', r['errors'])

    def test_invalid_stop_still_blocks(self):
        r = assess(self.user, **{**self.kw, 'stop': .98})
        self.assertFalse(r['allowed']); self.assertIn('invalid_stop_side', r['errors'])

    def test_open_position_cap_still_blocks(self):
        for _ in range(PROFILE['max_open_positions']): self.position(qty=1, margin=20)
        r = assess(self.user, **self.kw)
        self.assertFalse(r['allowed']); self.assertIn('demo_open_position_cap', r['errors'])

    def test_daily_loss_still_blocks(self):
        self.position(qty=1, margin=20, closed_at=timezone.now(), close_price=75, realized_pnl=-25)
        r = assess(self.user, **self.kw)
        self.assertFalse(r['allowed']); self.assertIn('demo_daily_loss_cap', r['errors'])

    def test_unknown_existing_stop_still_blocks(self):
        self.position(sl_price=None)
        r = assess(self.user, **self.kw)
        self.assertFalse(r['allowed']); self.assertIn('existing_demo_stop_missing_or_invalid', r['errors'])
