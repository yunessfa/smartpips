"""Verify from THIS server that every flow feed answers, and show what was recorded.

    python manage.py check_flow                 # live endpoint check
    python manage.py check_flow --recorded      # what is on disk

Run it once after deploying: the feeds were written against the exchange's
published formats and could not be exercised from the development sandbox.
"""
import json
import os
import time

from django.core.management.base import BaseCommand

from apps.market import futures_flow as ff
from apps.market.flow_store import STREAMS, default_root, iter_records, list_days, stream_path


class Command(BaseCommand):
    help = "Check the Binance USD-M flow feeds from this server, or summarise recorded data."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", default="BTCUSDT")
        parser.add_argument("--recorded", action="store_true")
        parser.add_argument("--dir", default=None)
        parser.add_argument("--ws-seconds", type=int, default=8)

    def handle(self, *args, **o):
        if o["recorded"]:
            return self._recorded(o["dir"] or default_root())
        sym, failed = o["symbol"], 0

        def check(name, fn, show):
            nonlocal failed
            try:
                self.stdout.write(self.style.SUCCESS(f"OK    {name}: {show(fn())}"))
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"FAIL  {name}: {exc}"))

        check("klines + taker volume", lambda: ff.klines(sym, "5m", 3),
              lambda r: f"{len(r)} bars, last delta {r[-1]['delta']:.3f} of {r[-1]['volume']:.3f}")
        check("open interest", lambda: ff.open_interest(sym), lambda r: f"{r['oi']:.3f}")
        check("open interest history", lambda: ff.open_interest_hist(sym, "5m", 5), lambda r: f"{len(r)} rows")
        check("funding / mark", lambda: ff.premium_index(sym),
              lambda r: f"mark {r['mark']}, funding {r['funding_rate']}")
        check("funding history", lambda: ff.funding_history(sym, limit=3), lambda r: f"{len(r)} rows")
        check("order book", lambda: ff.book_imbalance(ff.depth(sym, 100)),
              lambda r: f"spread {r['spread_bps']} bps, +/-0.1% imbalance {r['bands'][0]['imbalance']}")

        def ws():
            import websocket
            url = f"{ff.WS_MARKET_URL}/stream?streams={sym.lower()}@forceOrder"
            conn = websocket.create_connection(url, timeout=10)
            conn.settimeout(o["ws_seconds"])
            try:
                try:
                    return "connected, event: " + str(ff.parse_force_order(json.loads(conn.recv())))
                except websocket.WebSocketTimeoutException:
                    return f"connected (no liquidation in {o['ws_seconds']}s - normal)"
            finally:
                conn.close()
        check("liquidation websocket", ws, str)
        if failed:
            self.stdout.write(self.style.ERROR(f"{failed} feed(s) failed - see messages above"))
        else:
            self.stdout.write(self.style.SUCCESS("all flow feeds reachable"))

    def _recorded(self, root):
        try:
            with open(os.path.join(root, "status.json")) as fh:
                st = json.load(fh)
            age = time.time() - st.get("updated", 0)
            self.stdout.write(f"recorder: updated {int(age)}s ago, errors {st.get('errors')}, "
                              f"last error {st.get('last_error')}")
        except (OSError, ValueError):
            self.stdout.write("recorder: no status file (not started yet?)")
        try:
            symbols = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
        except OSError:
            self.stdout.write(f"nothing recorded under {root}")
            return
        for sym in symbols:
            for stream in STREAMS:
                days = list_days(root, sym, stream)
                if not days:
                    continue
                size = sum(os.path.getsize(stream_path(root, sym, stream, d)) for d in days)
                last = sum(1 for _ in iter_records(stream_path(root, sym, stream, days[-1])))
                self.stdout.write(f"{sym:10s} {stream:9s} {len(days):4d} days  {days[0]} .. {days[-1]}  "
                                  f"{size / 1e6:8.1f} MB  ({last} records on the last day)")
