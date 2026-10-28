"""
Watch gold/silver and notify subscribers when a NEW scalp setup appears.
Run once a minute from cron:

    * * * * * cd /var/www/smartpips/backend && /var/www/smartpips/backend/.venv/bin/python manage.py monitor_scalp >> /var/log/smartpips_monitor.log 2>&1

Note: if you use the MT5 EA bridge, alerts already fire on every EA push, so this
cron is only needed as a fallback (or when MT5 isn't connected).
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.alerts.push import vapid_configured
from apps.alerts.signal_check import evaluate_and_alert

log = logging.getLogger("smartpips.alerts")

# default gold/silver watch (always on)
WATCH = [("XAUUSD", "5m"), ("XAGUSD", "5m"), ("XAUUSD", "15m")]
# timeframes scanned for each user-watchlisted symbol
WATCH_TFS = ["1m", "5m", "15m", "1h"]


HEARTBEAT_KEY = "alerts_monitor_heartbeat"


class Command(BaseCommand):
    help = ("Run one monitoring pass over gold/silver + user watchlists and push new setups. "
            "With --loop it keeps running (Docker service) and writes a heartbeat.")

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true",
                            help="run forever (use as a long-running service instead of cron)")
        parser.add_argument("--interval", type=int, default=60, help="seconds between pass starts")
        parser.add_argument("--with-rules", action="store_true",
                            help="also evaluate position alert rules (check_alerts) each pass")

    def handle(self, *args, **options):
        if not options.get("loop"):
            return self._pass(options)
        interval = max(15, int(options.get("interval") or 60))
        self.stdout.write(f"alert monitor loop started (every {interval}s)")
        while True:
            started = time.monotonic()
            close_old_connections()
            try:
                self._pass(options)
            except Exception:
                # Never let one bad pass kill the service; the heartbeat shows it.
                log.exception("monitor pass crashed")
            close_old_connections()
            time.sleep(max(1.0, interval - (time.monotonic() - started)))

    def _pass(self, options):
        t0 = time.monotonic()
        stats = self._scan()
        rules_fired = None
        if options.get("with_rules"):
            try:
                from apps.alerts.rules import run_all
                rules_fired = run_all()
            except Exception:
                log.exception("position alert rules failed")
        try:
            from apps.accounts.settings_store import set_setting
            set_setting(HEARTBEAT_KEY, {
                "at": timezone.now().isoformat(), "duration_s": round(time.monotonic() - t0, 1),
                "pairs": stats["pairs"], "pushes": stats["pushes"], "errors": stats["errors"],
                "rules_fired": rules_fired,
            })
        except Exception:
            log.exception("could not write monitor heartbeat")
        return None

    def _scan(self):
        if not vapid_configured():
            self.stdout.write("VAPID not configured — internal notifications remain enabled; no browser push.")

        # 1) default gold/silver
        pairs = list(WATCH)

        # 2) every active user-watchlisted symbol, across all watch timeframes
        try:
            from apps.alerts.models import WatchItem
            symbols = (WatchItem.objects.filter(active=True)
                       .values_list("symbol", flat=True).distinct())
            for sym in symbols:
                for tf in WATCH_TFS:
                    if (sym, tf) not in pairs:
                        pairs.append((sym, tf))
        except Exception as exc:
            log.exception("watchlist load failed")
            self.stdout.write(self.style.ERROR(f"watchlist load failed: {exc}"))

        # Who is actually subscribed to what. Printed per pair so a silent
        # pass is explainable: "no new setup" and "nobody is watching this"
        # look identical in the old output but need very different fixes.
        from apps.alerts.gating import watchers

        total_sent = 0
        errors = 0
        for symbol, timeframe in pairs:
            try:
                try:
                    watching = len(watchers(symbol))
                except Exception:
                    log.exception("watcher lookup failed for %s", symbol)
                    watching = -1

                sent = evaluate_and_alert(symbol, timeframe)
                total_sent += sent or 0

                if sent:
                    self.stdout.write(self.style.SUCCESS(
                        f"{symbol} {timeframe}: new setup -> pushed to {sent} device(s) "
                        f"({watching} watcher(s))."))
                elif watching == 0:
                    # NOTE: the pair is still evaluated even with zero watchers,
                    # on purpose. evaluate_and_alert() keeps SignalState fresh;
                    # skipping it would make the first pass after someone adds
                    # a watch fire on a stale flip from hours ago.
                    self.stdout.write(
                        f"{symbol} {timeframe}: nobody is watching this pair.")
                else:
                    self.stdout.write(
                        f"{symbol} {timeframe}: no device push ({watching} watcher(s)); "
                        "internal notifications may have been stored; see backend logs.")
            except Exception as exc:
                errors += 1
                log.exception("monitor pass failed for %s %s", symbol, timeframe)
                self.stdout.write(self.style.ERROR(f"{symbol} {timeframe}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"done: {len(pairs)} pair(s) scanned, {total_sent} push(es) sent."))
        return {"pairs": len(pairs), "pushes": total_sent, "errors": errors}
