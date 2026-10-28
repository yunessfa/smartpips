import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { EASE } from "../motion.jsx";

/**
 * Section 7 visual: the Smart Exit engine re-evaluating a live position.
 *
 * A single open position sits on the left; the AI verdict panel on the right
 * cycles through the four real states. Crucially the chart reacts too — the
 * stop line moves when the verdict says trail, the size bar halves when it
 * says close part, the whole frame flashes red on exit. Without that coupling
 * this would just be four cards fading in and out, which proves nothing.
 *
 * Auto-advances while in view; clicking a state pins it, because a reader who
 * engages should not have the content pulled out from under them.
 */

const TONE = {
  info: { text: "text-info", border: "border-info/35", bg: "bg-info/[0.07]", dot: "bg-info", raw: "#5B8DEF" },
  gold: { text: "text-gold", border: "border-gold/35", bg: "bg-gold/[0.07]", dot: "bg-gold", raw: "#F0B90B" },
  up: { text: "text-up", border: "border-up/35", bg: "bg-up/[0.07]", dot: "bg-up", raw: "#0ECB81" },
  down: { text: "text-down", border: "border-down/35", bg: "bg-down/[0.07]", dot: "bg-down", raw: "#F6465A" },
};

// Where the stop line sits (%) and how much of the position remains, per state.
const REACTION = [
  { stop: 78, size: 100, pnl: "+186.40", pnlPct: "+3.1%" },   // HOLD
  { stop: 58, size: 100, pnl: "+248.60", pnlPct: "+4.2%" },   // TRAILING STOP
  { stop: 58, size: 50, pnl: "+312.90", pnlPct: "+5.3%" },    // CLOSE PART
  { stop: 58, size: 0, pnl: "+298.10", pnlPct: "+5.0%" },     // EXIT NOW
];

const SERIES = [42, 46, 44, 50, 48, 55, 52, 60, 57, 64, 61, 68, 72, 69, 76, 74, 81, 78, 85, 88];

export function SmartExit({ states, positionLabel, verdictLabel, className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref, { margin: "-25% 0px" });
  const [index, setIndex] = useState(0);
  const [pinned, setPinned] = useState(false);

  useEffect(() => {
    if (!inView || pinned || reduced) return undefined;
    const id = setInterval(() => setIndex((i) => (i + 1) % states.length), 3400);
    return () => clearInterval(id);
  }, [inView, pinned, reduced, states.length]);

  const active = states[index];
  const tone = TONE[active.tone] ?? TONE.gold;
  const react = REACTION[index] ?? REACTION[0];

  return (
    <div ref={ref} className={`grid gap-6 lg:grid-cols-[1.15fr_1fr] lg:gap-8 ${className}`}>

      {/* ---- the position, reacting to the verdict ---- */}
      <motion.div
        animate={{
          borderColor: index === 3 ? "rgba(246,70,90,0.35)" : "rgba(255,255,255,0.07)",
        }}
        transition={{ duration: 0.5 }}
        className="relative overflow-hidden rounded-2xl border bg-ink-900/70 p-4 sm:p-5"
      >
        <div className="sx-grid sx-grid-mask pointer-events-none absolute inset-0 opacity-50" />

        <div className="relative flex items-start justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-mist-500">
              {positionLabel}
            </div>
            <div className="mt-1 flex items-center gap-2">
              <span className="tnum text-base font-semibold text-mist-100">BTCUSDT</span>
              <span className="rounded bg-up/20 px-1.5 py-0.5 font-mono text-[9px] font-bold text-up">
                LONG 20×
              </span>
            </div>
          </div>
          <div className="text-end">
            <motion.div
              key={react.pnl}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: EASE }}
              className="tnum text-lg font-semibold text-up"
            >
              {react.pnl}
            </motion.div>
            <div className="tnum text-[11px] text-up/70">{react.pnlPct}</div>
          </div>
        </div>

        {/* chart with a stop line that actually moves */}
        <div className="relative mt-4 h-44 sm:h-52">
          <div className="flex h-full items-end gap-[3px]">
            {SERIES.map((v, i) => (
              <div
                key={i}
                className={`flex-1 rounded-[1px] ${
                  i === 0 || v >= SERIES[i - 1] ? "bg-up/60" : "bg-down/60"
                }`}
                style={{ height: `${(v / 88) * 100}%` }}
              />
            ))}
          </div>

          {/* entry */}
          <div className="absolute inset-x-0 flex items-center" style={{ top: "70%" }}>
            <div className="h-0 flex-1 border-t border-gold/60" />
            <span className="ms-1 rounded bg-gold/15 px-1 py-px font-mono text-[8px] text-gold">ENTRY</span>
          </div>

          {/* the stop — animates upward when the verdict says trail */}
          <motion.div
            className="absolute inset-x-0 flex items-center"
            animate={{ top: `${react.stop}%` }}
            transition={{ duration: 0.7, ease: EASE }}
            style={{ top: "78%" }}
          >
            <div className="h-0 flex-1 border-t border-dashed border-down/60" />
            <span className="ms-1 rounded bg-down/15 px-1 py-px font-mono text-[8px] text-down">SL</span>
          </motion.div>

          {index === 3 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="pointer-events-none absolute inset-0 rounded-lg bg-down/[0.07]"
            />
          )}
        </div>

        {/* remaining size — halves on "close part", empties on "exit" */}
        <div className="relative mt-4">
          <div className="mb-1.5 flex items-center justify-between text-[10px] text-mist-500">
            <span className="uppercase tracking-wider">Position size</span>
            <span className="tnum">{react.size}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
            <motion.div
              className="h-full rounded-full bg-gold"
              animate={{ width: `${react.size}%` }}
              transition={{ duration: 0.7, ease: EASE }}
            />
          </div>
        </div>
      </motion.div>

      {/* ---- the verdict ---- */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${tone.dot} live-dot`} />
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-mist-500">
            {verdictLabel}
          </span>
        </div>

        <div className="relative min-h-[170px]">
          <AnimatePresence mode="wait">
            <motion.div
              key={active.state}
              initial={{ opacity: 0, y: 14, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -10, filter: "blur(6px)" }}
              transition={{ duration: 0.45, ease: EASE }}
              className={`rounded-2xl border p-5 ${tone.border} ${tone.bg}`}
            >
              <div className={`font-mono text-[11px] font-bold uppercase tracking-[0.18em] ${tone.text}`}>
                {active.state}
              </div>
              <div className="mt-2.5 text-xl font-semibold text-mist-100">{active.headline}</div>
              <p className="mt-2 text-sm leading-relaxed text-mist-300">{active.reason}</p>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* state selector doubles as a progress indicator */}
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {states.map((s, i) => {
            const t = TONE[s.tone] ?? TONE.gold;
            const on = i === index;
            return (
              <button
                key={s.state}
                type="button"
                onClick={() => { setIndex(i); setPinned(true); }}
                className={`relative overflow-hidden rounded-lg border px-2 py-2 text-center
                  font-mono text-[9px] uppercase tracking-wider transition-all duration-300 ${
                  on ? `${t.border} ${t.bg} ${t.text}`
                     : "border-white/[0.06] text-mist-500 hover:border-white/15 hover:text-mist-300"
                }`}
              >
                {s.state}
                {on && !pinned && !reduced && (
                  <motion.span
                    key={`bar-${i}`}
                    className={`absolute bottom-0 start-0 h-px ${t.dot}`}
                    initial={{ width: "0%" }}
                    animate={{ width: "100%" }}
                    transition={{ duration: 3.4, ease: "linear" }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default SmartExit;
