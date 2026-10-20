import { useEffect, useMemo, useRef, useState } from "react";
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
 * Section 5: the Scalp Engine, played as a sequence.
 *
 * This section has to demonstrate the Confirm-Pullback logic, which means the
 * chart must show a *rejection* before it shows an entry. The three status
 * lines ("Price too far from EMA9" → "Pullback confirmed" → "Entry validated")
 * are wired to the same stage counter that drives the chart, so the text can
 * never claim something the chart is not showing.
 *
 * It plays once when scrolled into view. A looping demo trains the eye to
 * ignore it; a single run with an explicit Replay control respects the reader.
 */

const SERIES = buildSeries({ count: 70, seed: 20260808, regime: "story" });
const LEVELS = buildLevels(SERIES);

// Stage timings (ms). Six beats over ~5s.
const STAGE_MS = [600, 1500, 2400, 3300, 4100, 4900];

/** Simple EMA over closes — the reference the pullback is measured against. */
function ema(values, period) {
  const k = 2 / (period + 1);
  let prev = values[0];
  return values.map((v, i) => {
    if (i === 0) return v;
    prev = v * k + prev * (1 - k);
    return prev;
  });
}

export function ScalpSequence({ steps = [], checks = [], replayLabel, className = "" }) {
  const canvasRef = useRef(null);
  const hostRef = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(hostRef, { once: true, margin: "-20% 0px" });
  const [stage, setStage] = useState(-1);
  const [runId, setRunId] = useState(0);

  const EMA9 = useMemo(() => ema(SERIES.candles.map((c) => c.close), 9), []);

  useEffect(() => {
    if (reduced) {
      setStage(5);
      return undefined;
    }
    if (!inView) return undefined;
    setStage(-1);
    const timers = STAGE_MS.map((ms, i) => setTimeout(() => setStage(i), ms));
    return () => timers.forEach(clearTimeout);
  }, [inView, runId, reduced]);

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

      const padR = Math.min(56, w * 0.12);
      const padT = 16;
      const padB = 20;
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

      // Candles are always fully drawn: this sequence is about the analysis
      // arriving, not about the market being replayed tick by tick.
      SERIES.candles.forEach((c, i) => drawCandle(ctx, c, xAt(i), bw, toY, 1, 0.85));

      // EMA9 — the line the pullback is confirmed against.
      ctx.strokeStyle = rgba(C.text, 0.4);
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      EMA9.forEach((v, i) => {
        const x = xAt(i) + bw / 2;
        const y = toY(v);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      if (stage >= 0) drawTag(ctx, 16, toY(EMA9[2]) - 12, "EMA9", C.text);

      /* 0 — liquidity */
      if (stage >= 0) {
        const zY = toY(LEVELS.liquidityLow);
        ctx.fillStyle = rgba(C.gold, 0.1);
        ctx.fillRect(12, zY - 6, plotW, 12);
        drawTag(ctx, 16, zY, "LIQ", C.gold);
      }

      /* 1 — market structure shift */
      if (stage >= 1) {
        const sY = toY(LEVELS.structure);
        drawLevel(ctx, 12, right, sY, C.textBright, { dash: [6, 4], alpha: 0.35 });
        drawTag(ctx, xAt(SERIES.mssIndex), sY - 14, "MSS", C.goldSoft);
      }

      /* 2 — pullback: highlight the candles returning to the EMA */
      if (stage >= 2) {
        const from = SERIES.mssIndex + 1;
        const to = SERIES.entryIndex;
        ctx.fillStyle = rgba(C.goldSoft, 0.07);
        ctx.fillRect(xAt(from), padT, xAt(to) - xAt(from), plotH);
        drawTag(ctx, xAt(from) + 2, padT + 14, "PULLBACK", C.goldSoft);
      }

      /* 3 — confirmation marker */
      if (stage >= 3) {
        const ci = SERIES.entryIndex - 1;
        const cx = xAt(ci) + bw / 2;
        const cy = toY(SERIES.candles[ci].low) + 12;
        ctx.fillStyle = rgba(C.pos, 0.9);
        ctx.beginPath();
        ctx.arc(cx, cy, 3, 0, Math.PI * 2);
        ctx.fill();
        drawTag(ctx, cx + 8, cy, "CONF", C.pos);
      }

      /* 4 — entry */
      if (stage >= 4) {
        const eY = toY(LEVELS.entry);
        ctx.save();
        ctx.shadowColor = rgba(C.gold, 0.45);
        ctx.shadowBlur = 8;
        drawLevel(ctx, xAt(SERIES.entryIndex), right, eY, C.gold, {
          dash: [],
          width: 1.4,
          alpha: 0.95,
        });
        ctx.restore();
        drawTag(ctx, w - 6, eY, "ENTRY", C.gold, { align: "right" });
      }

      /* 5 — targets */
      if (stage >= 5) {
        const eY = toY(LEVELS.entry);
        const tpY = toY(LEVELS.tp);
        const slY = toY(LEVELS.sl);
        const zx = xAt(SERIES.entryIndex);
        ctx.fillStyle = rgba(C.pos, 0.1);
        ctx.fillRect(zx, tpY, right - zx, eY - tpY);
        ctx.fillStyle = rgba(C.neg, 0.1);
        ctx.fillRect(zx, eY, right - zx, slY - eY);
        drawLevel(ctx, zx, right, tpY, C.pos, { dash: [], alpha: 0.6 });
        drawLevel(ctx, zx, right, slY, C.neg, { dash: [], alpha: 0.6 });
        drawTag(ctx, w - 6, tpY, "TP", C.pos, { align: "right" });
        drawTag(ctx, w - 6, slY, "SL", C.neg, { align: "right" });
      }
    };

    draw(0);
    if (reduced) return undefined;
    // Redraw only while the stage is advancing; once settled, stop.
    const loop = () => {
      if (stopped) return;
      draw(0);
      raf = requestAnimationFrame(loop);
    };
    if (stage < 5) raf = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
    };
  }, [stage, EMA9, reduced]);

  // Which status line is showing. Tied to the same stage counter as the chart.
  const checkState = (i) => {
    if (i === 0) return stage >= 1 ? (stage >= 2 ? "done" : "active") : "idle";
    if (i === 1) return stage >= 2 ? (stage >= 4 ? "done" : "active") : "idle";
    return stage >= 4 ? "active" : "idle";
  };

  return (
    <div ref={hostRef} className={className}>
      <div className="overflow-hidden rounded-2xl border border-sp-line bg-sp-s1/60">
        <div className="flex items-center justify-between border-b border-sp-line px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-sp-pos" />
            <span className="font-mono text-[11px] tracking-wider text-sp-t2">BTCUSDT · 1m</span>
          </div>
          <button
            type="button"
            onClick={() => setRunId((v) => v + 1)}
            className="font-mono text-[10px] uppercase tracking-[0.2em] text-sp-t4 transition-colors hover:text-signal"
          >
            {replayLabel}
          </button>
        </div>

        <div className="h-[300px] sm:h-[380px] lg:h-[440px]">
          <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
        </div>

        {/* Confirm-pullback status. Deliberately styled as a terminal readout
            rather than a bullet list — it is machine output, and it should
            look like machine output. */}
        <div className="border-t border-sp-line px-4 py-3">
          <div className="flex flex-col gap-1.5">
            {checks.map((check, i) => {
              const state = checkState(i);
              const tone =
                state === "idle"
                  ? "text-sp-t4"
                  : state === "active"
                    ? "text-signal"
                    : "text-sp-pos";
              return (
                <div
                  key={check.text}
                  className={`flex items-center gap-2.5 font-mono text-[11px] transition-all duration-500 ${tone}`}
                  style={{ opacity: state === "idle" ? 0.35 : 1 }}
                >
                  <span className="tabular-nums text-sp-t4">{String(i + 1).padStart(2, "0")}</span>
                  <span
                    className={`h-1 w-1 rounded-full ${
                      state === "idle"
                        ? "bg-sp-t4"
                        : state === "active"
                          ? "bg-signal"
                          : "bg-sp-pos"
                    }`}
                  />
                  <span>{check.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Step legend, lighting up in step with the chart. */}
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {steps.map((s, i) => {
          const on = stage >= i;
          return (
            <div
              key={s.tag}
              className={`rounded-lg border px-3 py-2.5 transition-all duration-500 ${
                on ? "border-signal/25 bg-signal/[0.04]" : "border-sp-line bg-transparent"
              }`}
            >
              <div
                className={`font-mono text-[10px] tracking-[0.16em] transition-colors duration-500 ${
                  on ? "text-signal" : "text-sp-t4"
                }`}
              >
                {s.tag}
              </div>
              <div
                className={`mt-1 text-[12px] font-medium transition-colors duration-500 ${
                  on ? "text-sp-t1" : "text-sp-t4"
                }`}
              >
                {s.title}
              </div>
              <div className="mt-0.5 text-[10.5px] leading-snug text-sp-t4">{s.note}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ScalpSequence;
