import test from "node:test";
import assert from "node:assert/strict";
import { signalExpired } from "../src/lib/signalFreshness.js";

const now = 1_700_000_000_000;

test("market plan expires when price ran past the chase limit", () => {
  const ai = { signal: "buy", order_ticket: { order_type: "market", max_chase_price: 101 } };
  assert.equal(signalExpired(ai, 100.5, now), false);
  assert.equal(signalExpired(ai, 101.2, now), true);
});

test("limit pullback is NOT expired just because price is away from the limit", () => {
  const ai = { signal: "buy", stop_loss: 95, generated_at: now - 60_000,
    order_ticket: { order_type: "limit", limit_price: 98, limit_expiry_minutes: 30 } };
  assert.equal(signalExpired(ai, 103, now), false);
});

test("limit pullback expires by time or when the stop side is reached", () => {
  const base = { signal: "sell", stop_loss: 105, order_ticket: { order_type: "limit", limit_expiry_minutes: 30 } };
  assert.equal(signalExpired({ ...base, generated_at: now - 31 * 60_000 }, 100, now), true);
  assert.equal(signalExpired({ ...base, generated_at: now - 60_000 }, 105.5, now), true);
  assert.equal(signalExpired({ ...base, generated_at: now - 60_000 }, 100, now), false);
});
