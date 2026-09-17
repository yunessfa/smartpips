import { useEffect, useRef, useState } from "react";
import {
  motion,
  useInView,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";

/**
 * Motion primitives for the public site.
 *
 * Two rules hold everywhere in this file:
 *   1. Only `transform` and `opacity` (and `filter` for blur-to-focus) are
 *      animated, so every effect stays on the GPU compositor.
 *   2. Every scroll animation runs `once`, so after a section has been seen
 *      it stops costing anything at all.
 *
 * `useReducedMotion` is honoured by each primitive individually rather than
 * relying only on the global CSS override, because Framer drives inline
 * styles that CSS `animation: none` cannot reach.
 */

export const EASE = [0.2, 0.7, 0.3, 1];

/* ------------------------------------------------------------- reveal --- */

/**
 * The workhorse: fades a block up into place as it enters the viewport.
 * `blur` adds the blur-to-focus feel; keep it for headlines, skip it for
 * long body copy where blurred text reads as a rendering bug.
 */
export function Reveal({
  children,
  delay = 0,
  y = 24,
  blur = false,
  once = true,
  className = "",
  as = "div",
}) {
  const reduced = useReducedMotion();
  const M = motion[as] || motion.div;
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <M
      className={className}
      initial={{ opacity: 0, y, filter: blur ? "blur(10px)" : "blur(0px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once, margin: "-12% 0px -12% 0px" }}
      transition={{ duration: 0.85, delay, ease: EASE }}
    >
      {children}
    </M>
  );
}

/** Parent that releases its children one after another. */
export function Stagger({ children, delay = 0, gap = 0.09, className = "" }) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-10% 0px" }}
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: gap, delayChildren: delay } },
      }}
    >
      {children}
    </motion.div>
  );
}

/** Child of <Stagger>. */
export function StaggerItem({ children, y = 22, className = "" }) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y },
        show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: EASE } },
      }}
    >
      {children}
    </motion.div>
  );
}

/* --------------------------------------------------------- text reveal --- */

/**
 * Headline reveal, word by word, each rising from behind a clipping mask.
 *
 * Splitting on words (not characters) is deliberate: Persian is a cursive
 * script, and splitting Persian into individual characters breaks the glyph
 * joins and renders the word as disconnected letters.
 */
export function TextReveal({
  text,
  className = "",
  delay = 0,
  wordDelay = 0.055,
  immediate = false,
}) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref, { once: true, margin: "0px" });
  const words = String(text).split(" ");

  // Masked words are positioned at y:110% and are therefore *invisible* until
  // their animation runs. That makes the trigger safety-critical: if it never
  // resolves, the headline silently disappears — which is exactly what
  // happened to the hero when this relied on `whileInView` alone.
  //
  // Two defences: `immediate` plays on mount (used for above-the-fold copy,
  // where waiting for an intersection callback buys nothing), and everything
  // else animates from an explicit `useInView` boolean rather than Framer's
  // implicit viewport tracking, so the visible state is always something we
  // can reason about.
  const play = immediate || inView;

  if (reduced) return <span className={className}>{text}</span>;

  return (
    <span ref={ref} className={className}>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          // `pb-[0.12em]` gives descenders (g, y, j) room inside the mask;
          // without it the clip shears the bottom off the typeface.
          className="inline-block overflow-hidden align-bottom pb-[0.12em]"
        >
          <motion.span
            className="inline-block"
            initial={{ y: "110%" }}
            animate={play ? { y: 0 } : { y: "110%" }}
            transition={{ duration: 0.9, delay: delay + i * wordDelay, ease: EASE }}
          >
            {word}
            {i < words.length - 1 ? "\u00A0" : ""}
          </motion.span>
        </span>
      ))}
    </span>
  );
}

/* ------------------------------------------------------------ counter --- */

/**
 * Counts up when scrolled into view. Uses rAF rather than a Framer spring so
 * the formatted output (suffixes, decimals, thousands separators) stays under
 * our control, and eases out so the last digits settle rather than snap.
 */
export function Counter({
  to,
  from = 0,
  duration = 1900,
  decimals = 0,
  prefix = "",
  suffix = "",
  separator = true,
  className = "",
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-15% 0px" });
  const reduced = useReducedMotion();
  const [value, setValue] = useState(from);

  useEffect(() => {
    if (!inView) return undefined;
    if (reduced) { setValue(to); return undefined; }
    let raf = 0;
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);      // easeOutCubic
      setValue(from + (to - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, from, duration, reduced]);

  const shown = separator
    ? value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    : value.toFixed(decimals);

  return (
    <span ref={ref} className={`tnum ${className}`}>
      {prefix}{shown}{suffix}
    </span>
  );
}

/* ---------------------------------------------------------- parallax ---- */

/** Vertical parallax driven by the element's own scroll progress. */
export function Parallax({ children, distance = 60, className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [distance, -distance]);
  const smooth = useSpring(y, { stiffness: 90, damping: 26, mass: 0.4 });
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <div ref={ref} className={className}>
      <motion.div style={{ y: smooth }}>{children}</motion.div>
    </div>
  );
}

/* ---------------------------------------------------------- magnetic ---- */

/**
 * Pulls an element gently toward the cursor. Writes CSS custom properties
 * instead of React state so the pointer move never triggers a re-render.
 */
export function Magnetic({ children, strength = 0.32, className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return undefined;
    // Coarse pointers (touch) have no hover state; skip the listeners there.
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;

    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      el.style.setProperty("--mx", `${dx * strength}px`);
      el.style.setProperty("--my", `${dy * strength}px`);
    };
    const onLeave = () => {
      el.style.setProperty("--mx", "0px");
      el.style.setProperty("--my", "0px");
    };

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [strength, reduced]);

  return (
    <span ref={ref} className={`sx-magnetic inline-flex ${className}`}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------- mouse follow --- */

/**
 * Returns a normalised pointer position (-1..1) relative to the element.
 * Used to tilt the hero visual and the dashboard mockup toward the cursor.
 */
export function useMouseTilt(max = 8) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const [tilt, setTilt] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return undefined;
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;

    let raf = 0;
    const onMove = (e) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect();
        const nx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
        const ny = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
        setTilt({ x: Math.max(-1, Math.min(1, nx)) * max, y: Math.max(-1, Math.min(1, ny)) * max });
      });
    };
    const onLeave = () => setTilt({ x: 0, y: 0 });

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [max, reduced]);

  return { ref, tilt };
}

/* -------------------------------------------------------- canvas gate --- */

/**
 * True only while the element is on screen. Canvas visuals use this to stop
 * their rAF loop entirely when scrolled past — the single biggest reason this
 * page stays smooth with this many live visuals on it.
 */
export function useOnScreen(margin = "120px") {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const io = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [margin]);

  return { ref, visible };
}

/** Scroll progress (0..1) across a target element. */
export function useSectionProgress(offset = ["start end", "end start"]) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset });
  return { ref, progress: scrollYProgress };
}

export { motion, useReducedMotion, useInView, useScroll, useTransform, useSpring };
