"""USD macro-calendar adapter shared by the UI and the pre-trade blackout.
Impact means expected volatility, never a prediction of price direction.
"""
import os
import time
from datetime import datetime, timezone
import requests
from urllib.parse import urlparse

_cache = {"events": None, "ts": 0.0, "error": None}
DEFAULT_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _load_events():
    if _cache["events"] is not None and time.time() - _cache["ts"] < 600:
        return _cache["events"]
    try:
        response = requests.get(os.getenv("ECONOMIC_CALENDAR_URL") or DEFAULT_URL,
                                timeout=8, headers={"User-Agent": "SmartPips/1.0"})
        response.raise_for_status()
        data = response.json()
        raw = data if isinstance(data, list) else data.get("events", [])
        events = []
        for ev in raw:
            if not isinstance(ev, dict):
                continue
            currency = str(ev.get("currency") or ev.get("country") or "USD").upper()
            if currency != "USD":
                continue
            impact = str(ev.get("impact", "unknown")).lower()
            impact = {"3": "high", "red": "high", "2": "medium", "orange": "medium",
                      "1": "low", "yellow": "low"}.get(impact, impact)
            try:
                when = datetime.fromisoformat(str(ev.get("time") or ev.get("date")).replace("Z", "+00:00"))
                if when.tzinfo is None:  # no fabricated timezone
                    continue
            except (ValueError, TypeError):
                continue
            events.append({"time": when.astimezone(timezone.utc).isoformat(), "impact": impact,
                           "title": str(ev.get("title") or "USD event"), "currency": currency})
        _cache.update(events=sorted(events, key=lambda e: e["time"]), ts=time.time(), error=None)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        _cache["error"] = "calendar_unavailable"
    return _cache["events"] or []


def upcoming_events(symbol="XAUUSD", limit=5):
    events = _load_events()
    now = datetime.now(timezone.utc)
    selected = []
    for ev in events:
        minutes = (datetime.fromisoformat(ev["time"]) - now).total_seconds() / 60
        if minutes >= -5:
            selected.append({**ev, "minutes_until": round(minutes, 1)})
    age = time.time() - _cache["ts"] if _cache["ts"] else None
    return {"events": selected[:limit], "symbol": symbol,
            "status": "unavailable" if _cache["events"] is None else "stale" if _cache["error"] or age > 900 else "ok",
            "fetched_at": datetime.fromtimestamp(_cache["ts"], timezone.utc).isoformat() if _cache["ts"] else None,
            "source": urlparse(os.getenv("ECONOMIC_CALENDAR_URL") or DEFAULT_URL).hostname,
            "scope": "USD macro events; indirect relevance to crypto",
            "direction": "unknown"}


def high_impact_soon(within_min=30):
    data = upcoming_events(limit=100)
    for ev in data["events"]:
        if ev["impact"] == "high" and -5 <= ev["minutes_until"] <= within_min:
            return True, f"{ev['title']} in ~{int(max(ev['minutes_until'], 0))}m"
    return False, ""
