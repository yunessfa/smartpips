"""Append-only storage for recorded futures flow data.

Layout (one gzip JSON-lines file per symbol, stream and UTC day):

    <root>/<SYMBOL>/<stream>/<YYYY-MM-DD>.jsonl.gz

Plain files instead of database rows on purpose: an order-book snapshot every
few seconds is tens of thousands of rows a day per symbol, it is only ever read
sequentially by research scripts, and files can be copied off the server with
scp. Nothing in the web app reads these files.
"""
import gzip
import json
import os
import threading
import zlib
from datetime import datetime, timezone

STREAMS = ("depth", "kline_1m", "oi", "funding", "liq")


def default_root():
    return os.getenv("FLOW_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "flow-data")


def day_of(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def stream_path(root, symbol, stream, day):
    return os.path.join(root, symbol.upper(), stream, f"{day}.jsonl.gz")


class DayWriter:
    """Thread-safe appender that rotates files at UTC midnight.

    Each open file is one gzip member; reopening after a restart appends a new
    member, which gzip readers treat as one continuous stream. flush() makes
    everything written so far readable even if the process is killed.
    """

    def __init__(self, root):
        self.root = root
        self._files = {}                 # (symbol, stream) -> (day, handle)
        self._lock = threading.Lock()
        self.counts = {}
        self.last = {}

    def write(self, symbol, stream, record, ts):
        day = day_of(ts)
        key = (symbol.upper(), stream)
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        with self._lock:
            cur = self._files.get(key)
            if cur is None or cur[0] != day:
                if cur is not None:
                    cur[1].close()
                path = stream_path(self.root, symbol, stream, day)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                cur = (day, gzip.open(path, "ab", compresslevel=6))
                self._files[key] = cur
            cur[1].write(line)
            self.counts[stream] = self.counts.get(stream, 0) + 1
            self.last[stream] = ts

    def flush(self):
        with self._lock:
            for _, handle in self._files.values():
                handle.flush()

    def close(self):
        with self._lock:
            for _, handle in self._files.values():
                try:
                    handle.close()
                except OSError:
                    pass
            self._files.clear()


def iter_records(path):
    """Yield records from one file. A file cut off mid-write (crash, disk full) yields
    everything up to the last complete line instead of raising."""
    buf = b""
    try:
        with open(path, "rb") as raw:
            dec = zlib.decompressobj(wbits=31)
            while True:
                chunk = raw.read(1 << 16)
                if not chunk:
                    break
                while chunk:
                    try:
                        buf += dec.decompress(chunk)
                    except zlib.error:
                        chunk = b""
                        break
                    if dec.eof:                      # next gzip member (the writer was restarted)
                        chunk = dec.unused_data
                        dec = zlib.decompressobj(wbits=31)
                    else:
                        chunk = b""
                *lines, buf = buf.split(b"\n")
                for line in lines:
                    if line:
                        try:
                            yield json.loads(line)
                        except ValueError:
                            continue
    except OSError:
        return


def list_days(root, symbol, stream):
    folder = os.path.join(root, symbol.upper(), stream)
    try:
        return sorted(f[:-9] for f in os.listdir(folder) if f.endswith(".jsonl.gz"))
    except OSError:
        return []


def read_stream(root, symbol, stream, start_day=None, end_day=None):
    for day in list_days(root, symbol, stream):
        if (start_day and day < start_day) or (end_day and day > end_day):
            continue
        yield from iter_records(stream_path(root, symbol, stream, day))
