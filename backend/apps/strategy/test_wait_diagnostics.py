from unittest.mock import patch
from django.test import SimpleTestCase
from .backtest import backtest
from .test_hotfix import historical_bars
from .engine import run_strategy


class WaitDiagnosticsTests(SimpleTestCase):
    def test_each_gate_is_counted_once_per_bar_and_retains_example(self):
        snapshot={'signal':'wait','reason':'two gates', 'wait_reasons':[
            {'code':'low_score','message':'score 41 below 66'},
            {'code':'weak_conviction','message':'conviction 12 below 42'},
            {'code':'low_score','message':'duplicate must not double count'}]}
        with patch('apps.strategy.engine.run_strategy',return_value=snapshot):
            result=backtest('BTCUSDT',historical_bars(n=100),timeframe='1m')
        d=result['diagnostics']; n=d['bars_evaluated']
        self.assertEqual(d['base_engine_wait'],n)
        self.assertEqual(d['base_wait_reasons']['low_score']['count'],n)
        self.assertEqual(d['base_wait_reasons']['weak_conviction']['count'],n)
        self.assertIn('41',d['base_wait_reasons']['low_score']['example'])
        self.assertFalse(d['strategy_veto_reasons'])

    def test_strategy_wait_does_not_replace_original_base_wait_diagnostics(self):
        def veto(d,*a,**kw):
            d.update(signal='wait',reason='Active strategy does not cover this market/symbol/timeframe.')
        version=type('Version',(),{'strategy':object()})()
        with patch('apps.strategy.engine.run_strategy',side_effect=lambda *a,**kw:{'signal':'wait','wait_reasons':[{'code':'low_score','message':'score below 66'}]}), \
             patch('apps.strategy.selection.apply_strategy',side_effect=veto):
            r=backtest('BTCUSDT',historical_bars(n=100),version=version)
        self.assertGreater(r['diagnostics']['base_wait_reasons']['low_score']['count'],0)
        self.assertEqual(r['diagnostics']['strategy_veto'],0)

    def test_strategy_veto_is_separate_from_base_wait(self):
        def veto(d,*a,**kw):
            d.update(signal='wait',reason='Active strategy does not cover this market/symbol/timeframe.')
        version=type('Version',(),{'strategy':object()})()
        with patch('apps.strategy.engine.run_strategy',side_effect=lambda *a,**kw:{'signal':'buy'}), \
             patch('apps.strategy.selection.apply_strategy',side_effect=veto):
            r=backtest('BTCUSDT',historical_bars(n=100),version=version)
        d=r['diagnostics']
        self.assertEqual(d['base_engine_wait'],0)
        self.assertEqual(d['strategy_veto_reasons']['strategy_scope']['count'],d['bars_evaluated'])

    def test_real_engine_returns_structured_gates_matching_original_reason(self):
        result=run_strategy('BTCUSDT','1m',historical_bars(n=200),{},as_of=None)
        if result['signal']=='wait':
            self.assertTrue(result['wait_reasons'])
            self.assertEqual(result['reason'],'; '.join(r['message'] for r in result['wait_reasons']))
        else:
            self.assertFalse(result['wait_reasons'])
