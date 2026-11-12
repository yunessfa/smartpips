from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from . import calendar_guard as calendar


def feed(*events):
    now = datetime.now(timezone.utc)
    return [{"country": "USD", "impact": impact, "title": title,
             "date": (now + timedelta(minutes=minutes)).isoformat()} for title, impact, minutes in events]


class NewsBlackoutWindow(SimpleTestCase):
    def setUp(self):
        calendar._cache.update(events=None, ts=0, error=None)

    def _with(self, *events):
        p = patch("apps.market.calendar_guard.requests.get")
        get = p.start()
        self.addCleanup(p.stop)
        get.return_value.json.return_value = feed(*events)

    def test_blocks_before_the_release(self):
        self._with(("CPI m/m", "High", 25))
        blocked, info = calendar.high_impact_soon()
        self.assertTrue(blocked)
        self.assertIn("CPI m/m in ~", info)

    def test_does_not_block_far_ahead_or_for_medium_impact(self):
        self._with(("FOMC", "High", 45), ("Jobless Claims", "Medium", 5))
        self.assertEqual(calendar.high_impact_soon(), (False, ""))

    def test_cooldown_after_the_release(self):
        self._with(("Non-Farm Employment Change", "High", -10))
        blocked, info = calendar.high_impact_soon()
        self.assertTrue(blocked)
        self.assertIn("released 10m ago", info)

    def test_cooldown_ends(self):
        self._with(("Non-Farm Employment Change", "High", -20))
        self.assertFalse(calendar.high_impact_soon()[0])

    @override_settings(NEWS_BLACKOUT_BEFORE_MIN=60, NEWS_BLACKOUT_AFTER_MIN=30)
    def test_window_is_configurable_and_reported(self):
        self._with(("FOMC Statement", "High", -25))
        self.assertTrue(calendar.high_impact_soon()[0])
        calendar._cache.update(events=None, ts=0, error=None)
        self._with(("FOMC Statement", "High", 50))
        self.assertTrue(calendar.high_impact_soon()[0])
        data = calendar.upcoming_events("BTCUSDT")
        self.assertEqual(data["blackout"], {"before_min": 60, "after_min": 30})

    def test_released_event_stays_listed_through_its_cooldown(self):
        self._with(("CPI y/y", "High", -12), ("Old", "High", -40))
        titles = [e["title"] for e in calendar.upcoming_events("BTCUSDT")["events"]]
        self.assertEqual(titles, ["CPI y/y"])

    def test_explicit_arguments_still_win(self):
        self._with(("CPI", "High", 25))
        self.assertFalse(calendar.high_impact_soon(within_min=10)[0])
