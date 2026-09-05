"""One-shot health check for the data feeds, alert routing and logging.

Run this on the SERVER (the box that has internet), not on a dev laptop:

    cd backend && python manage.py check_feeds

It is read-only apart from writing one deliberate test line into the log file,
so it is safe to run on production at any time.

Why a management command instead of a doc full of curl commands: this runs
inside Django, so it uses the *same* settings, cache and code path the app
uses. A curl test can pass while the app still fails (different env, different
cache), and that is exactly the kind of false green you don't want when money
is involved.
"""

import logging
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

log = logging.getLogger("smartpips.health")

OK = "\033[92m"
BAD = "\033[91m"
WARN = "\033[93m"
DIM = "\033[90m"
END = "\033[0m"


class Command(BaseCommand):
    help = "Check LBank metal feeds, candle sources, alert routing and logging."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeframe", default="5m",
            help="Timeframe to request candles for (default 5m).",
        )
        parser.add_argument(
            "--no-log-test", action="store_true",
            help="Skip writing the deliberate test line into the log file.",
        )

    # ------------------------------------------------------------- output --
    def head(self, text):
        self.stdout.write(f"\n{text}\n" + "-" * len(text))

    def good(self, text):
        self.stdout.write(f"  {OK}PASS{END}  {text}")

    def warn(self, text):
        self.warnings += 1
        self.stdout.write(f"  {WARN}WARN{END}  {text}")

    def fail(self, text):
        self.failures += 1
        self.stdout.write(f"  {BAD}FAIL{END}  {text}")

    def note(self, text):
        self.stdout.write(f"        {DIM}{text}{END}")

    # ------------------------------------------------------------- runner --
    def handle(self, *args, **opts):
        self.failures = 0
        self.warnings = 0
        tf = opts["timeframe"]

        self.stdout.write("SmartPips feed / alert / logging check")

        self.check_settings()
        self.check_lbank_metals(tf)
        self.check_price_layer()
        self.check_candle_layer(tf)
        self.check_alert_routing()
        self.check_logging(skip_write=opts["no_log_test"])

        self.head("Summary")
        if self.failures:
            self.stdout.write(
                f"  {BAD}{self.failures} failure(s){END}, {self.warnings} warning(s)"
            )
            self.note("Read the FAIL lines above, then check /api/logs/?q=lbank")
        elif self.warnings:
            self.stdout.write(f"  {WARN}{self.warnings} warning(s){END}, no failures")
        else:
            self.stdout.write(f"  {OK}everything healthy{END}")

    # ----------------------------------------------------------- settings --
    def check_settings(self):
        self.head("1. Settings")
        for name, expected in (
            ("METALS_DATA_SOURCE", "lbank"),
            ("CRYPTO_PERP_DATA_SOURCE", "binance"),
        ):
            val = getattr(settings, name, None)
            if val == expected:
                self.good(f"{name} = {val!r}")
            else:
                self.warn(f"{name} = {val!r} (expected {expected!r})")

        base = getattr(settings, "LBANK_FUTURES_BASE_URL", None)
        if base:
            self.good(f"LBANK_FUTURES_BASE_URL = {base}")
        else:
            self.fail("LBANK_FUTURES_BASE_URL is not set")

        if getattr(settings, "BITUNIX_API_KEY", ""):
            self.warn("BITUNIX_API_KEY still has a value — Bitunix should be dormant")
        else:
            self.good("Bitunix credentials are empty (dormant, as intended)")

        log_dir = getattr(settings, "LOG_DIR", None)
        if log_dir:
            self.good(f"LOG_DIR = {log_dir}")
        else:
            self.warn("LOG_DIR is None — file logging is OFF, console only")
            self.note("Usually a permissions problem on backend/logs/")

    # -------------------------------------------------------- lbank metals --
    def check_lbank_metals(self, tf):
        self.head("2. LBank metal feed (the part that could not be tested offline)")
        try:
            from apps.lbank import metals
        except Exception as exc:
            self.fail(f"cannot import apps.lbank.metals: {exc}")
            return

        try:
            avail = metals.available()
        except Exception as exc:
            self.fail(f"available() raised: {exc}")
            return

        for symbol in sorted(metals.SUPPORTED):
            contract = metals.resolve_symbol(symbol)
            if not contract:
                self.fail(f"{symbol}: LBank has no matching contract")
                self.note("Symbol discovery failed. Check /api/logs/?q=lbank for the")
                self.note("instrument list it saw, then widen _MATCH in metals.py.")
                continue
            self.good(f"{symbol}: contract = {contract}")

            price = metals.fetch_price(symbol)
            if price:
                self.good(f"{symbol}: price = {price}")
                self.sanity_check_price(symbol, price)
            else:
                self.fail(f"{symbol}: no price returned")

            candles = metals.fetch_candles(symbol, timeframe=tf, limit=120)
            if candles is None:
                self.fail(f"{symbol}: no {tf} candles — all 4 kline attempts failed")
                self.note("This is the one thing I could not verify without internet.")
                self.note("Run: python manage.py check_feeds --timeframe 1h")
            elif len(candles) < 30:
                self.warn(f"{symbol}: only {len(candles)} candles (need 30+)")
            else:
                last = candles[-1]
                self.good(f"{symbol}: {len(candles)} x {tf} candles, last close = "
                          f"{last.get('close')}")
                self.check_candle_order(symbol, candles)

        if not any(avail.values()):
            self.fail("LBank served NO metals at all — do not trade on this build")

    def sanity_check_price(self, symbol, price):
        """Catch a feed that returns a number but the WRONG number.

        A live-but-wrong price is more dangerous than no price, because
        everything downstream looks healthy while sizing is nonsense.
        """
        bands = {"XAUUSD": (1000, 6000), "XAGUSD": (10, 200)}
        lo, hi = bands.get(symbol, (0, float("inf")))
        if not (lo <= float(price) <= hi):
            self.fail(f"{symbol}: {price} is outside the sane band {lo}–{hi}")
            self.note("Probably the wrong contract (or a per-gram/per-lot quote).")

    def check_candle_order(self, symbol, candles):
        times = [c.get("time") for c in candles if c.get("time")]
        if times and times != sorted(times):
            self.fail(f"{symbol}: candles are not in ascending time order")
        elif len(times) != len(set(times)):
            self.warn(f"{symbol}: duplicate candle timestamps")

    # ---------------------------------------------------------- price layer --
    def check_price_layer(self):
        self.head("3. App price layer (what the pages actually call)")
        try:
            from apps.market.metals import fetch_metal_price
        except Exception as exc:
            self.fail(f"cannot import fetch_metal_price: {exc}")
            return

        for symbol in ("XAUUSD", "XAGUSD"):
            try:
                price = fetch_metal_price(symbol)
            except Exception as exc:
                self.fail(f"fetch_metal_price({symbol}) raised: {exc}")
                continue
            if price:
                self.good(f"fetch_metal_price({symbol}) = {price}")
            else:
                self.fail(f"fetch_metal_price({symbol}) = None")
                self.note("By design there is NO fallback to Yahoo/gold-api now.")
                self.note("To temporarily restore it: METALS_DATA_SOURCE=legacy")

    # --------------------------------------------------------- candle layer --
    def check_candle_layer(self, tf):
        self.head("4. Candle layer (feeds the scalp strategy)")
        try:
            from apps.market.candles import fetch_candles
        except Exception as exc:
            self.fail(f"cannot import fetch_candles: {exc}")
            return

        for symbol in ("XAUUSD", "XAGUSD", "BTCUSDT"):
            try:
                rows = fetch_candles(symbol, tf, 120)
            except Exception as exc:
                self.fail(f"fetch_candles({symbol}) raised: {exc}")
                continue
            if rows and len(rows) >= 30:
                self.good(f"{symbol} {tf}: {len(rows)} candles")
            elif rows:
                self.warn(f"{symbol} {tf}: only {len(rows)} candles — strategy needs 30+")
            else:
                self.fail(f"{symbol} {tf}: no candles")

    # -------------------------------------------------------- alert routing --
    def check_alert_routing(self):
        self.head("5. Alert routing (the leak that sent your colleague's alerts to you)")
        try:
            from apps.alerts import gating
            from apps.alerts.models import PushSubscription, WatchItem
            from apps.alerts.push import vapid_configured
        except Exception as exc:
            self.fail(f"cannot import the alerts modules: {exc}")
            return

        if vapid_configured():
            self.good("VAPID keys configured — web push can be delivered")
        else:
            self.warn("VAPID not configured — in-app alerts only, no push")

        User = get_user_model()
        users = list(User.objects.filter(is_active=True).order_by("username"))
        if not users:
            self.warn("no active users to check")
            return

        # Per-user picture: what they watch, and whether they are muted.
        for user in users:
            items = list(WatchItem.objects.filter(user=user, active=True)
                         .order_by("symbol"))
            subs = PushSubscription.objects.filter(user=user, enabled=True).count()
            watching = ", ".join(f"{i.symbol}(>={i.min_score})" for i in items) or "nothing"
            self.stdout.write(f"  {user.username}: watches {watching}; {subs} device(s)")

            state = gating.loss_limit_state(user)
            if state.get("blocked"):
                self.stdout.write(
                    f"        {WARN}trade alerts MUTED{END}: {state.get('reason')} "
                    f"(lost {state.get('lost')} / limit {state.get('limit')})"
                )
            else:
                self.note("trade alerts active (loss limit not reached)")

        # The actual regression test: who would receive a gold signal?
        self.stdout.write("")
        for symbol in ("XAUUSD", "BTCUSDT"):
            try:
                recips, skipped = gating.recipients(symbol, score=75, timeframe="5m")
            except Exception as exc:
                self.fail(f"recipients({symbol}) raised: {exc}")
                continue

            names = ", ".join(u.username for u in recips) or "nobody"
            self.stdout.write(f"  a score-75 {symbol} signal would notify: {names}")
            if skipped:
                self.note("muted: " + ", ".join(
                    f"{s['user'].username}({s['reason']})" for s in skipped))

            # Anyone notified MUST own an active watch item for it.
            leaked = [u.username for u in recips
                      if not WatchItem.objects.filter(
                          user=u, active=True,
                          symbol__in=[symbol, f"{symbol}:PERP"]).exists()]
            if leaked:
                self.fail(f"{symbol}: notified without a watch item: {leaked}")
            else:
                self.good(f"{symbol}: every recipient owns an active watch item")

        self.note("If a name appears here that should not, that user has their own")
        self.note("active WatchItem for the symbol — remove it in their watchlist.")

    # --------------------------------------------------------------- logging --
    def check_logging(self, skip_write=False):
        self.head("6. Logging")
        try:
            from config.health import log_path
        except Exception as exc:
            self.fail(f"cannot import config.health: {exc}")
            return

        path = log_path()
        if not path:
            self.warn("no log file configured — console/journald only")
            self.note("Then read logs with: journalctl -u smartpips -n 200")
            return

        self.stdout.write(f"  file: {path}")
        if not os.path.exists(path):
            self.warn("log file does not exist yet (it appears on the first log line)")

        before = os.path.getsize(path) if os.path.exists(path) else 0

        if skip_write:
            self.note("skipping the write test (--no-log-test)")
            return

        # Prove the whole chain end to end: a real exception, with traceback,
        # actually landing on disk. A handler that is configured but silently
        # dropping records is a classic failure mode.
        try:
            raise RuntimeError("check_feeds: deliberate test error, safe to ignore")
        except RuntimeError:
            log.exception("check_feeds wrote this on purpose — you can ignore it")

        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass

        after = os.path.getsize(path) if os.path.exists(path) else 0
        if after > before:
            self.good(f"test error written to disk (+{after - before} bytes)")
            self.note("Now open the Logs page in the app and you should see it.")
        else:
            self.fail("log file did not grow — handler is not writing")
            self.note(f"Check ownership/permissions on {os.path.dirname(path)}")
