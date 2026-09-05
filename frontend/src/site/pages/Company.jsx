import { usePageCopy } from "../pageCopy/index.js";
import { Reveal, Stagger, StaggerItem } from "../motion.jsx";
import DashboardMockup from "../visuals/DashboardMockup.jsx";
import { useCopy } from "../copy.js";
import {
  FaqList,
  PageCTA,
  PageHeader,
  Section,
  SectionHead,
  Shell,
  StepFlow,
} from "./kit.jsx";

/**
 * About and How-it-works.
 *
 * Both are prose-led pages, so the job here is typographic rather than
 * visual: a measured column width, a clear hierarchy, and no decorative cards
 * padding out the space.
 */

/* ------------------------------------------------------------------- about */

export function AboutPage() {
  const p = usePageCopy();

  return (
    <>
      <PageHeader eyebrow={p.about.eyebrow} line1={p.about.line1} line2={p.about.line2} lead={p.about.lead} />

      {/* Long-form sections in a single measured column. ~68ch is the point
          where body copy stops being comfortable to read. */}
      <Section tone="base" className="py-20 sm:py-24">
        <Shell>
          <div className="grid gap-14 lg:grid-cols-[minmax(0,30fr)_minmax(0,70fr)] lg:gap-20">
            <div className="lg:sticky lg:top-28 lg:self-start">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-signal-soft">
                SmartPips
              </span>
            </div>
            <div className="space-y-12">
              {p.about.sections.map((s) => (
                <Reveal key={s.title}>
                  <div>
                    <h2 className="text-[19px] font-semibold tracking-tight text-sp-t1 sm:text-[21px]">
                      {s.title}
                    </h2>
                    <p className="mt-3 max-w-[68ch] text-[15px] leading-[1.85] text-sp-t3">{s.body}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </Shell>
      </Section>

      {/* Principles. Four short statements, set as a rule-separated list rather
          than four glass cards. */}
      <Section tone="deep" className="py-20 sm:py-24">
        <Shell>
          <Stagger className="grid gap-x-14 sm:grid-cols-2">
            {p.about.principles.map((pr, i) => (
              <StaggerItem key={pr.title}>
                <div className="border-t border-sp-line py-6">
                  <div className="flex items-baseline gap-4">
                    <span className="font-mono text-[10.5px] tabular-nums text-signal">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h3 className="text-[15.5px] font-semibold tracking-tight text-sp-t1">{pr.title}</h3>
                      <p className="mt-1.5 max-w-[42ch] text-[13.5px] leading-relaxed text-sp-t3">{pr.note}</p>
                    </div>
                  </div>
                </div>
              </StaggerItem>
            ))}
          </Stagger>
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}

/* ------------------------------------------------------------ how it works */

export function HowPage() {
  const p = usePageCopy();
  const c = useCopy();

  return (
    <>
      <PageHeader eyebrow={p.how.eyebrow} line1={p.how.line1} line2={p.how.line2} lead={p.how.lead} />

      {/* Five stages on one connected line — the same flow the landing page
          shows, given room to breathe. */}
      <Section tone="base" className="py-16 sm:py-20 lg:py-24">
        <Shell wide>
          <StepFlow steps={c.how.steps} columns={5} />
        </Shell>
      </Section>

      {/* What it actually looks like once you are inside. */}
      <Section tone="deep" className="overflow-hidden py-20 sm:py-24">
        <Shell wide>
          <SectionHead line1={c.product.line1} line2={c.product.line2} lead={c.product.sub} center className="mb-16" />
          <Reveal>
            <DashboardMockup />
          </Reveal>
        </Shell>
      </Section>

      <Section tone="base" className="py-20 sm:py-24">
        <Shell>
          <SectionHead line1={p.how.faqTitle} className="mb-12" />
          <FaqList items={p.how.faqs} />
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}
