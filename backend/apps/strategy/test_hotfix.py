"""Regression tests of raw persisted presets, not serializer-normalized fixtures."""
import math
import time
from types import SimpleNamespace
from unittest.mock import patch
import requests
from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIClient
from .backtest import TF_SECONDS
from .config_models import Strategy, StrategyVersion
from .presets import PRESETS
from .rule_engine import evaluate
from .rule_schema import RuleError, validate_rules, validate_weights, validate_risk


def historical_bars(timeframe='5m', n=500):
    step = TF_SECONDS[timeframe]
    last = int(time.time()) // step * step - step
    result = []
    for i in range(n):
        p = 60000 + 200 * math.sin(i / 17) + i
        result.append(dict(time=last - (n - 1 - i) * step, open=p, high=p+70,
                           low=p-70, close=p+10, volume=100+i % 13))
    return result


class RawRuleTests(SimpleTestCase):
    def test_all_raw_presets_without_optional_keys_evaluate(self):
        for p in PRESETS:
            v = SimpleNamespace(rules=p['rules'], weights=p['weights'], risk=p['risk'],
                                min_confidence=p['min_confidence'], version=1,
                                strategy=SimpleNamespace(direction=p['direction'], name=p['name']))
            result = evaluate(v, {'signal': 'buy', 'rsi': 60, 'score': 80})
            self.assertNotEqual(result.get('code'), 'invalid_strategy_config', p['key'])
            self.assertIn(result['signal'], ('BUY', 'SELL', 'WAIT'))

    def test_corrupt_legacy_config_fails_closed(self):
        for rules in ([{'block': 'not_a_block'}], ['broken'], {'wrong': 'shape'}):
            v = SimpleNamespace(rules=rules, weights={}, risk={}, min_confidence=70,
                                version=1, strategy=SimpleNamespace(direction='both', name='bad'))
            result = evaluate(v, {'signal': 'buy'})
            self.assertEqual(result['signal'], 'WAIT')
            self.assertEqual(result['code'], 'invalid_strategy_config')

    def test_nonfinite_values_are_not_accepted(self):
        with self.assertRaises(RuleError):
            validate_rules([{'block': 'rsi', 'operator': 'gte', 'value': float('nan')}])
        with self.assertRaises(RuleError):
            validate_weights({'rsi': float('nan')})
        with self.assertRaises(RuleError):
            validate_risk({'min_rr': float('inf')})


class LiveBacktestAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('hotfix')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_every_preset_activation_raw_db_backtest_and_live_real_engine(self):
        # Only external market/news IO is stubbed. Real DB, rule evaluator,
        # engine, resampling and simulator run end-to-end on 500 synthetic bars.
        library = self.client.get('/api/strategy/strategies/').data
        for p in PRESETS:
            with self.subTest(preset=p['key']):
                preset = next(s for s in library if s['is_preset'] and s['preset_key'] == p['key'])
                response = self.client.post(f"/api/strategy/strategies/{preset['id']}/activate/")
                self.assertEqual(response.status_code, 200, response.data)
                owned_id = response.data['id']
                # Simulate clones already stored by the old unnormalized code.
                StrategyVersion.objects.filter(strategy_id=owned_id).update(rules=p['rules'])
                timeframe = p['timeframes'][0]
                def candles(symbol, tf, limit=500):
                    return historical_bars(tf, limit)
                with patch('apps.market.candles.fetch_candles', side_effect=candles), \
                     patch('apps.market.calendar_guard.high_impact_soon', return_value=(False, '')):
                    result = self.client.post(f'/api/strategy/strategies/{owned_id}/backtest/',
                                              {'timeframe': timeframe}, format='json')
                    self.assertEqual(result.status_code, 200, result.data)
                    self.assertEqual(result.data['candles_used'], 500)
                    self.assertIn('trades', result.data)
                    live = self.client.post('/api/chat/scalp/', {
                        'symbol': 'BTCUSDT', 'price': 60200, 'timeframe': timeframe,
                        'explain': False}, format='json')
                    self.assertEqual(live.status_code, 200, live.data)
                    self.assertEqual(live.data['strategy_id'], owned_id)
                    self.assertIn('strategy_evaluation', live.data)
                    self.assertNotEqual(live.data['strategy_evaluation'].get('code'),
                                        'invalid_strategy_config')

    def test_no_history_is_503_not_fake_tick_backtest(self):
        with patch('apps.market.candles.fetch_candles', return_value=[]):
            r = self.client.post('/api/strategy/backtest/', {
                'symbol': 'BTCUSDT', 'tick_series': [60000]*100}, format='json')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.data['code'], 'no_data')

    def test_scalp_backtest_uses_active_strategy_and_version(self):
        p = PRESETS[0]
        s = Strategy.objects.create(user=self.user, name='Selected', is_active=True,
                                    market='crypto', timeframes=['5m'])
        v = StrategyVersion.objects.create(strategy=s, rules=p['rules'],
                                            weights=p['weights'], risk=p['risk'])
        with patch('apps.market.candles.fetch_candles', return_value=historical_bars(n=100)):
            r = self.client.post('/api/strategy/backtest/', {'symbol': 'BTCUSDT'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['strategy_id'], s.pk)
        self.assertEqual(r.data['strategy_version_id'], v.pk)

    def test_provider_timeout_is_structured_503(self):
        with patch('apps.market.candles.fetch_candles', side_effect=requests.Timeout()):
            r = self.client.post('/api/strategy/backtest/', {'symbol': 'BTCUSDT'})
        self.assertEqual(r.status_code, 503)

    def test_invalid_input_is_400_not_500(self):
        for data in ({'symbol': ['BTCUSDT']}, {'symbol': 'INVALID'}, {'timeframe': {}},
                     {'timeframe': '3m'}):
            # Empty values default; a nonempty object must fail validation.
            if data == {'timeframe': {}}:
                data = {'timeframe': {'bad': '5m'}}
            self.assertEqual(self.client.post('/api/strategy/backtest/', data,
                                             format='json').status_code, 400)

    def test_closed_candles_sorted_deduplicated_both_endpoints(self):
        raw = historical_bars(n=100)
        step = 300
        current = {**raw[-1], 'time': int(time.time()) // step * step}
        supplied = list(reversed(raw)) + [raw[-1], current]
        strategy = Strategy.objects.create(user=self.user, name='history')
        StrategyVersion.objects.create(strategy=strategy)
        with patch('apps.market.candles.fetch_candles', return_value=supplied):
            for path in ('/api/strategy/backtest/',
                         f'/api/strategy/strategies/{strategy.pk}/backtest/'):
                r = self.client.post(path, {'symbol': 'BTCUSDT'}, format='json')
                self.assertEqual(r.status_code, 200, r.data)
                self.assertEqual(r.data['candles_used'], 100)

    def test_short_corrupt_and_gapped_history_explicit(self):
        for raw, status, code in (
                (historical_bars(n=30), 400, 'insufficient_history'),
                ([{**historical_bars(n=1)[0], 'close': 'bad'}], 503, 'invalid_market_data'),
                (historical_bars(n=100)[1:40] + historical_bars(n=100)[41:], 400, 'insufficient_contiguous_history')):
            with patch('apps.market.candles.fetch_candles', return_value=raw):
                r = self.client.post('/api/strategy/backtest/', {'symbol': 'BTCUSDT'})
            self.assertEqual(r.status_code, status, r.data)
            self.assertEqual(r.data['code'], code)

    def test_metal_strategy_defaults_to_gold_not_bitcoin(self):
        strategy = Strategy.objects.create(user=self.user, name='Gold', market='metals')
        StrategyVersion.objects.create(strategy=strategy)
        with patch('apps.market.candles.fetch_candles', return_value=historical_bars(n=100)) as fetch:
            r = self.client.post(f'/api/strategy/strategies/{strategy.pk}/backtest/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(fetch.call_args.args[0], 'XAUUSD')
        self.assertEqual(self.client.post(f'/api/strategy/strategies/{strategy.pk}/backtest/',
                                         {'symbol': 'BTCUSDT'}).status_code, 400)

    def test_broken_saved_backtest_does_not_crash_list_or_activation(self):
        from django.utils import timezone
        s = Strategy.objects.create(user=self.user, name='Legacy')
        StrategyVersion.objects.create(strategy=s, backtest=['old'], backtest_at=timezone.now())
        self.assertEqual(self.client.get('/api/strategy/strategies/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/strategy/strategies/{s.pk}/activate/').status_code, 400)

    def test_optional_explanation_failure_preserves_real_analysis(self):
        from apps.ai.models import AIProvider
        AIProvider.objects.create(label='fixture', is_active=True)
        with patch('apps.market.candles.fetch_candles', side_effect=lambda s, tf, limit: historical_bars(tf, limit)), \
             patch('apps.market.calendar_guard.high_impact_soon', return_value=(False, '')), \
             patch('apps.chat.views.chat_completion', side_effect=RuntimeError('fixture failure')):
            with self.assertLogs('apps.chat.views', level='ERROR'):
                r = self.client.post('/api/chat/scalp/', {'symbol': 'BTCUSDT', 'price': 60200}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('score', r.data)
        self.assertIn('explanation', r.data)


class CandleCacheTests(SimpleTestCase):
    def test_short_chart_window_cannot_truncate_backtest(self):
        from django.core.cache import cache
        from apps.market import candles
        cache.clear(); candles._cache.clear()
        with patch.object(candles, '_binance_candles', side_effect=lambda s, tf, limit: historical_bars(tf, limit)) as provider:
            self.assertEqual(len(candles.fetch_candles('BTCUSDT', '5m', 200)), 200)
            self.assertEqual(len(candles.fetch_candles('BTCUSDT', '5m', 500)), 500)
            self.assertEqual(provider.call_count, 2)
        cache.clear(); candles._cache.clear()
