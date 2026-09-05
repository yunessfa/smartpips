"""
High-impact economic-event guard for gold (XAUUSD reacts hard to USD data).

The review asked: "High Impact News in 20 minutes => NO TRADE". Reliable free
economic-calendar APIs need a key, so this module is source-agnostic:

- If ECONOMIC_CALENDAR_URL is set, we fetch a JSON list of events
  [{"time": ISO8601, "impact": "high", "title": "CPI"}, ...] and check the window.
- Otherwise it stays safely inert (returns no blackout) so the app keeps working,
  and the UI/explanation simply notes the calendar isn't connected.

This keeps the *mechanism* in place exactly as recommended; wiring a data source is
a config change, not a code change.
"""
import os
from datetime import datetime, timezone

import requests

_cache = {"events": None, "ts": 0.0}


def _load_events():
    import time
    if _cache["events"] is not None and time.time() - _cache["ts"] < 600:
        return _cache["events"]

    url = os.getenv("ECONOMIC_CALENDAR_URL")
    events = []
    try:
        if url:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()
            events = data if isinstance(data, list) else data.get("events", [])
        else:
            # Free default: ForexFactory weekly calendar (JSON, no key).
            r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                             timeout=8, headers={"User-Agent": "SmartPips/1.0"})
            r.raise_for_status()
            raw = r.json()
            for ev in raw:
                # only USD high-impact events move gold hard
                if str(ev.get("country", "")).upper() != "USD":
                    continue
                if str(ev.get("impact", "")).lower() != "high":
                    continue
                events.append({"time": ev.get("date"), "impact": "high",
                               "title": ev.get("title", "USD event")})
        _cache["events"] = events
        _cache["ts"] = time.time()
    except (requests.RequestException, ValueError, TypeError):
        return _cache["events"] or []
    return events


def high_impact_soon(within_min=30):
    """Return (blocked: bool, info: str). Blocks trades near high-impact USD events."""
    events = _load_events()
    if not events:
        return False, ""
    now = datetime.now(timezone.utc)
    for ev in events:
        if str(ev.get("impact", "")).lower() not in ("high", "3", "red"):
            continue
        ts = ev.get("time") or ev.get("date")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        delta_min = (when - now).total_seconds() / 60
        if -5 <= delta_min <= within_min:
            return True, f"{ev.get('title', 'High-impact event')} in ~{int(max(delta_min,0))}m"
    return False, ""
