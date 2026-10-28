import { useCallback, useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import { Pill } from "../primitives.jsx";

/**
 * Section 6 visual: one trade replayed from structure shift to exit.
 *
 * Built in SVG so the price path can literally draw itself (`pathLength`) and
 * the markers can be real text. A timeline drives five stages; each stage
 * reveals its marker on the chart and highlights the matching row beneath.
 *
 * It plays once when scrolled into view rather than looping forever — an
 * endlessly repeating animation in the middle of a page competes with reading.
 * A replay control is provided for anyone who wants to see it again.
 */

// Price path in a 0..100 x 0..60 user space. Hand-shaped, not random: the
// sweep below support before the expansion is the whole point of the setup.
const PATH = "M 2,34 L 8,31 L 14,35 L 20,30 L 26,33 L 32,27 L 38,31 L 44,44 L 50,26 L 56,22 L 62,25 L 68,17 L 74,20 L 80,12 L 88,9";

// Stage anchors: [x, y] in the same user space, matched to the path above.
const STAGES = [
  { at: [32, 27], tone: "gold", dashed: false },   // MSS
  { at: [44, 44], tone: "info", dashed: false },   // liquidity sweep
  { at: [50, 26], tone: "gold", dashed: true },    // entry
  { at: [80, 12], tone: "up", dashed: true },      // target
  { at: [88, 9], tone: "up", dashed: false },      // exit
];

const STROKE = {
  gold: "#F0B90B",
  up: "#0ECB81",
  down: "#F6465A",
  info: "#5B8DEF",
};

export function ScalpReplay({ steps, replayLabel, className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref, { once: true, margin: "-20% 0px" });
  const [stage, setStage] = useState(-1);
  const [runId, setRunId] = useState(0);

  const play = useCallback(() => {
    setStage(-1);
    setRunId((n) => n + 1);
  }, []);

  // Advance the timeline once the path has had time to draw.
  useEffect(() => {
    if (!inView) return undefined;
    if (reduced) { setStage(STAGES.length - 1); return undefined; }

    const timers = STAGES.map((_, i) =>
      setTimeout(() => setStage(i), 1500 + i * 850),
    );
    return () => timers.forEach(clearTimeout);
  }, [inView, reduced, runId]);

  return (
    <div ref={ref} className={className}>
      <div className="relative overflow-hidden rounded-2xl border border-white/[0.07] bg-ink-900/70">
        <div className="sx-grid sx-grid-mask pointer-events-none absolute inset-0 opacity-60" />

        {/* header strip, echoing the real terminal */}
        <div className="relative flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="tnum text-xs font-semibold text-mist-100">BTCUSDT</span>
            <Pill tone="gold">5m</Pill>
          </div>
          <button
            type="button"
            onClick={play}
            className="rounded-full border border-white/12 px-3 py-1 font-mono text-[10px]
              uppercase tracking-wider text-mist-300 transition-colors
              hover:border-gold/40 hover:text-gold"
          >
            {replayLabel}
          </button>
        </div>

        <svg viewBox="0 0 100 60" className="relative block h-[300px] w-full sm:h-[380px]" role="img"
          aria-label="A trade replayed from structure shift through entry to exit">

          {/* liquidity shelf that gets swept */}
          <motion.rect
            x="0" y="41" width="100" height="5"
            fill="rgba(91,141,239,0.10)"
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ duration: 0.8, delay: 0.4 }}
          />
          <motion.line
            x1="0" y1="43.5" x2="100" y2="43.5"
            stroke="rgba(91,141,239,0.35)" strokeWidth="0.2" strokeDasharray="1 1.5"
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ duration: 0.8, delay: 0.4 }}
          />

          {/* profit zone from entry to target */}
          <motion.rect
            x="50" y="12" width="50" height="14"
            fill="rgba(14,203,129,0.09)"
            initial={{ opacity: 0 }}
            animate={stage >= 2 ? { opacity: 1 } : { opacity: 0 }}
            transition={{ duration: 0.6 }}
          />

          {/* the price path, drawing itself */}
          <motion.path
            key={runId}
            d={PATH}
            fill="none"
            stroke="#EAECEF"
            strokeWidth="0.55"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: reduced ? 1 : 0 }}
            animate={inView ? { pathLength: 1 } : {}}
            transition={{ duration: reduced ? 0 : 5.2, ease: "linear" }}
          />

          {/* stage markers */}
          {STAGES.map((s, i) => {
            const on = stage >= i;
            const [cx, cy] = s.at;
            const label = steps[i]?.key ?? "";
            return (
              <g key={label}>
                {s.dashed && (
                  <motion.line
                    x1={cx} y1={cy} x2="100" y2={cy}
                    stroke={STROKE[s.tone]} strokeWidth="0.2" strokeDasharray="1 1.2"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: on ? 0.65 : 0 }}
                    transition={{ duration: 0.4 }}
                  />
                )}
                <motion.circle
                  cx={cx} cy={cy} r="1.1"
                  fill={STROKE[s.tone]}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: on ? 1 : 0, opacity: on ? 1 : 0 }}
                  transition={{ type: "spring", stiffness: 320, damping: 18 }}
                  style={{ transformOrigin: `${cx}px ${cy}px` }}
                />
                {on && !reduced && (
                  <motion.circle
                    cx={cx} cy={cy} r="1.1"
                    fill="none" stroke={STROKE[s.tone]} strokeWidth="0.2"
                    initial={{ scale: 1, opacity: 0.8 }}
                    animate={{ scale: 4, opacity: 0 }}
                    transition={{ duration: 1.4, repeat: Infinity, repeatDelay: 0.6 }}
                    style={{ transformOrigin: `${cx}px ${cy}px` }}
                  />
                )}
                <motion.text
                  x={cx} y={cy - 2.6}
                  textAnchor="middle"
                  fill={STROKE[s.tone]}
                  style={{ fontSize: "2.4px", fontFamily: "ui-monospace, monospace", fontWeight: 600 }}
                  initial={{ opacity: 0, y: 2 }}
                  animate={{ opacity: on ? 1 : 0 }}
                  transition={{ duration: 0.4 }}
                >
                  {label}
                </motion.text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* stage legend — rows light up in step with the chart */}
      <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {steps.map((s, i) => {
          const on = stage >= i;
          return (
            <div
              key={s.key}
              className={`rounded-xl border p-3 transition-all duration-500 ${
                on
                  ? "border-gold/25 bg-gold/[0.05]"
                  : "border-white/[0.05] bg-white/[0.015] opacity-45"
              }`}
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-gold">
                {s.key}
              </div>
              <div className="mt-1.5 text-sm font-medium text-mist-100">{s.label}</div>
              <div className="mt-1 text-xs leading-snug text-mist-500">{s.desc}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ScalpReplay;
