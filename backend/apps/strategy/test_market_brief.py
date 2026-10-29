"""Market brief + dashboard overview (2026-10)."""
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from . import market_brief
from .test_trend_pullback import series


class BriefTests(SimpleTestCase):
    def setUp(self):
        self.h1 = series(700, 3600, drift=0.003, rng=0.006)
        end = self.h1[-1]["time"] + 3600
        self.h4 = series(400, 14400, drift=0.006, rng=0.01, t0=end - 400 * 14400)

    def test_facts_next_step_and_update_time(self):
        b = market_brief.build({"signal": "wait", "support": 1, "resistance": 2}, "BTCUSDT", "1h",
                               self.h1, {"4h": self.h4})
        keys = [f["key"] for f in b["facts"]]
        self.assertEqual(keys, ["h4_trend", "ema_stack", "stretch", "volatility"])
        self.assertEqual(b["facts"][0]["value"], 1)
        self.assertEqual(b["next_update_at"], self.h1[-1]["time"] + 2 * 3600)
        self.assertTrue(b["fingerprint"])
        # stretched uptrend + enough volatility, but decision says wait -> generic block
        self.assertIn(b["next"]["code"], ("blocked", "wait_stretch"))

    def test_same_bar_same_fingerprint_new_bar_new_fingerprint(self):
        a = market_brief.build({"signal": "wait"}, "BTCUSDT", "1h", self.h1, {"4h": self.h4})
        b = market_brief.build({"signal": "wait"}, "BTCUSDT", "1h", self.h1, {"4h": self.h4})
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        c = market_brief.build({"signal": "wait"}, "BTCUSDT", "1h", self.h1[:-1], {"4h": self.h4})
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])

    def test_quiet_market_points_to_volatility(self):
        quiet = series(700, 3600, drift=0.0004, rng=0.0008)
        end = quiet[-1]["time"] + 3600
        h4 = series(400, 14400, drift=0.001, rng=0.002, t0=end - 400 * 14400)
        b = market_brief.build({"signal": "wait"}, "BTCUSDT", "1h", quiet, {"4h": h4})
        self.assertEqual(b["next"]["code"], "wait_volatility")
        self.assertEqual([f for f in b["facts"] if f["key"] == "volatility"][0]["state"], "bad")
        text = market_brief.lines(b, {})
        self.assertTrue(any("نوسان بیشتر" in x for x in text))

    def test_unvalidated_timeframe_and_h1_for_short_tf(self):
        m1 = series(700, 60, drift=0.0005, rng=0.002)
        b = market_brief.build({"signal": "wait"}, "BTCUSDT", "1m", m1, {"4h": self.h4, "1h": self.h1})
        self.assertEqual(b["next"]["code"], "tf_not_validated")
        self.assertIn("h1_trend", [f["key"] for f in b["facts"]])

    def test_wait_text_is_persian(self):
        self.assertIn("نوسان", market_brief.wait_text({"wait_reasons": [{"code": "stop_below_cost_floor"}]}))


class OverviewEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.api.force_authenticate(get_user_model().objects.create_user("ov"))
        now = int(time.time())
        self.h1 = series(600, 3600, t0=(now // 3600) * 3600 - 600 * 3600, drift=0.003, rng=0.006)
        self.h4 = series(600, 14400, t0=(now // 14400) * 14400 - 600 * 14400, drift=0.006, rng=0.01)

    def fake(self, symbol, timeframe="5m", limit=200):
        if not symbol.startswith("BTC"):
            return []
        return {"1h": self.h1, "4h": self.h4}.get(timeframe, [])[-limit:]

    def test_overview_rows_and_validation(self):
        with patch("apps.market.candles.fetch_candles", side_effect=self.fake), \
             patch("apps.market.calendar_guard.high_impact_soon", return_value=(False, "")):
            r = self.api.get("/api/strategy/overview/?tf=1h&symbols=BTCUSDT,ETHUSDT,FOOUSDT")
        self.assertEqual(r.status_code, 200, r.data)
        rows = {x["symbol"]: x for x in r.data["results"]}
        self.assertIn("brief", rows["BTCUSDT:PERP"])
        self.assertIn(rows["BTCUSDT:PERP"]["signal"], ("buy", "wait"))
        self.assertIsNone(rows["ETHUSDT:PERP"].get("brief"))
        self.assertEqual(rows["FOOUSDT:PERP"]["error"], "unsupported")
        self.assertEqual(self.api.get("/api/strategy/overview/?tf=1m").status_code, 400)
