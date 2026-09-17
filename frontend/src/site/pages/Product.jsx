import { usePageCopy } from "../pageCopy/index.js";
import { Reveal, Stagger, StaggerItem } from "../motion.jsx";
import LayerChart from "../visuals/LayerChart.jsx";
import EngineCore from "../visuals/EngineCore.jsx";
import ScalpSequence from "../visuals/ScalpSequence.jsx";
import SmartExitLive from "../visuals/SmartExitLive.jsx";
import RegimeSim from "../visuals/RegimeSim.jsx";
import { useCopy } from "../copy.js";
import {
  ListGroups,
  NoteBlock,
  PageCTA,
  PageHeader,
  Section,
  SectionHead,
  Shell,
  StepFlow,
} from "./kit.jsx";

/**
 * The four product sub-pages.
 *
 * These reuse the landing page's visuals rather than reimplementing them. That
 * is deliberate: a sub-page that explains the scalp engine with a *different*
 * chart than the landing page used would undermine the product identity the
 * redesign was about. Same engine, same series, more room to explain it.
 *
 * The landing deck (copy.js) supplies labels for the visuals; pageCopy supplies
 * the page prose. Neither duplicates the other.
 */

/* ---------------------------------------------------------------- features */

export function FeaturesPage() {
  const p = usePageCopy();
  const c = useCopy();

  return (
    <>
      <PageHeader eyebrow={p.features.eyebrow} line1={p.features.line1} line2={p.features.line2} lead={p.features.lead} />

      {/* The layer chart carries the argument: nine capabilities described in
          prose would be a wall of text, but stacked on one chart they read as
          a single system. */}
      <Section tone="base" className="py-16 sm:py-20">
        <Shell wide>
          <Reveal>
            <LayerChart items={c.layers.items} hint={c.layers.hint} />
          </Reveal>
        </Shell>
      </Section>

      <Section tone="deep" className="py-20 sm:py-24 lg:py-28">
        <Shell>
          <SectionHead line1={p.features.groupTitle} lead={p.features.groupLead} className="mb-14" />
          <ListGroups groups={p.features.groups} />
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}

/* --------------------------------------------------------------------- ai */

export function AIPage() {
  const p = usePageCopy();
  const c = useCopy();

  return (
    <>
      <PageHeader eyebrow={p.ai.eyebrow} line1={p.ai.line1} line2={p.ai.line2} lead={p.ai.lead} />

      {/* Full-width, because the core diagram was the single worst offender for
          "visual too small inside a huge black area" in the previous build. */}
      <Section tone="base" className="py-14 sm:py-16">
        <Shell wide>
          <EngineCore
            inputs={c.engine.inputs}
            coreLabel={c.engine.core}
            verdictLabel={c.engine.verdict}
          />
        </Shell>
      </Section>

      <Section tone="deep" className="py-20 sm:py-24 lg:py-28">
        <Shell>
          <SectionHead line1={p.ai.stepsTitle} className="mb-14" />
          <StepFlow steps={p.ai.steps} columns={4} />
          <div className="mt-16">
            <NoteBlock title={p.ai.honestTitle} body={p.ai.honestBody} />
          </div>
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}

/* ------------------------------------------------------------------ scalp */

export function ScalpPage() {
  const p = usePageCopy();
  const c = useCopy();

  return (
    <>
      <PageHeader eyebrow={p.scalp.eyebrow} line1={p.scalp.line1} line2={p.scalp.line2} lead={p.scalp.lead} />

      <Section tone="base" className="py-14 sm:py-16">
        <Shell wide>
          <Reveal>
            <ScalpSequence steps={c.scalp.steps} checks={c.scalp.checks} replayLabel={c.scalp.replay} />
          </Reveal>
        </Shell>
      </Section>

      <Section tone="deep" className="py-20 sm:py-24 lg:py-28">
        <Shell>
          <div className="grid gap-14 lg:grid-cols-[minmax(0,42fr)_minmax(0,58fr)] lg:gap-20">
            <SectionHead line1={p.scalp.logicTitle} lead={p.scalp.logicLead} />
            <Stagger>
              {p.scalp.logicItems.map((item, i) => (
                <StaggerItem key={item.title}>
                  <div className="border-t border-sp-line py-6">
                    <div className="flex items-baseline gap-4">
                      <span className="font-mono text-[10.5px] tabular-nums text-signal">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <h3 className="text-[15.5px] font-semibold tracking-tight text-sp-t1">{item.title}</h3>
                        <p className="mt-2 max-w-[52ch] text-[13.5px] leading-[1.75] text-sp-t3">{item.note}</p>
                      </div>
                    </div>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          </div>
          <div className="mt-16">
            <NoteBlock title={p.scalp.noteTitle} body={p.scalp.noteBody} />
          </div>
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}

/* -------------------------------------------------------------- smart exit */

export function ExitPage() {
  const p = usePageCopy();
  const c = useCopy();

  return (
    <>
      <PageHeader eyebrow={p.exit.eyebrow} line1={p.exit.line1} line2={p.exit.line2} lead={p.exit.lead} />

      <Section tone="base" className="py-14 sm:py-16">
        <Shell wide>
          <Reveal>
            <SmartExitLive
              states={c.exit.states}
              positionLabel={c.exit.positionLabel}
              verdictLabel={c.exit.verdict}
              reads={c.exit.reads}
            />
          </Reveal>
        </Shell>
      </Section>

      {/* The four verdicts, spelled out in prose. The visual shows *that* the
          recommendation changes; this explains what each one means. */}
      <Section tone="deep" className="py-20 sm:py-24">
        <Shell>
          <SectionHead line1={p.exit.decisionsTitle} className="mb-12" />
          <Stagger className="grid gap-x-12 sm:grid-cols-2">
            {p.exit.decisions.map((d, i) => (
              <StaggerItem key={d.title}>
                <div className="border-t border-sp-line py-6">
                  <div className="flex items-baseline gap-4">
                    <span className="font-mono text-[10.5px] tabular-nums text-signal">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h3 className="text-[15.5px] font-semibold tracking-tight text-sp-t1">{d.title}</h3>
                      <p className="mt-2 max-w-[44ch] text-[13.5px] leading-[1.75] text-sp-t3">{d.note}</p>
                    </div>
                  </div>
                </div>
              </StaggerItem>
            ))}
          </Stagger>
        </Shell>
      </Section>

      {/* Regime simulator lives here rather than on the landing page's terms:
          exit decisions are where the regime actually changes your answer. */}
      <Section tone="base" className="py-20 sm:py-24">
        <Shell wide>
          <SectionHead
            line1={p.exit.regimeTitle}
            lead={p.exit.regimeLead}
            center
            className="mb-14"
          />
          <Reveal>
            <RegimeSim items={c.regime.items} />
          </Reveal>
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}
