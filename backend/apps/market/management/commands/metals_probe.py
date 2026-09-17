"""Explain, in one command, WHY there is or isn't gold/silver data.

Run on the SERVER, inside the backend container:

    docker exec smartpips-backend python manage.py metals_probe --clear-cache
    docker exec smartpips-backend python manage.py metals_probe --symbol XAGUSD --tf 15m

It walks the exact code path the app uses and prints the real failure at each
step instead of collapsing everything into "no data":

  1. settings        - selected source, configured host, available fallbacks
  2. instrument list - does LBank answer, and with how many contracts
  3. symbol match    - which LBank contract our XAUUSD resolved to
  4. price           - last price for that contract
  5. LBank candles   - the kline endpoints (these are the ones behind the WAF)
  6. app layer       - apps.market.candles.fetch_candles, i.e. what the engine
                       really gets, including the fallback chain, and WHICH
                       source supplied the bars
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
                            help="Drop cached symbol/price/candles and the "
                                 "kline circuit breaker first, so the probe "
                                 "really hits the network.")

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

        from django.core.cache import cache

        from apps.lbank import metals as lb

        if opts["clear_cache"]:
            for key in (f"lbank:metal-symbol:{symbol}",
                        f"lbank:metal-price:{symbol}",
                        f"lbank:metal-candles:{symbol}:{tf}",
                        "lbank:kline-endpoint",
                        lb._KLINE_DEAD_KEY,
                        "td:cooldown",
                        f"candles:{symbol}:{tf}"):
                cache.delete(key)
            self.stdout.write("cache cleared for this symbol\n")

        # 1 -------------------------------------------------------- settings
        self.head("1. Settings")
        source = getattr(settings, "METALS_DATA_SOURCE", "lbank")
        import os
        self.stdout.write(f"        METALS_DATA_SOURCE   = {source}")
        self.stdout.write(f"        LBANK_FUTURES_BASE   = {lb._BASE}")
        self.stdout.write(f"        product group        = {lb._PRODUCT_GROUP}")
        self.stdout.write(
            "        METALS_STRICT_SOURCE = "
            f"{os.getenv('METALS_STRICT_SOURCE') or '(off - fallbacks allowed)'}")
        self.stdout.write(
            "        TWELVEDATA_KEY       = "
            f"{'set' if os.getenv('TWELVEDATA_KEY') else 'MISSING'}")
        if cache.get(lb._KLINE_DEAD_KEY):
            self.note("LBank kline circuit breaker is OPEN (all endpoints were "
                      "refused recently). Use --clear-cache to force a retry.")

        # 2 ------------------------------------------------- instrument list
        self.head("2. LBank instrument list")
        rows = lb._rows(lb._get(f"{lb._PUB}/instrument",
                                {"productGroup": lb._PRODUCT_GROUP}))
        if rows:
            self.good(f"{len(rows)} contracts returned")
            sample = [str(r.get("symbol")) for r in rows[:6] if isinstance(r, dict)]
            self.note("first few: " + ", ".join(sample))
        else:
            self.fail("no contracts - "
                      f"{lb.LAST_ERRORS.get(lb._PUB + '/instrument', 'empty response')}")

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
            self.warn("no candles from LBank")
            for path, err in lb.LAST_ERRORS.items():
                self.note(f"{path}: {err}")
            self.note("403 on the kline paths while /instrument and /marketData "
                      "answer 200 means the venue publishes prices but not "
                      "public contract klines to us. That is THEIR gate, not a "
                      "bug here - the fallback chain below covers it.")

        # 6 ------------------------------------------- the layer the app uses
        self.head(f"6. App candle layer ({tf})")
        from apps.market.candles import _metal_fallback_candles
        from apps.market.candles import fetch_candles as app_candles

        app_bars = app_candles(symbol, tf, 300)
        if app_bars:
            newest = app_bars[-1].get("time")
            age = int(time.time() - newest) if newest else None
            self.good(f"fetch_candles() returned {len(app_bars)} bars "
                      f"(last close {app_bars[-1]['close']}"
                      + (f", age={age}s)" if age is not None else ")"))
            if not bars:
                # Ask the chain which source would answer, for the report.
                _, src = _metal_fallback_candles(symbol, tf, 300)
                self.note(f"source: {src or 'cache'} (not LBank) - prices may "
                          f"differ slightly from LBank's book")
        else:
            self.fail("fetch_candles() returned nothing - the engine sits out, "
                      "which is exactly why there are no gold signals")

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
                grade = out.get("grade")
                if isinstance(grade, dict):      # {'grade': '-', 'stars': 0, ...}
                    grade = grade.get("grade")
                self.stdout.write(
                    f"        signal={out.get('signal')} "
                    f"score={out.get('score')} grade={grade} "
                    f"quality={out.get('data_quality')}")
                reasons = out.get("reasons_plain")
                if isinstance(reasons, dict):
                    reasons = list(reasons.values())
                elif isinstance(reasons, str):
                    reasons = [reasons]
                for r in list(reasons or [])[:6]:
                    self.note(f"- {r}")
                if out.get("signal") == "wait":
                    self.note("'wait' on healthy bars is NOT a bug: the score is "
                              "below the alert threshold (WatchItem.min_score, "
                              "default 68).")
            except Exception as exc:
                self.warn(f"engine call failed: {type(exc).__name__}: {exc}")

        # ------------------------------------------------------------ verdict
        self.head("Verdict")
        if app_bars and len(app_bars) >= 30 and price:
            self.stdout.write(
                f"  {OK}Gold/silver data is flowing: price + {len(app_bars)} "
                f"bars. Signals are possible; whether one fires depends on the "
                f"score.{END}")
        elif app_bars:
            self.stdout.write(f"  {WARN}Partial data only.{END}")
        else:
            self.stdout.write(
                f"  {BAD}No metal bars from any source - no metal signals are "
                f"possible until this is fixed.{END}")
