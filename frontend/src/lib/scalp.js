// Lightweight scalp indicators computed from a rolling array of tick prices.
// (newest price is the last element)

export function ema(values, period) {
  if (!values.length) return null;
  const k = 2 / (period + 1);
  let e = values[0];
  for (let i = 1; i < values.length; i++) e = values[i] * k + e * (1 - k);
  return e;
}

export function rsi(values, period = 14) {
  if (values.length < period + 1) return null;
  let gains = 0;
  let losses = 0;
  const start = values.length - period;
  for (let i = start; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    if (d >= 0) gains += d; else losses -= d;
  }
  if (gains + losses === 0) return 50;
  const rs = gains / (losses || 1e-9);
  return 100 - 100 / (1 + rs);
}

// Average absolute tick-to-tick move over the last `period` ticks (ATR proxy).
export function atrProxy(values, period = 14) {
  if (values.length < 2) return null;
  const start = Math.max(1, values.length - period);
  let sum = 0;
  let n = 0;
  for (let i = start; i < values.length; i++) { sum += Math.abs(values[i] - values[i - 1]); n++; }
  return n ? sum / n : null;
}

export function momentum(values, lookback = 10) {
  if (values.length <= lookback) return 0;
  const a = values[values.length - 1 - lookback];
  const b = values[values.length - 1];
  return a ? ((b - a) / a) * 100 : 0;
}

// Full EMA series (for MACD). Returns array same length as input.
function emaSeries(values, period) {
  if (!values.length) return [];
  const k = 2 / (period + 1);
  const out = [values[0]];
  for (let i = 1; i < values.length; i++) out.push(values[i] * k + out[i - 1] * (1 - k));
  return out;
}

// MACD (12/26/9 by default) — returns {macd, signal, hist} on the latest tick.
export function macd(values, fast = 12, slow = 26, signalP = 9) {
  if (values.length < slow + signalP) return null;
  const ef = emaSeries(values, fast);
  const es = emaSeries(values, slow);
  const macdLine = values.map((_, i) => ef[i] - es[i]);
  const signalLine = emaSeries(macdLine, signalP);
  const i = values.length - 1;
  return { macd: macdLine[i], signal: signalLine[i], hist: macdLine[i] - signalLine[i] };
}

// Stochastic oscillator (%K period 9, %D smoothing 3) — scalp-tuned per the doc.
export function stochastic(values, kPeriod = 9, dPeriod = 3) {
  if (values.length < kPeriod + dPeriod) return null;
  const kSeries = [];
  for (let i = kPeriod - 1; i < values.length; i++) {
    const window = values.slice(i - kPeriod + 1, i + 1);
    const hi = Math.max(...window);
    const lo = Math.min(...window);
    kSeries.push(hi === lo ? 50 : ((values[i] - lo) / (hi - lo)) * 100);
  }
  const k = kSeries[kSeries.length - 1];
  const dWindow = kSeries.slice(-dPeriod);
  const d = dWindow.reduce((a, b) => a + b, 0) / dWindow.length;
  return { k, d };
}

// Detect a simple candlestick-style signal from the recent tick path
// (approximation: a sharp reversal off a local extreme = pin-bar-like).
export function priceActionSignal(values) {
  if (values.length < 6) return "none";
  const w = values.slice(-6);
  const lo = Math.min(...w), hi = Math.max(...w);
  const last = w[w.length - 1], prev = w[w.length - 2];
  const range = hi - lo || 1e-9;
  // bullish: dipped near the low then snapped up
  if ((prev - lo) / range < 0.25 && last > prev) return "bullish pin";
  // bearish: spiked near the high then dropped
  if ((hi - prev) / range < 0.25 && last < prev) return "bearish pin";
  return "none";
}

// Build the numeric panel + a composite BUY-side score (0..100).
// A lightweight market-regime classifier (a cheap stand-in for a GMM): looks at
// recent volatility and trend alignment to label the tape.
export function marketRegime(values) {
  if (values.length < 12) return "warming up";
  const rets = [];
  for (let i = values.length - 20; i < values.length; i++) {
    if (i > 0 && values[i - 1]) rets.push((values[i] - values[i - 1]) / values[i - 1]);
  }
  const m = rets.reduce((a, b) => a + b, 0) / (rets.length || 1);
  const vol = Math.sqrt(rets.reduce((a, b) => a + (b - m) ** 2, 0) / (rets.length || 1));
  const e9 = ema(values.slice(-30), 9);
  const e20 = ema(values.slice(-60), 20);
  const price = values[values.length - 1];
  const trending = e9 != null && e20 != null && Math.abs(e9 - e20) / price > 3e-4;

  if (vol > 8e-4) return trending ? (e9 > e20 ? "volatile up" : "volatile down") : "choppy/volatile";
  if (trending) return e9 > e20 ? "trending up" : "trending down";
  return "ranging (low vol)";
}

export function computeScalp(values) {
  const price = values[values.length - 1] ?? null;
  const e9 = ema(values.slice(-30), 9);
  const e20 = ema(values.slice(-60), 20);
  const e50 = ema(values.slice(-150), 50);
  const e200 = values.length >= 60 ? ema(values, 200) : null;
  const r = rsi(values, 14);
  const mom = momentum(values, 10);
  const atr = atrProxy(values, 14);
  const regime = marketRegime(values);
  const mac = macd(values, 12, 26, 9);
  const stoch = stochastic(values, 9, 3);
  const pa = priceActionSignal(values);

  // ---- Multi-layer scoring (Trend → Momentum → Price action) per the playbook ----
  const eps = price ? price * 1e-5 : 0;

  // Layer 1: TREND (EMA stack). +1 bullish / -1 bearish.
  let trend = 0;
  if (e9 != null && e50 != null) trend += e9 > e50 + eps ? 1 : -1;
  if (e50 != null && e200 != null) trend += e50 > e200 + eps ? 1 : -1;
  else if (e9 != null && e20 != null) trend += e9 > e20 + eps ? 1 : -1;
  if (price != null && e9 != null) trend += price > e9 + eps ? 1 : -1;
  const trendDir = trend > 0 ? 1 : trend < 0 ? -1 : 0;

  // Layer 2: MOMENTUM (RSI + MACD + Stochastic) must confirm the trend.
  let bull = 0, bear = 0;
  if (r != null) { if (r > 52) bull++; else if (r < 48) bear++; }
  if (mac) { if (mac.hist > 0) bull++; else if (mac.hist < 0) bear++; }
  if (stoch) { if (stoch.k > stoch.d && stoch.k < 85) bull++; else if (stoch.k < stoch.d && stoch.k > 15) bear++; }
  if (mom > 0.005) bull++; else if (mom < -0.005) bear++;

  // Layer 3: PRICE ACTION filter.
  if (pa === "bullish pin") bull++;
  if (pa === "bearish pin") bear++;

  const momTotal = bull + bear;
  const buyShare = momTotal ? bull / momTotal : 0.5;
  // Composite score blends trend alignment and momentum share.
  let score = Math.round(((trendDir + 1) / 2 * 0.5 + buyShare * 0.5) * 100);
  score = Math.max(0, Math.min(100, score));

  // ATR gate + regime gate: don't fire in dead/ranging tape.
  const tooQuiet = atr == null || (price && atr / price < 1e-4);
  const ranging = regime.includes("ranging") || regime.includes("choppy");

  let signal = "wait";
  if (!tooQuiet && !ranging) {
    // Require trend AND momentum to agree (A+ only).
    if (trendDir > 0 && buyShare >= 0.6 && score >= 66) signal = "buy";
    else if (trendDir < 0 && buyShare <= 0.4 && score <= 34) signal = "sell";
  }

  const f = (v, d = 2) => (v != null && Number.isFinite(v) ? v.toFixed(d) : "—");
  return {
    price, ema9: e9, ema20: e20, ema50: e50, ema200: e200,
    rsi: r, momentum: mom, atr, regime, macd: mac, stoch, priceAction: pa,
    score, signal, trendDir,
    indicators: {
      "EMA 9": f(e9), "EMA 50": f(e50), "EMA 200": f(e200),
      RSI: f(r, 1),
      MACD: mac ? f(mac.hist, 3) : "—",
      "Stoch %K/%D": stoch ? `${f(stoch.k, 0)}/${f(stoch.d, 0)}` : "—",
      "Momentum %": f(mom, 3),
      "ATR (tick)": f(atr, 3),
      "Price action": pa,
      Regime: regime,
      Trend: trendDir > 0 ? "up" : trendDir < 0 ? "down" : "flat",
      "Composite score": `${score}/100`,
    },
  };
}

