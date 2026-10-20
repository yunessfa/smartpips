import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import {
  C,
  buildLevels,
  buildSeries,
  drawCandle,
  drawGrid,
  drawLevel,
  drawTag,
  fitCanvas,
  phase,
  rgba,
  roundRect,
} from "./series.js";
import { useOnScreen } from "../motion.jsx";

/**
 * The hero's trading visualisation.
 *
 * Every annotation (MSS, LIQ, ENTRY, TP, SL, AI, R:R) is drawn *on the canvas*
 * and anchored to the price it describes. That is the whole point: the brief
 * called out "random floating stickers", and the fix is not styling, it is
 * making each label geometrically dependent on the series. The MSS tag sits on
 * the swing high that actually broke; the TP zone is drawn from the entry to
 * a price that is genuinely 2.4R away.
 *
 * The load sequence runs on one clock (`elapsed`), so the whole thing is a
 * single deterministic timeline rather than a pile of competing transitions.
 */

const SERIES = buildSeries({ count: 66, seed: 20260808, regime: "story" });
const LEVELS = buildLevels(SERIES);

// Timeline, in milliseconds. Total run ≈ 2.8s.
const T = {
  grid: [0, 420],
  candles: [340, 1150],
  liquidity: [1240, 420],
  structure: [1500, 360],
  ai: [1760, 360],
  entry: [1980, 320],
  targets: [2180, 420],
  rr: [2500, 320],
};
const SETTLED = 2900;

export function HeroChart({ labels, className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: hostRef, visible } = useOnScreen("200px");
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

      // ----------------------------------------------------------- layout
      const padL = 10;
      const padR = Math.min(64, w * 0.13); // room for right-edge price tags
      const padT = 18;
      const volH = Math.max(26, h * 0.13);
      const padB = volH + 18;

      const plotW = w - padL - padR;
      const plotH = h - padT - padB;
      if (plotW < 40 || plotH < 40) return;

      // Pad the price range so the TP/SL zones are never clipped.
      const lo = Math.min(SERIES.min, LEVELS.sl);
      const hi = Math.max(SERIES.max, LEVELS.tp);
      const span = (hi - lo) * 1.1;
      const mid = (hi + lo) / 2;
      const top = mid + span / 2;
      const toY = (p) => padT + ((top - p) / span) * plotH;

      const n = SERIES.candles.length;
      const step = plotW / n;
      const bw = Math.max(2, step * 0.58);
      const xAt = (i) => padL + step * i + (step - bw) / 2;

      // --------------------------------------------------------- progress
      const p = (key) => phase(elapsed, T[key][0], T[key][1]);
      const gridP = p("grid");
      const candleP = p("candles");
      const liqP = p("liquidity");
      const structP = p("structure");
      const aiP = p("ai");
      const entryP = p("entry");
      const tgtP = p("targets");
      const rrP = p("rr");

      // Idle breathing, only after the intro has settled.
      const idle = elapsed > SETTLED ? (elapsed - SETTLED) / 1000 : 0;

      drawGrid(ctx, padL, padT, plotW, plotH, gridP);

      // ------------------------------------------------- liquidity zones
      // Drawn beneath the candles so price sits *inside* the zone rather
      // than being covered by a translucent rectangle.
      if (liqP > 0) {
        const zoneY = toY(LEVELS.liquidityLow);
        const zoneH = Math.max(6, plotH * 0.045);
        const pulse = 0.5 + Math.sin(idle * 1.6) * 0.5;

        ctx.fillStyle = rgba(C.gold, 0.07 * liqP + 0.03 * pulse * liqP);
        ctx.fillRect(padL, zoneY - zoneH / 2, plotW * liqP, zoneH);
        drawLevel(ctx, padL, padL + plotW * liqP, zoneY, C.gold, {
          dash: [3, 5],
          alpha: 0.4 * liqP,
        });

        // Mirror zone above the range — resting liquidity on the other side.
        const upperY = toY(LEVELS.structure + LEVELS.risk * 0.35);
        ctx.fillStyle = rgba(C.gold, 0.05 * liqP);
        ctx.fillRect(padL, upperY - zoneH / 2, plotW * liqP, zoneH);
      }

      // ---------------------------------------------------------- candles
      SERIES.candles.forEach((c, i) => {
        // Each candle owns a slice of the reveal window and grows from its
        // open price, so the series draws left-to-right like a live feed.
        const local = Math.max(0, Math.min((candleP * n - i) / 1.6, 1));
        if (local <= 0) return;
        const eased = 1 - Math.pow(1 - local, 2);
        drawCandle(ctx, c, xAt(i), bw, toY, eased, eased);
      });

      // ------------------------------------------------------- order flow
      // A volume/delta strip. Subtle by design: it is context, not a feature.
      const volTop = h - volH - 6;
      SERIES.candles.forEach((c, i) => {
        const local = Math.max(0, Math.min((candleP * n - i) / 1.6, 1));
        if (local <= 0) return;
        const bh = c.volume * volH * local;
        ctx.fillStyle = rgba(c.up ? C.pos : C.neg, 0.3 * local);
        ctx.fillRect(xAt(i), volTop + volH - bh, bw, bh);
      });

      // --------------------------------------------------- structure line
      if (structP > 0) {
        const sY = toY(LEVELS.structure);
        const sX = padL + plotW * structP;
        drawLevel(ctx, padL, sX, sY, C.textBright, { dash: [6, 4], alpha: 0.32 * structP });
        if (structP > 0.55) {
          // Anchored to the candle that broke structure, not to a corner.
          drawTag(ctx, xAt(SERIES.mssIndex) - 6, sY - 14, labels.mss, C.goldSoft);
        }
      }

      // ---------------------------------------------------- AI marker
      if (aiP > 0) {
        const c = SERIES.candles[SERIES.mssIndex];
        const mx = xAt(SERIES.mssIndex) + bw / 2;
        const my = toY(c.low) + 14;

        // Expanding ring: the "analysing" beat. Continues after the intro.
        const ringT = (idle % 2.4) / 2.4;
        if (idle > 0) {
          ctx.strokeStyle = rgba(C.gold, (1 - ringT) * 0.5);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(mx, my, 6 + ringT * 20, 0, Math.PI * 2);
          ctx.stroke();
        }

        ctx.fillStyle = rgba(C.gold, 0.95 * aiP);
        ctx.beginPath();
        ctx.arc(mx, my, 3.5 * aiP, 0, Math.PI * 2);
        ctx.fill();

        if (aiP > 0.5) drawTag(ctx, mx + 10, my + 2, labels.ai, C.gold);
      }

      // -------------------------------------------------------- TP / SL
      if (tgtP > 0) {
        const eY = toY(LEVELS.entry);
        const tpY = toY(LEVELS.tp);
        const slY = toY(LEVELS.sl);
        const zx = xAt(SERIES.entryIndex);
        const zw = (padL + plotW - zx) * tgtP;

        ctx.fillStyle = rgba(C.pos, 0.1);
        ctx.fillRect(zx, tpY, zw, eY - tpY);
        ctx.fillStyle = rgba(C.neg, 0.1);
        ctx.fillRect(zx, eY, zw, slY - eY);

        drawLevel(ctx, zx, zx + zw, tpY, C.pos, { dash: [], alpha: 0.55 });
        drawLevel(ctx, zx, zx + zw, slY, C.neg, { dash: [], alpha: 0.55 });

        if (tgtP > 0.7) {
          drawTag(ctx, w - 6, tpY, labels.tp, C.pos, { align: "right" });
          drawTag(ctx, w - 6, slY, labels.sl, C.neg, { align: "right" });
        }
      }

      // ---------------------------------------------------------- entry
      if (entryP > 0) {
        const eY = toY(LEVELS.entry);
        const ex = xAt(SERIES.entryIndex);
        const ew = (padL + plotW - ex) * entryP;

        ctx.save();
        ctx.shadowColor = rgba(C.gold, 0.5);
        ctx.shadowBlur = 8;
        drawLevel(ctx, ex, ex + ew, eY, C.gold, { dash: [], width: 1.4, alpha: 0.95 });
        ctx.restore();

        // A packet travelling the entry line: the only continuous motion in
        // the chart once it settles. One moving element reads as "live";
        // several read as a screensaver.
        if (idle > 0) {
          const tt = (idle % 3.4) / 3.4;
          const px = ex + ew * tt;
          const grad = ctx.createLinearGradient(px - 34, 0, px, 0);
          grad.addColorStop(0, rgba(C.goldSoft, 0));
          grad.addColorStop(1, rgba(C.goldSoft, 0.7));
          ctx.strokeStyle = grad;
          ctx.lineWidth = 1.6;
          ctx.beginPath();
          ctx.moveTo(Math.max(ex, px - 34), eY);
          ctx.lineTo(px, eY);
          ctx.stroke();
        }

        if (entryP > 0.6) drawTag(ctx, w - 6, eY, labels.entry, C.gold, { align: "right" });
      }

      // ------------------------------------------------------------ R:R
      if (rrP > 0) {
        const text = `${labels.rr} ${labels.rrValue}`;
        ctx.font = "600 10px 'JetBrains Mono', ui-monospace, monospace";
        const tw = ctx.measureText(text).width + 16;
        const bx = padL + 8;
        const by = padT + 8;
        ctx.globalAlpha = rrP;
        roundRect(ctx, bx, by, tw, 20, 5);
        ctx.fillStyle = "rgba(8,10,13,0.85)";
        ctx.fill();
        ctx.strokeStyle = rgba(C.gold, 0.3);
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = rgba(C.goldSoft, 1);
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(text, bx + 8, by + 10.5);
        ctx.globalAlpha = 1;
      }
    };

    // Reduced motion: render the finished frame once, no clock at all.
    if (reduced) {
      draw(SETTLED + 500);
      const onResize = () => draw(SETTLED + 500);
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
    }

    if (!visible) return undefined;
    if (!startRef.current) startRef.current = performance.now();

    const loop = (now) => {
      if (stopped) return;
      draw(now - startRef.current);
      raf = requestAnimationFrame(loop);
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

export default HeroChart;
