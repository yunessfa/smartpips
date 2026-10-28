"""Health check + log viewer (fixes T-2 from the technical review).

Three endpoints, deliberately kept in `config/` so no new Django app and no new
migration are needed:

    GET  /api/health/       public, cheap    -> uptime monitors, systemd, docker
    GET  /api/health/deep/  staff            -> DB + cache + market feeds + push
    GET  /api/logs/         super admin      -> read the rotating log file
    POST /api/logs/test/    super admin      -> emit one test ERROR line

Why /api/health/ is public: an uptime monitor cannot log in. It returns only
"am I alive and can I reach my database" — no versions, no settings, no counts.
Everything that could help an attacker profile the box lives in /deep/, which
requires staff.

Why the log viewer is super-admin only: logs contain usernames, symbols, order
sizes and stack traces. That is trading-account-shaped data, so it sits behind
the same bar as changing another user's password.
"""
import logging
import os
import re
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

log = logging.getLogger("smartpips.health")

_STARTED_AT = time.time()

# Never let a log line leak a live credential into the browser, even to an
# admin. Anything that looks like a key/secret/token gets masked on read.
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|secret[_-]?key|token|password|passwd|authorization|"
    r"sign|signature|p256dh|auth)\s*[=:\"']*\s*([A-Za-z0-9_\-./+=]{6,})"
)


def _redact(line):
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}=***redacted***", line)


def log_path():
    """The file RotatingFileHandler is writing to, per settings.LOGGING."""
    try:
        handlers = settings.LOGGING.get("handlers", {})
        filename = handlers.get("file", {}).get("filename")
        if filename:
            return Path(filename)
    except Exception:  # noqa: BLE001 — health must never 500
        log.exception("could not read LOGGING handler config")
    return Path(settings.BASE_DIR) / "logs" / "smartpips.log"


# ------------------------------------------------------------ liveness ----
@api_view(["GET"])
@permission_classes([AllowAny])
def health_view(request):
    """Liveness + readiness in one cheap call. 200 = safe to send traffic.

    A DB round-trip is included on purpose: a process that is running but
    cannot reach Postgres is not healthy, and a load balancer needs to know
    that difference.
    """
    checks = {}
    ok = True

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks["database"] = "error"
        log.exception("health: database unreachable: %s", exc)

    try:
        cache.set("health:ping", "1", 10)
        checks["cache"] = "ok" if cache.get("health:ping") == "1" else "degraded"
    except Exception:  # noqa: BLE001
        checks["cache"] = "error"
        log.exception("health: cache unreachable")

    return Response(
        {"status": "ok" if ok else "unhealthy",
         "uptime_seconds": int(time.time() - _STARTED_AT),
         "checks": checks},
        status=200 if ok else 503,
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def health_deep_view(request):
    """Everything an operator wants at 3am, in one request.

    Each probe is wrapped separately so one dead integration reports as dead
    instead of blanking the whole page — the exact failure mode the review
    called out.
    """
    out = {"status": "ok", "uptime_seconds": int(time.time() - _STARTED_AT),
           "debug": bool(settings.DEBUG), "checks": {}}

    def probe(name, fn):
        try:
            out["checks"][name] = fn()
        except Exception as exc:  # noqa: BLE001
            out["checks"][name] = {"ok": False, "error": str(exc)[:200]}
            log.exception("health probe %s failed", name)

    def _db():
        from django.contrib.auth import get_user_model
        return {"ok": True, "engine": connection.vendor,
                "users": get_user_model().objects.count()}

    def _cache():
        cache.set("health:deep", "1", 10)
        return {"ok": cache.get("health:deep") == "1",
                "backend": settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]}

    def _push():
        from apps.alerts.push import vapid_configured
        from apps.alerts.models import PushSubscription
        return {"ok": vapid_configured(),
                "subscriptions": PushSubscription.objects.filter(enabled=True).count()}

    def _metals():
        # Are gold/silver actually being served by LBank right now?
        from apps.lbank.metals import available
        listed = available()
        return {"ok": any(listed.values()), "source": "lbank", "symbols": listed}

    def _logfile():
        path = log_path()
        if not path.exists():
            return {"ok": False, "error": "log file not created yet"}
        return {"ok": True, "path": str(path),
                "size_bytes": path.stat().st_size,
                "writable": os.access(path, os.W_OK)}

    probe("database", _db)
    probe("cache", _cache)
    probe("push", _push)
    probe("metals_feed", _metals)
    probe("log_file", _logfile)

    if any(isinstance(v, dict) and v.get("ok") is False
           for k, v in out["checks"].items() if k in ("database", "cache")):
        out["status"] = "unhealthy"
        return Response(out, status=503)
    return Response(out)


# ----------------------------------------------------------------- logs ----
_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@api_view(["GET"])
@permission_classes([IsAdminUser])
def logs_view(request):
    """Tail the rotating log file so errors can be READ, not just written.

    Query params:
        lines=200      how many of the most recent lines (max 2000)
        level=ERROR    keep only lines at/above this level
        q=text         substring filter

    Only the tail is read (seek from the end), so a 20MB log costs the same as
    a 20KB one.
    """
    if not request.user.is_superuser:
        return Response({"error": "Only a super admin can read the server log."},
                        status=403)

    path = log_path()
    if not path.exists():
        return Response({"path": str(path), "lines": [], "count": 0,
                         "note": "No log file yet — it is created on the first "
                                 "log write after a restart."})

    try:
        limit = max(1, min(2000, int(request.query_params.get("lines") or 200)))
    except (TypeError, ValueError):
        limit = 200
    level = (request.query_params.get("level") or "").upper()
    needle = (request.query_params.get("q") or "").strip().lower()

    wanted = set()
    if level in _LEVELS:
        wanted = set(_LEVELS[_LEVELS.index(level):])

    # Read at most the last ~4MB; enough for thousands of lines, bounded memory.
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - 4_000_000))
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        log.exception("could not read log file")
        return Response({"error": f"Could not read log file: {exc}"}, status=500)

    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if wanted and not any(f'"{lv}"' in line or f" {lv} " in line for lv in wanted):
            continue
        if needle and needle not in line.lower():
            continue
        rows.append(_redact(line))

    rows = rows[-limit:]
    return Response({"path": str(path), "size_bytes": size,
                     "count": len(rows), "lines": rows})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def logs_test_view(request):
    """Emit one WARNING and one ERROR (with traceback) so the admin can prove
    the whole logging chain works end to end before trusting it in an
    incident."""
    if not request.user.is_superuser:
        return Response({"error": "Only a super admin can do this."}, status=403)
    log.warning("log self-test (warning) requested by %s", request.user.username)
    try:
        raise RuntimeError("log self-test — this exception is intentional")
    except RuntimeError:
        log.exception("log self-test (error) requested by %s", request.user.username)
    return Response({"ok": True, "path": str(log_path())})
