import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequestGate } from '../src/lib/requestGate.js';

test('poll cannot supersede a slow manual analysis', () => {
  const gate = createRequestGate();
  const manual = gate.begin();
  for (let i = 0; i < 8; i++) assert.equal(gate.begin(), null);
  assert.equal(gate.current(manual), true);
  gate.finish(manual);
  assert.notEqual(gate.begin(), null);
});

test('changed context rejects old result without releasing the new request', () => {
  const gate = createRequestGate();
  const old = gate.begin();
  gate.invalidate();
  const current = gate.begin();
  assert.equal(gate.current(old), false);
  gate.finish(old);
  assert.equal(gate.current(current), true);
  assert.equal(gate.begin(), null);
});

test('finished request may not publish again', () => {
  const gate = createRequestGate();
  const id = gate.begin();
  gate.finish(id);
  assert.equal(gate.current(id), false);
});