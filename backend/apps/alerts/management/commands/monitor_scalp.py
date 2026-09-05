"""
Watch gold/silver and notify subscribers when a NEW scalp setup appears.
Run once a minute from cron:

    * * * * * cd /var/www/smartpips/backend && /var/www/smartpips/backend/.venv/bin/python manage.py monitor_scalp >> /var/log/smartpips_monitor.log 2>&1

Note: if you use the MT5 EA bridge, alerts already fire on every EA push, so this
cron is only needed as a fallback (or when MT5 isn't connected).
"""
import logging

from django.core.management.base import BaseCommand

from apps.alerts.push import vapid_configured
from apps.alerts.signal_check import evaluate_and_alert

log = logging.getLogger("smartpips.alerts")

# default gold/silver watch (always on)
WATCH = [("XAUUSD", "5m"), ("XAGUSD", "5m"), ("XAUUSD", "15m")]
# timeframes scanned for each user-watchlisted symbol
WATCH_TFS = ["5m", "15m", "1h"]


class Command(BaseCommand):
    help = "Run one monitoring pass over gold/silver + user watchlists and push new setups."

    def handle(self, *args, **options):
        if not vapid_configured():
            self.stdout.write("VAPID keys not set — run gen_vapid and put keys in .env.")
            return

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
                        f"{symbol} {timeframe}: no new setup ({watching} watcher(s)).")
            except Exception as exc:
                log.exception("monitor pass failed for %s %s", symbol, timeframe)
                self.stdout.write(self.style.ERROR(f"{symbol} {timeframe}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"done: {len(pairs)} pair(s) scanned, {total_sent} push(es) sent."))
