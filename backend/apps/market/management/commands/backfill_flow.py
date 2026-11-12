"""Download the futures history that IS available: bars with real taker volume,
funding rates and the last month of open interest.

    python manage.py backfill_flow --symbols BTCUSDT --days 730 --interval 5m

Output (CSV, gzip) under $FLOW_DATA_DIR/<SYMBOL>/hist/:
    kline_<interval>/<YYYY-MM>.csv.gz   time,open,high,low,close,volume,quote_volume,trades,taker_buy,taker_sell,delta
    funding.csv.gz                      time,rate,mark
    oi_5m.csv.gz                        time,oi,oi_value     (merged with earlier runs)

Safe to re-run: finished months are skipped, the current month is refreshed.
Order book and liquidations have no history - see `record_flow`.
"""
import csv
import gzip
import io
import os
import time
from datetime import datetime, timezone

import requests
from django.core.management.base import BaseCommand

from apps.market import futures_flow as ff
from apps.market.flow_store import default_root

KLINE_COLS = ["time", "open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy",
              "taker_sell", "delta"]


def month_starts(start_ts, end_ts):
    d = datetime.fromtimestamp(start_ts, tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    while d.timestamp() < end_ts:
        nxt = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
        out.append((d.strftime("%Y-%m"), int(d.timestamp()), int(nxt.timestamp())))
        d = nxt
    return out


def write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])
    os.replace(tmp, path)                      # never leave a half-written month behind


def read_csv(path):
    try:
        with gzip.open(path, "rt", newline="") as fh:
            return list(csv.DictReader(io.StringIO(fh.read())))
    except (OSError, EOFError):
        return []


def fetch_range(symbol, interval, start_ts, end_ts, session, pause, fetch=ff.klines, now=None):
    """All CLOSED bars with start_ts <= time < end_ts, paging forward 1500 at a time."""
    step = ff.TF_SECONDS[interval]
    now = time.time() if now is None else now
    out, cursor = [], start_ts
    while cursor < end_ts:
        rows = fetch(symbol, interval, 1500, start_ms=cursor * 1000, end_ms=end_ts * 1000 - 1, session=session)
        rows = [b for b in rows if cursor <= b["time"] < end_ts]
        if not rows:
            break
        out.extend(rows)
        cursor = rows[-1]["time"] + step
        if pause:
            time.sleep(pause)
    return [b for b in out if b["time"] + step <= now]


class Command(BaseCommand):
    help = "Backfill taker-volume bars, funding history and recent open interest for crypto perps."

    def add_arguments(self, parser):
        parser.add_argument("--symbols", default=os.getenv("FLOW_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT"))
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--interval", default="5m", choices=("1m", "5m", "15m", "1h"))
        parser.add_argument("--dir", default=None)
        parser.add_argument("--pause", type=float, default=0.5, help="seconds between requests (rate limit)")

    def handle(self, *args, **o):
        root = o["dir"] or default_root()
        session = requests.Session()
        now = int(time.time())
        start = now - o["days"] * 86400
        this_month = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m")
        for symbol in [ff.base_symbol(s) for s in o["symbols"].split(",") if s.strip()]:
            hist = os.path.join(root, symbol, "hist")
            total = 0
            for label, m0, m1 in month_starts(start, now):
                path = os.path.join(hist, f"kline_{o['interval']}", f"{label}.csv.gz")
                if os.path.exists(path) and label != this_month:
                    continue
                try:
                    rows = fetch_range(symbol, o["interval"], m0, min(m1, now), session, o["pause"])
                except ff.FlowError as exc:
                    self.stderr.write(f"{symbol} {label}: {exc}")
                    if "rate limited" in str(exc):
                        time.sleep(60)
                    continue
                if rows:
                    write_csv(path, KLINE_COLS, rows)
                    total += len(rows)
                    self.stdout.write(f"{symbol} {label}: {len(rows)} bars")
            try:
                fund, cursor = [], start * 1000
                while True:
                    page = ff.funding_history(symbol, start_ms=cursor, limit=1000, session=session)
                    page = [r for r in page if r["time"] * 1000 >= cursor]
                    if not page:
                        break
                    fund.extend(page)
                    cursor = page[-1]["time"] * 1000 + 1
                    if len(page) < 1000:
                        break
                    time.sleep(o["pause"])
                if fund:
                    write_csv(os.path.join(hist, "funding.csv.gz"), ["time", "rate", "mark"], fund)
            except ff.FlowError as exc:
                self.stderr.write(f"{symbol} funding: {exc}")
                fund = []
            try:
                oi_path = os.path.join(hist, "oi_5m.csv.gz")
                merged = {int(r["time"]): r for r in read_csv(oi_path) if r.get("time")}
                cursor = (now - 29 * 86400) * 1000      # the exchange keeps one month; stay inside it
                while True:
                    page = ff.open_interest_hist(symbol, "5m", 500, start_ms=cursor, session=session)
                    page = [r for r in page if r["time"] * 1000 >= cursor]
                    if not page:
                        break
                    for r in page:
                        merged[r["time"]] = r
                    cursor = page[-1]["time"] * 1000 + 1
                    if len(page) < 500:
                        break
                    time.sleep(o["pause"])
                if merged:
                    write_csv(oi_path, ["time", "oi", "oi_value"], [merged[k] for k in sorted(merged)])
            except ff.FlowError as exc:
                self.stderr.write(f"{symbol} open interest: {exc}")
                merged = {}
            self.stdout.write(self.style.SUCCESS(
                f"{symbol}: {total} new bars, {len(fund)} funding rows, {len(merged)} OI rows -> {hist}"))
