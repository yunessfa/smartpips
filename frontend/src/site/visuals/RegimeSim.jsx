import { useEffect, useMemo, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import {
  C,
  buildSeries,
  drawCandle,
  drawGrid,
  drawLevel,
  drawTag,
  fitCanvas,
  rgba,
} from "./series.js";

/**
 * Section 7: Market Regime.
 *
 * Four cards describing four market conditions would be the template answer.
 * Instead there is one simulator: selecting a regime rebuilds the series with
 * genuinely different behaviour (the range regime mean-reverts, the low-vol
 * regime compresses), and the annotation changes to match what a trader would
 * actually be looking for in that environment.
 *
 * The point being made is that SmartPips classifies the environment *before*
 * it looks for a setup — so the visual has to prove the environments differ.
 */

const REGIME_SEED = { trend: 5501, range: 8802, highvol: 3303, lowvol: 9904 };

export function RegimeSim({ items = [], className = "" }) {
  const [active, setActive] = useState(0);
  const canvasRef = useRef(null);
  const hostRef = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(hostRef, { margin: "-15% 0px" });
  const startRef = useRef(0);

  const current = items[active] || items[0];

  // Rebuilt only when the regime changes, not every frame.
  const series = useMemo(() => {
    if (!current) return null;
    return buildSeries({
      count: 64,
      seed: REGIME_SEED[current.id] || 1234,
      regime: current.id,
    });
  }, [current]);

  // Restart the draw-in whenever the regime changes, so switching feels like
  // the chart is re-rendering under a new classification.
  useEffect(() => {
    startRef.current = performance.now();
  }, [active]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !series) return undefined;
    let raf = 0;
    let stopped = false;

    const draw = (elapsed) => {
      const fitted = fitCanvas(canvas);
      if (!fitted) return;
      const { ctx, w, h } = fitted;
      ctx.clearRect(0, 0, w, h);

      const padT = 14;
      const padB = 14;
      const plotW = w - 24;
      const plotH = h - padT - padB;
      if (plotW < 60 || plotH < 60) return;

      const span = (series.max - series.min) * 1.15;
      const mid = (series.max + series.min) / 2;
      const toY = (p) => padT + ((mid + span / 2 - p) / span) * plotH;

      const n = series.candles.length;
      const step = plotW / n;
      const bw = Math.max(2, step * 0.58);
      const xAt = (i) => 12 + step * i + (step - bw) / 2;
      const right = 12 + plotW;

      const p = reduced ? 1 : Math.min(elapsed / 800, 1);
      const eased = 1 - Math.pow(1 - p, 3);

      drawGrid(ctx, 12, padT, plotW, plotH, 1);

      series.candles.forEach((c, i) => {
        const local = Math.max(0, Math.min((eased * n - i) / 1.5, 1));
        if (local <= 0) return;
        drawCandle(ctx, c, xAt(i), bw, toY, local, local);
      });

      if (eased < 0.9) return;

      // Regime-specific annotation. This is the part that makes the section
      // an argument rather than four skins of the same chart.
      const id = current.id;
      if (id === "trend") {
        // Trend channel.
        const first = series.candles[2].low;
        const last = series.candles[n - 3].low;
        ctx.strokeStyle = rgba(C.gold, 0.4);
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(xAt(2), toY(first));
        ctx.lineTo(xAt(n - 3), toY(last));
        ctx.stroke();
        ctx.setLineDash([]);
        drawTag(ctx, xAt(n - 14), toY(last) + 16, "CONTINUATION", C.gold);
      } else if (id === "range") {
        // Range edges: the only levels that matter here.
        const hiP = series.max - (series.max - series.min) * 0.12;
        const loP = series.min + (series.max - series.min) * 0.12;
        ctx.fillStyle = rgba(C.gold, 0.06);
        ctx.fillRect(12, toY(hiP), plotW, toY(loP) - toY(hiP));
        drawLevel(ctx, 12, right, toY(hiP), C.neg, { dash: [5, 4], alpha: 0.5 });
        drawLevel(ctx, 12, right, toY(loP), C.pos, { dash: [5, 4], alpha: 0.5 });
        drawTag(ctx, 16, toY(hiP), "SUPPLY", C.neg);
        drawTag(ctx, 16, toY(loP), "DEMAND", C.pos);
      } else if (id === "highvol") {
        // Wide invalidation band around the last price.
        const last = series.candles[n - 1].close;
        const band = (series.max - series.min) * 0.22;
        ctx.fillStyle = rgba(C.neg, 0.08);
        ctx.fillRect(12, toY(last + band), plotW, toY(last - band) - toY(last + band));
        drawTag(ctx, 16, toY(last + band) + 12, "WIDE STOP · SMALL SIZE", C.neg);
      } else if (id === "lowvol") {
        // Compression wedge.
        const last = series.candles[n - 1].close;
        const band = (series.max - series.min) * 0.08;
        ctx.fillStyle = rgba(C.gold, 0.07);
        ctx.fillRect(12, toY(last + band), plotW, toY(last - band) - toY(last + band));
        drawLevel(ctx, 12, right, toY(last + band), C.gold, { dash: [4, 4], alpha: 0.45 });
        drawLevel(ctx, 12, right, toY(last - band), C.gold, { dash: [4, 4], alpha: 0.45 });
        drawTag(ctx, 16, toY(last + band) - 12, "COMPRESSION · WAIT", C.goldSoft);
      }
    };

    if (reduced) {
      draw(1000);
      return undefined;
    }
    const loop = (now) => {
      if (stopped) return;
      const elapsed = now - startRef.current;
      draw(elapsed);
      // Finite reveal: stop burning frames once the annotation has landed.
      if (elapsed < 1400) raf = requestAnimationFrame(loop);
    };
    if (inView) raf = requestAnimationFrame(loop);
    else draw(1400);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
    };
  }, [series, current, reduced, inView, active]);

  if (!current) return null;

  return (
    <div ref={hostRef} className={className}>
      {/* Regime selector */}
      <div className="mb-5 flex flex-wrap gap-2">
        {items.map((item, i) => {
          const on = i === active;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActive(i)}
              onMouseEnter={() => setActive(i)}
              className={`rounded-full border px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] transition-all duration-300 ${
                on
                  ? "border-signal/40 bg-signal/[0.08] text-signal"
                  : "border-sp-line text-sp-t4 hover:border-sp-edge hover:text-sp-t2"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="overflow-hidden rounded-2xl border border-sp-line bg-sp-s1/60">
        <div className="flex items-center justify-between border-b border-sp-line px-4 py-2.5">
          <span className="font-mono text-[11px] tracking-wider text-sp-t2">BTCUSDT · 15m</span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">
            {current.label}
          </span>
        </div>
        <div className="h-[260px] sm:h-[320px] lg:h-[360px]">
          <canvas ref={canvasRef} className="block h-full w-full" aria-hidden />
        </div>
        <div className="border-t border-sp-line px-5 py-4">
          <p className="text-[13.5px] leading-relaxed text-sp-t2">{current.note}</p>
        </div>
      </div>
    </div>
  );
}

export default RegimeSim;
