from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.alerts.models import UserSignalState, WatchItem
from . import radar


def bars(n=90, step=300, end=1_000_000_200):
    start = end - n * step
    return [{"time": start + i * step, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 10.0}
            for i in range(n)]


class SpikeTests(SimpleTestCase):
    NOW = 1_000_000_200

    def test_quiet_market_has_no_spike(self):
        self.assertIsNone(radar.find_spike(bars(), "5m", now=self.NOW))

    def test_impulse_and_wick_are_classified(self):
        b = bars(); b[-2].update(open=100, high=106, low=99.9, close=105.8, volume=80)
        s = radar.find_spike(b, "5m", now=self.NOW)
        self.assertEqual((s["kind"], s["minutes_ago"]), ("impulse_up", 5))
        b = bars(); b[-1].update(open=100, high=100.2, low=94, close=99.9, volume=80)
        self.assertEqual(radar.find_spike(b, "5m", now=self.NOW)["kind"], "wick_down")

    def test_forming_bar_is_ignored(self):
        b = bars(); b[-1].update(high=110, volume=500)
        self.assertIsNone(radar.find_spike(b, "5m", now=b[-1]["time"] + 10))

    def test_high_range_without_volume_is_not_a_spike(self):
        b = bars(); b[-1].update(high=106, close=105.5)
        self.assertIsNone(radar.find_spike(b, "5m", now=self.NOW))

    def test_dead_feed_reports_nothing(self):
        b = bars(); b[-1].update(high=106, close=105.5, volume=90)
        self.assertIsNone(radar.find_spike(b, "5m", now=self.NOW + 86400))


class PolymarketTests(SimpleTestCase):
    def event(self, **kw):
        return {"title": "What price will Bitcoin hit in December?", "slug": "btc-dec", "volume24hr": "1000",
                "endDate": "2026-12-31T00:00:00Z", "markets": [
                    {"groupItemTitle": "100k", "outcomes": '["Yes","No"]', "outcomePrices": '["0.40","0.60"]', "active": True},
                    {"groupItemTitle": "500k", "outcomes": '["Yes","No"]', "outcomePrices": '["0.001","0.999"]', "active": True},
                    {"groupItemTitle": "closed", "outcomes": '["Yes","No"]', "outcomePrices": '["0.5","0.5"]', "closed": True},
                    {"groupItemTitle": "bad", "outcomes": "nope", "outcomePrices": "[]"}], **kw}

    def test_keeps_only_live_uncertain_markets(self):
        out = radar.parse_polymarket([self.event()])
        self.assertEqual([m["label"] for m in out[0]["markets"]], ["100k"])
        self.assertEqual(out[0]["markets"][0]["yes_pct"], 40.0)

    def test_ignores_non_crypto_titles(self):
        self.assertEqual(radar.parse_polymarket([self.event(title="Who wins the election?")]), [])


class SourceIsolationTests(TestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)

    def test_failed_source_serves_last_good_value(self):
        self.assertEqual(radar._cached("t1", 60, lambda: {"value": 7})["status"], "ok")
        cache.delete("radar:t1")
        def boom():
            raise ValueError("down")
        out = radar._cached("t1", 60, boom)
        self.assertEqual((out["status"], out["value"]), ("stale", 7))

    def test_failed_source_without_history_is_unavailable(self):
        def boom():
            raise ValueError("down")
        self.assertEqual(radar._cached("t2", 60, boom), {"status": "unavailable"})

    def test_macro_without_key_makes_no_request(self):
        with self.settings(POLYGON_API_KEY=""), patch.object(radar, "_json") as call:
            self.assertEqual(radar.macro()["status"], "needs_key")
        call.assert_not_called()

    def test_macro_change_is_close_to_close(self):
        bars = {"results": [{"t": 1795132800000, "o": 737.46, "c": 715.87},
                            {"t": 1795219200000, "o": 713.56, "c": 689.81}]}
        with self.settings(POLYGON_API_KEY="k"), patch.object(radar, "_json", return_value=bars) as call:
            row = radar.macro()["rows"][0]
        self.assertEqual((row["close"], row["change_pct"]), (689.81, -3.64))
        self.assertEqual(call.call_args.kwargs["headers"], {"Authorization": "Bearer k"})

    def test_cmc_is_used_only_with_a_key(self):
        cmc = {"data": {"btc_dominance": 58.1, "eth_dominance": 10.2, "quote": {"USD": {
            "total_market_cap": 2e12, "total_market_cap_yesterday_percentage_change": -1.234}}}}
        with self.settings(CMC_API_KEY="k"), patch.object(radar, "_json", return_value=cmc) as call:
            out = radar.global_metrics()
        self.assertEqual((out["source"], out["change_24h_pct"]), ("CoinMarketCap", -1.23))
        self.assertEqual(call.call_args.kwargs["headers"], {"X-CMC_PRO_API_KEY": "k"})


class BoardTests(TestCase):
    def test_board_is_scoped_to_the_user_and_explains_waits(self):
        a, b = User.objects.create_user("a"), User.objects.create_user("b")
        WatchItem.objects.create(user=a, symbol="BTCUSDT:PERP")
        UserSignalState.objects.create(user=a, symbol="BTCUSDT:PERP", timeframe="1h", last_signal="wait",
                                       last_reason="price is only 0.20 ATR from EMA21 — wait")
        UserSignalState.objects.create(user=b, symbol="BTCUSDT:PERP", timeframe="1h", last_signal="buy")
        board = radar.playbook_board(a, ["BTCUSDT:PERP"])
        self.assertEqual(board["BTCUSDT:PERP"]["1h"]["signal"], "wait")
        self.assertEqual(board["BTCUSDT:PERP"]["1h"]["code"], "no_push")
        self.assertEqual(radar.user_symbols(a), ["BTCUSDT:PERP"])
        self.assertEqual(len(radar.user_symbols(b)), len(radar.DEFAULT_SYMBOLS))
