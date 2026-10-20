from unittest.mock import patch, Mock
from datetime import datetime, timedelta, timezone
from django.test import SimpleTestCase
from . import calendar_guard as calendar


class CalendarTests(SimpleTestCase):
    def setUp(self):
        calendar._cache.update(events=None, ts=0, error=None)

    @patch("apps.market.calendar_guard.requests.get")
    def test_next_event_all_impacts_and_usd_only(self, get):
        now = datetime.now(timezone.utc)
        get.return_value.json.return_value = [
            {"country": "USD", "impact": "Low", "date": (now + timedelta(minutes=5)).isoformat(), "title": "Low"},
            {"country": "USD", "impact": "High", "date": (now + timedelta(minutes=10)).isoformat(), "title": "CPI"},
            {"country": "EUR", "impact": "High", "date": (now + timedelta(minutes=2)).isoformat()},
            {"country": "USD", "impact": "High", "date": "2026-10-17T12:00:00"},
        ]
        data = calendar.upcoming_events("BTCUSDT")
        self.assertEqual(len(data["events"]), 2)
        self.assertEqual(data["events"][0]["title"], "Low")
        self.assertEqual(data["direction"], "unknown")
        self.assertTrue(calendar.high_impact_soon()[0])

    @patch("apps.market.calendar_guard.requests.get")
    def test_unavailable_not_confused_with_no_news(self, get):
        import requests
        get.side_effect = requests.Timeout()
        self.assertEqual(calendar.upcoming_events()["status"], "unavailable")

    @patch("apps.market.calendar_guard.requests.get")
    def test_stale_data_is_explicit(self, get):
        import requests
        calendar._cache.update(events=[], ts=1)
        get.side_effect = requests.Timeout()
        self.assertEqual(calendar.upcoming_events()["status"], "stale")
