import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import {
  C,
  buildLevels,
  buildSeries,
  drawCandle,
  drawGrid,
  drawLevel,
  drawTag,
  fitCanvas,
  rgba,
} from "./series.js";

/**
 * Section 4: five layers of analysis applied to ONE chart.
 *
 * The brief was explicit that this must not become five unrelated cards, and
 * the implementation enforces that literally: there is a single canvas and a
 * single series, and each "layer" is nothing more than an opacity channel
 * into the same render pass. Turning a layer on cannot possibly draw a
 * different market, because there is only one market in the component.
 *
 * Each layer's opacity is eased toward its target every frame rather than
 * snapped, so switching layers cross-dissolves instead of flickering.
 */

const SERIES = buildSeries({ count: 72, seed: 20260808, regime: "story" });
const LEVELS = buildLevels(SERIES);

const LAYER_IDS = ["structure", "liquidity", "orderflow", "risk", "exit"];

export function LayerChart({ items = [], hint, className = "" }) {
  const [active, setActive] = useState(0);
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const hostRef = useRef(null);
  const inView = useInView(hostRef, { margin: "-15% 0px" });

  // Live opacity per layer. Held in a ref so the render loop can mutate it
  // without triggering React re-renders sixty times a second.
  const alphaRef = useRef(LAYER_IDS.map(() => 0));

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

      // Ease each layer toward 1 (at or below the active index) or 0.
      // Layers are cumulative: selecting "Risk" keeps structure and liquidity
      // visible, because that is how a trader actually stacks a read.
      const target = LAYER_IDS.map((_, i) => (i <= active ? 1 : 0));
      alphaRef.current = alphaRef.current.map((a, i) =>
        reduced ? target[i] : a + (target[i] - a) * 0.09,
      );
      const A = alphaRef.current;

      const padR = Math.min(58, w * 0.12);
      const padT = 16;
      const volH = Math.max(30, h * 0.14);
      const padB = volH + 16;
      const plotW = w - padR - 12;
      const plotH = h - padT - padB;
      if (plotW < 60 || plotH < 60) return;

      const lo = Math.min(SERIES.min, LEVELS.sl);
      const hi = Math.max(SERIES.max, LEVELS.tp);
      const span = (hi - lo) * 1.1;
      const mid = (hi + lo) / 2;
      const toY = (p) => padT + ((mid + span / 2 - p) / span) * plotH;

      const n = SERIES.candles.length;
      const step = plotW / n;
      const bw = Math.max(2, step * 0.58);
      const xAt = (i) => 12 + step * i + (step - bw) / 2;
      const right = 12 + plotW;

      drawGrid(ctx, 12, padT, plotW, plotH, 1);

      /* -- 02 liquidity (drawn first so candles sit inside the zones) ----- */
      if (A[1] > 0.01) {
        const zY = toY(LEVELS.liquidityLow);
        const zh = Math.max(8, plotH * 0.05);
        ctx.fillStyle = rgba(C.gold, 0.1 * A[1]);
        ctx.fillRect(12, zY - zh / 2, plotW, zh);
        const upperY = toY(LEVELS.structure + LEVELS.risk * 0.4);
        ctx.fillStyle = rgba(C.gold, 0.07 * A[1]);
        ctx.fillRect(12, upperY - zh / 2, plotW, zh);
        if (A[1] > 0.6) drawTag(ctx, 18, zY, "LIQ", C.gold);
      }

      /* -- 05 exit zones -------------------------------------------------- */
      if (A[4] > 0.01) {
        const eY = toY(LEVELS.entry);
        const tpY = toY(LEVELS.tp);
        const zx = xAt(SERIES.entryIndex);
        ctx.fillStyle = rgba(C.pos, 0.1 * A[4]);
        ctx.fillRect(zx, tpY, right - zx, eY - tpY);
        drawLevel(ctx, zx, right, tpY, C.pos, { dash: [], alpha: 0.6 * A[4] });
        if (A[4] > 0.6) drawTag(ctx, w - 6, tpY, "TP", C.pos, { align: "right" });
      }

      /* -- 04 risk -------------------------------------------------------- */
      if (A[3] > 0.01) {
        const eY = toY(LEVELS.entry);
        const slY = toY(LEVELS.sl);
        const zx = xAt(SERIES.entryIndex);
        ctx.fillStyle = rgba(C.neg, 0.1 * A[3]);
        ctx.fillRect(zx, eY, right - zx, slY - eY);
        drawLevel(ctx, zx, right, slY, C.neg, { dash: [], alpha: 0.6 * A[3] });
        drawLevel(ctx, zx, right, eY, C.gold, { dash: [], width: 1.3, alpha: 0.85 * A[3] });
        if (A[3] > 0.6) {
          drawTag(ctx, w - 6, slY, "SL", C.neg, { align: "right" });
          drawTag(ctx, w - 6, eY, "ENTRY", C.gold, { align: "right" });
        }
      }

      /* -- candles (always present: they are the subject, not a layer) ---- */
      SERIES.candles.forEach((c, i) => {
        drawCandle(ctx, c, xAt(i), bw, toY, 1, 1);
      });

      /* -- 03 order flow -------------------------------------------------- */
      const volTop = h - volH - 6;
      if (A[2] > 0.01) {
        SERIES.candles.forEach((c, i) => {
          const bh = c.volume * volH;
          ctx.fillStyle = rgba(c.up ? C.pos : C.neg, 0.45 * A[2]);
          ctx.fillRect(xAt(i), volTop + volH - bh, bw, bh);
        });
        ctx.strokeStyle = rgba(C.grid, 0.06 * A[2]);
        ctx.beginPath();
        ctx.moveTo(12, volTop + volH);
        ctx.lineTo(right, volTop + volH);
        ctx.stroke();
      }

      /* -- 01 market structure -------------------------------------------- */
      if (A[0] > 0.01) {
        // Swing points, then the level that broke. Drawn above the candles
        // because structure is an interpretation *of* them.
        const sY = toY(LEVELS.structure);
        drawLevel(ctx, 12, right, sY, C.textBright, { dash: [6, 4], alpha: 0.34 * A[0] });

        ctx.fillStyle = rgba(C.textBright, 0.5 * A[0]);
        for (let i = 2; i < n - 2; i++) {
          const c = SERIES.candles[i];
          const isHigh =
            c.high > SERIES.candles[i - 1].high &&
            c.high > SERIES.candles[i - 2].high &&
            c.high > SERIES.candles[i + 1].high &&
            c.high > SERIES.candles[i + 2].high;
          const isLow =
            c.low < SERIES.candles[i - 1].low &&
            c.low < SERIES.candles[i - 2].low &&
            c.low < SERIES.candles[i + 1].low &&
            c.low < SERIES.candles[i + 2].low;
          if (isHigh || isLow) {
            ctx.beginPath();
            ctx.arc(xAt(i) + bw / 2, toY(isHigh ? c.high : c.low) + (isHigh ? -5 : 5), 1.8, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        if (A[0] > 0.6) drawTag(ctx, xAt(SERIES.mssIndex), sY - 14, "MSS", C.goldSoft);
      }
    };

    if (reduced) {
      draw(0);
      return undefined;
    }
    // Only spend frames while the section is on screen.
    if (!inView) {
      draw(0);
      return undefined;
    }
    const loop = (now) => {
      if (stopped) return;
      draw(now);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
    };
  }, [active, reduced, inView]);

  return (
    <div ref={hostRef} className={`grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-12 ${className}`}>
      {/* Chart. Order is reversed on mobile so the visual leads. */}
      <div className="order-1 lg:order-none">
        <div className="relative overflow-hidden rounded-2xl border border-sp-line bg-sp-s1/60">
          <div className="flex items-center justify-between border-b border-sp-line px-4 py-2.5">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-sp-pos" />
              <span className="font-mono text-[11px] tracking-wider text-sp-t2">BTCUSDT · 5m</span>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">
              {items[active]?.num} {items[active]?.title}
            </span>
          </div>
          <div className="h-[300px] sm:h-[400px] lg:h-[480px]">
            <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
          </div>
        </div>
      </div>

      {/* Layer switcher */}
      <div className="order-2 lg:order-none">
        <div className="mb-4 font-mono text-[10px] uppercase tracking-[0.22em] text-sp-t4">{hint}</div>
        <div className="flex flex-col">
          {items.map((item, i) => {
            const on = i === active;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActive(i)}
                onMouseEnter={() => setActive(i)}
                className={`group relative border-s-2 px-4 py-4 text-start transition-all duration-300 ${
                  on ? "border-signal bg-signal/[0.05]" : "border-sp-line hover:border-sp-edge"
                }`}
              >
                <div className="flex items-baseline gap-3">
                  <span
                    className={`font-mono text-[11px] tabular-nums transition-colors duration-300 ${
                      on ? "text-signal" : "text-sp-t4"
                    }`}
                  >
                    {item.num}
                  </span>
                  <span
                    className={`text-[15px] font-semibold transition-colors duration-300 ${
                      on ? "text-sp-t1" : "text-sp-t3"
                    }`}
                  >
                    {item.title}
                  </span>
                </div>
                <p
                  className={`mt-1.5 text-[12.5px] leading-relaxed transition-colors duration-300 ${
                    on ? "text-sp-t2" : "text-sp-t4"
                  }`}
                >
                  {item.note}
                </p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default LayerChart;
