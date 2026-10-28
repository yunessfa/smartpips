import test from 'node:test';
import assert from 'node:assert/strict';
import {formatOrderWarning, formatOrderError} from '../src/lib/orderRisk.js';
for (const code of ['demo_trade_risk_cap', 'demo_total_stop_risk_cap']) {
  test(`${code} is readable and advisory in Persian and English`, () => {
    const w = {code, estimated_risk_usdt:35.67, recommended_max_pct:.5};
    assert.match(formatOrderWarning(w, true), /مانع سفارش نیست/);
    assert.match(formatOrderWarning(w), /not an order block/);
    assert.match(formatOrderWarning(w, true), /35.67/);
    assert.ok(!formatOrderWarning(w, true).includes(code));
  });
}
test('hard errors are translated individually, unknown errors preserved', () => {
  const message = formatOrderError('demo_available_margin; demo_daily_loss_cap', true);
  assert.match(message, /موجودی آزاد/); assert.match(message, /زیان روزانه/);
  assert.equal(formatOrderError('Exchange unavailable', true), 'Exchange unavailable');
});
test('old server rejection is not described as successful order', () => {
  assert.match(formatOrderError('demo_trade_risk_cap', true), /به‌روزرسانی بک‌اند لازم/);
});
test('leverage warning remains advisory', () => {
  assert.match(formatOrderWarning({code:'leverage_above_recommended', leverage:75,recommended_max:10},true), /75×/);
});
