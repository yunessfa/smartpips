"""Regression tests for the 2026-10 scalp-geometry / signal-integrity fixes."""
import math
import time

from django.test import SimpleTestCase

from .engine import _validate_setup, run_strategy
from .orderflow import fvg_quality
from .scalp_plan import TF_PARAMS, build_plan
from . import backtest as bt


def bar(t, o, h, l, c, v=1.0):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


def trend_bars(n=200, start=100.0, step=0.05, wiggle=0.15, t0=1_700_000_000, tf=300):
    """Gently rising market with small pullbacks (real-looking pivots)."""
    rows, p = [], start
    for i in range(n):
        drift = step if (i % 7) not in (5, 6) else -step * 1.5
        o = p
        c = p + drift
        h = max(o, c) + wiggle * 0.5
        l = min(o, c) - wiggle * 0.5
        rows.append(bar(t0 + i * tf, o, h, l, c))
        p = c
    return rows


class FVGLifecycleTests(SimpleTestCase):
    def test_fully_traversed_gap_is_not_reported(self):
        rows = [bar(i, *v) for i, v in enumerate(
            [(100, 101, 99, 100), (99, 100, 98, 99), (102, 103, 99, 102), (103, 104, 102, 103), (103, 104, 99, 103)])]
        # gap 100..102 formed at index 3 (low 102 > high[1] 100) then low 99 traded through it
        self.assertIsNone(fvg_quality(rows))

    def test_partial_fill_measured_from_path_not_close(self):
        rows = [bar(i, *v) for i, v in enumerate(
            [(100, 101, 99, 100), (99, 100, 98, 99), (102, 103, 99, 102), (103, 104, 102, 103), (104, 105, 101, 104.5)])]
        q = fvg_quality(rows)
        self.assertEqual(q["direction"], "bullish")
        self.assertEqual(q["fill_pct"], 50.0)   # low 101 reached half of the 100..102 gap

    def test_filled_or_stale_gap_does_not_count_as_zone(self):
        tf = dict(flow={"bias": 1}, sweep={"bias": 1}, smc={"bos": "bullish"},
                  fvg_q={"direction": "bullish", "fill_pct": 100, "age": 100})
        q = _validate_setup("buy", tf, 1, {"name": "London"}, "safe")
        self.assertFalse(q["checks"]["order_block_fvg"])


class FourHourPolicyTests(SimpleTestCase):
    def test_4h_safe_uses_local_trend_when_no_htf_exists(self):
        tf = dict(flow={"bias": 1}, sweep={"bias": 1}, smc={"bos": "bullish"}, ema50=110, ema200=100,
                  fvg_q={"direction": "bullish", "fill_pct": 10, "age": 2})
        q = _validate_setup("buy", tf, 0, {"name": "London"}, "safe", htf_missing=True)
        self.assertTrue(q["checks"]["trend_aligned"])
        self.assertTrue(q["pass"])
        # but a missing HTF never upgrades a counter-trend trade
        tf_down = dict(tf, ema50=90)
        self.assertFalse(_validate_setup("buy", tf_down, 0, {"name": "London"}, "safe", htf_missing=True)["pass"])


class ScalpPlanTests(SimpleTestCase):
    def setUp(self):
        self.rows = trend_bars()
        self.price = self.rows[-1]["close"]
        self.atr = 0.2

    def test_stop_is_timeframe_sized_not_fixed_point_eight_percent(self):
        plans = [build_plan("buy", "BTCUSDT", "5m", self.rows, self.price, a) for a in (0.2, 0.3, 0.4)]
        plans = [p for p in plans if "reject" not in p]
        self.assertTrue(plans, "no executable plan for a clean uptrend")
        plan = plans[0]
        stop_pct = abs(plan["entry"] - plan["stop"]) / plan["entry"] * 100
        self.assertGreaterEqual(stop_pct, TF_PARAMS["5m"]["crypto_floor"] - 1e-9)
        self.assertLess(stop_pct, 0.8)
        # main target is a scalp target (<= 2R), not 3R/4.8R
        self.assertLessEqual(plan["tp_r"][1], 2.0)
        self.assertLessEqual(plan["tp_r"][2], 2.5)
        self.assertGreaterEqual(plan["net_rr"], 1.0)

    def test_targets_are_ordered_and_on_correct_side(self):
        for direction in ("buy", "sell"):
            plan = build_plan(direction, "BTCUSDT", "5m", self.rows, self.price, self.atr)
            if "reject" in plan:
                continue
            want = 1 if direction == "buy" else -1
            prices = plan["tp_prices"]
            self.assertTrue(all((p - plan["entry"]) * want > 0 for p in prices))
            self.assertTrue(all((b - a) * want > 0 for a, b in zip(prices, prices[1:])))
            self.assertTrue((plan["entry"] - plan["stop"]) * want > 0)

    def test_stretched_move_becomes_pullback_limit_not_market_chase(self):
        rows = trend_bars()
        last = rows[-1]["close"]
        # violent impulse: +6 ATR in the last bars
        for k in range(6):
            o = last
            last = last + 0.25
            rows.append(bar(rows[-1]["time"] + 300, o, last + 0.02, o - 0.02, last))
        plan = build_plan("buy", "BTCUSDT", "5m", rows, last, self.atr)
        if "reject" in plan:
            self.assertIn(plan["reject"][0], ("chasing", "stop_too_wide"))
            return
        self.assertEqual(plan["entry_plan"]["type"], "limit")
        self.assertLess(plan["entry"], last)
        self.assertGreater(plan["entry_plan"]["expiry_bars"], 0)

    def test_fee_gate_rejects_targets_eaten_by_costs(self):
        # tiny ATR on 1m: floor dominates; target still clears fees -> plan exists
        plan = build_plan("buy", "BTCUSDT", "1m", self.rows, self.price, 0.001)
        if "reject" not in plan:
            self.assertGreaterEqual(plan["net_rr"], 1.0)
            self.assertGreater(plan["est_round_trip_cost_pct"], 0)

    def test_stop_cap_rejects_instead_of_widening(self):
        rows = trend_bars()
        # a deep old swing low makes the only structural stop very far away
        rows[-30]["low"] = rows[-1]["close"] * 0.9
        rows[-30]["high"] = max(rows[-30]["high"], rows[-30]["low"])
        plan = build_plan("buy", "BTCUSDT", "5m", rows[-80:], rows[-1]["close"], self.atr)
        if "reject" in plan:
            return
        stop_dist = plan["entry"] - plan["stop"]
        cap = max(TF_PARAMS["5m"]["max_atr"] * self.atr,
                  plan["entry"] * TF_PARAMS["5m"]["crypto_floor"] / 100 * 1.25)
        self.assertLessEqual(stop_dist, cap + 1e-9)


class EngineIntegrationTests(SimpleTestCase):
    def test_run_strategy_exposes_plan_fields_and_never_returns_3r_targets(self):
        rows = trend_bars(300)
        htf = {"15m": trend_bars(200, tf=900), "1h": trend_bars(200, tf=3600)}
        d = run_strategy("BTCUSDT", "5m", rows, htf, live_price=rows[-1]["close"], mode="aggressive")
        self.assertIn("entry_plan", d)
        if d["signal"] in ("buy", "sell"):
            self.assertLessEqual(d["risk_reward"], 2.0)
            self.assertIsNotNone(d["entry_plan"])
            self.assertEqual(len(d["tp_levels"]), 3)
        else:
            self.assertTrue(d["wait_reasons"])


class BacktestLimitEntryTests(SimpleTestCase):
    def test_limit_plan_fills_only_on_touch_and_market_never_chases(self):
        rows = trend_bars(120)
        calls = {"n": 0}

        def fake_decide(symbol, candles_so_far, **kw):
            calls["n"] += 1
            if calls["n"] != 1:
                return None
            px = candles_so_far[-1]["close"]
            return {"direction": "buy", "entry": px - 10.0, "stop": px - 11.0, "target": px - 8.0,
                    "entry_type": "limit", "expiry_bars": 3}

        orig = bt._decide_at
        bt._decide_at = fake_decide
        try:
            res = bt.backtest("BTCUSDT", rows, timeframe="5m")
        finally:
            bt._decide_at = orig
        # the limit 10 points below price is never touched in a rising market
        self.assertEqual(res["trades"], 0)
        self.assertEqual(res["diagnostics"].get("limit_not_filled"), 1)


class PriceProvenanceTests(SimpleTestCase):
    def test_live_price_far_from_candle_feed_is_refused(self):
        from unittest.mock import patch
        from .decision import decide
        now = int(time.time())
        step = 300
        rows = trend_bars(300, t0=(now // step) * step - 300 * step, tf=step)
        with patch("apps.market.candles.fetch_candles", return_value=rows):
            d = decide("BTCUSDT", "5m", live_price=rows[-1]["close"] * 1.5)
        self.assertEqual(d["signal"], "wait")
        self.assertEqual(d["data_quality"], "price_mismatch")


class MetalPlanTests(SimpleTestCase):
    def test_gold_5m_plan_is_executable_and_scalp_sized(self):
        rows = trend_bars(200, start=4150.0, step=1.2, wiggle=3.0)
        price = rows[-1]["close"]
        plans = [build_plan(d, "XAUUSD", "5m", rows, price, a) for d in ("buy",) for a in (4.0, 5.0, 6.0)]
        ok = [p for p in plans if "reject" not in p]
        self.assertTrue(ok, plans)
        for p in ok:
            self.assertLess(p["stop_pct"], 0.35)      # old fixed gold floor was 0.35% (~$14)
            self.assertLessEqual(p["tp_r"][1], 2.0)
