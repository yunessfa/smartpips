import { Link } from "react-router-dom";
import { Reveal, Stagger, StaggerItem, TextReveal } from "../motion.jsx";

/**
 * Shared building blocks for the public sub-pages.
 *
 * Landing.jsx keeps its own local primitives on purpose — it is a one-off
 * composition and shouldn't be constrained by a generic kit. Everything after
 * it, though, is the same shape repeated: a page header, some sections, a
 * closing CTA. Centralising that here is what keeps nine pages consistent
 * without nine copies of the same spacing decisions.
 *
 * Spacing rules baked in, per the brief:
 *   • max-width 1440 outer / 1280 content — never wider,
 *   • no arbitrary min-h-screen sections; height follows content,
 *   • one vertical rhythm (py-20 / 28 / 32) used everywhere.
 */

export function Shell({ children, className = "", wide = false }) {
  return (
    <div
      className={`mx-auto w-full px-5 sm:px-8 ${wide ? "max-w-site" : "max-w-content"} ${className}`}
    >
      {children}
    </div>
  );
}

const TONE = {
  base: "bg-sp-base",
  deep: "bg-sp-deep",
  void: "bg-sp-void",
};

export function Section({ id, children, className = "", tone = "base" }) {
  return (
    <section id={id} className={`relative ${TONE[tone] || TONE.base} ${className}`}>
      {children}
    </section>
  );
}

export function Eyebrow({ children, className = "" }) {
  return (
    <div
      className={`flex items-center gap-2.5 font-mono text-[10.5px] uppercase tracking-[0.2em] text-sp-t4 ${className}`}
    >
      <span className="h-px w-6 bg-signal/50" />
      {children}
    </div>
  );
}

/**
 * Page title. `immediate` is on by default because a page header is always
 * above the fold — the same bug that made the landing hero render invisible.
 */
export function PageTitle({ line1, line2, className = "" }) {
  return (
    <h1 className={`site-display text-sp-t1 ${className}`}>
      <TextReveal text={line1} immediate />
      {line2 ? <TextReveal text={line2} immediate delay={0.12} className="text-sp-t3" /> : null}
    </h1>
  );
}

export function Lead({ children, className = "" }) {
  return (
    <p className={`text-[15px] leading-[1.75] text-sp-t3 sm:text-[16.5px] ${className}`}>
      {children}
    </p>
  );
}

/**
 * The header every sub-page opens with. Deliberately not full-viewport: a
 * marketing sub-page that hides its own content below a 100vh title is a
 * spacing failure, not a design choice.
 */
export function PageHeader({ eyebrow, line1, line2, lead, children }) {
  return (
    <Section tone="void" className="overflow-hidden pb-14 pt-28 sm:pb-16 sm:pt-32 lg:pb-20 lg:pt-36">
      {/* One restrained bloom, offset so it reads as light rather than a
          gradient panel. */}
      <div
        className="pointer-events-none absolute -top-40 end-[-10%] h-[560px] w-[560px] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(240,184,11,0.075) 0%, rgba(240,184,11,0.02) 45%, transparent 72%)",
        }}
      />
      <div className="sx-grid sx-grid-mask pointer-events-none absolute inset-0 opacity-25" />

      <Shell className="relative">
        <Reveal>
          <Eyebrow>{eyebrow}</Eyebrow>
        </Reveal>
        <PageTitle
          line1={line1}
          line2={line2}
          className="mt-6 text-[2.4rem] leading-[1.06] sm:text-[3.1rem] lg:text-[3.6rem]"
        />
        {lead ? (
          <Reveal delay={0.18}>
            <Lead className="mt-6 max-w-[54ch]">{lead}</Lead>
          </Reveal>
        ) : null}
        {children}
      </Shell>
    </Section>
  );
}

/** Section-level heading, one step down from PageTitle. */
export function SectionHead({ eyebrow, line1, line2, lead, center = false, className = "" }) {
  return (
    <div className={`${center ? "mx-auto max-w-[62ch] text-center" : "max-w-[58ch]"} ${className}`}>
      {eyebrow ? (
        <Reveal>
          <Eyebrow className={center ? "justify-center" : ""}>{eyebrow}</Eyebrow>
        </Reveal>
      ) : null}
      <Reveal delay={0.06}>
        <h2 className="site-display mt-5 text-[1.9rem] leading-[1.1] text-sp-t1 sm:text-[2.4rem] lg:text-[2.75rem]">
          {line1}
          {line2 ? (
            <>
              <br />
              <span className="text-sp-t3">{line2}</span>
            </>
          ) : null}
        </h2>
      </Reveal>
      {lead ? (
        <Reveal delay={0.12}>
          <Lead className="mt-5">{lead}</Lead>
        </Reveal>
      ) : null}
    </div>
  );
}

/**
 * The frame used around every chart or diagram. Same chrome as the landing
 * hero frame, so a visual moved between pages still looks native.
 */
export function VisualFrame({ label, meta, children, className = "" }) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-white/[0.07] bg-sp-s1/50 shadow-[0_24px_70px_-32px_rgba(0,0,0,0.95)] ${className}`}
    >
      {label || meta ? (
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-sp-t4">{label}</span>
          {meta ? (
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal-soft">
              {meta}
            </span>
          ) : null}
        </div>
      ) : null}
      {children}
    </div>
  );
}

/**
 * A capability item. Not a card — a rule and a label. Nine rounded glass cards
 * in a grid is exactly the template look the brief rules out, so the visual
 * weight here comes from the hairline and the number, not from a container.
 */
export function ListItem({ index, title, note }) {
  return (
    <StaggerItem>
      <div className="group border-t border-sp-line py-5 transition-colors duration-300 hover:border-signal/30">
        <div className="flex items-baseline gap-4">
          {index ? (
            <span className="font-mono text-[10.5px] tabular-nums text-sp-t4 transition-colors duration-300 group-hover:text-signal">
              {index}
            </span>
          ) : null}
          <div>
            <h3 className="text-[15.5px] font-semibold tracking-tight text-sp-t1">{title}</h3>
            {note ? (
              <p className="mt-1.5 max-w-[46ch] text-[13.5px] leading-relaxed text-sp-t3">{note}</p>
            ) : null}
          </div>
        </div>
      </div>
    </StaggerItem>
  );
}

/** Groups of capability items, three across on desktop. */
export function ListGroups({ groups }) {
  return (
    <div className="grid gap-x-12 gap-y-12 lg:grid-cols-3">
      {groups.map((g) => (
        <div key={g.title}>
          <h3 className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-signal-soft">
            {g.title}
          </h3>
          <Stagger className="mt-5">
            {g.items.map((item, i) => (
              <ListItem
                key={item.title}
                index={String(i + 1).padStart(2, "0")}
                title={item.title}
                note={item.note}
              />
            ))}
          </Stagger>
        </div>
      ))}
    </div>
  );
}

/**
 * Numbered steps joined by a single continuous line — the line is the point,
 * since it is what makes a list read as a flow of information.
 */
export function StepFlow({ steps, columns = 4 }) {
  const cols = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" }[columns] || "lg:grid-cols-4";
  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-x-0 top-[7px] hidden h-px bg-gradient-to-r from-transparent via-sp-edge to-transparent lg:block" />
      <Stagger className={`relative grid gap-10 sm:grid-cols-2 ${cols}`} gap={0.1}>
        {steps.map((s) => (
          <StaggerItem key={s.num + s.title}>
            <div className="relative">
              <span className="absolute -top-[1px] start-0 hidden h-3.5 w-3.5 -translate-y-1/2 rounded-full border border-signal/40 bg-sp-void lg:block">
                <span className="absolute inset-[3px] rounded-full bg-signal/70" />
              </span>
              <div className="lg:pt-8">
                <span className="font-mono text-[11px] tabular-nums tracking-[0.16em] text-signal">
                  {s.num}
                </span>
                <h3 className="mt-2.5 text-[16px] font-semibold tracking-tight text-sp-t1">{s.title}</h3>
                <p className="mt-2 max-w-[34ch] text-[13.5px] leading-relaxed text-sp-t3">{s.note}</p>
              </div>
            </div>
          </StaggerItem>
        ))}
      </Stagger>
    </div>
  );
}

/** A quiet block for the honest, non-marketing caveats. */
export function NoteBlock({ title, body }) {
  return (
    <Reveal>
      <div className="border-s-2 border-signal/40 bg-sp-s1/40 px-6 py-5">
        <h3 className="text-[14.5px] font-semibold tracking-tight text-sp-t1">{title}</h3>
        <p className="mt-2 max-w-[62ch] text-[13.5px] leading-[1.75] text-sp-t3">{body}</p>
      </div>
    </Reveal>
  );
}

/** Accessible accordion. Uses <details> so it works without JS and is
 *  keyboard-navigable for free. */
export function FaqList({ items }) {
  return (
    <div className="divide-y divide-sp-line border-y border-sp-line">
      {items.map((f) => (
        <details key={f.q} className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-[15px] font-medium text-sp-t1 transition-colors duration-200 hover:text-signal-soft">
            <span>{f.q}</span>
            <span className="relative h-3 w-3 shrink-0">
              <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-sp-t3" />
              <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-sp-t3 transition-transform duration-300 group-open:scale-y-0" />
            </span>
          </summary>
          <p className="max-w-[68ch] pb-6 text-[14px] leading-[1.8] text-sp-t3">{f.a}</p>
        </details>
      ))}
    </div>
  );
}

export function GoldLink({ to, children, className = "" }) {
  return (
    <Link
      to={to}
      className={`group relative inline-flex items-center gap-2 rounded-xl bg-signal px-6 py-3.5 text-[14.5px] font-semibold text-sp-void transition-all duration-300 hover:bg-signal-soft ${className}`}
    >
      {children}
    </Link>
  );
}

export function GhostLink({ to, children, className = "" }) {
  return (
    <Link
      to={to}
      className={`inline-flex items-center gap-2 rounded-xl border border-white/12 px-6 py-3.5 text-[14.5px] font-medium text-sp-t2 transition-all duration-300 hover:border-signal/40 hover:text-sp-t1 ${className}`}
    >
      {children}
    </Link>
  );
}

/**
 * The closing CTA, shared by every sub-page so the site ends the same way
 * regardless of where the visitor entered.
 */
export function PageCTA({ copy }) {
  return (
    <Section tone="void" className="relative overflow-hidden py-24 sm:py-28 lg:py-32">
      <div
        className="pointer-events-none absolute inset-x-0 bottom-[-45%] mx-auto h-[520px] max-w-[900px] rounded-full"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(240,184,11,0.09) 0%, rgba(240,184,11,0.02) 45%, transparent 70%)",
        }}
      />
      <Shell className="relative text-center">
        <h2 className="site-display text-[2.1rem] leading-[1.08] text-sp-t1 sm:text-[2.8rem] lg:text-[3.2rem]">
          {copy.line1}
          <br />
          <span className="text-sp-t3">{copy.line2}</span>
        </h2>
        <Lead className="mx-auto mt-5 max-w-[46ch]">{copy.sub}</Lead>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <GoldLink to="/register">{copy.primary}</GoldLink>
          <GhostLink to="/features">{copy.secondary}</GhostLink>
        </div>
      </Shell>
    </Section>
  );
}
