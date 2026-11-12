from datetime import datetime, timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.strategy import old_levels as OL

DAY = 86400
T0 = int(datetime(2026, 3, 2, tzinfo=timezone.utc).timestamp())      # a Monday


def day(i, high, low, close=None, open_=None):
    close = (high + low) / 2 if close is None else close
    return {"time": T0 + i * DAY, "open": close if open_ is None else open_, "high": high, "low": low,
            "close": close}


def flat(n, high=105.0, low=95.0, start=0):
    return [day(start + i, high, low) for i in range(n)]


class OldLevelRules(SimpleTestCase):
    def test_forming_day_week_and_month_are_never_levels(self):
        # 16 closed days (Mon 2 Mar .. Tue 17 Mar) + a forming 17th with an extreme high
        daily = flat(16) + [day(16, 500.0, 96.0)]
        now = T0 + 16 * DAY + 3600
        levels = OL.build_levels(*[OL._clean(daily, DAY, now)[0], []])
        self.assertFalse([lv for lv in levels if lv["price"] == 500.0])
        weeks = sorted({lv["avail"] for lv in levels if lv["src"] == "W"})
        self.assertEqual(weeks, [T0 + 7 * DAY, T0 + 14 * DAY])        # third week still forming
        self.assertFalse([lv for lv in levels if lv["src"] == "M"])    # March has not closed

    def test_level_is_not_taken_by_the_move_that_formed_it(self):
        daily = flat(12)
        daily[5] = day(5, 130.0, 95.0)                                 # the old high
        now = T0 + 12 * DAY
        out = OL.summarize(daily, [], price=100.0, now=now)
        highs = [x for x in out["levels"] if x["kind"] == "high"]
        self.assertIn(130.0, [x["price"] for x in highs])
        top = next(x for x in highs if x["price"] == 130.0)
        self.assertIn("D", top["sources"])
        self.assertEqual(top["distance_pct"], 30.0)

    def test_level_disappears_once_a_later_bar_trades_through_it(self):
        daily = flat(12)
        daily[5] = day(5, 130.0, 95.0)
        daily[9] = day(9, 131.0, 95.0)                                 # takes 130, leaves its own 131
        out = OL.summarize(daily, [], price=100.0, now=T0 + 12 * DAY)
        prices = [x["price"] for x in out["levels"]]
        self.assertNotIn(130.0, prices)
        self.assertIn(131.0, prices)

    def test_equal_high_does_not_take_a_level(self):
        daily = flat(12)
        daily[5] = day(5, 130.0, 95.0)
        daily[9] = day(9, 130.0, 95.0)                                 # touches, does not trade through
        out = OL.summarize(daily, [], price=100.0, now=T0 + 12 * DAY)
        self.assertIn(130.0, [x["price"] for x in out["levels"]])

    def test_previous_day_and_week_are_reported_even_when_taken(self):
        daily = flat(14)                                               # two full weeks, all 105 / 95
        daily[13] = day(13, 110.0, 94.0)                               # Sunday of week 2 = previous day
        forming = day(14, 111.0, 96.0)                                 # today already took PDH
        out = OL.summarize(daily + [forming], [], price=108.0, now=T0 + 14 * DAY + 60)
        self.assertEqual(out["previous"]["PDH"], {"price": 110.0, "taken": True})
        self.assertEqual(out["previous"]["PDL"], {"price": 94.0, "taken": False})
        self.assertEqual(out["previous"]["PWH"]["price"], 110.0)
        self.assertNotIn(110.0, [x["price"] for x in out["levels"]])
        low = next(x for x in out["levels"] if x["price"] == 94.0)
        self.assertEqual(low["label"], "PWL")                          # week outranks day in the label
        self.assertTrue(low["major"])

    def test_recent_intraday_bars_take_a_level_before_the_daily_feed_refreshes(self):
        daily = flat(12)
        daily[5] = day(5, 130.0, 95.0)
        now = T0 + 12 * DAY + 600
        recent = [{"time": T0 + 12 * DAY + 300, "open": 129.0, "high": 130.5, "low": 128.0, "close": 129.5}]
        out = OL.summarize(daily, [], now=now, recent=recent)
        self.assertEqual(out["price"], 129.5)
        self.assertNotIn(130.0, [x["price"] for x in out["levels"]])

    def test_major_levels_are_not_crowded_out_by_a_staircase_of_daily_highs(self):
        # week 1 holds the big high; week 2 and 3 step down every day
        daily = [day(i, 200.0 if i == 2 else 150.0 - i, 90.0) for i in range(21)]
        out = OL.summarize(daily, [], price=100.0, now=T0 + 21 * DAY)
        above = [x for x in out["levels"] if x["kind"] == "high"]
        self.assertTrue(any(x["price"] == 200.0 and x["major"] for x in above))
        self.assertLessEqual(len([x for x in above if not x["major"]]), 3)

    def test_too_little_history_returns_an_empty_result(self):
        out = OL.summarize(flat(5), [], now=T0 + 5 * DAY)
        self.assertEqual(out["levels"], [])
        self.assertEqual(out["history_days"], 0)

    def test_bad_rows_are_ignored(self):
        daily = flat(12) + [{"time": "x"}, {"time": T0 + 3 * DAY, "open": 1, "high": 1, "low": 2, "close": 1}]
        out = OL.summarize(daily, [], price=100.0, now=T0 + 12 * DAY)
        self.assertEqual(out["history_days"], 12)


class OldLevelsEndpoint(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("lv", password="x")
        self.client = APIClient()

    def test_requires_login(self):
        self.assertIn(self.client.get("/api/strategy/levels/?symbol=BTCUSDT:PERP").status_code, (401, 403))

    def test_rejects_unknown_symbol(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/strategy/levels/?symbol=XAUUSD").status_code, 400)

    def test_returns_levels_and_marks_them_context_only(self):
        self.client.force_authenticate(self.user)
        import time
        start = (int(time.time()) // DAY - 20) * DAY
        daily = [{"time": start + i * DAY, "open": 100.0, "high": 130.0 if i == 4 else 105.0, "low": 95.0,
                  "close": 100.0} for i in range(21)]
        with mock.patch("apps.market.candles.fetch_daily_candles", return_value=(daily, "bitunix")), \
                mock.patch("apps.market.candles.fetch_candles", return_value=[]):
            res = self.client.get("/api/strategy/levels/?symbol=btcusdt")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["symbol"], "BTCUSDT:PERP")
        self.assertEqual(body["role"], "context_only")
        self.assertEqual(body["source"], "bitunix")
        self.assertIn(130.0, [x["price"] for x in body["levels"]])

    def test_reports_unavailable_without_daily_history(self):
        self.client.force_authenticate(self.user)
        with mock.patch("apps.market.candles.fetch_daily_candles", return_value=([], None)):
            body = self.client.get("/api/strategy/levels/?symbol=ETHUSDT:PERP").json()
        self.assertEqual(body["status"], "unavailable")
        self.assertEqual(body["levels"], [])
