import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
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
 * Section 6: Smart Exit.
 *
 * The requirement that makes this section work is coupling: the chart must
 * *change* when the verdict changes. Four cards that fade in and out prove
 * nothing. So each verdict carries a concrete market reaction — where the
 * stop sits, how much size remains, what the open PnL is — and the canvas
 * renders that state. Trailing the stop visibly moves the red line up;
 * closing part visibly halves the size bar; exiting flashes the frame.
 *
 * It auto-advances while on screen, and clicking a verdict pins it so a
 * reader can study one state without fighting the timer.
 */

const SERIES = buildSeries({ count: 58, seed: 88213, regime: "trend" });
const LEVELS = buildLevels(SERIES);

// Market reaction per verdict. `stopAt` is a 0..1 position between the
// original stop and the entry; `size` is remaining position percent.
const REACTION = [
  { stopAt: 0, size: 100, pnl: 186.4, note: "structure" },
  { stopAt: 0.55, size: 100, pnl: 248.6, note: "trail" },
  { stopAt: 0.55, size: 50, pnl: 312.9, note: "partial" },
  { stopAt: 0.55, size: 0, pnl: 298.1, note: "flat" },
];

const TONE = {
  info: { text: "text-info", border: "border-info/30", bg: "bg-info/[0.07]", dot: "bg-info" },
  gold: { text: "text-signal", border: "border-signal/30", bg: "bg-signal/[0.07]", dot: "bg-signal" },
  up: { text: "text-sp-pos", border: "border-sp-pos/30", bg: "bg-sp-pos/[0.07]", dot: "bg-sp-pos" },
  down: { text: "text-sp-neg", border: "border-sp-neg/30", bg: "bg-sp-neg/[0.07]", dot: "bg-sp-neg" },
};

export function SmartExitLive({
  states = [],
  positionLabel,
  verdictLabel,
  reads = [],
  className = "",
}) {
  const hostRef = useRef(null);
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(hostRef, { margin: "-25% 0px" });
  const [active, setActive] = useState(0);
  const [pinned, setPinned] = useState(false);

  // Animated stop position, so trailing the stop glides rather than jumping.
  const stopRef = useRef(0);

  useEffect(() => {
    if (reduced || pinned || !inView) return undefined;
    const id = setInterval(() => setActive((v) => (v + 1) % states.length), 3400);
    return () => clearInterval(id);
  }, [pinned, inView, reduced, states.length]);

  const reaction = REACTION[active] || REACTION[0];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let raf = 0;
    let stopped = false;

    const draw = () => {
      const fitted = fitCanvas(canvas);
      if (!fitted) return;
      const { ctx, w, h } = fitted;
      ctx.clearRect(0, 0, w, h);

      const padR = Math.min(52, w * 0.13);
      const padT = 14;
      const padB = 16;
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
      SERIES.candles.forEach((c, i) => drawCandle(ctx, c, xAt(i), bw, toY, 1, 0.85));

      // Ease the stop toward its target for this verdict.
      stopRef.current += (reaction.stopAt - stopRef.current) * (reduced ? 1 : 0.08);
      const stopPrice = LEVELS.sl + (LEVELS.entry - LEVELS.sl) * stopRef.current;

      const eY = toY(LEVELS.entry);
      const sY = toY(stopPrice);

      // Risk band shrinks as the stop trails up — the visual payoff of the
      // "protect what the move has given" line in the copy.
      ctx.fillStyle = rgba(C.neg, 0.09);
      ctx.fillRect(12, eY, plotW, sY - eY);

      drawLevel(ctx, 12, right, eY, C.gold, { dash: [], width: 1.3, alpha: 0.9 });
      drawLevel(ctx, 12, right, sY, C.neg, { dash: [], width: 1.3, alpha: 0.9 });
      drawTag(ctx, w - 6, eY, "ENTRY", C.gold, { align: "right" });
      drawTag(ctx, w - 6, sY, "SL", C.neg, { align: "right" });

      // When flat, strike the position out.
      if (reaction.size === 0) {
        ctx.strokeStyle = rgba(C.neg, 0.5);
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(xAt(n - 8), padT);
        ctx.lineTo(xAt(n - 8), padT + plotH);
        ctx.stroke();
        ctx.setLineDash([]);
        drawTag(ctx, xAt(n - 8) + 6, padT + 14, "CLOSED", C.neg);
      }
    };

    if (reduced) {
      draw();
      return undefined;
    }
    const loop = () => {
      if (stopped) return;
      draw();
      raf = requestAnimationFrame(loop);
    };
    if (inView) raf = requestAnimationFrame(loop);
    else draw();
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
    };
  }, [active, inView, reduced, reaction]);

  const tone = TONE[states[active]?.tone] || TONE.info;
  const isExit = states[active]?.tone === "down";

  return (
    <div ref={hostRef} className={`grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-10 ${className}`}>
      {/* Chart + position frame */}
      <motion.div
        className="overflow-hidden rounded-2xl border bg-sp-s1/60 transition-colors duration-500"
        animate={{
          borderColor: isExit ? "rgba(240,68,92,0.4)" : "rgba(28,34,41,1)",
        }}
      >
        <div className="flex items-center justify-between border-b border-sp-line px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <span className={`h-1.5 w-1.5 rounded-full ${reaction.size === 0 ? "bg-sp-t4" : "bg-sp-pos"}`} />
            <span className="font-mono text-[11px] tracking-wider text-sp-t2">BTCUSDT · LONG</span>
          </div>
          <span className="font-mono text-[11px] tabular-nums text-sp-pos">
            +${reaction.pnl.toFixed(2)}
          </span>
        </div>

        <div className="h-[260px] sm:h-[320px] lg:h-[380px]">
          <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
        </div>

        {/* Position size bar — halves on CLOSE PART, empties on EXIT NOW. */}
        <div className="border-t border-sp-line px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-sp-t4">
              {positionLabel}
            </span>
            <span className="font-mono text-[11px] tabular-nums text-sp-t2">{reaction.size}%</span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-sp-s3">
            <motion.div
              className="h-full rounded-full bg-signal"
              animate={{ width: `${reaction.size}%` }}
              transition={{ duration: 0.7, ease: [0.2, 0.7, 0.3, 1] }}
            />
          </div>
        </div>
      </motion.div>

      {/* Verdict panel */}
      <div>
        {/* What the engine is re-reading. */}
        <div className="mb-4 flex flex-wrap gap-1.5">
          {reads.map((r) => (
            <span
              key={r}
              className="rounded-full border border-sp-line px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-sp-t4"
            >
              {r}
            </span>
          ))}
        </div>

        <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-sp-t4">
          {verdictLabel}
        </div>

        <div className="flex flex-col gap-2">
          {states.map((s, i) => {
            const on = i === active;
            const t = TONE[s.tone] || TONE.info;
            return (
              <button
                key={s.label}
                type="button"
                onClick={() => {
                  setActive(i);
                  setPinned(true);
                }}
                className={`rounded-xl border px-4 py-3 text-start transition-all duration-400 ${
                  on ? `${t.border} ${t.bg}` : "border-sp-line bg-transparent hover:border-sp-edge"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <span className={`h-1.5 w-1.5 rounded-full ${on ? t.dot : "bg-sp-t4"}`} />
                  <span
                    className={`font-mono text-[11px] uppercase tracking-[0.18em] transition-colors duration-300 ${
                      on ? t.text : "text-sp-t3"
                    }`}
                  >
                    {s.label}
                  </span>
                </div>
                <motion.p
                  className="mt-1.5 overflow-hidden text-[12.5px] leading-relaxed text-sp-t3"
                  animate={{ height: on ? "auto" : 0, opacity: on ? 1 : 0 }}
                  transition={{ duration: 0.35 }}
                >
                  {s.note}
                </motion.p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default SmartExitLive;
