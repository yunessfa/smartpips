import { useState } from "react";
import { usePageCopy, CONTACT_EMAIL } from "../pageCopy/index.js";
import { Reveal, Stagger, StaggerItem } from "../motion.jsx";
import {
  FaqList,
  GhostLink,
  GoldLink,
  PageCTA,
  PageHeader,
  Section,
  SectionHead,
  Shell,
} from "./kit.jsx";

/**
 * Pricing, FAQ and Contact.
 *
 * Two honesty constraints shaped these:
 *   • Prices are placeholders ("—") in pageCopy. Rather than inventing figures,
 *     the plan card renders a "pricing on request" state that looks intentional
 *     instead of unfinished, and the note below explains why.
 *   • There is no contact endpoint in the backend, so the form composes a mail
 *     message instead of pretending to submit and silently losing it.
 */

/* ----------------------------------------------------------------- pricing */

function PlanCard({ plan, monthly }) {
  const hasPrice = plan.price && plan.price !== "\u2014";

  return (
    <StaggerItem className="h-full">
      <div
        className={`relative flex h-full flex-col rounded-2xl border p-7 transition-colors duration-300 ${
          plan.featured
            ? "border-signal/35 bg-sp-s2/70 shadow-[0_24px_70px_-34px_rgba(240,184,11,0.35)]"
            : "border-sp-line bg-sp-s1/45 hover:border-white/12"
        }`}
      >
        {plan.featured ? (
          <span className="absolute -top-2.5 start-7 rounded-full border border-signal/35 bg-sp-void px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.16em] text-signal">
            {plan.name}
          </span>
        ) : null}

        <h3 className="text-[17px] font-semibold tracking-tight text-sp-t1">{plan.name}</h3>
        <p className="mt-2 min-h-[42px] max-w-[34ch] text-[13.5px] leading-relaxed text-sp-t3">
          {plan.tagline}
        </p>

        <div className="mt-6 flex items-baseline gap-2 border-t border-sp-line pt-6">
          <span
            className={`font-mono tabular-nums ${
              hasPrice ? "text-[2rem] font-bold text-sp-t1" : "text-[1.4rem] text-sp-t3"
            }`}
          >
            {plan.price}
          </span>
          {hasPrice ? (
            <span className="text-[12.5px] text-sp-t4">{monthly}</span>
          ) : null}
        </div>

        <ul className="mt-6 flex-1 space-y-3">
          {plan.features.map((f) => (
            <li key={f} className="flex items-start gap-2.5 text-[13.5px] leading-relaxed text-sp-t2">
              <svg viewBox="0 0 16 16" className="mt-[3px] h-3.5 w-3.5 shrink-0 text-signal" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M3 8.5l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>{f}</span>
            </li>
          ))}
        </ul>

        <div className="mt-8">
          {plan.featured ? (
            <GoldLink to="/register" className="w-full justify-center">
              {plan.cta}
            </GoldLink>
          ) : (
            <GhostLink to="/contact" className="w-full justify-center">
              {plan.cta}
            </GhostLink>
          )}
        </div>
      </div>
    </StaggerItem>
  );
}

export function PricingPage() {
  const p = usePageCopy();

  return (
    <>
      <PageHeader eyebrow={p.pricing.eyebrow} line1={p.pricing.line1} line2={p.pricing.line2} lead={p.pricing.lead} />

      <Section tone="base" className="py-14 sm:py-16">
        <Shell>
          <Stagger className="grid items-stretch gap-6 lg:grid-cols-3">
            {p.pricing.plans.map((plan) => (
              <PlanCard key={plan.name} plan={plan} monthly={p.pricing.monthly} />
            ))}
          </Stagger>

          <Reveal>
            <p className="mx-auto mt-10 max-w-[62ch] border-s-2 border-signal/40 ps-5 text-[13.5px] leading-[1.8] text-sp-t3">
              {p.pricing.note}
            </p>
          </Reveal>
        </Shell>
      </Section>

      <Section tone="deep" className="py-20 sm:py-24">
        <Shell>
          <SectionHead line1={p.pricing.faqTitle} className="mb-12" />
          <FaqList items={p.pricing.faqs} />
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}

/* --------------------------------------------------------------------- faq */

export function FaqPage() {
  const p = usePageCopy();

  return (
    <>
      <PageHeader eyebrow={p.faq.eyebrow} line1={p.faq.line1} line2={p.faq.line2} lead={p.faq.lead} />

      <Section tone="base" className="py-14 sm:py-16 lg:py-20">
        <Shell>
          <div className="space-y-16">
            {p.faq.groups.map((g) => (
              <div key={g.title} className="grid gap-8 lg:grid-cols-[minmax(0,26fr)_minmax(0,74fr)] lg:gap-16">
                <h2 className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-signal-soft lg:sticky lg:top-28 lg:self-start">
                  {g.title}
                </h2>
                <FaqList items={g.items} />
              </div>
            ))}
          </div>
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}

/* ----------------------------------------------------------------- contact */

const FIELD =
  "w-full rounded-xl border border-sp-line bg-sp-s1/70 px-4 py-3 text-[14.5px] text-sp-t1 outline-none transition-all duration-200 placeholder:text-sp-t4 focus:border-signal/45 focus:bg-sp-s2/70 focus:ring-1 focus:ring-signal/20";
const LABEL = "mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-sp-t4";

export function ContactPage() {
  const p = usePageCopy();
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });

  function set(key) {
    return (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  /**
   * No POST endpoint exists for this yet, and a form that appears to submit
   * while discarding the message is worse than no form. So this hands the
   * message to the user's mail client with everything already filled in.
   */
  function compose(e) {
    e.preventDefault();
    const subject = form.subject || "SmartPips";
    const body = [
      form.name ? `${p.contact.name}: ${form.name}` : "",
      form.email ? `${p.contact.email}: ${form.email}` : "",
      "",
      form.message,
    ]
      .filter(Boolean)
      .join("\n");
    window.location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(
      subject,
    )}&body=${encodeURIComponent(body)}`;
  }

  return (
    <>
      <PageHeader eyebrow={p.contact.eyebrow} line1={p.contact.line1} line2={p.contact.line2} lead={p.contact.lead} />

      <Section tone="base" className="py-14 sm:py-16 lg:py-20">
        <Shell>
          <div className="grid gap-14 lg:grid-cols-[minmax(0,58fr)_minmax(0,42fr)] lg:gap-20">
            {/* form */}
            <Reveal>
              <form onSubmit={compose}>
                <h2 className="text-[19px] font-semibold tracking-tight text-sp-t1">
                  {p.contact.formTitle}
                </h2>
                <p className="mt-2 text-[13px] text-sp-t4">{p.contact.formNote}</p>

                <div className="mt-7 grid gap-5 sm:grid-cols-2">
                  <div>
                    <label htmlFor="c-name" className={LABEL}>{p.contact.name}</label>
                    <input id="c-name" value={form.name} onChange={set("name")} className={FIELD} />
                  </div>
                  <div>
                    <label htmlFor="c-email" className={LABEL}>{p.contact.email}</label>
                    <input id="c-email" type="email" dir="ltr" value={form.email} onChange={set("email")} className={FIELD} />
                  </div>
                </div>

                <div className="mt-5">
                  <label htmlFor="c-subject" className={LABEL}>{p.contact.subject}</label>
                  <input id="c-subject" value={form.subject} onChange={set("subject")} className={FIELD} />
                </div>

                <div className="mt-5">
                  <label htmlFor="c-message" className={LABEL}>{p.contact.message}</label>
                  <textarea
                    id="c-message"
                    rows={6}
                    value={form.message}
                    onChange={set("message")}
                    className={`${FIELD} resize-y`}
                  />
                </div>

                <button
                  type="submit"
                  className="mt-7 w-full rounded-xl bg-signal px-6 py-3.5 text-[14.5px] font-semibold text-sp-void transition-all duration-300 hover:bg-signal-soft sm:w-auto"
                >
                  {p.contact.send}
                </button>
              </form>
            </Reveal>

            {/* direct details */}
            <Reveal delay={0.1}>
              <div className="space-y-10">
                <div>
                  <h2 className="text-[19px] font-semibold tracking-tight text-sp-t1">
                    {p.contact.directTitle}
                  </h2>
                  <dl className="mt-6 space-y-5">
                    <div className="border-t border-sp-line pt-4">
                      <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-sp-t4">
                        {p.contact.emailLabel}
                      </dt>
                      <dd className="mt-1.5">
                        <a
                          href={`mailto:${CONTACT_EMAIL}`}
                          dir="ltr"
                          className="font-mono text-[13.5px] text-signal transition-colors hover:text-signal-soft"
                        >
                          {CONTACT_EMAIL}
                        </a>
                      </dd>
                    </div>
                    <div className="border-t border-sp-line pt-4">
                      <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-sp-t4">
                        {p.contact.responseLabel}
                      </dt>
                      <dd className="mt-1.5 text-[13.5px] text-sp-t2">{p.contact.responseValue}</dd>
                    </div>
                  </dl>
                </div>

                <div>
                  <h3 className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-signal-soft">
                    {p.contact.topicsTitle}
                  </h3>
                  <ul className="mt-4 space-y-2.5">
                    {p.contact.topics.map((topic) => (
                      <li key={topic} className="flex items-start gap-2.5 text-[13.5px] leading-relaxed text-sp-t3">
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-signal/70" />
                        <span>{topic}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Reveal>
          </div>
        </Shell>
      </Section>

      <PageCTA copy={p.cta} />
    </>
  );
}
