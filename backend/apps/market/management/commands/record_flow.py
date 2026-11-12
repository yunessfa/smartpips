"""Record futures order-flow data that cannot be downloaded later.

    python manage.py record_flow --symbols BTCUSDT,ETHUSDT,SOLUSDT

Runs forever (docker-compose.flow.yml). Per symbol it stores:
  depth     order-book snapshot (top N levels each side) every --depth-interval s
  kline_1m  every closed 1m bar with real taker buy / sell volume
  oi        open interest, once a minute
  funding   mark / index price and funding rate, once a minute
  liq       liquidation orders from the websocket (a sample: the exchange pushes
            at most the largest one per symbol per second)

Order book and liquidations have no public history: whatever is not recorded
is gone. Taker volume, funding and one month of OI can be backfilled with
`backfill_flow`. Files land in $FLOW_DATA_DIR (see apps.market.flow_store).
"""
import json
import logging
import os
import signal
import threading
import time

import requests
from django.core.management.base import BaseCommand

from apps.market import futures_flow as ff
from apps.market.flow_store import DayWriter, default_root

log = logging.getLogger("smartpips.flow")
DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT"


def compact_depth(book, levels):
    return {"t": round(book["time"], 3), "u": book.get("last_update_id"),
            "b": book["bids"][:levels], "a": book["asks"][:levels]}


def liquidation_loop(symbols, on_event, stop, connect=None, url=None, idle_timeout=400):
    """Blocking websocket reader with reconnect. `connect` is injectable for tests."""
    if connect is None:
        try:
            import websocket
        except ImportError:
            log.error("websocket-client is not installed - liquidations are NOT being recorded")
            return
        connect = websocket.create_connection
    streams = "/".join(f"{s.lower()}@forceOrder" for s in symbols)
    url = url or f"{ff.WS_MARKET_URL}/stream?streams={streams}"
    backoff = 2
    while not stop.is_set():
        ws = None
        try:
            ws = connect(url, timeout=20)
            ws.settimeout(idle_timeout)      # the server pings every few minutes; silence = dead link
            log.info("liquidation stream connected (%d symbols)", len(symbols))
            backoff = 2
            while not stop.is_set():
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    ev = ff.parse_force_order(json.loads(raw))
                except ValueError:
                    continue
                if ev:
                    on_event(ev)
        except Exception as exc:              # network drops, 24h disconnect, timeouts
            if not stop.is_set():
                log.warning("liquidation stream dropped (%s: %s); reconnecting in %ss",
                            type(exc).__name__, str(exc)[:80], backoff)
        finally:
            try:
                if ws is not None:
                    ws.close()
            except Exception:
                pass
        stop.wait(backoff)
        backoff = min(backoff * 2, 60)


class Recorder:
    def __init__(self, symbols, root, depth_interval=10, depth_levels=100, session=None, clock=time.time):
        self.symbols = symbols
        self.writer = DayWriter(root)
        self.root = root
        self.depth_interval = depth_interval
        self.depth_levels = depth_levels
        self.session = session or requests.Session()
        self.clock = clock
        self.last_kline = {}                 # symbol -> open time of the last bar written
        self.errors = 0
        self.last_error = None
        self.started = clock()
        self.pause_until = 0.0

    def _fail(self, what, exc):
        self.errors += 1
        self.last_error = f"{what}: {exc}"
        log.warning("flow recorder: %s failed: %s", what, exc)
        if "rate limited" in str(exc):
            self.pause_until = self.clock() + 60          # back off instead of earning an IP ban

    def depth_pass(self):
        for s in self.symbols:
            try:
                book = ff.depth(s, self.depth_levels, session=self.session)
                self.writer.write(s, "depth", compact_depth(book, self.depth_levels), self.clock())
            except ff.FlowError as exc:
                self._fail(f"depth {s}", exc)

    def minute_pass(self):
        now = self.clock()
        for s in self.symbols:
            try:
                for b in ff.klines(s, "1m", 5, session=self.session):
                    if b["time"] + 60 <= now and b["time"] > self.last_kline.get(s, 0):
                        self.writer.write(s, "kline_1m", b, b["time"])
                        self.last_kline[s] = b["time"]
            except ff.FlowError as exc:
                self._fail(f"klines {s}", exc)
            try:
                oi = ff.open_interest(s, session=self.session)
                self.writer.write(s, "oi", {"t": round(oi["time"], 3), "oi": oi["oi"]}, now)
            except ff.FlowError as exc:
                self._fail(f"open interest {s}", exc)
            try:
                p = ff.premium_index(s, session=self.session)
                self.writer.write(s, "funding", {"t": round(p["time"], 3), "mark": p["mark"], "index": p["index"],
                                                 "rate": p["funding_rate"], "next": p["next_funding_time"]}, now)
            except ff.FlowError as exc:
                self._fail(f"funding {s}", exc)

    def on_liquidation(self, ev):
        if ev["symbol"] in self.symbols:
            self.writer.write(ev["symbol"], "liq", {"t": round(ev["time"], 3), "side": ev["side"],
                                                    "liq": ev["liquidated"], "p": ev["price"], "q": ev["qty"]},
                              self.clock())

    def write_status(self):
        status = {"started": self.started, "updated": self.clock(), "symbols": self.symbols,
                  "counts": dict(self.writer.counts), "last": dict(self.writer.last),
                  "errors": self.errors, "last_error": self.last_error,
                  "depth_interval": self.depth_interval, "depth_levels": self.depth_levels}
        tmp = os.path.join(self.root, "status.json.tmp")
        try:
            os.makedirs(self.root, exist_ok=True)
            with open(tmp, "w") as fh:
                json.dump(status, fh)
            os.replace(tmp, os.path.join(self.root, "status.json"))
        except OSError as exc:
            log.warning("flow recorder: cannot write status: %s", exc)

    def run(self, stop, sleep=None):
        sleep = sleep or stop.wait
        next_depth = self.clock()
        next_minute = (int(self.clock()) // 60 + 1) * 60 + 3      # a few seconds after the bar closes
        next_flush = self.clock() + 30
        while not stop.is_set():
            now = self.clock()
            if now < self.pause_until:
                sleep(1.0)
                continue
            if now >= next_depth:
                self.depth_pass()
                next_depth = max(next_depth + self.depth_interval, self.clock())
            if now >= next_minute:
                self.minute_pass()
                next_minute = (int(self.clock()) // 60 + 1) * 60 + 3
            if now >= next_flush:
                self.writer.flush()
                self.write_status()
                next_flush = self.clock() + 30
            sleep(max(0.05, min(next_depth, next_minute, next_flush) - self.clock()))
        self.writer.flush()
        self.write_status()
        self.writer.close()


class Command(BaseCommand):
    help = "Record order book, taker volume, open interest, funding and liquidations for crypto perps."

    def add_arguments(self, parser):
        parser.add_argument("--symbols", default=os.getenv("FLOW_SYMBOLS", DEFAULT_SYMBOLS))
        parser.add_argument("--dir", default=None, help="output folder (default $FLOW_DATA_DIR)")
        parser.add_argument("--depth-interval", type=int, default=10, help="seconds between book snapshots")
        parser.add_argument("--depth-levels", type=int, default=100, choices=(20, 50, 100, 500))
        parser.add_argument("--no-liquidations", action="store_true")

    def handle(self, *args, **o):
        symbols = [ff.base_symbol(s) for s in o["symbols"].split(",") if s.strip()]
        root = o["dir"] or default_root()
        interval = max(2, o["depth_interval"])
        # REST weight per minute: depth costs 5 (<=100 levels) or 10 (500); stay far below the 2400 limit.
        weight = len(symbols) * ((60 / interval) * (10 if o["depth_levels"] > 100 else 5) + 5)
        if weight > 1200:
            self.stderr.write(f"refusing to start: ~{int(weight)} request weight / min is too close to the limit; "
                              "use fewer symbols or a longer --depth-interval")
            return
        rec = Recorder(symbols, root, interval, o["depth_levels"])
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        if not o["no_liquidations"]:
            threading.Thread(target=liquidation_loop, args=(symbols, rec.on_liquidation, stop), daemon=True,
                             name="flow-liquidations").start()
        self.stdout.write(f"flow recorder started: {', '.join(symbols)} -> {root} "
                          f"(book every {interval}s, {o['depth_levels']} levels, ~{int(weight)} weight/min)")
        rec.run(stop)
        self.stdout.write("flow recorder stopped cleanly")
