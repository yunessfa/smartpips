"""
Trading-session awareness for gold/silver scalping.

Gold moves best during the London and New York sessions (and especially their
overlap). The Asian session and the off-hours are quieter and produce more false
breakouts, so the engine should be more cautious then.

All times are computed in UTC so the result is independent of the server timezone.
Approx session windows (UTC):
  - Asia:           00:00 - 07:00
  - London:         07:00 - 16:00
  - New York:       12:00 - 21:00
  - London/NY overlap: 12:00 - 16:00  (best for gold)
"""
from datetime import datetime, timezone


def current_session(now=None):
    """Return {name, score(0-10), quality, overlap} for the current UTC time."""
    now = now or datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0

    london = 7 <= h < 16
    newyork = 12 <= h < 21
    asia = h < 7
    overlap = 12 <= h < 16  # London + NY

    # "Kill zones" — the first hour after London (08:00 UTC) and NY (13:30 UTC) open
    # plus the London close (16:00) carry most of gold's daily range.
    london_open = 8 <= h < 9
    ny_open = 13.5 <= h < 14.5
    london_close = 16 <= h < 17

    if ny_open or (overlap and london_open):
        return {"name": "NY open (kill-zone)", "score": 10, "quality": "prime", "overlap": True}
    if london_open:
        return {"name": "London open (kill-zone)", "score": 10, "quality": "prime", "overlap": False}
    if overlap:
        return {"name": "London/NY overlap", "score": 9, "quality": "prime", "overlap": True}
    if london_close:
        return {"name": "London close", "score": 8, "quality": "good", "overlap": False}
    if london:
        return {"name": "London", "score": 8, "quality": "good", "overlap": False}
    if newyork:
        return {"name": "New York", "score": 7, "quality": "good", "overlap": False}
    if asia:
        return {"name": "Asia", "score": 3, "quality": "quiet", "overlap": False}
    return {"name": "Off-hours", "score": 2, "quality": "quiet", "overlap": False}


def session_factor(now=None):
    """A 0.0-1.0 multiplier on confidence based on how active the session is.

    Prime overlap = full confidence; quiet hours are dampened so weak setups in
    thin liquidity don't get over-rated.
    """
    s = current_session(now)
    # score 10 -> 1.0, score 2 -> ~0.8
    return round(0.75 + (s["score"] / 10.0) * 0.25, 3)
