"""Explain, in one command, WHY there is or isn't gold/silver data.

Run it on the SERVER (the box with internet), inside the backend container:

    docker exec smartpips-backend python manage.py metals_probe
    docker exec smartpips-backend python manage.py metals_probe --symbol XAGUSD --tf 15m

It walks the exact same code path the app uses, step by step, and prints the
real failure at each step instead of collapsing everything into "no data":

  1. settings        - which source is selected, which host is configured
  2. instrument list - does LBank answer at all, and with how many contracts
  3. symbol match    - which contract our XAUUSD resolved to
  4. price           - last price from that contract
  5. candles         - how many bars, how old the newest one is
  6. app path        - apps.market.candles.fetch_candles (the layer the engine
                       actually calls, including the fallback chain)
  7. engine          - what the strategy says about those bars right now

Read-only. Safe on production.
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand

OK = "\033[92m"
BAD = "\033[91m"
WARN = "\033[93m"
DIM = "\033[90m"
END = "\033[0m"


class Command(BaseCommand):
    help = "Diagnose the gold/silver data path end to end (LBank + fallbacks)."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", default="XAUUSD",
                            help="XAUUSD (default) or XAGUSD.")
        parser.add_argument("--tf", default="5m",
                            help="Timeframe for the candle probe (default 5m).")
        parser.add_argument("--clear-cache", action="store_true",
                            help="Drop the cached symbol/price/candles first, "
                                 "so the probe hits the network for real.")

    # ---------------------------------------------------------------- output
    def head(self, text):
        self.stdout.write(f"\n{text}\n" + "-" * len(text))

    def good(self, text):
        self.stdout.write(f"  {OK}OK{END}    {text}")

    def warn(self, text):
        self.stdout.write(f"  {WARN}WARN{END}  {text}")

    def fail(self, text):
        self.failures += 1
        self.stdout.write(f"  {BAD}FAIL{END}  {text}")

    def note(self, text):
        self.stdout.write(f"        {DIM}{text}{END}")

    # ---------------------------------------------------------------- runner
    def handle(self, *args, **opts):
        self.failures = 0
        symbol = opts["symbol"].upper().replace(":PERP", "")
        tf = opts["tf"]

        from apps.lbank import metals as lb

        if opts["clear_cache"]:
            from django.core.cache import cache
            for key in (f"lbank:metal-symbol:{symbol}",
                        f"lbank:metal-price:{symbol}",
                        f"lbank:metal-candles:{symbol}:{tf}",
                        "lbank:kline-endpoint"):
                cache.delete(key)
            for key in (f"candles:{symbol}:{tf}",):
                cache.delete(key)
            self.stdout.write("cache cleared for this symbol\n")

        # 1 -------------------------------------------------------- settings
        self.head("1. Settings")
        source = getattr(settings, "METALS_DATA_SOURCE", "lbank")
        self.stdout.write(f"        METALS_DATA_SOURCE   = {source}")
        self.stdout.write(f"        LBANK_FUTURES_BASE   = {lb._BASE}")
        self.stdout.write(f"        product group        = {lb._PRODUCT_GROUP}")
        if source != "lbank":
            self.warn("metals are NOT on LBank right now (legacy chain active)")

        # 2 ------------------------------------------------- instrument list
        self.head("2. LBank instrument list")
        rows = lb._rows(lb._get(f"{lb._PUB}/instrument",
                                {"productGroup": lb._PRODUCT_GROUP}))
        if rows:
            self.good(f"{len(rows)} contracts returned")
            sample = [str(r.get("symbol")) for r in rows[:6] if isinstance(r, dict)]
            self.note("first few: " + ", ".join(sample))
        else:
            err = lb.LAST_ERRORS.get(f"{lb._PUB}/instrument", "empty response")
            self.fail(f"no contracts - {err}")
            if "403" in str(err):
                self.note("HTTP 403 = the venue's firewall refused this server. "
                          "Browser headers are already sent; if it persists the "
                          "server IP or its region is blocked, so metals must "
                          "come from the fallback chain or a proxy.")

        # 3 ------------------------------------------------------- symbol
        self.head("3. Symbol resolution")
        contract = lb.resolve_symbol(symbol)
        if contract:
            self.good(f"{symbol} -> {contract}")
        else:
            self.fail(f"{symbol} did not match any listed contract")

        # 4 -------------------------------------------------------- price
        self.head("4. Price")
        price = lb.fetch_price(symbol)
        if price:
            self.good(f"last price = {price}")
        else:
            self.fail("no price from LBank")

        # 5 ------------------------------------------------------- candles
        self.head(f"5. LBank candles ({tf})")
        bars = lb.fetch_candles(symbol, tf, 300)
        if bars:
            newest = bars[-1].get("time")
            age = int(time.time() - newest) if newest else None
            self.good(f"{len(bars)} bars, newest close={bars[-1]['close']}"
                      + (f", age={age}s" if age is not None else ""))
            if age is not None and age > 900:
                self.warn("newest bar is over 15 minutes old - stale feed")
        else:
            self.fail("no candles from LBank (no kline endpoint answered)")
            for path, err in lb.LAST_ERRORS.items():
                self.note(f"{path}: {err}")

        # 6 ------------------------------------------- the layer the app uses
        self.head(f"6. App candle layer ({tf})")
        from apps.market.candles import fetch_candles as app_candles
        app_bars = app_candles(f"{symbol}", tf, 300)
        if app_bars:
            self.good(f"fetch_candles() returned {len(app_bars)} bars "
                      f"(last close {app_bars[-1]['close']})")
            if not bars:
                self.warn("these came from the FALLBACK chain, not LBank - "
                          "prices may differ slightly from LBank's book")
        else:
            self.fail("fetch_candles() returned nothing - the engine will sit "
                      "out, which is exactly why there are no gold signals")

        # 7 -------------------------------------------------------- engine
        self.head("7. Strategy engine")
        if not app_bars or len(app_bars) < 30:
            self.note(f"skipped: only {len(app_bars or [])} bars "
                      f"(the engine needs at least 30)")
        else:
            try:
                from apps.strategy.engine import run_strategy
                live = app_bars[-1]["close"]
                out = run_strategy(symbol, tf, app_bars, {}, live_price=live) or {}
                self.stdout.write(
                    f"        signal={out.get('signal')} "
                    f"score={out.get('score')} grade={out.get('grade')} "
                    f"quality={out.get('data_quality')}")
                for r in (out.get("reasons_plain") or [])[:6]:
                    self.note(f"- {r}")
                if out.get("signal") == "wait":
                    self.note("'wait' with healthy bars is NOT a bug: the score "
                              "is simply below the alert threshold "
                              "(WatchItem.min_score, default 68).")
            except Exception as exc:
                self.warn(f"engine call failed: {exc}")

        # ------------------------------------------------------------ verdict
        self.head("Verdict")
        if self.failures == 0:
            self.stdout.write(f"  {OK}Gold data path is healthy.{END}")
        elif app_bars:
            self.stdout.write(
                f"  {WARN}LBank is failing, but bars are coming from the "
                f"fallback source, so signals can still be produced.{END}")
        else:
            self.stdout.write(
                f"  {BAD}No metal bars from any source - no gold signals are "
                f"possible until this is fixed.{END}")
