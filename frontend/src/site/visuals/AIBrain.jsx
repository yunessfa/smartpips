import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";

/**
 * Section 4 visual: six market inputs converging into a single AI core.
 *
 * The convergence is driven by scroll position rather than a timer, so the
 * reader controls the pace and the motion always feels like a direct response
 * to their own action. Nodes start wide and drift inward as the section is
 * read; the connector lines draw themselves over the same progress.
 *
 * Built with SVG + transforms (no canvas): there are only ~20 elements here,
 * the labels must stay real selectable text for accessibility and RTL, and
 * SVG gives crisp lines at any DPI for free.
 */

const RADIUS_START = 46;   // % of the square container
const RADIUS_END = 33;

/** One orbiting input node. Owns its own transforms so hooks stay top-level. */
function BrainNode({ index, total, label, desc, progress, reduced }) {
  const angle = (-90 + (index * 360) / total) * (Math.PI / 180);
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);

  const r = useTransform(progress, [0, 1], [RADIUS_START, RADIUS_END]);
  const left = useTransform(r, (v) => `${50 + cos * v}%`);
  const top = useTransform(r, (v) => `${50 + sin * v}%`);
  const opacity = useTransform(progress, [0, 0.25, 1], [0, 1, 1]);
  const scale = useTransform(progress, [0, 0.4, 1], [0.82, 1, 1.03]);

  const style = reduced
    ? { left: `${50 + cos * RADIUS_END}%`, top: `${50 + sin * RADIUS_END}%` }
    : { left, top, opacity, scale };

  return (
    <motion.div
      style={style}
      className="absolute -translate-x-1/2 -translate-y-1/2 w-[124px] sm:w-[150px] text-center"
    >
      <div className="sx-card rounded-xl px-3 py-2.5">
        <div className="text-[11px] sm:text-xs font-semibold text-mist-100 leading-tight">
          {label}
        </div>
        <div className="mt-1 text-[9px] sm:text-[10px] text-mist-500 leading-snug hidden sm:block">
          {desc}
        </div>
      </div>
    </motion.div>
  );
}

/** Connector from one node to the core, drawing itself as the section scrolls. */
function Connector({ index, total, progress, reduced }) {
  const angle = (-90 + (index * 360) / total) * (Math.PI / 180);
  const r = useTransform(progress, [0, 1], [RADIUS_START, RADIUS_END]);
  const x2 = useTransform(r, (v) => 50 + Math.cos(angle) * v);
  const y2 = useTransform(r, (v) => 50 + Math.sin(angle) * v);
  const pathLength = useTransform(progress, [0.1, 0.7], [0, 1]);
  const opacity = useTransform(progress, [0.1, 0.5], [0, 1]);

  if (reduced) {
    return (
      <line
        x1="50" y1="50"
        x2={50 + Math.cos(angle) * RADIUS_END}
        y2={50 + Math.sin(angle) * RADIUS_END}
        stroke="rgba(240,185,11,0.28)"
        strokeWidth="0.25"
      />
    );
  }

  return (
    <motion.line
      x1="50" y1="50" x2={x2} y2={y2}
      stroke="rgba(240,185,11,0.32)"
      strokeWidth="0.25"
      style={{ pathLength, opacity }}
    />
  );
}

/** A packet of data travelling inward along one connector. */
function Packet({ index, total, progress, reduced }) {
  const angle = (-90 + (index * 360) / total) * (Math.PI / 180);
  if (reduced) return null;
  return (
    <motion.circle
      r="0.7"
      fill="rgba(252,213,53,0.95)"
      initial={{ opacity: 0 }}
      animate={{
        cx: [50 + Math.cos(angle) * RADIUS_START, 50 + Math.cos(angle) * 8],
        cy: [50 + Math.sin(angle) * RADIUS_START, 50 + Math.sin(angle) * 8],
        opacity: [0, 1, 1, 0],
      }}
      transition={{
        duration: 2.6,
        delay: index * 0.42,
        repeat: Infinity,
        repeatDelay: 0.7,
        ease: "easeIn",
        times: [0, 0.15, 0.8, 1],
      }}
    />
  );
}

export function AIBrain({ inputs, coreLabel, className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 85%", "center 45%"],
  });
  // Smoothing prevents the nodes from snapping during fast scroll flicks.
  const progress = useSpring(scrollYProgress, { stiffness: 80, damping: 24, mass: 0.5 });

  const total = inputs.length;
  const coreScale = useTransform(progress, [0, 1], [0.86, 1]);
  const coreGlow = useTransform(progress, [0, 1], [0.25, 1]);

  return (
    <div
      ref={ref}
      className={`relative mx-auto aspect-square w-full max-w-[620px] ${className}`}
    >
      {/* connectors + packets, in a 100x100 user-space so all maths is in % */}
      <svg
        viewBox="0 0 100 100"
        className="absolute inset-0 h-full w-full overflow-visible"
        aria-hidden
      >
        {inputs.map((_, i) => (
          <Connector key={`c${i}`} index={i} total={total} progress={progress} reduced={reduced} />
        ))}
        {inputs.map((_, i) => (
          <Packet key={`p${i}`} index={i} total={total} progress={progress} reduced={reduced} />
        ))}
      </svg>

      {/* the core */}
      <motion.div
        style={reduced ? undefined : { scale: coreScale }}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
      >
        <div className="relative grid h-28 w-28 sm:h-36 sm:w-36 place-items-center">
          {/* expanding rings */}
          {!reduced && [0, 1, 2].map((i) => (
            <span
              key={i}
              className="absolute h-full w-full rounded-full border border-gold/25 animate-pulse-ring"
              style={{ animationDelay: `${i * 0.8}s` }}
            />
          ))}
          <motion.div
            style={reduced ? undefined : { opacity: coreGlow }}
            className="absolute h-[150%] w-[150%] rounded-full sx-spot"
          />
          <div className="relative grid h-20 w-20 sm:h-24 sm:w-24 place-items-center rounded-full
            border border-gold/35 bg-ink-900/90 shadow-glow backdrop-blur">
            <span className="px-2 text-center font-mono text-[9px] sm:text-[10px] uppercase
              tracking-[0.16em] text-gold leading-tight">
              {coreLabel}
            </span>
          </div>
        </div>
      </motion.div>

      {/* input nodes */}
      {inputs.map((input, i) => (
        <BrainNode
          key={input.label}
          index={i}
          total={total}
          label={input.label}
          desc={input.desc}
          progress={progress}
          reduced={reduced}
        />
      ))}
    </div>
  );
}

export default AIBrain;
