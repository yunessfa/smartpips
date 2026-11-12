import gzip
import json
import os
import tempfile
import threading
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.market import futures_flow as ff
from apps.market.flow_store import DayWriter, iter_records, list_days, read_stream, stream_path
from apps.market.management.commands import backfill_flow, record_flow

# Shapes copied from the exchange's published examples.
KLINE = [1700000000000, "100.0", "110.0", "95.0", "105.0", "50.0", 1700000299999, "5200.0", 321, "30.0",
         "3100.0", "0"]
DEPTH = {"lastUpdateId": 7, "E": 1700000000500, "T": 1700000000400,
         "bids": [["99.0", "3"], ["99.9", "1"], ["99.5", "2"]],
         "asks": [["100.1", "1"], ["101.0", "4"], ["100.5", "1"]]}
FORCE = {"stream": "btcusdt@forceOrder", "data": {"e": "forceOrder", "E": 1700000001000, "o": {
    "s": "BTCUSDT", "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "0.5", "p": "99.0", "ap": "99.2", "X": "FILLED",
    "l": "0.5", "z": "0.5", "T": 1700000000900}}}


class Parsers(SimpleTestCase):
    def test_kline_delta_is_taker_buy_minus_taker_sell(self):
        b = ff.parse_kline(KLINE)
        self.assertEqual(b["time"], 1700000000)
        self.assertEqual((b["taker_buy"], b["taker_sell"], b["delta"]), (30.0, 20.0, 10.0))
        self.assertIsNone(ff.parse_kline(["x"]))

    def test_depth_is_sorted_best_first_and_drops_bad_rows(self):
        book = ff.parse_depth({**DEPTH, "bids": DEPTH["bids"] + [["bad", "1"], ["98", "0"]]})
        self.assertEqual([p for p, _ in book["bids"]], [99.9, 99.5, 99.0])
        self.assertEqual([p for p, _ in book["asks"]], [100.1, 100.5, 101.0])
        self.assertIsNone(ff.parse_depth({"bids": [], "asks": []}))

    def test_force_order_side_maps_to_the_position_that_was_liquidated(self):
        ev = ff.parse_force_order(FORCE)
        self.assertEqual((ev["symbol"], ev["side"], ev["liquidated"]), ("BTCUSDT", "SELL", "long"))
        self.assertAlmostEqual(ev["notional"], 49.6)
        raw = {**FORCE["data"], "o": {**FORCE["data"]["o"], "S": "BUY"}}
        self.assertEqual(ff.parse_force_order(raw)["liquidated"], "short")      # raw (non-combined) envelope
        self.assertIsNone(ff.parse_force_order({"e": "aggTrade"}))
        self.assertIsNone(ff.parse_force_order("x"))

    def test_book_imbalance_and_incomplete_band_flag(self):
        out = ff.book_imbalance(ff.parse_depth(DEPTH), bands=(0.2, 5.0))
        self.assertAlmostEqual(out["mid"], 100.0)
        self.assertEqual(out["spread_bps"], 20.0)
        near, wide = out["bands"]
        self.assertEqual((near["bid_qty"], near["ask_qty"], near["imbalance"]), (1.0, 1.0, 0.0))
        self.assertTrue(near["complete"])
        self.assertEqual((wide["bid_qty"], wide["ask_qty"]), (6.0, 6.0))
        self.assertFalse(wide["complete"])                # the book does not reach +/-5%

    def test_delta_summary_windows(self):
        bars = [{"time": i * 300, "open": 100 + i, "close": 101 + i, "volume": 10.0, "delta": d}
                for i, d in enumerate([2.0, -4.0, 6.0])]
        out = ff.delta_summary(bars, windows=(1, 3))
        self.assertEqual(out["cvd"], [2.0, -2.0, 4.0])
        self.assertEqual(out["windows"][0]["delta_pct"], 60.0)
        self.assertEqual(out["windows"][1]["delta"], 4.0)
        self.assertEqual(ff.delta_summary([])["bars"], 0)

    def test_oi_summary_changes(self):
        hist = [{"time": t, "oi": oi} for t, oi in ((0, 100.0), (86400 - 14400, 110.0), (86400 - 3600, 120.0),
                                                    (86400, 132.0))]
        out = ff.oi_summary(hist)
        self.assertEqual({c["window"]: c["change_pct"] for c in out["changes"]},
                         {"1h": 10.0, "4h": 20.0, "24h": 32.0})


class RestErrors(SimpleTestCase):
    def _resp(self, status, payload=None, text=""):
        r = mock.Mock(status_code=status, text=text, headers={})
        r.json.return_value = payload
        return r

    def test_rate_limit_and_region_block_are_named(self):
        with mock.patch.object(ff.requests, "get", return_value=self._resp(429)):
            with self.assertRaisesRegex(ff.FlowError, "rate limited"):
                ff.open_interest("BTCUSDT")
        with mock.patch.object(ff.requests, "get", return_value=self._resp(451)):
            with self.assertRaisesRegex(ff.FlowError, "region"):
                ff.depth("BTCUSDT")

    def test_snapshot_sections_fail_independently_and_skip_the_forming_bar(self):
        now = int(time.time())
        closed = [1000 * (now - 900), "1", "2", "1", "2", "10", 0, "20", 5, "7", "14", "0"]
        forming = [1000 * (now - 100), "2", "3", "2", "3", "99", 0, "99", 5, "99", "99", "0"]

        def fake(url, params=None, **_):
            if url.endswith("/fapi/v1/klines"):
                return self._resp(200, [closed, forming])
            if url.endswith("/fapi/v1/premiumIndex"):
                return self._resp(200, {"markPrice": "100.5", "indexPrice": "100.0", "lastFundingRate": "0.0001",
                                        "nextFundingTime": 1700000000000, "time": 1700000000000})
            if url.endswith("/fapi/v1/depth"):
                return self._resp(200, DEPTH)
            return self._resp(500, text="boom")           # open-interest history is down
        with mock.patch.object(ff.requests, "get", side_effect=fake):
            out = ff.snapshot("BTCUSDT:PERP", "5m")
        self.assertEqual(out["status"], "partial")
        self.assertEqual(out["errors"], ["open_interest"])
        self.assertEqual(out["delta"]["bars"], 1)          # the forming bar is not counted
        self.assertEqual(out["delta"]["windows"][0]["delta"], 4.0)
        self.assertEqual(out["funding"]["rate_pct"], 0.01)
        self.assertEqual(out["funding"]["basis_bps"], 50.0)
        self.assertEqual(out["venue"], "binance_usdm")


class Store(SimpleTestCase):
    def test_roundtrip_rotation_and_restart_append(self):
        with tempfile.TemporaryDirectory() as root:
            w = DayWriter(root)
            w.write("btcusdt", "oi", {"n": 1}, 1700000000)                    # 2023-11-14
            w.write("BTCUSDT", "oi", {"n": 2}, 1700000000 + 86400)             # next day -> new file
            w.close()
            w2 = DayWriter(root)                                               # restart: appends a gzip member
            w2.write("BTCUSDT", "oi", {"n": 3}, 1700000000 + 86400 + 5)
            w2.close()
            self.assertEqual(list_days(root, "BTCUSDT", "oi"), ["2023-11-14", "2023-11-15"])
            self.assertEqual([r["n"] for r in read_stream(root, "BTCUSDT", "oi")], [1, 2, 3])
            self.assertEqual([r["n"] for r in read_stream(root, "BTCUSDT", "oi", start_day="2023-11-15")], [2, 3])

    def test_flushed_data_survives_a_kill_and_a_truncated_file_is_readable(self):
        with tempfile.TemporaryDirectory() as root:
            w = DayWriter(root)
            for i in range(200):
                w.write("BTCUSDT", "depth", {"i": i, "pad": "x" * 50}, 1700000000)
            w.flush()                                                          # no close(): simulated kill -9
            path = stream_path(root, "BTCUSDT", "depth", "2023-11-14")
            self.assertEqual(len(list(iter_records(path))), 200)
            with open(path, "rb") as fh:
                data = fh.read()
            with open(path, "wb") as fh:
                fh.write(data[: len(data) // 2])                               # disk-full style truncation
            got = [r["i"] for r in iter_records(path)]
            self.assertTrue(0 < len(got) < 200)
            self.assertEqual(got, list(range(len(got))))
            self.assertEqual(list(iter_records(os.path.join(root, "missing.jsonl.gz"))), [])


class RecorderPasses(SimpleTestCase):
    def test_minute_pass_writes_each_closed_bar_once_and_survives_feed_errors(self):
        now = [1700000100.0]
        bars = [{"time": 1699999980, "delta": 1.0}, {"time": 1700000040, "delta": 2.0}, {"time": 1700000100, "delta": 3.0}]
        with tempfile.TemporaryDirectory() as root:
            rec = record_flow.Recorder(["BTCUSDT"], root, session=object(), clock=lambda: now[0])
            with mock.patch.object(ff, "klines", return_value=bars), \
                    mock.patch.object(ff, "open_interest", return_value={"time": 1.0, "oi": 5.0}), \
                    mock.patch.object(ff, "premium_index", side_effect=ff.FlowError("rate limited on x")):
                rec.minute_pass()
                rec.minute_pass()                                              # same bars again: no duplicates
            rec.writer.close()
            self.assertEqual([r["time"] for r in read_stream(root, "BTCUSDT", "kline_1m")], [1699999980, 1700000040])
            self.assertEqual(len(list(read_stream(root, "BTCUSDT", "oi"))), 2)
            self.assertEqual(rec.errors, 2)
            self.assertGreater(rec.pause_until, now[0])                        # rate limit -> back off

    def test_depth_pass_and_liquidation_filter(self):
        with tempfile.TemporaryDirectory() as root:
            rec = record_flow.Recorder(["BTCUSDT"], root, depth_levels=2, session=object(), clock=lambda: 1700000000.0)
            with mock.patch.object(ff, "depth", return_value=ff.parse_depth(DEPTH)):
                rec.depth_pass()
            rec.on_liquidation(ff.parse_force_order(FORCE))
            rec.on_liquidation({**ff.parse_force_order(FORCE), "symbol": "DOGEUSDT"})   # not recorded
            rec.write_status()
            rec.writer.close()
            snap = next(read_stream(root, "BTCUSDT", "depth"))
            self.assertEqual((len(snap["b"]), len(snap["a"]), snap["u"]), (2, 2, 7))
            self.assertEqual([r["liq"] for r in read_stream(root, "BTCUSDT", "liq")], ["long"])
            with open(os.path.join(root, "status.json")) as fh:
                self.assertEqual(json.load(fh)["counts"], {"depth": 1, "liq": 1})

    def test_run_loop_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as root:
            t = [1700000050.0]
            rec = record_flow.Recorder(["BTCUSDT"], root, depth_interval=10, session=object(), clock=lambda: t[0])
            stop = threading.Event()
            calls = {"depth": 0, "minute": 0}
            rec.depth_pass = lambda: calls.__setitem__("depth", calls["depth"] + 1)
            rec.minute_pass = lambda: calls.__setitem__("minute", calls["minute"] + 1)

            def sleep(dt):
                t[0] += dt
                if t[0] >= 1700000050.0 + 65:
                    stop.set()
            rec.run(stop, sleep=sleep)
            self.assertEqual(calls["minute"], 1)
            self.assertIn(calls["depth"], (6, 7, 8))
            self.assertTrue(os.path.exists(os.path.join(root, "status.json")))

    def test_liquidation_loop_reconnects_and_ignores_garbage(self):
        stop, got = threading.Event(), []

        class Conn:
            def __init__(self, frames):
                self.frames = list(frames)

            def settimeout(self, _):
                pass

            def recv(self):
                if not self.frames:
                    raise ConnectionError("dropped")
                return self.frames.pop(0)

            def close(self):
                pass
        conns = [Conn(["not json", json.dumps({"result": None})]), Conn([json.dumps(FORCE)])]

        def connect(url, timeout=None):
            self.assertIn("/market/stream?streams=btcusdt@forceOrder", url)
            if not conns:
                stop.set()
                raise ConnectionError("done")
            return conns.pop(0)
        with mock.patch.object(threading.Event, "wait", lambda self, timeout=None: None):
            record_flow.liquidation_loop(["BTCUSDT"], got.append, stop, connect=connect)
        self.assertEqual([e["liquidated"] for e in got], ["long"])


class Backfill(SimpleTestCase):
    def test_fetch_range_pages_forward_and_drops_the_forming_bar(self):
        calls = []

        def fetch(symbol, interval, limit, start_ms=None, end_ms=None, session=None):
            calls.append(start_ms // 1000)
            start = start_ms // 1000
            return [{"time": t} for t in range(start, min(start + 3 * 300, 3000), 300)]     # 3 bars per page
        rows = backfill_flow.fetch_range("BTCUSDT", "5m", 0, 3000, None, 0, fetch=fetch, now=2700)
        self.assertEqual(calls, [0, 900, 1800, 2700])
        self.assertEqual([r["time"] for r in rows], list(range(0, 2700, 300)))             # 2700 is still forming

    def test_month_starts_and_atomic_csv(self):
        months = backfill_flow.month_starts(1704067200 + 5, 1709251200 + 5)                  # 2024-01-01 .. 2024-03-01
        self.assertEqual([m[0] for m in months], ["2024-01", "2024-02", "2024-03"])
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "a", "b.csv.gz")
            backfill_flow.write_csv(path, ["time", "oi"], [{"time": 1, "oi": 2.5}])
            self.assertEqual(backfill_flow.read_csv(path), [{"time": "1", "oi": "2.5"}])
            self.assertFalse(os.path.exists(path + ".tmp"))
            with gzip.open(path, "rt") as fh:
                self.assertEqual(fh.readline().strip(), "time,oi")


class FlowEndpoint(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user("flow", password="x")

    def test_auth_validation_and_cache(self):
        self.assertIn(self.client.get("/api/market/flow/?symbol=BTCUSDT").status_code, (401, 403))
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/market/flow/?symbol=XAUUSD").status_code, 400)
        self.assertEqual(self.client.get("/api/market/flow/?symbol=BTCUSDT&timeframe=7m").status_code, 400)
        payload = {"status": "ok", "symbol": "BTCUSDT", "errors": []}
        with mock.patch.object(ff, "snapshot", return_value=payload) as snap:
            self.assertEqual(self.client.get("/api/market/flow/?symbol=BTCUSDT:PERP").json(), payload)
            self.client.get("/api/market/flow/?symbol=BTCUSDT:PERP")
        self.assertEqual(snap.call_count, 1)

    def test_unavailable_snapshot_is_not_cached(self):
        self.client.force_authenticate(self.user)
        with mock.patch.object(ff, "snapshot", return_value={"status": "unavailable", "errors": ["a"]}) as snap:
            self.client.get("/api/market/flow/?symbol=ETHUSDT")
            self.client.get("/api/market/flow/?symbol=ETHUSDT")
        self.assertEqual(snap.call_count, 2)
