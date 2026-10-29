"""Trend-pullback playbook + long-history backtest (2026-10)."""
import math
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from . import trend_pullback as tp
from .backtest import backtest, evidence, _closed_htf
from .backtest_data import requested_bars, historical_window


def series(n, step, start=100.0, drift=0.003, rng=0.004, t0=None, dips_every=0, dip_depth=0.0):
    """Trending candles; optional sharp dips (wick-only pullbacks) every k bars."""
    t0 = t0 if t0 is not None else (int(time.time()) // step) * step - n * step
    rows, p = [], start
    for i in range(n):
        o = p
        c = p * (1 + drift)
        h = max(o, c) * (1 + rng / 2)
        low = min(o, c) * (1 - rng / 2)
        if dips_every and i % dips_every == dips_every - 1:
            low = min(o, c) * (1 - dip_depth)
        rows.append({"time": t0 + i * step, "open": o, "high": h, "low": low, "close": c, "volume": 10.0})
        p = c
    return rows


class IndicatorTests(SimpleTestCase):
    def test_ema_matches_recurrence_seeded_with_first_value(self):
        vals = [1, 2, 3, 4, 5]
        e = tp.ema_series(vals, 3)
        k = 0.5
        ref = [1.0]
        for v in vals[1:]:
            ref.append(v * k + ref[-1] * (1 - k))
        self.assertEqual([round(x, 9) for x in e], [round(x, 9) for x in ref])

    def test_wilder_atr_first_bar_is_high_minus_low(self):
        rows = [{"high": 11, "low": 9, "close": 10}, {"high": 12, "low": 10, "close": 11}]
        a = tp.atr_series(rows, 14)
        self.assertEqual(a[0], 2)
        self.assertAlmostEqual(a[1], 2 * (1 / 14) + 2 * (13 / 14))


class HTFAlignmentTests(SimpleTestCase):
    def test_htf_bar_is_only_visible_after_it_closed(self):
        rows = series(300, 14400, t0=0)
        view = tp.HTFView(rows, 14400)
        # bar k covers [k*4h, (k+1)*4h); at exactly (k+1)*4h it is closed
        self.assertEqual(view.at(14400 * 10), 9)
        self.assertEqual(view.at(14400 * 10 - 1), 8)
        self.assertIsNone(view.at(14399))

    def test_backtest_htf_slice_never_contains_open_bar(self):
        rows = series(50, 3600, t0=0)
        got = _closed_htf(rows, "1h", 3600 * 10 + 1800)
        self.assertEqual(got[-1]["time"], 3600 * 9)


class PlaybookDecisionTests(SimpleTestCase):
    def setUp(self):
        self.h1 = series(700, 3600, drift=0.003, rng=0.006)
        end = self.h1[-1]["time"] + 3600
        self.h4 = series(400, 14400, drift=0.006, rng=0.01, t0=end - 400 * 14400)

    def test_uptrend_stretched_gives_limit_buy_at_ema21_with_validated_geometry(self):
        d = tp.apply({}, "BTCUSDT:PERP", "1h", self.h1, {"4h": self.h4})
        self.assertEqual(d["signal"], "buy", d.get("wait_reasons"))
        ind = tp.indicators(self.h1)
        self.assertAlmostEqual(d["entry_plan"]["price"], ind["e21"][-1], delta=ind["e21"][-1] * 1e-6)
        self.assertEqual(d["entry_plan"]["type"], "limit")
        self.assertEqual(d["entry_plan"]["expiry_bars"], tp.LIMIT_VALID_BARS)
        risk = d["entry"] - d["stop_loss"]
        self.assertAlmostEqual(risk, 1.5 * ind["atr"][-1], delta=risk * 1e-3)
        self.assertAlmostEqual((d["take_profit"] - d["entry"]) / risk, 3.0, places=2)
        self.assertEqual(d["exit_plan"]["max_hold_bars"], 72)
        self.assertEqual(d["signal_source"], "playbook")
        self.assertGreaterEqual(d["stop_pct"], tp.MIN_STOP_PCT)

    def test_quiet_market_is_skipped_by_min_stop_filter(self):
        quiet = series(700, 3600, drift=0.0004, rng=0.0008)
        end = quiet[-1]["time"] + 3600
        h4 = series(400, 14400, drift=0.001, rng=0.002, t0=end - 400 * 14400)
        d = tp.apply({}, "BTCUSDT", "1h", quiet, {"4h": h4})
        self.assertEqual(d["signal"], "wait")
        self.assertIn("stop_below_cost_floor", [w["code"] for w in d["wait_reasons"]])

    def test_counter_trend_and_missing_htf_are_wait(self):
        down4 = series(400, 14400, drift=-0.006, rng=0.01, t0=self.h4[0]["time"])
        d = tp.apply({}, "BTCUSDT", "1h", self.h1, {"4h": down4})
        self.assertEqual(d["signal"], "wait")
        d = tp.apply({}, "BTCUSDT", "1h", self.h1, {"4h": []})
        self.assertEqual(d["signal"], "wait")
        self.assertIn("htf_unavailable", [w["code"] for w in d["wait_reasons"]])

    def test_short_timeframes_need_1h_agreement_and_1m_is_not_supported(self):
        m15 = series(700, 900, drift=0.002, rng=0.005)
        end = m15[-1]["time"] + 900
        h4 = series(400, 14400, drift=0.006, rng=0.01, t0=end - 400 * 14400)
        h1_down = series(400, 3600, drift=-0.003, rng=0.006, t0=end - 400 * 3600)
        d = tp.apply({}, "BTCUSDT", "15m", m15, {"4h": h4, "1h": h1_down})
        self.assertEqual(d["signal"], "wait")
        self.assertIn("h1_conflict", [w["code"] for w in d["wait_reasons"]])
        d = tp.apply({}, "BTCUSDT", "1m", m15, {"4h": h4})
        self.assertIn("playbook_timeframe", [w["code"] for w in d["wait_reasons"]])

    def test_metals_are_not_validated(self):
        d = tp.apply({}, "XAUUSD", "1h", self.h1, {"4h": self.h4})
        self.assertEqual(d["signal"], "wait")


class PlaybookBacktestTests(SimpleTestCase):
    def test_limit_fills_on_dips_targets_hit_and_hold_capped(self):
        h1 = series(1500, 3600, drift=0.003, rng=0.006, dips_every=40, dip_depth=0.06)
        end = h1[-1]["time"] + 3600
        h4 = series(700, 14400, drift=0.006, rng=0.01, t0=end - 700 * 14400)
        r = backtest("BTCUSDT", h1, timeframe="1h", mode="trend", htf_series={"4h": h4})
        self.assertEqual(r["signal_source"], "playbook")
        self.assertGreater(r["trades"], 0)
        for t in r["trade_list"]:
            self.assertEqual(t["entry_type"], "limit")
            self.assertLessEqual(t["exit_index"] - t["entry_index"], tp.MAX_HOLD_BARS)
            self.assertLess(t["r"], t["gross_r"])  # fees + funding deducted
        self.assertIn(r["evidence"]["verdict"],
                      ("insufficient_sample", "positive_edge", "inconclusive", "negative_edge"))
        self.assertGreater(r["diagnostics"].get("limit_not_filled", 0), 0)

    def test_no_dips_means_no_fills_never_chases(self):
        h1 = series(900, 3600, drift=0.003, rng=0.006)
        end = h1[-1]["time"] + 3600
        h4 = series(500, 14400, drift=0.006, rng=0.01, t0=end - 500 * 14400)
        r = backtest("BTCUSDT", h1, timeframe="1h", mode="trend", htf_series={"4h": h4})
        self.assertEqual(r["trades"], 0)
        self.assertGreater(r["diagnostics"]["limit_not_filled"], 0)


class EvidenceTests(SimpleTestCase):
    def test_small_samples_are_never_called_an_edge(self):
        e = evidence([{"r": 2.0, "entry_time": 0}] * 5)
        self.assertEqual(e["verdict"], "insufficient_sample")

    def test_ci_and_verdicts(self):
        good = [{"r": r, "entry_time": i * 86400} for i, r in enumerate([1.0, -0.5] * 40)]
        e = evidence(good)
        self.assertEqual(e["verdict"], "positive_edge")
        self.assertLess(e["expectancy_95ci"][0], 0.25)
        self.assertGreater(e["expectancy_95ci"][1], 0.25)
        noise = [{"r": r, "entry_time": 0} for r in [1.0, -1.0] * 40]
        self.assertEqual(evidence(noise)["verdict"], "inconclusive")
        self.assertEqual(e["out_of_sample"]["n"], 24)
        self.assertTrue(e["monthly"])


class HistoryRequestTests(SimpleTestCase):
    def test_bars_are_validated_with_tf_defaults(self):
        self.assertEqual(requested_bars({}, "5m"), 6000)
        self.assertEqual(requested_bars({"bars": "1000"}, "1h"), 1000)
        from rest_framework.exceptions import ValidationError
        for bad in ("abc", 10, 10**6):
            with self.assertRaises(ValidationError):
                requested_bars({"bars": bad}, "1h")

    def test_long_window_comes_from_paginated_history(self):
        rows = series(3000, 300, rng=0.002)
        with patch("apps.market.candles.fetch_history", return_value=(rows, {"source": "test", "pages": 15})) as fh:
            window, info = historical_window("BTCUSDT:PERP", "5m", with_diagnostics=True, bars=3000)
        fh.assert_called_once()
        self.assertGreaterEqual(len(window), 2990)
        self.assertEqual(info["source"], "test")
        self.assertGreater(info["days_covered"], 10)

    def test_history_paginates_backwards_without_duplicates(self):
        from apps.market import candles
        cache.clear()
        allrows = series(1000, 300)

        def page(base, tf, limit, end_time=None):
            pool = [r for r in allrows if end_time is None or r["time"] * 1000 <= end_time]
            return pool[-limit:]
        with patch("apps.bitunix.client.BitunixClient.klines", side_effect=page), \
             patch("apps.market.candles.time.sleep"):
            rows, info = candles.fetch_history("BTCUSDT:PERP", "5m", 950)
        self.assertEqual(len(rows), 950)
        self.assertEqual([r["time"] for r in rows], sorted({r["time"] for r in rows}))
        self.assertEqual(info["source"], "bitunix")
        self.assertGreaterEqual(info["pages"], 5)
        cache.clear()


class LiveDecideTrendModeTests(TestCase):
    def setUp(self):
        cache.clear()
        step = 3600
        now = int(time.time())
        self.h1 = series(600, step, t0=(now // step) * step - 600 * step, drift=0.003, rng=0.006)
        self.h4 = series(600, 14400, t0=(now // 14400) * 14400 - 600 * 14400, drift=0.006, rng=0.01)

    def fake(self, symbol, timeframe="5m", limit=200):
        return {"1h": self.h1, "4h": self.h4}.get(timeframe, [])[-limit:]

    def test_trend_mode_returns_playbook_plan(self):
        from .decision import decide
        with patch("apps.market.candles.fetch_candles", side_effect=self.fake), \
             patch("apps.market.calendar_guard.high_impact_soon", return_value=(False, "")):
            d = decide("BTCUSDT", "1h", mode="trend")
        self.assertEqual(d["signal_source"], "playbook")
        self.assertEqual(d["signal"], "buy", d.get("wait_reasons"))
        self.assertEqual(d["entry_plan"]["type"], "limit")

    def test_active_playbook_preset_drives_alert_path(self):
        from .presets import sync_presets
        from .config_models import Strategy
        from .decision import decide
        sync_presets()
        user = get_user_model().objects.create_user("pb")
        preset = Strategy.objects.get(user=None, preset_key="trend_pullback")
        api = APIClient()
        api.force_authenticate(user)
        r = api.post(f"/api/strategy/strategies/{preset.pk}/activate/", {}, format="json")
        self.assertIn(r.status_code, (200, 201), r.data)
        with patch("apps.market.candles.fetch_candles", side_effect=self.fake), \
             patch("apps.market.calendar_guard.high_impact_soon", return_value=(False, "")):
            d = decide("BTCUSDT", "1h", user=user, mode="safe")   # the alert monitor's call
        self.assertEqual(d["signal_source"], "playbook")
        self.assertEqual(d["strategy_evaluation"]["code"], "playbook_only")
        self.assertIn(d["signal"], ("buy", "wait"))
        if d["signal"] == "buy":
            self.assertEqual(d["entry_plan"]["type"], "limit")

    def test_rule_schema_accepts_playbook_source(self):
        from .rule_schema import validate_risk, RuleError
        self.assertEqual(validate_risk({"signal_source": "playbook"})["playbook"], "trend_pullback")
        with self.assertRaises(RuleError):
            validate_risk({"signal_source": "playbook", "playbook": "magic"})
