import { useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";

/**
 * Section 3: "Six Inputs. One Decision."
 *
 * The previous version of this section failed for a compositional reason, not
 * an aesthetic one: a small diagram floating in a tall black container. The
 * fix is structural — the visual now sizes itself to the section rather than
 * sitting inside it, the core is ~32% of the frame, and the six inputs are
 * pushed out to the edges so the negative space between them is *spanned by
 * the connections* instead of just being empty.
 *
 * The stage machine (inputs → connections → flow → core → verdict) fires once
 * on entry. It is a five-beat argument and it should land in about 3.5s.
 */

// Six anchor points on an ellipse. Deliberately not evenly spaced: the three
// on each side are grouped, which reads as designed rather than auto-generated.
const POS = [
  { x: 50, y: 4, anchor: "top" },     // Market Structure
  { x: 93, y: 27, anchor: "right" },  // Order Flow
  { x: 93, y: 73, anchor: "right" },  // Liquidity
  { x: 50, y: 96, anchor: "bottom" }, // Volatility
  { x: 7, y: 73, anchor: "left" },    // Risk
  { x: 7, y: 27, anchor: "left" },    // Trade History
];

const STAGE_AT = [0, 700, 1400, 2300, 3100]; // ms offsets for the five beats

export function EngineCore({ inputs = [], coreLabel, verdictLabel, className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref, { once: true, margin: "-20% 0px" });
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (reduced) {
      setStage(4);
      return undefined;
    }
    if (!inView) return undefined;
    const timers = STAGE_AT.map((ms, i) => setTimeout(() => setStage(i), ms));
    return () => timers.forEach(clearTimeout);
  }, [inView, reduced]);

  const nodes = inputs.slice(0, 6);

  return (
    <div ref={ref} className={`relative w-full ${className}`}>
      {/* ------------------------------------------------ desktop radial */}
      <div className="relative mx-auto hidden aspect-[16/10] w-full max-w-[1080px] lg:block">
        {/* Connections. One SVG behind everything, so the lines are true
            straight runs from each node to the core rather than CSS approximations. */}
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          aria-hidden
        >
          {POS.map((p, i) => (
            <g key={i}>
              <motion.line
                x1={p.x}
                y1={p.y}
                x2={50}
                y2={50}
                stroke="rgba(240,184,11,0.22)"
                strokeWidth={0.18}
                vectorEffect="non-scaling-stroke"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={stage >= 1 ? { pathLength: 1, opacity: 1 } : {}}
                transition={{ duration: 0.7, delay: i * 0.08, ease: [0.2, 0.7, 0.3, 1] }}
              />
              {/* Data packet travelling inward. Starts at beat 3 and keeps
                  looping: the engine is described in the present tense. */}
              {stage >= 2 && !reduced && (
                <motion.circle
                  r={0.7}
                  fill="#FFD45A"
                  initial={{ cx: p.x, cy: p.y, opacity: 0 }}
                  animate={{
                    cx: [p.x, 50],
                    cy: [p.y, 50],
                    opacity: [0, 1, 1, 0],
                  }}
                  transition={{
                    duration: 1.6,
                    delay: i * 0.18,
                    repeat: Infinity,
                    repeatDelay: 1.1,
                    ease: "easeIn",
                  }}
                />
              )}
            </g>
          ))}
        </svg>

        {/* Input nodes */}
        {nodes.map((node, i) => {
          const p = POS[i];
          const translate =
            p.anchor === "left"
              ? "translate(0,-50%)"
              : p.anchor === "right"
                ? "translate(-100%,-50%)"
                : "translate(-50%,-50%)";
          return (
            <motion.div
              key={node.title}
              className="absolute w-[210px]"
              style={{ left: `${p.x}%`, top: `${p.y}%`, transform: translate }}
              initial={{ opacity: 0, scale: 0.9, filter: "blur(6px)" }}
              animate={stage >= 0 && inView ? { opacity: 1, scale: 1, filter: "blur(0px)" } : {}}
              transition={{ duration: 0.6, delay: i * 0.09, ease: [0.2, 0.7, 0.3, 1] }}
            >
              <div className="rounded-xl border border-white/10 bg-sp-s2/80 px-4 py-3 backdrop-blur-sm transition-colors duration-500 hover:border-signal/30">
                <div className="text-[13px] font-semibold text-sp-t1">{node.title}</div>
                <div className="mt-1 text-[11px] leading-relaxed text-sp-t3">{node.note}</div>
              </div>
            </motion.div>
          );
        })}

        {/* AI core — sized as a share of the frame, which is what keeps it
            dominant at every breakpoint. */}
        <div className="absolute left-1/2 top-1/2 h-[32%] w-[32%] -translate-x-1/2 -translate-y-1/2">
          <CoreOrb active={stage >= 3} label={coreLabel} reduced={reduced} />
        </div>
      </div>

      {/* ------------------------------------------------- mobile stacked */}
      <div className="lg:hidden">
        <div className="mx-auto mb-8 h-40 w-40">
          <CoreOrb active={stage >= 3} label={coreLabel} reduced={reduced} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {nodes.map((node, i) => (
            <motion.div
              key={node.title}
              className="rounded-xl border border-white/10 bg-sp-s2/70 px-4 py-3"
              initial={{ opacity: 0, y: 14 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: i * 0.07 }}
            >
              <div className="text-[13px] font-semibold text-sp-t1">{node.title}</div>
              <div className="mt-1 text-[11px] leading-relaxed text-sp-t3">{node.note}</div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Verdict — the fifth beat, and the payoff line of the section. */}
      <motion.div
        className="mt-10 flex justify-center lg:mt-4"
        initial={{ opacity: 0, y: 16 }}
        animate={stage >= 4 ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, ease: [0.2, 0.7, 0.3, 1] }}
      >
        <div className="inline-flex items-center gap-3 rounded-full border border-signal/25 bg-signal/[0.07] px-6 py-2.5">
          <span className="h-1.5 w-1.5 rounded-full bg-signal" />
          <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-signal-soft">
            {verdictLabel}
          </span>
        </div>
      </motion.div>
    </div>
  );
}

/** The core itself: concentric rings that spin up once the data arrives. */
function CoreOrb({ active, label, reduced }) {
  return (
    <div className="relative h-full w-full">
      {/* Ambient bloom. Kept wide and very low opacity so the core glows
          without the section turning gold. */}
      <div
        className="absolute -inset-[60%] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(240,184,11,0.16) 0%, rgba(240,184,11,0.05) 35%, transparent 70%)",
          opacity: active ? 1 : 0.25,
          transition: "opacity 1.2s ease",
        }}
      />

      {!reduced &&
        active &&
        [0, 1, 2].map((i) => (
          <span
            key={i}
            className="absolute inset-0 rounded-full border border-signal/25 animate-pulse-ring"
            style={{ animationDelay: `${i * 0.8}s` }}
          />
        ))}

      <motion.div
        className="absolute inset-[14%] rounded-full border border-signal/20"
        animate={reduced || !active ? {} : { rotate: 360 }}
        transition={{ duration: 26, repeat: Infinity, ease: "linear" }}
        style={{ borderStyle: "dashed" }}
      />
      <motion.div
        className="absolute inset-[26%] rounded-full border border-signal/30"
        animate={reduced || !active ? {} : { rotate: -360 }}
        transition={{ duration: 18, repeat: Infinity, ease: "linear" }}
      />

      <div className="absolute inset-[36%] flex items-center justify-center rounded-full border border-signal/40 bg-sp-base/80 backdrop-blur-sm">
        <span
          className="px-1 text-center font-mono text-[9px] uppercase leading-tight tracking-[0.16em] transition-colors duration-700"
          style={{ color: active ? "#FFD45A" : "#6B7280" }}
        >
          {label}
        </span>
      </div>
    </div>
  );
}

export default EngineCore;
