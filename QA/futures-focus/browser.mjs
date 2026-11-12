// UI fixture check for the futures-only focus, old levels and the real order-flow panel.
// Synthetic data, NOT live market data. Run the dev server first:
//   cd frontend && npx vite --port 5175 --host 127.0.0.1
//   PLAYWRIGHT=/path/to/playwright/index.mjs node QA/futures-focus/browser.mjs
import fs from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT || 'playwright');
const OUT = process.env.OUT || 'QA/futures-focus/artifacts';
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, headless: true, args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, timezoneId: 'Asia/Tehran', reducedMotion: 'reduce' });
await context.addInitScript(() => {
  localStorage.setItem('smartpips_token', 'local-ui-fixture'); localStorage.setItem('smartpips_user', 'Local test');
  localStorage.setItem('lang', 'fa'); localStorage.setItem('sp_auto', '0'); localStorage.setItem('bx_mode', 'demo');
  localStorage.setItem('sp_balance', '1000'); localStorage.setItem('sp_symbol', 'XAUUSD');   // stale metal choice must fall back
});
const now = Math.floor(Date.now() / 1000);
const candles = Array.from({ length: 180 }, (_, i) => { const close = 74000 + Math.sin(i / 11) * 500 + i * 2; return { time: now - (180 - i) * 900, open: close - 30, close, high: close + 60, low: close - 70, volume: 100 + i }; });
const price = candles.at(-1).close;
const lv = (label, p, kind, major, sources, age) => ({ label, price: p, kind, major, sources, age_days: age, distance_pct: +(((p - price) / price) * 100).toFixed(3), weight: major ? 3 : 1 });
const levels = { status: 'ok', symbol: 'BTCUSDT:PERP', source: 'fixture', price, role: 'context_only', history_days: 1000,
  levels: [lv('PDH', price + 600, 'high', false, ['D'], 0.3), lv('DH', price + 1300, 'high', false, ['D', 'P4'], 2.2), lv('PWH', price + 5200, 'high', true, ['W', 'D', 'PD'], 7.2),
           lv('PDL', price - 550, 'low', false, ['D'], 0.3), lv('WL', price - 4100, 'low', true, ['W', 'D'], 21.4), lv('ML', price - 9000, 'low', true, ['M', 'W', 'D'], 100.2)],
  previous: { PDH: { price: price + 600, taken: false }, PDL: { price: price - 550, taken: false }, PWH: { price: price + 5200, taken: false }, PWL: { price: price + 100, taken: true } } };
const flow = { status: 'partial', symbol: 'BTCUSDT', venue: 'binance_usdm', timeframe: '15m', errors: ['open_interest'], role: 'context_only',
  delta: { bars: 96, cvd: Array.from({ length: 96 }, (_, i) => Math.sin(i / 9) * 300 + i * 4), windows: [
    { bars: 1, volume: 820.5, delta: 95.2, delta_pct: 11.6, price_change_pct: 0.12 }, { bars: 6, volume: 5100, delta: -402.7, delta_pct: -7.9, price_change_pct: -0.31 }, { bars: 24, volume: 21000, delta: 880.1, delta_pct: 4.19, price_change_pct: 0.84 }] },
  funding: { mark: price, index: price - 12, funding_rate: 0.0001, rate_pct: 0.01, basis_bps: 1.62, next_funding_time: now + 5400 },
  book: { mid: price, spread_bps: 0.01, bands: [{ band_pct: 0.1, imbalance: 0.21, complete: true }, { band_pct: 0.25, imbalance: -0.08, complete: true }, { band_pct: 0.5, imbalance: 0.02, complete: true }, { band_pct: 1, imbalance: -0.3, complete: false }] } };
const hits = {}; const errors = [];
await context.route('**/*', async (route) => {
  const u = new URL(route.request().url());
  if (!['127.0.0.1', 'localhost'].includes(u.hostname)) return route.abort();
  if (!u.pathname.startsWith('/api/')) return route.continue();
  const p = u.pathname; hits[p] = (hits[p] || 0) + 1; let data = {};
  if (p.endsWith('/auth/me/')) data = { username: 'Local test', is_admin: false };
  else if (p.endsWith('/market_access/')) data = { metals: false, spot: false, futures: true, futures_only: true };
  else if (p.endsWith('/prefs/risk_limits/')) data = { max_leverage: 20, max_position_usdt: 500, max_open_positions: 5, today_loss: 0 };
  else if (p.endsWith('/assets/quotes/')) data = [];
  else if (p.endsWith('/strategy/levels/')) data = levels;
  else if (p.endsWith('/market/flow/')) data = flow;
  else if (p.endsWith('/market/metal/') || p.endsWith('/ticker/')) data = { ok: true, price };
  else if (p.endsWith('/market/candles/')) data = { candles, source: 'fixture' };
  else if (p.endsWith('/market/calendar/')) data = { status: 'ok', fetched_at: new Date().toISOString(), blackout: { before_min: 30, after_min: 15 },
    events: [{ title: 'CPI m/m', impact: 'high', currency: 'USD', time: new Date(Date.now() - 6 * 60000).toISOString(), minutes_until: -6 }] };
  else if (p.endsWith('/positions/')) data = { positions: [], history: [], marginUsed: 0 };
  else if (p.endsWith('/bitunix/status/')) data = { connected: false, configured: false, diagnostics: {} };
  else if (p.endsWith('/bitunix/account/')) data = { account: { available: 1000 } };
  else if (p.endsWith('/depth/')) data = { book: { bids: [[price - 1, 2]], asks: [[price + 1, 3]] } };
  else if (p.endsWith('/trades/stats/')) data = { open: 0, closed: 0, total_pnl: 0, win_rate: 0 };
  else if (p.endsWith('/trades/profile/')) data = { total_trades: 0 };
  else if (p.endsWith('/trades/journal/')) data = { enough: false, trades: 0, min_trades: 5 };
  else if (p.endsWith('/trades/') || p.endsWith('/watchlist/') || p.endsWith('/notifications/') || p.endsWith('/strategy/strategies/')) data = [];
  else if (p.endsWith('/exit_advice/')) data = { advice: [] };
  else if (p.endsWith('/unread-count/')) data = { unread: 0 };
  else if (p.includes('/strategy/')) data = [];
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
});
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); if (!ok) console.error('FAIL', name, detail); };
for (const width of [1440, 390]) {
  const page = await context.newPage(); page.on('pageerror', (e) => errors.push(`${width}: ${e.message}`));
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1100 });
  await page.goto('http://127.0.0.1:5175/app');
  await page.waitForURL('**/app/scalp');
  check(`${width} /app redirects to scalp`, page.url().endsWith('/app/scalp'));
  await page.goto('http://127.0.0.1:5175/app/chat'); await page.waitForURL('**/app/scalp');
  check(`${width} /app/chat redirects to scalp`, page.url().endsWith('/app/scalp'));
  await page.locator('.sp-terminal').waitFor();
  if (width === 390) await page.getByRole('button', { name: 'Menu', exact: true }).click();
  const nav = (await page.locator('nav a').allInnerTexts()).join(' | ');
  check(`${width} nav has no dashboard / assistant`, !/داشبورد|دستیار/.test(nav), nav);
  check(`${width} nav keeps scalp + journal`, /اسکالپ|Scalp/i.test(nav) && nav.length > 20, nav);
  if (width === 390) await page.mouse.click(20, 400);   // backdrop (the drawer opens on the right in RTL)
  await page.getByRole('button', { name: /BTC futures/ }).first().waitFor();   // page chunk loaded
  const body = await page.locator('body').innerText();
  check(`${width} stale metal symbol fell back to a perp`, /BTC futures/.test(body) && !/XAU/.test(body));
  // symbol picker: futures only, no group tabs
  await page.getByRole('button', { name: /BTC futures/ }).first().click();
  const picker = await page.locator('input[placeholder]').first().locator('xpath=ancestor::div[contains(@class,"absolute")]').innerText();
  check(`${width} picker has no spot / metals`, !/اسپات|فلزات|XAU|spot/i.test(picker), picker.slice(0, 80));
  await page.keyboard.press('Escape'); await page.mouse.click(5, 5);
  // old levels on the chart
  const toggle = page.getByRole('button', { name: /سطوح قدیمی/ }).first(); await toggle.waitFor();
  check(`${width} old-level toggle is on and counts 6`, (await toggle.getAttribute('aria-pressed')) === 'true' && /6/.test(await toggle.innerText()), await toggle.innerText());
  await toggle.scrollIntoViewIfNeeded(); await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/chart-${width}.png` });
  await toggle.click();
  check(`${width} toggle switches off`, (await toggle.getAttribute('aria-pressed')) === 'false');
  await toggle.click();
  // market context panels
  await page.getByText('📚', { exact: false }).first().click();
  const flowPanel = page.locator('section', { hasText: 'جریان سفارش واقعی' }).last(); await flowPanel.waitFor();
  const ft = await flowPanel.innerText();
  check(`${width} flow panel shows delta, funding, book and the partial-data note`, /11\.6%/.test(ft) && /0\.0100%/.test(ft) && /±0\.1%/.test(ft) && /open_interest/.test(ft), ft.slice(0, 120));
  const lvPanel = page.locator('section', { hasText: 'سطوح قدیمی دست‌نخورده' }).last(); await lvPanel.waitFor();
  const lt = await lvPanel.innerText();
  check(`${width} levels panel lists PWH / ML, the taken PWL and the evidence note`, /PWH/.test(lt) && /ML/.test(lt) && /زده‌شده/.test(lt) && /سودده نبود/.test(lt));
  const news = await page.locator('section', { hasText: 'رویداد اقتصادی بعدی' }).last().innerText();
  check(`${width} news panel shows the post-release cooldown`, /دقیقه از انتشار گذشته/.test(news) && /دقیقه بعد از انتشار/.test(news), news.slice(0, 100));
  await flowPanel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${OUT}/context-${width}.png`, fullPage: width === 390 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check(`${width} no horizontal overflow`, overflow <= 1, String(overflow));
  await page.close();
}
check('no page JavaScript errors', errors.length === 0, errors.join('; '));
check('levels and flow endpoints were called', hits['/api/strategy/levels/'] > 0 && hits['/api/market/flow/'] > 0);
fs.writeFileSync('QA/futures-focus/results.json', JSON.stringify({ note: 'Synthetic fixtures; not live market data.', passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length, results }, null, 1));
console.log(`${results.filter((r) => r.ok).length} passed, ${results.filter((r) => !r.ok).length} failed`);
await browser.close();
process.exit(results.some((r) => !r.ok) ? 1 : 0);
