"""Single entry point for raising a user-facing notification.

Everything in the app that wants to tell a user something should call `notify`
rather than talking to `push.broadcast` directly. The reason is ordering: the
internal `Notification` row is the source of truth and is written first, then a
browser push is attempted as a best-effort mirror. If VAPID is unconfigured, the
user denied permission, or the push service is down, the notification centre
still shows the message the next time the panel is opened.
"""

import logging

from .models import Notification

log = logging.getLogger("smartpips.alerts")


def notify(user, *, title, body="", category="system", level="info", url="",
           symbol="", trade=None, rule=None, meta=None, push=True, force=False):
    """Persist a notification for `user` and optionally mirror it to Web Push.

    Returns the created Notification, or None when the message was suppressed.

    LOSS-LIMIT MUTE
    ---------------
    Once a user is past their daily loss limit there is no point pinging them
    with new setups — they are not supposed to open anything else today, and
    the app itself already refuses those orders. Only trade-shaped categories
    (signal/trading) are muted. risk/pnl/system messages ALWAYS go through,
    because muting those would hide the very warning that explains why the
    setups went quiet.

    Pass force=True for messages that must land regardless — in particular the
    message announcing that the mute just kicked in.

    Push failures are swallowed on purpose: a dead push subscription must
    never break the calling flow (closing a trade, the monitor cron, ...).
    """
    if not force:
        try:
            from .gating import notify_allowed
            if not notify_allowed(user, category):
                log.info("muted %s notification for %s: %s", category,
                         getattr(user, "username", user), str(title)[:80])
                return None
        except Exception:
            # A bug in the gate must never swallow notifications wholesale:
            # log it and fall through to delivering the message.
            log.exception("notify gating check failed for %s", user)

    note = Notification.objects.create(
        user=user,
        title=str(title)[:140],
        body=body or "",
        category=category,
        level=level,
        url=url or "",
        symbol=symbol or "",
        trade=trade,
        rule=rule,
        meta=meta or {},
    )

    if push:
        try:
            from .push import broadcast, vapid_configured
            if vapid_configured():
                broadcast({
                    "title": note.title,
                    "body": note.body,
                    # Deep links must carry the /app prefix: the public site owns "/".
                    "url": note.url or "/app/notifications",
                    "symbol": note.symbol,
                    "category": note.category,
                    "notificationId": note.id,
                }, users=[user])
        except Exception:
            # Was a bare `pass`. A dead push service looked identical to a
            # working one, so "I get nothing on my phone" was undebuggable.
            log.exception("push mirror failed for notification id=%s user=%s",
                          note.id, getattr(user, "username", user))

    return note


def unread_count(user):
    return Notification.objects.filter(user=user, read=False).count()
