import { Link } from "react-router-dom";
import { Magnetic } from "./motion.jsx";

/**
 * Layout and UI atoms for the public site.
 *
 * These are intentionally separate from `components/ui.jsx` (the panel's kit).
 * The panel optimises for density and scanability; the marketing site
 * optimises for rhythm and air. Sharing one set of primitives across both
 * would compromise each.
 *
 * Everything here uses logical properties (`ms-`, `me-`, `text-start`) so the
 * whole site mirrors correctly in Persian with no RTL-specific branches.
 */

/* ------------------------------------------------------------ layout ---- */

/** Consistent max-width and gutters for every section. */
export function Container({ children, className = "", size = "default" }) {
  const max = size === "narrow" ? "max-w-3xl" : size === "wide" ? "max-w-[1440px]" : "max-w-[1200px]";
  return <div className={`${max} mx-auto px-5 sm:px-8 ${className}`}>{children}</div>;
}

/**
 * A page section. Vertical rhythm is set here once so no section can drift
 * out of step with the others.
 */
export function Section({
  children,
  className = "",
  id,
  spacing = "default",
  bleed = false,
}) {
  const pad = {
    tight: "py-16 sm:py-20",
    default: "py-24 sm:py-32",
    loose: "py-32 sm:py-44",
  }[spacing];
  return (
    <section id={id} className={`relative ${pad} ${bleed ? "" : "overflow-hidden"} ${className}`}>
      {children}
    </section>
  );
}

/* --------------------------------------------------------- typography --- */

/** Small monospaced label above a headline. Establishes the terminal feel. */
export function Eyebrow({ children, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2 font-mono text-[11px] uppercase
      tracking-[0.22em] text-gold ${className}`}>
      <span className="h-px w-6 bg-gold/50" />
      {children}
    </span>
  );
}

/** Section headline. */
export function Display({ children, className = "", size = "md", as: Tag = "h2" }) {
  const scale = {
    sm: "text-3xl sm:text-4xl",
    md: "text-4xl sm:text-5xl lg:text-[3.4rem]",
    lg: "text-5xl sm:text-6xl lg:text-7xl",
    xl: "text-[2.75rem] sm:text-6xl lg:text-[5rem]",
  }[size];
  return (
    <Tag className={`site-display text-mist-100 ${scale} ${className}`}>{children}</Tag>
  );
}

/** Body copy under a headline. Capped for a comfortable measure. */
export function Lead({ children, className = "" }) {
  return (
    <p className={`text-mist-300 text-base sm:text-lg leading-relaxed max-w-2xl ${className}`}>
      {children}
    </p>
  );
}

/** Standard section intro: eyebrow + headline + lead, centred or start-aligned. */
export function SectionHead({ eyebrow, title, lead, align = "start", className = "" }) {
  const alignment = align === "center" ? "text-center items-center mx-auto" : "text-start items-start";
  return (
    <div className={`flex flex-col gap-5 ${alignment} ${align === "center" ? "max-w-3xl" : ""} ${className}`}>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <Display>{title}</Display>
      {lead && <Lead className={align === "center" ? "mx-auto" : ""}>{lead}</Lead>}
    </div>
  );
}

/* ------------------------------------------------------------ buttons --- */

/**
 * Primary call to action. Gold is reserved for this and nothing else — one
 * per screen — which is what keeps the accent feeling valuable.
 */
export function GoldButton({ to, href, children, className = "", size = "md", magnetic = true }) {
  const pad = size === "lg" ? "px-7 py-3.5 text-[15px]" : "px-5 py-2.5 text-sm";
  const cls = `sx-sheen group relative inline-flex items-center justify-center gap-2 rounded-full
    bg-gold ${pad} font-semibold text-ink-950 shadow-glow-sm
    transition-[box-shadow,background-color] duration-300
    hover:bg-gold-soft hover:shadow-glow focus:outline-none focus-visible:ring-2
    focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 ${className}`;

  const inner = to
    ? <Link to={to} className={cls}>{children}</Link>
    : <a href={href} className={cls}>{children}</a>;

  return magnetic ? <Magnetic strength={0.25}>{inner}</Magnetic> : inner;
}

/** Secondary action — quiet, outlined, never competes with the gold CTA. */
export function GhostButton({ to, href, children, className = "", size = "md" }) {
  const pad = size === "lg" ? "px-7 py-3.5 text-[15px]" : "px-5 py-2.5 text-sm";
  const cls = `inline-flex items-center justify-center gap-2 rounded-full border border-white/12
    ${pad} font-medium text-mist-100 transition-colors duration-300
    hover:border-white/25 hover:bg-white/[0.04] focus:outline-none focus-visible:ring-2
    focus-visible:ring-white/30 ${className}`;
  return to
    ? <Link to={to} className={cls}>{children}</Link>
    : <a href={href} className={cls}>{children}</a>;
}

/* -------------------------------------------------------------- cards --- */

/** Glass surface with a light-catching top edge. */
export function GlassCard({ children, className = "", padded = true }) {
  return (
    <div className={`sx-card rounded-2xl ${padded ? "p-6 sm:p-7" : ""} ${className}`}>
      {children}
    </div>
  );
}

/**
 * Feature card with a genuine 3D tilt on hover.
 *
 * The tilt is CSS-only (`:hover` + `transform-style: preserve-3d`) rather than
 * JS pointer tracking, because a fixed subtle tilt reads as "premium depth"
 * while a cursor-tracked one on a grid of cards reads as "gimmick" — and it
 * costs zero JavaScript.
 */
export function TiltCard({ children, className = "" }) {
  return (
    <div className={`group [perspective:1200px] ${className}`}>
      <div className="sx-card h-full rounded-2xl p-6 sm:p-7 [transform-style:preserve-3d]
        transition-transform duration-500 ease-[cubic-bezier(.2,.7,.3,1)]
        group-hover:[transform:rotateX(4deg)_rotateY(-4deg)_translateZ(12px)]">
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ accents --- */

/** Soft gold light source. At most one per section. */
export function Spotlight({ className = "", size = 620 }) {
  return (
    <div
      aria-hidden
      className={`sx-spot pointer-events-none absolute rounded-full ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

/** Faint terminal grid, masked so it fades out at the edges. */
export function GridBackdrop({ className = "" }) {
  return (
    <div aria-hidden className={`sx-grid sx-grid-mask pointer-events-none absolute inset-0 ${className}`} />
  );
}

/** Full-bleed hairline divider between sections. */
export function Rule({ className = "" }) {
  return <div aria-hidden className={`sx-rule ${className}`} />;
}

/** Monospaced stat label/value pair used across several sections. */
export function Metric({ label, children, className = "" }) {
  return (
    <div className={className}>
      <div className="text-mist-100 text-3xl sm:text-4xl font-semibold">{children}</div>
      <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.18em] text-mist-500">
        {label}
      </div>
    </div>
  );
}

/** Small state pill (LONG / HOLD / EXIT NOW …). */
export function Pill({ children, tone = "neutral", className = "" }) {
  const tones = {
    neutral: "bg-white/[0.06] text-mist-300 border-white/10",
    gold: "bg-gold/12 text-gold border-gold/25",
    up: "bg-up/12 text-up border-up/25",
    down: "bg-down/12 text-down border-down/25",
    info: "bg-info/12 text-info border-info/25",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1
      font-mono text-[10px] uppercase tracking-[0.14em] ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}
