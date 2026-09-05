import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { useCopy } from "../copy.js";
import { EASE, Reveal, Stagger, StaggerItem, TextReveal } from "../motion.jsx";
import { GhostButton, GoldButton } from "../primitives.jsx";
import HeroChart from "../visuals/HeroChart.jsx";
import { IntelCanvas, NoiseCanvas, TransformBeam } from "../visuals/RawIntel.jsx";
import EngineCore from "../visuals/EngineCore.jsx";
import LayerChart from "../visuals/LayerChart.jsx";
import ScalpSequence from "../visuals/ScalpSequence.jsx";
import SmartExitLive from "../visuals/SmartExitLive.jsx";
import RegimeSim from "../visuals/RegimeSim.jsx";
import DashboardMockup from "../visuals/DashboardMockup.jsx";
import CTABackdrop from "../visuals/CTABackdrop.jsx";

/**
 * SmartPips landing page.
 *
 * The order of these sections is the design. It is an argument, read top to
 * bottom, and each section answers exactly one question:
 *
 *   Hero      what is it
 *   Context   why do I need it            (the problem)
 *   Engine    how does it think           (the method)
 *   Layers    what does it analyse        (the substance)
 *   Scalp     how does it help me enter
 *   Exit      how does it manage the trade
 *   Regime    does it understand my conditions
 *   Product   what does it look like      (the proof)
 *   How       how do I use it
 *   Trust     can I believe it            (the honesty)
 *   CTA       why now
 *
 * Two composition rules are enforced throughout, because the previous build
 * broke both:
 *   • No arbitrary `min-h-screen`. Section height comes from content, so we
 *     never ship a viewport of empty black.
 *   • Every section visual is at least as visually heavy as its text block.
 *     A 200px diagram under a 60px headline reads as an unfinished page.
 */

/* ---------------------------------------------------------- primitives -- */

/** Outer shell. 1440px max, content column 1280px. */
function Shell({ children, className = "", wide = false }) {
  return (
    <div
      className={`mx-auto w-full px-5 sm:px-8 lg:px-12 ${wide ? "max-w-site" : "max-w-content"} ${className}`}
    >
      {children}
    </div>
  );
}

function Section({ id, children, className = "", tone = "base" }) {
  const bg = tone === "deep" ? "bg-sp-deep" : tone === "void" ? "bg-sp-void" : "bg-sp-base";
  return (
    <section id={id} className={`relative ${bg} py-20 sm:py-28 lg:py-32 ${className}`}>
      {children}
    </section>
  );
}

function Eyebrow({ children }) {
  return (
    <div className="mb-5 flex items-center gap-2.5">
      <span className="h-1 w-1 rounded-full bg-signal" />
      <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-signal">
        {children}
      </span>
    </div>
  );
}

/**
 * Two-line display headline.
 *
 * `immediate` is passed for above-the-fold copy so the words animate on mount
 * rather than waiting on an intersection callback — the hero headline must
 * never be able to not appear.
 */
function Headline({ line1, line2, size = "md", immediate = false, muted = true }) {
  const scale =
    size === "lg"
      ? "text-[2.5rem] leading-[1.05] sm:text-display-md lg:text-display-lg"
      : "text-[2rem] leading-[1.08] sm:text-display-sm lg:text-display-md";
  return (
    <h2 className={`site-display ${scale} text-sp-t1`}>
      <span className="block">
        <TextReveal text={line1} immediate={immediate} />
      </span>
      <span className={`block ${muted ? "text-sp-t3" : "text-sp-t1"}`}>
        <TextReveal text={line2} delay={0.1} immediate={immediate} />
      </span>
    </h2>
  );
}

function Lead({ children, className = "" }) {
  return (
    <p className={`max-w-xl text-[15px] leading-relaxed text-sp-t2 sm:text-base ${className}`}>
      {children}
    </p>
  );
}

/** Standard section header: eyebrow, headline, lead. */
function Head({ eyebrow, line1, line2, lead, center = false, size = "md" }) {
  return (
    <div className={center ? "mx-auto max-w-2xl text-center" : "max-w-2xl"}>
      <Reveal>
        <div className={center ? "flex justify-center" : ""}>
          <Eyebrow>{eyebrow}</Eyebrow>
        </div>
      </Reveal>
      <Headline line1={line1} line2={line2} size={size} />
      {lead && (
        <Reveal delay={0.15}>
          <Lead className={`mt-5 ${center ? "mx-auto" : ""}`}>{lead}</Lead>
        </Reveal>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- hero -- */

function Hero({ c }) {
  const reduced = useReducedMotion();

  return (
    <section className="relative overflow-hidden bg-sp-void pb-16 pt-28 sm:pb-20 sm:pt-32 lg:pb-24 lg:pt-36">
      {/* Ambient depth. A single wide, very low-opacity gold bloom behind the
          chart — enough to lift it off the black, far short of a gradient. */}
      <div
        className="pointer-events-none absolute -top-40 end-[-10%] h-[720px] w-[720px] rounded-full opacity-60"
        style={{
          background:
            "radial-gradient(circle, rgba(240,184,11,0.10) 0%, rgba(240,184,11,0.03) 40%, transparent 70%)",
        }}
      />
      <div className="sx-grid sx-grid-mask pointer-events-none absolute inset-0 opacity-40" />

      <Shell wide className="relative">
        {/* 42/58 split. The chart is the larger half, but the text column has
            a hard minimum so it can never be squeezed into a corner. */}
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(420px,42fr)_58fr] lg:gap-10 xl:gap-16">
          {/* ------------------------------------------------------- copy */}
          <div className="relative z-10">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: EASE }}
            >
              <div className="mb-6 inline-flex items-center gap-2.5 rounded-full border border-signal/20 bg-signal/[0.05] px-3.5 py-1.5">
                <span className="relative flex h-1.5 w-1.5">
                  {!reduced && (
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal opacity-60" />
                  )}
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-signal" />
                </span>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-signal-soft">
                  {c.hero.eyebrow}
                </span>
              </div>
            </motion.div>

            {/* The visual focus of the page. Near-white, weight 700, tight
                leading, no gradient — contrast is what makes it dominant. */}
            <h1 className="site-display text-[2.6rem] leading-[1.03] text-sp-t1 sm:text-[3.4rem] lg:text-[4rem] xl:text-[4.5rem]">
              <span className="block">
                <TextReveal text={c.hero.line1} immediate delay={0.12} />
              </span>
              <span className="block">
                <TextReveal text={c.hero.line2} immediate delay={0.24} />
              </span>
            </h1>

            <motion.p
              className="mt-6 max-w-lg text-[15px] leading-relaxed text-sp-t2 sm:text-[16.5px]"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.6, ease: EASE }}
            >
              {c.hero.sub}
            </motion.p>

            <motion.div
              className="mt-9 flex flex-wrap items-center gap-3"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.75, ease: EASE }}
            >
              <GoldButton to="/register" size="lg">
                {c.hero.ctaPrimary}
              </GoldButton>
              <GhostButton href="#ai" size="lg">
                {c.hero.ctaSecondary}
              </GhostButton>
            </motion.div>

            {/* Intelligence status. Styled as a monospace readout with a
                vertical rail — machine output, not a bullet list. */}
            <motion.div
              className="mt-10 border-s border-sp-line ps-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 1.5 }}
            >
              {c.hero.status.map((line, i) => (
                <motion.div
                  key={line}
                  className="flex items-center gap-2.5 py-1"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.6, delay: 1.6 + i * 0.35, ease: EASE }}
                >
                  <motion.span
                    className="h-1 w-1 rounded-full bg-signal"
                    animate={reduced ? {} : { opacity: [0.35, 1, 0.35] }}
                    transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.5 }}
                  />
                  <span className="font-mono text-[11px] tracking-wide text-sp-t3">{line}</span>
                </motion.div>
              ))}
            </motion.div>
          </div>

          {/* ------------------------------------------------------ visual */}
          <motion.div
            className="relative"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.2, ease: EASE }}
          >
            <div className="relative overflow-hidden rounded-2xl border border-white/[0.07] bg-sp-s1/70 shadow-lift backdrop-blur-sm">
              {/* Chart header: the instrument identity, integrated into the
                  frame rather than floating over the candles. */}
              <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5 rounded-md border border-signal/20 bg-signal/[0.06] px-2 py-1">
                    <span className="h-1 w-1 rounded-full bg-signal" />
                    <span className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-signal-soft">
                      {c.hero.chart.engine}
                    </span>
                  </span>
                  <span className="font-mono text-[12px] font-medium tabular-nums text-sp-t1">
                    {c.hero.chart.symbol}
                  </span>
                  <span className="font-mono text-[11px] text-sp-t4">{c.hero.chart.timeframe}</span>
                </div>
                <div className="hidden items-center gap-3 sm:flex">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-sp-t4">
                    {c.hero.chart.structure}
                  </span>
                  <span className="h-3 w-px bg-sp-line" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-sp-t4">
                    {c.hero.chart.liquidity}
                  </span>
                </div>
              </div>

              <div className="h-[340px] sm:h-[420px] lg:h-[480px] xl:h-[520px]">
                <HeroChart labels={c.hero.chart} />
              </div>

              {/* Signal confidence: the last beat of the load sequence. */}
              <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-3">
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-sp-t4">
                  {c.hero.chart.confidence}
                </span>
                <div className="flex items-center gap-3">
                  <div className="h-1 w-24 overflow-hidden rounded-full bg-sp-s3 sm:w-32">
                    <motion.div
                      className="h-full rounded-full bg-signal"
                      initial={{ width: 0 }}
                      animate={{ width: "94%" }}
                      transition={{ duration: 1.1, delay: 2.5, ease: EASE }}
                    />
                  </div>
                  <motion.span
                    className="font-mono text-[12px] font-semibold tabular-nums text-signal"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 2.7 }}
                  >
                    94%
                  </motion.span>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </Shell>
    </section>
  );
}

/* ------------------------------------------------------------- context -- */

function Context({ c }) {
  return (
    <Section tone="deep">
      <Shell wide>
        <Head
          eyebrow={c.context.eyebrow}
          line1={c.context.line1}
          line2={c.context.line2}
          lead={c.context.sub}
          size="lg"
        />

        <div className="mt-14 grid items-stretch gap-4 lg:grid-cols-[1fr_auto_1fr] lg:gap-2">
          {/* Raw */}
          <Reveal>
            <Panel label={c.context.rawLabel} dim>
              <NoiseCanvas />
            </Panel>
          </Reveal>

          <div className="flex items-center justify-center lg:w-24">
            <TransformBeam className="h-16 w-full lg:h-full" />
          </div>

          {/* Intelligence */}
          <Reveal delay={0.15}>
            <Panel label={c.context.outLabel} accent>
              <IntelCanvas labels={c.hero.chart} />
            </Panel>
          </Reveal>
        </div>

        {/* The five outputs. A single hairline row, not five cards. */}
        <Stagger className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-sp-line bg-sp-line sm:grid-cols-3 lg:grid-cols-5">
          {c.context.outputs.map((o) => (
            <StaggerItem key={o.title} className="bg-sp-base p-4">
              <div className="text-[13px] font-semibold text-signal">{o.title}</div>
              <div className="mt-1 text-[11.5px] leading-snug text-sp-t3">{o.note}</div>
            </StaggerItem>
          ))}
        </Stagger>
      </Shell>
    </Section>
  );
}

function Panel({ label, children, dim = false, accent = false }) {
  return (
    <div
      className={`h-full overflow-hidden rounded-2xl border bg-sp-s1/50 ${
        accent ? "border-signal/15" : "border-sp-line"
      }`}
    >
      <div className="flex items-center gap-2 border-b border-sp-line px-4 py-2.5">
        <span className={`h-1 w-1 rounded-full ${accent ? "bg-signal" : "bg-sp-t4"}`} />
        <span
          className={`font-mono text-[10px] uppercase tracking-[0.2em] ${
            accent ? "text-signal" : "text-sp-t4"
          }`}
        >
          {label}
        </span>
      </div>
      <div className={`h-[240px] sm:h-[280px] ${dim ? "opacity-80" : ""}`}>{children}</div>
    </div>
  );
}

/* -------------------------------------------------------------- engine -- */

function Engine({ c }) {
  return (
    <Section id="ai" tone="base">
      <Shell wide>
        <Head
          eyebrow={c.engine.eyebrow}
          line1={c.engine.line1}
          line2={c.engine.line2}
          lead={c.engine.sub}
          center
          size="lg"
        />
        <div className="mt-12 lg:mt-8">
          <EngineCore
            inputs={c.engine.inputs}
            coreLabel={c.engine.core}
            verdictLabel={c.engine.verdict}
          />
        </div>
      </Shell>
    </Section>
  );
}

/* -------------------------------------------------------------- layers -- */

function Layers({ c }) {
  return (
    <Section id="features" tone="deep">
      <Shell wide>
        <Head
          eyebrow={c.layers.eyebrow}
          line1={c.layers.line1}
          line2={c.layers.line2}
          lead={c.layers.sub}
          size="lg"
        />
        <LayerChart items={c.layers.items} hint={c.layers.hint} className="mt-14" />
      </Shell>
    </Section>
  );
}

/* --------------------------------------------------------------- scalp -- */

function Scalp({ c }) {
  return (
    <Section id="scalp" tone="base">
      <Shell wide>
        <Head
          eyebrow={c.scalp.eyebrow}
          line1={c.scalp.line1}
          line2={c.scalp.line2}
          lead={c.scalp.sub}
          size="lg"
        />
        <ScalpSequence
          steps={c.scalp.steps}
          checks={c.scalp.checks}
          replayLabel={c.scalp.replay}
          className="mt-14"
        />
      </Shell>
    </Section>
  );
}

/* ---------------------------------------------------------------- exit -- */

function Exit({ c }) {
  return (
    <Section id="smart-exit" tone="deep">
      <Shell wide>
        <Head
          eyebrow={c.exit.eyebrow}
          line1={c.exit.line1}
          line2={c.exit.line2}
          lead={c.exit.sub}
          size="lg"
        />
        <SmartExitLive
          states={c.exit.states}
          positionLabel={c.exit.positionLabel}
          verdictLabel={c.exit.verdict}
          reads={c.exit.reads}
          className="mt-14"
        />
      </Shell>
    </Section>
  );
}

/* -------------------------------------------------------------- regime -- */

function Regime({ c }) {
  return (
    <Section tone="base">
      <Shell wide>
        <Head
          eyebrow={c.regime.eyebrow}
          line1={c.regime.line1}
          line2={c.regime.line2}
          lead={c.regime.sub}
          size="lg"
        />
        <RegimeSim items={c.regime.items} className="mt-12" />
      </Shell>
    </Section>
  );
}

/* ------------------------------------------------------------- product -- */

function Product({ c }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 85%", "end 30%"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [40, -40]);

  return (
    <Section id="product" tone="void" className="overflow-hidden">
      <Shell wide>
        <div ref={ref} className="grid items-center gap-14 lg:grid-cols-[40fr_60fr] lg:gap-12">
          <div>
            <Head
              eyebrow={c.product.eyebrow}
              line1={c.product.line1}
              line2={c.product.line2}
              lead={c.product.sub}
            />
            <Reveal delay={0.2}>
              <div className="mt-7 flex flex-wrap gap-2">
                {c.product.bullets.map((b) => (
                  <span
                    key={b}
                    className="rounded-full border border-sp-line px-3 py-1.5 text-[12px] text-sp-t3"
                  >
                    {b}
                  </span>
                ))}
              </div>
            </Reveal>
            <Reveal delay={0.3}>
              <div className="mt-8">
                <GhostButton to="/app" size="lg">
                  {c.product.cta}
                </GhostButton>
              </div>
            </Reveal>
          </div>

          <motion.div style={reduced ? undefined : { y }}>
            <DashboardMockup />
          </motion.div>
        </div>
      </Shell>
    </Section>
  );
}

/* ------------------------------------------------------------------ how -- */

function How({ c }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 75%", "end 60%"],
  });

  return (
    <Section id="how-it-works" tone="base">
      <Shell wide>
        <Head
          eyebrow={c.how.eyebrow}
          line1={c.how.line1}
          line2={c.how.line2}
          lead={c.how.sub}
          size="lg"
        />

        <div ref={ref} className="relative mt-16">
          {/* The connecting line. Horizontal on desktop, vertical on mobile,
              and it draws itself as the section scrolls — the line *is* the
              flow of information the copy describes. */}
          <div className="absolute inset-x-0 top-[22px] hidden h-px bg-sp-line lg:block">
            <motion.div
              className="h-full origin-left bg-gradient-to-r from-signal/60 to-signal"
              style={{ scaleX: scrollYProgress }}
            />
          </div>
          <div className="absolute bottom-0 start-[22px] top-0 w-px bg-sp-line lg:hidden">
            <motion.div
              className="w-full origin-top bg-gradient-to-b from-signal/60 to-signal"
              style={{ scaleY: scrollYProgress }}
            />
          </div>

          <div className="grid gap-10 lg:grid-cols-5 lg:gap-6">
            {c.how.steps.map((s, i) => (
              <Reveal key={s.num} delay={i * 0.08}>
                <div className="relative ps-14 lg:ps-0">
                  <div className="absolute start-0 top-0 flex h-11 w-11 items-center justify-center rounded-full border border-sp-edge bg-sp-base font-mono text-[12px] tabular-nums text-signal lg:relative lg:mb-6">
                    {s.num}
                  </div>
                  <div className="text-[17px] font-semibold text-sp-t1">{s.title}</div>
                  <p className="mt-2 text-[13px] leading-relaxed text-sp-t3">{s.note}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </Shell>
    </Section>
  );
}

/* ---------------------------------------------------------------- trust -- */

function Trust({ c }) {
  return (
    <Section tone="deep">
      <Shell wide>
        <div className="grid gap-12 lg:grid-cols-[42fr_58fr] lg:gap-16">
          <Head
            eyebrow={c.trust.eyebrow}
            line1={c.trust.line1}
            line2={c.trust.line2}
            lead={c.trust.sub}
            size="lg"
          />

          {/* Method, as a numbered ledger. No metrics, because we have none
              worth quoting and inventing them would cost more than it buys. */}
          <div className="lg:pt-4">
            <Stagger className="divide-y divide-sp-line border-y border-sp-line">
              {c.trust.pillars.map((p, i) => (
                <StaggerItem key={p.title}>
                  <div className="group flex items-baseline gap-5 py-4 transition-colors duration-300">
                    <span className="font-mono text-[11px] tabular-nums text-sp-t4">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-[150px] text-[15px] font-semibold text-sp-t1">
                      {p.title}
                    </span>
                    <span className="text-[13px] text-sp-t3">{p.note}</span>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>

            <Reveal delay={0.2}>
              <p className="mt-6 text-[12px] leading-relaxed text-sp-t4">{c.trust.disclaimer}</p>
            </Reveal>
          </div>
        </div>
      </Shell>
    </Section>
  );
}

/* ------------------------------------------------------------------ cta -- */

function FinalCTA({ c }) {
  return (
    <section className="relative overflow-hidden bg-sp-void py-28 sm:py-36 lg:py-44">
      <CTABackdrop />
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-[560px] w-[560px] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(240,184,11,0.09) 0%, rgba(240,184,11,0.02) 45%, transparent 70%)",
        }}
      />

      <Shell className="relative text-center">
        <Headline line1={c.cta.line1} line2={c.cta.line2} size="lg" muted={false} />
        <Reveal delay={0.15}>
          <p className="mx-auto mt-6 max-w-md text-[15px] leading-relaxed text-sp-t2 sm:text-base">
            {c.cta.sub}
          </p>
        </Reveal>
        <Reveal delay={0.25}>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <GoldButton to="/register" size="lg">
              {c.cta.primary}
            </GoldButton>
            <GhostButton to="/app" size="lg">
              {c.cta.secondary}
            </GhostButton>
          </div>
        </Reveal>
        <Reveal delay={0.35}>
          <p className="mt-6 font-mono text-[11px] tracking-wide text-sp-t4">{c.cta.reassure}</p>
        </Reveal>
      </Shell>
    </section>
  );
}

/* ----------------------------------------------------------------- page -- */

export default function Landing() {
  const c = useCopy();
  return (
    <div className="bg-sp-base">
      <Hero c={c} />
      <Context c={c} />
      <Engine c={c} />
      <Layers c={c} />
      <Scalp c={c} />
      <Exit c={c} />
      <Regime c={c} />
      <Product c={c} />
      <How c={c} />
      <Trust c={c} />
      <FinalCTA c={c} />
    </div>
  );
}
