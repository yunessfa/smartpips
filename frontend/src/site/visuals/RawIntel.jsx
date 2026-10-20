import { useEffect, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  C,
  buildLevels,
  buildSeries,
  drawCandle,
  drawGrid,
  drawLevel,
  drawTag,
  fitCanvas,
  mulberry32,
  phase,
  rgba,
} from "./series.js";
import { useOnScreen } from "../motion.jsx";

/**
 * Section 2: "Raw Market Data → SmartPips Intelligence".
 *
 * The persuasive weight of this section rests on one thing: both panels must
 * plausibly be *the same market*. So the right-hand panel renders the exact
 * series from `series.js`, and the left-hand panel renders that same series
 * buried under an order of magnitude more noise. The viewer should be able to
 * squint at the left panel and just barely make out the shape they can read
 * effortlessly on the right. That is the argument, made visually.
 */

const SERIES = buildSeries({ count: 66, seed: 20260808, regime: "story" });
const LEVELS = buildLevels(SERIES);

/* ------------------------------------------------------------- noise ---- */

export function NoiseCanvas({ className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: hostRef, visible } = useOnScreen("160px");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let raf = 0;
    let stopped = false;

    const draw = (t) => {
      const fitted = fitCanvas(canvas);
      if (!fitted) return;
      const { ctx, w, h } = fitted;
      ctx.clearRect(0, 0, w, h);

      const rnd = mulberry32(4711);
      const span = (SERIES.max - SERIES.min) * 1.35;
      const mid = (SERIES.max + SERIES.min) / 2;
      const toY = (p) => ((mid + span / 2 - p) / span) * h;

      // 1) The real series, drawn faintly — the signal that is *present* but
      //    unreadable. This is what the right panel will recover.
      SERIES.candles.forEach((c, i) => {
        const x = (i / SERIES.candles.length) * w;
        ctx.strokeStyle = rgba(C.text, 0.1);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, toY(c.high));
        ctx.lineTo(x, toY(c.low));
        ctx.stroke();
      });

      // 2) Dense unstructured ticks at every scale.
      const ticks = w < 420 ? 220 : 420;
      for (let i = 0; i < ticks; i++) {
        const x = rnd() * w;
        const y = rnd() * h;
        const len = 2 + rnd() * 16;
        ctx.strokeStyle = rgba(C.text, 0.06 + rnd() * 0.16);
        ctx.lineWidth = rnd() > 0.85 ? 1.4 : 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x, y + len);
        ctx.stroke();
      }

      // 3) Volatility spikes and market events — the things that grab your
      //    attention and usually mean nothing.
      for (let i = 0; i < 30; i++) {
        const x = rnd() * w;
        const y = rnd() * h;
        const up = rnd() > 0.5;
        ctx.strokeStyle = rgba(up ? C.pos : C.neg, 0.1 + rnd() * 0.14);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x, y + (up ? -1 : 1) * (12 + rnd() * 30));
        ctx.stroke();
      }

      // 4) Drifting data particles. The only animated element: enough to feel
      //    alive, not enough to compete with the right-hand panel.
      const drift = reduced ? 0 : t / 1000;
      for (let i = 0; i < 26; i++) {
        const seedX = rnd();
        const seedY = rnd();
        const x = ((seedX + drift * 0.02 * (0.4 + seedY)) % 1) * w;
        const y = seedY * h;
        ctx.fillStyle = rgba(C.text, 0.16);
        ctx.fillRect(x, y, 1.5, 1.5);
      }
    };

    if (reduced || !visible) {
      draw(0);
      return undefined;
    }
    const start = performance.now();
    const loop = (now) => {
      if (stopped) return;
      draw(now - start);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
    };
  }, [visible, reduced]);

  return (
    <div ref={hostRef} className={`relative h-full w-full ${className}`}>
      <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
    </div>
  );
}

/* ------------------------------------------------------ intelligence ---- */

export function IntelCanvas({ labels, className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: hostRef, visible } = useOnScreen("120px");
  const startRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let raf = 0;
    let stopped = false;

    const draw = (elapsed) => {
      const fitted = fitCanvas(canvas);
      if (!fitted) return;
      const { ctx, w, h } = fitted;
      ctx.clearRect(0, 0, w, h);

      const padR = Math.min(44, w * 0.14);
      const plotW = w - padR - 6;
      const plotH = h - 16;
      const lo = Math.min(SERIES.min, LEVELS.sl);
      const hi = Math.max(SERIES.max, LEVELS.tp);
      const span = (hi - lo) * 1.12;
      const mid = (hi + lo) / 2;
      const toY = (p) => 8 + ((mid + span / 2 - p) / span) * plotH;

      const n = SERIES.candles.length;
      const step = plotW / n;
      const bw = Math.max(1.5, step * 0.56);
      const xAt = (i) => 6 + step * i + (step - bw) / 2;

      const drawP = phase(elapsed, 0, 900);
      const overlayP = phase(elapsed, 700, 700);

      drawGrid(ctx, 6, 8, plotW, plotH, 1);

      // Liquidity, identified.
      if (overlayP > 0) {
        const zY = toY(LEVELS.liquidityLow);
        ctx.fillStyle = rgba(C.gold, 0.09 * overlayP);
        ctx.fillRect(6, zY - 5, plotW * overlayP, 10);
      }

      SERIES.candles.forEach((c, i) => {
        const local = Math.max(0, Math.min((drawP * n - i) / 1.5, 1));
        if (local <= 0) return;
        drawCandle(ctx, c, xAt(i), bw, toY, local, local);
      });

      if (overlayP > 0) {
        // Structure, bias, risk and exit — the four things the copy promises.
        drawLevel(ctx, 6, 6 + plotW * overlayP, toY(LEVELS.structure), C.textBright, {
          dash: [5, 4],
          alpha: 0.3 * overlayP,
        });
        drawLevel(ctx, xAt(SERIES.entryIndex), 6 + plotW, toY(LEVELS.entry), C.gold, {
          dash: [],
          width: 1.3,
          alpha: 0.9 * overlayP,
        });

        const eY = toY(LEVELS.entry);
        const tpY = toY(LEVELS.tp);
        const slY = toY(LEVELS.sl);
        const zx = xAt(SERIES.entryIndex);
        const zw = (6 + plotW - zx) * overlayP;
        ctx.fillStyle = rgba(C.pos, 0.1 * overlayP);
        ctx.fillRect(zx, tpY, zw, eY - tpY);
        ctx.fillStyle = rgba(C.neg, 0.1 * overlayP);
        ctx.fillRect(zx, eY, zw, slY - eY);

        if (overlayP > 0.75 && w > 300) {
          drawTag(ctx, w - 4, tpY, labels.tp, C.pos, { align: "right" });
          drawTag(ctx, w - 4, eY, labels.entry, C.gold, { align: "right" });
          drawTag(ctx, w - 4, slY, labels.sl, C.neg, { align: "right" });
        }
      }
    };

    if (reduced) {
      draw(3000);
      return undefined;
    }
    if (!visible) return undefined;
    if (!startRef.current) startRef.current = performance.now();

    const loop = (now) => {
      if (stopped) return;
      const elapsed = now - startRef.current;
      draw(elapsed);
      // This panel is a finite reveal, not a loop: once it has drawn itself
      // it stops costing frames entirely.
      if (elapsed < 1800) raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
    };
  }, [visible, reduced, labels]);

  return (
    <div ref={hostRef} className={`relative h-full w-full ${className}`}>
      <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
    </div>
  );
}

/* -------------------------------------------------------------- beam ---- */

/**
 * The transformation beam that replaces the old circular arrow. It reads as
 * processing rather than as "next slide": pulses travel from the noisy side
 * into the intelligent side, continuously.
 */
export function TransformBeam({ className = "" }) {
  const reduced = useReducedMotion();
  return (
    <div className={`relative flex items-center justify-center ${className}`} aria-hidden>
      {/* Rail: horizontal on desktop, vertical when the panels stack. */}
      <div className="absolute inset-x-0 top-1/2 hidden h-px -translate-y-1/2 bg-gradient-to-r from-transparent via-signal/30 to-transparent lg:block" />
      <div className="absolute inset-y-0 left-1/2 h-full w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-signal/30 to-transparent lg:hidden" />

      {!reduced &&
        [0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="absolute h-1 w-1 rounded-full bg-signal-soft shadow-[0_0_10px_2px_rgba(240,184,11,0.5)]"
            initial={{ opacity: 0 }}
            animate={{
              opacity: [0, 1, 1, 0],
              // Travels left-to-right on wide screens; the vertical rail is
              // decorative there, and vice versa on narrow ones.
              x: ["-140%", "140%"],
            }}
            transition={{
              duration: 2.2,
              delay: i * 0.7,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}

      <div className="relative z-10 flex h-11 w-11 items-center justify-center rounded-full border border-signal/25 bg-sp-base/90 backdrop-blur-sm">
        <div className="absolute inset-0 rounded-full bg-signal/10 blur-md" />
        <svg viewBox="0 0 24 24" className="relative h-4 w-4 text-signal" fill="none">
          <path
            d="M4 12h14m0 0-5-5m5 5-5 5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lg:block hidden"
          />
          <path
            d="M12 4v14m0 0-5-5m5 5 5-5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lg:hidden"
          />
        </svg>
      </div>
    </div>
  );
}
