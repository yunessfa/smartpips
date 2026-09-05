/**
 * Shared market-series engine for the public site.
 *
 * Why this file exists: the previous build drew a different, ad-hoc chart in
 * every section. Nothing lined up, and the site read as a collection of
 * decorations rather than one product. Every chart on the landing page now
 * derives from this module, so the candles in the hero, the intelligence
 * layers, the scalp replay and the regime simulator are recognisably the
 * same instrument rendered with different analysis on top.
 *
 * Everything here is deterministic (seeded PRNG). A landing page that draws
 * different candles on every reload feels fake; a fixed series feels like a
 * screenshot of something real.
 */

/* ------------------------------------------------------------ palette --- */

export const C = {
  gold: "240,184,11",
  goldBright: "245,184,0",
  goldSoft: "255,212,90",
  pos: "0,200,150",
  neg: "240,68,92",
  grid: "255,255,255",
  text: "156,163,175",
  textBright: "243,244,246",
};

export const rgba = (triplet, a) => `rgba(${triplet},${a})`;

/* --------------------------------------------------------------- rng ---- */

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------------------------------------- series --- */

/**
 * Builds a candle series with a deliberate narrative shape rather than a pure
 * random walk. A random walk almost never produces the thing a trader is
 * looking for (a sweep, then a break, then a retest), so the hero would show
 * markers pointing at nothing in particular. The `regime` argument selects
 * the behaviour, which is what makes the regime simulator in section 7
 * meaningful instead of four re-skins of the same noise.
 *
 * @param {object}  opts
 * @param {number}  opts.count    number of candles
 * @param {number}  opts.seed     PRNG seed
 * @param {string}  opts.regime   "story" | "trend" | "range" | "highvol" | "lowvol"
 * @param {number}  opts.base     starting price
 * @returns {{candles: Array, min: number, max: number, sweepIndex: number,
 *            mssIndex: number, entryIndex: number}}
 */
export function buildSeries({
  count = 64,
  seed = 20260808,
  regime = "story",
  base = 64200,
} = {}) {
  const rnd = mulberry32(seed);
  const candles = [];

  // Narrative anchors, expressed as fractions so they scale with `count`.
  const sweepIndex = Math.round(count * 0.34);
  const mssIndex = Math.round(count * 0.5);
  const entryIndex = Math.round(count * 0.66);

  let price = base;
  let vol = regime === "highvol" ? 190 : regime === "lowvol" ? 34 : 90;

  for (let i = 0; i < count; i++) {
    const t = i / (count - 1);
    let drift = 0;

    if (regime === "story") {
      // Down into the sweep, sharp reclaim through the MSS, then a measured
      // expansion. This is the shape the hero markers annotate.
      if (i < sweepIndex) drift = -24;
      else if (i < sweepIndex + 3) drift = -70;
      else if (i < mssIndex) drift = 46;
      else if (i < entryIndex) drift = -14;
      else drift = 40;
    } else if (regime === "trend") {
      drift = 34 + Math.sin(t * 5) * 10;
    } else if (regime === "range") {
      // Mean-revert toward the base rather than drifting anywhere.
      drift = (base - price) * 0.22;
      vol = 62;
    } else if (regime === "highvol") {
      drift = Math.sin(t * 9) * 60;
    } else if (regime === "lowvol") {
      drift = Math.sin(t * 3) * 8;
    }

    const open = price;
    const noise = (rnd() - 0.5) * vol * 2;
    const close = open + drift + noise;
    const wick = vol * (0.35 + rnd() * 0.65);

    // The sweep candle gets an exaggerated lower wick: that long tail *is*
    // the liquidity grab the section copy refers to.
    const isSweep = regime === "story" && i >= sweepIndex && i < sweepIndex + 2;
    const low = Math.min(open, close) - (isSweep ? wick * 2.6 : wick);
    const high = Math.max(open, close) + wick * 0.8;

    candles.push({
      i,
      open,
      close,
      high,
      low,
      up: close >= open,
      // Volume spikes on the sweep and the break — order flow should agree
      // with the story the price is telling.
      volume:
        0.35 +
        rnd() * 0.3 +
        (isSweep || (regime === "story" && Math.abs(i - mssIndex) < 2) ? 0.55 : 0),
    });
    price = close;
  }

  const lows = candles.map((c) => c.low);
  const highs = candles.map((c) => c.high);
  const min = Math.min(...lows);
  const max = Math.max(...highs);

  return { candles, min, max, sweepIndex, mssIndex, entryIndex };
}

/**
 * Trade levels derived from the series, so the entry line and the TP/SL zones
 * sit on real prices instead of arbitrary pixel offsets.
 */
export function buildLevels(series) {
  const { candles, sweepIndex, entryIndex } = series;
  const entry = candles[entryIndex].close;
  const sl = candles[sweepIndex].low - (entry - candles[sweepIndex].low) * 0.05;
  const risk = entry - sl;
  return {
    entry,
    sl,
    tp: entry + risk * 2.4, // matches the advertised R:R 1:2.4
    risk,
    structure: Math.max(...candles.slice(0, series.mssIndex).map((c) => c.high)),
    liquidityLow: Math.min(...candles.slice(sweepIndex - 4, sweepIndex + 2).map((c) => c.low)),
  };
}

/* ------------------------------------------------------------ canvas ---- */

/** Sizes a canvas to its container in CSS pixels, capping DPR at 2. */
export function fitCanvas(canvas) {
  const parent = canvas.parentElement;
  if (!parent) return null;
  const rect = parent.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: rect.width, h: rect.height };
}

/** Eased 0..1 progress for a timeline window. */
export function phase(elapsed, start, duration) {
  const p = Math.max(0, Math.min((elapsed - start) / duration, 1));
  return 1 - Math.pow(1 - p, 3); // easeOutCubic
}

/** Rounded rect that degrades gracefully where roundRect is unavailable. */
export function roundRect(ctx, x, y, w, h, r) {
  if (ctx.roundRect) {
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
    return;
  }
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * Draws a small label chip. These are drawn *on the canvas*, anchored to the
 * price they describe, which is the difference between an annotation and a
 * floating sticker.
 */
export function drawTag(ctx, x, y, text, colour, { align = "left", mono = true } = {}) {
  ctx.font = `600 10px ${mono ? "'JetBrains Mono', ui-monospace, monospace" : "Inter, sans-serif"}`;
  const padX = 6;
  const w = ctx.measureText(text).width + padX * 2;
  const h = 17;
  const left = align === "right" ? x - w : x;
  const top = y - h / 2;

  roundRect(ctx, left, top, w, h, 4);
  ctx.fillStyle = "rgba(8,10,13,0.92)";
  ctx.fill();
  ctx.strokeStyle = rgba(colour, 0.45);
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = rgba(colour, 1);
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(text, left + padX, top + h / 2 + 0.5);
}

/** Horizontal dashed level line. */
export function drawLevel(ctx, x1, x2, y, colour, { dash = [4, 4], width = 1, alpha = 0.7 } = {}) {
  ctx.save();
  ctx.setLineDash(dash);
  ctx.strokeStyle = rgba(colour, alpha);
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(x1, y);
  ctx.lineTo(x2, y);
  ctx.stroke();
  ctx.restore();
}

/** Background grid. Kept very low contrast so it reads as depth, not texture. */
export function drawGrid(ctx, x, y, w, h, alpha = 1) {
  ctx.save();
  ctx.strokeStyle = rgba(C.grid, 0.035 * alpha);
  ctx.lineWidth = 1;
  const cols = 8;
  const rows = 5;
  for (let i = 1; i < cols; i++) {
    const gx = x + (w / cols) * i;
    ctx.beginPath();
    ctx.moveTo(gx, y);
    ctx.lineTo(gx, y + h);
    ctx.stroke();
  }
  for (let i = 1; i < rows; i++) {
    const gy = y + (h / rows) * i;
    ctx.beginPath();
    ctx.moveTo(x, gy);
    ctx.lineTo(x + w, gy);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * Draws the candle body + wick. `reveal` (0..1) scales the candle up from its
 * open price, which is what makes the hero candles "grow" into place instead
 * of merely fading in.
 */
export function drawCandle(ctx, c, x, bw, toY, reveal = 1, alpha = 1) {
  const colour = c.up ? C.pos : C.neg;
  const oY = toY(c.open);
  const hY = oY + (toY(c.high) - oY) * reveal;
  const lY = oY + (toY(c.low) - oY) * reveal;
  const cY = oY + (toY(c.close) - oY) * reveal;

  ctx.strokeStyle = rgba(colour, 0.75 * alpha);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x + bw / 2, hY);
  ctx.lineTo(x + bw / 2, lY);
  ctx.stroke();

  const top = Math.min(oY, cY);
  const height = Math.max(Math.abs(cY - oY), 1);
  ctx.fillStyle = rgba(colour, 0.9 * alpha);
  ctx.fillRect(x, top, bw, height);
}
