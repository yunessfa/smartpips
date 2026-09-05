import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import { useOnScreen } from "../motion.jsx";

/**
 * The hero's living market visualization.
 *
 * Everything is drawn on a single 2D canvas: a candle series in gentle
 * perspective, liquidity shelves, entry/TP/SL levels, AI signal nodes that
 * fire as price reaches them, and data particles streaming along the series.
 *
 * Why canvas rather than Three.js: every element here is a 2D object given
 * depth through scale and opacity. A WebGL scene would add ~600KB to the
 * critical path to draw the same picture. The depth cue that actually sells
 * it is the parallax between layers, which costs nothing.
 *
 * Performance guarantees:
 *  - the rAF loop is fully stopped when the canvas is off screen
 *  - device pixel ratio is capped at 2 (retina is enough; 3x is wasted fill)
 *  - particle and candle counts scale down on narrow viewports
 *  - honours prefers-reduced-motion by painting one static frame
 */

const GOLD = "240,185,11";
const UP = "14,203,129";
const DOWN = "246,70,90";

/** Deterministic pseudo-random so the composition is art-directed, not luck. */
function mulberry32(seed) {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Builds a random-walk candle series with a mild upward drift. */
function buildSeries(count, seed) {
  const rnd = mulberry32(seed);
  const out = [];
  let price = 100;
  for (let i = 0; i < count; i += 1) {
    const drift = 0.16;
    const vol = 1.5 + rnd() * 1.6;
    const open = price;
    const close = open + (rnd() - 0.5) * vol * 2 + drift;
    const high = Math.max(open, close) + rnd() * vol * 0.8;
    const low = Math.min(open, close) - rnd() * vol * 0.8;
    out.push({ open, close, high, low });
    price = close;
  }
  return out;
}

export function HeroVisual({ className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: gateRef, visible } = useOnScreen("200px");
  const pointer = useRef({ x: 0, y: 0, tx: 0, ty: 0 });

  // Track the pointer for the parallax tilt. Stored in a ref so pointer
  // movement never re-renders React.
  useEffect(() => {
    const el = gateRef.current;
    if (!el || reduced) return undefined;
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;
    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      pointer.current.tx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
      pointer.current.ty = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
    };
    const onLeave = () => { pointer.current.tx = 0; pointer.current.ty = 0; };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [gateRef, reduced]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    let w = 0;
    let h = 0;
    let dpr = 1;
    let raf = 0;
    let t = 0;

    const isNarrow = () => w < 620;
    let series = [];
    let particles = [];
    let nodes = [];

    function seed() {
      const candleCount = isNarrow() ? 34 : 56;
      series = buildSeries(candleCount, 20260808);

      const particleCount = isNarrow() ? 26 : 54;
      const rnd = mulberry32(7);
      particles = Array.from({ length: particleCount }, () => ({
        p: rnd(),                       // progress 0..1 along the stream
        lane: Math.floor(rnd() * 3),    // which depth lane
        speed: 0.00045 + rnd() * 0.0011,
        size: 0.7 + rnd() * 1.5,
      }));

      // AI signal nodes anchored to specific candles in the series.
      nodes = [
        { i: 0.28, label: "MSS", tone: GOLD },
        { i: 0.52, label: "LIQ", tone: GOLD },
        { i: 0.74, label: "AI", tone: UP },
      ];
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    // ---- geometry -------------------------------------------------------
    // The chart sits in a padded box; a slight vertical squash plus a
    // horizontal shear give it the sense of lying back in space.
    function box() {
      const padX = isNarrow() ? 18 : 40;
      const padTop = isNarrow() ? 60 : 84;
      const padBottom = isNarrow() ? 54 : 74;
      return { x: padX, y: padTop, w: w - padX * 2, h: h - padTop - padBottom };
    }

    function priceRange() {
      let lo = Infinity;
      let hi = -Infinity;
      for (const c of series) { if (c.low < lo) lo = c.low; if (c.high > hi) hi = c.high; }
      const pad = (hi - lo) * 0.12;
      return { lo: lo - pad, hi: hi + pad };
    }

    function draw() {
      const b = box();
      const { lo, hi } = priceRange();
      const span = hi - lo || 1;

      // Ease the pointer toward its target for a weighty, non-jittery follow.
      const p = pointer.current;
      p.x += (p.tx - p.x) * 0.06;
      p.y += (p.ty - p.y) * 0.06;
      const shearX = p.x * (isNarrow() ? 0 : 14);
      const shiftY = p.y * (isNarrow() ? 0 : 10);

      const yOf = (price) => b.y + b.h - ((price - lo) / span) * b.h + shiftY;
      const xOf = (i) => b.x + (i / (series.length - 1)) * b.w + shearX * ((i / series.length) - 0.5) * 2;

      ctx.clearRect(0, 0, w, h);

      // ---- liquidity shelves: horizontal bands where orders rest --------
      const shelves = [
        { price: lo + span * 0.78, strength: 0.85 },
        { price: lo + span * 0.34, strength: 0.6 },
      ];
      for (const s of shelves) {
        const y = yOf(s.price);
        const bandH = 12;
        const pulse = 0.5 + 0.5 * Math.sin(t * 0.0012 + s.price);
        const g = ctx.createLinearGradient(b.x, y, b.x + b.w, y);
        g.addColorStop(0, `rgba(${GOLD},0)`);
        g.addColorStop(0.5, `rgba(${GOLD},${0.07 * s.strength * (0.7 + pulse * 0.3)})`);
        g.addColorStop(1, `rgba(${GOLD},0)`);
        ctx.fillStyle = g;
        ctx.fillRect(b.x, y - bandH / 2, b.w, bandH);

        ctx.strokeStyle = `rgba(${GOLD},${0.16 * s.strength})`;
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 6]);
        ctx.beginPath();
        ctx.moveTo(b.x, y);
        ctx.lineTo(b.x + b.w, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // ---- candles ------------------------------------------------------
      const step = b.w / series.length;
      const cw = Math.max(2, step * 0.52);
      for (let i = 0; i < series.length; i += 1) {
        const c = series[i];
        const x = xOf(i);
        // Depth: older candles (left) sit further back — smaller and dimmer.
        const depth = 0.42 + (i / series.length) * 0.58;
        const bull = c.close >= c.open;
        const tone = bull ? UP : DOWN;

        // A slow travelling highlight reads as "the engine is scanning".
        const scan = (t * 0.00016) % 1.4 - 0.2;
        const dist = Math.abs(i / series.length - scan);
        const lit = Math.max(0, 1 - dist * 7);

        const alpha = 0.2 + depth * 0.5 + lit * 0.4;
        const yO = yOf(c.open);
        const yC = yOf(c.close);
        const yH = yOf(c.high);
        const yL = yOf(c.low);

        ctx.strokeStyle = `rgba(${tone},${alpha * 0.65})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, yH);
        ctx.lineTo(x, yL);
        ctx.stroke();

        const bodyH = Math.max(1.5, Math.abs(yC - yO));
        const bw = cw * (0.7 + depth * 0.3);
        ctx.fillStyle = `rgba(${tone},${alpha})`;
        ctx.fillRect(x - bw / 2, Math.min(yO, yC), bw, bodyH);

        if (lit > 0.05) {
          ctx.shadowBlur = 14 * lit;
          ctx.shadowColor = `rgba(${tone},${0.5 * lit})`;
          ctx.fillRect(x - bw / 2, Math.min(yO, yC), bw, bodyH);
          ctx.shadowBlur = 0;
        }
      }

      // ---- entry / TP / SL levels ---------------------------------------
      const entryI = Math.floor(series.length * 0.58);
      const entry = series[entryI].close;
      const tp = entry + span * 0.2;
      const sl = entry - span * 0.1;

      const levels = [
        { price: tp, tone: UP, label: "TP", dash: [5, 4] },
        { price: entry, tone: GOLD, label: "ENTRY", dash: [] },
        { price: sl, tone: DOWN, label: "SL", dash: [5, 4] },
      ];

      ctx.font = "600 9px ui-monospace, 'JetBrains Mono', monospace";
      ctx.textBaseline = "middle";

      for (const lv of levels) {
        const y = yOf(lv.price);
        const x0 = xOf(entryI);

        ctx.strokeStyle = `rgba(${lv.tone},0.5)`;
        ctx.lineWidth = lv.label === "ENTRY" ? 1.4 : 1;
        ctx.setLineDash(lv.dash);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(b.x + b.w, y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Axis tag on the right edge.
        const tw = ctx.measureText(lv.label).width + 10;
        const tagX = b.x + b.w - tw;
        ctx.fillStyle = `rgba(${lv.tone},0.16)`;
        ctx.beginPath();
        ctx.roundRect(tagX, y - 7, tw, 14, 3);
        ctx.fill();
        ctx.fillStyle = `rgba(${lv.tone},0.95)`;
        ctx.fillText(lv.label, tagX + 5, y + 0.5);
      }

      // Shaded profit zone between entry and target — the payoff, made visible.
      const yEntry = yOf(entry);
      const yTp = yOf(tp);
      const zg = ctx.createLinearGradient(0, yTp, 0, yEntry);
      zg.addColorStop(0, `rgba(${UP},0.14)`);
      zg.addColorStop(1, `rgba(${UP},0)`);
      ctx.fillStyle = zg;
      ctx.fillRect(xOf(entryI), yTp, b.x + b.w - xOf(entryI), yEntry - yTp);

      // ---- data particles streaming along the series --------------------
      for (const pt of particles) {
        pt.p += pt.speed;
        if (pt.p > 1) pt.p -= 1;
        const idx = pt.p * (series.length - 1);
        const i0 = Math.floor(idx);
        const i1 = Math.min(series.length - 1, i0 + 1);
        const frac = idx - i0;
        const price = series[i0].close + (series[i1].close - series[i0].close) * frac;
        const laneOffset = (pt.lane - 1) * 14;
        const x = xOf(idx);
        const y = yOf(price) + laneOffset;
        const fade = Math.sin(pt.p * Math.PI);

        ctx.fillStyle = `rgba(${GOLD},${0.5 * fade})`;
        ctx.beginPath();
        ctx.arc(x, y, pt.size, 0, Math.PI * 2);
        ctx.fill();

        // Short motion trail sells the sense of flow.
        ctx.strokeStyle = `rgba(${GOLD},${0.16 * fade})`;
        ctx.lineWidth = pt.size * 0.7;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - 11, y);
        ctx.stroke();
      }

      // ---- AI signal nodes ----------------------------------------------
      for (const n of nodes) {
        const idx = n.i * (series.length - 1);
        const c = series[Math.round(idx)];
        const x = xOf(idx);
        const y = yOf(c.high) - 16;

        // Expanding ring, restarting on a loop.
        const phase = ((t * 0.0006) + n.i) % 1;
        const r = 4 + phase * 22;
        ctx.strokeStyle = `rgba(${n.tone},${(1 - phase) * 0.5})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = `rgba(${n.tone},0.9)`;
        ctx.beginPath();
        ctx.arc(x, y, 2.6, 0, Math.PI * 2);
        ctx.fill();

        // Leader line down to the candle it refers to.
        ctx.strokeStyle = `rgba(${n.tone},0.22)`;
        ctx.beginPath();
        ctx.moveTo(x, y + 4);
        ctx.lineTo(x, yOf(c.high) - 2);
        ctx.stroke();

        ctx.fillStyle = `rgba(${n.tone},0.85)`;
        ctx.font = "600 8.5px ui-monospace, 'JetBrains Mono', monospace";
        ctx.textAlign = "center";
        ctx.fillText(n.label, x, y - 12);
        ctx.textAlign = "start";
      }
    }

    function frame(now) {
      t = now;
      draw();
      raf = requestAnimationFrame(frame);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    if (reduced) {
      draw();                                   // one static, complete frame
    } else if (visible) {
      raf = requestAnimationFrame(frame);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [visible, reduced]);

  return (
    <div ref={gateRef} className={`relative ${className}`}>
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        role="img"
        aria-label="Live market analysis visualization"
      />
    </div>
  );
}

export default HeroVisual;
