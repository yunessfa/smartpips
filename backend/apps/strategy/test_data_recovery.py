from unittest.mock import patch
from django.test import SimpleTestCase
from .test_hotfix import historical_bars
from .backtest_data import historical_window
from .backtest import backtest


class HistoricalDataRecoveryTests(SimpleTestCase):
    def test_one_gap_does_not_discard_other_valid_candles_or_stitch_a_trade(self):
        raw=historical_bars(n=500); del raw[103]
        with patch('apps.market.candles.fetch_candles',return_value=raw):
            window,info=historical_window('BTCUSDT:PERP','5m',with_diagnostics=True)
        self.assertEqual(len(window),396)
        self.assertEqual(info['gaps_detected'],1)
        self.assertTrue(info['partial_history'])
        self.assertTrue(all(b['time']-a['time']==300 for a,b in zip(window,window[1:])))

    def test_numeric_strings_milliseconds_and_one_bad_bar(self):
        raw=historical_bars(n=300)
        raw[20]['close']='bad'
        raw=[{k:str(v*1000 if k=='time' else v) for k,v in b.items()} for b in raw]
        with patch('apps.market.candles.fetch_candles',return_value=raw):
            window,info=historical_window('BTCUSDT','5m',with_diagnostics=True)
        self.assertEqual(info['invalid_rows'],1)
        self.assertEqual(len(window),279)
        self.assertTrue(info['partial_history'])

    def test_zero_trade_backtest_has_metrics_and_rejection_diagnostics(self):
        with patch('apps.strategy.engine.run_strategy',return_value={'signal':'wait','score':20}):
            result=backtest('BTCUSDT',historical_bars(n=100))
        self.assertEqual(result['trades'],0)
        self.assertEqual(result['wins'],0); self.assertIsNone(result['win_rate'])
        self.assertGreater(result['diagnostics']['base_engine_wait'],0)
        self.assertEqual(result['diagnostics']['bars_evaluated'],result['diagnostics']['base_engine_wait'])
