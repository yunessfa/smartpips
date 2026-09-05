/**
 * English copy for the public sub-pages.
 *
 * Editorial rules, same as the landing deck: no buzzwords, no invented proof
 * (no user counts, win rates or returns), and every claim has to describe
 * something the product actually does.
 */

export const en = {
  about: {
    eyebrow: "About",
    line1: "Built by traders,",
    line2: "for traders who think.",
    lead: "SmartPips exists because the hard part of trading is not finding a signal. It is deciding which information deserves your attention, and what to do once you are already in a position.",
    sections: [
      {
        title: "The problem we started with",
        body: "Most tools give you more indicators. More indicators produce more opinions, and more opinions produce hesitation. We wanted the opposite: fewer, better-supported decisions, each one traceable back to a specific market condition.",
      },
      {
        title: "How we approach it",
        body: "SmartPips reads the market the way a discretionary trader does — structure first, then liquidity, then order flow and volatility — and only then looks for an entry. Risk and trade management are part of the analysis, not an afterthought bolted on at the end.",
      },
      {
        title: "What we will not claim",
        body: "We do not publish win rates, profit figures or user counts, because none of them would tell you anything reliable about your own results. What we can describe honestly is the process, and that is what this site documents.",
      },
    ],
    principles: [
      { title: "Process over prediction", note: "A repeatable method beats a lucky call." },
      { title: "Context over signals", note: "A level means nothing without the structure around it." },
      { title: "Risk is first-class", note: "Position size and invalidation are part of the setup." },
      { title: "No black boxes", note: "Every read shows you what it was based on." },
    ],
  },

  features: {
    eyebrow: "Features",
    line1: "Everything SmartPips",
    line2: "looks at, in one place.",
    lead: "Nine independent views of the same market, combined into a single structured read. Turn the layers on below to see how they stack.",
    groupTitle: "The full capability set",
    groupLead: "Grouped by the question each one answers.",
    groups: [
      {
        title: "Reading the market",
        items: [
          { title: "Market structure", note: "Swing points, trend state, and the level that invalidates the current read." },
          { title: "Liquidity", note: "Resting liquidity, sweeps, and the zones price is likely to reach for." },
          { title: "Order flow", note: "Whether the volume behind a move supports it or contradicts it." },
          { title: "Volatility", note: "Expansion and compression, and what each implies for stop distance." },
        ],
      },
      {
        title: "Forming a decision",
        items: [
          { title: "Signal confirmation", note: "A setup is not actionable until the confirming conditions are present." },
          { title: "Risk", note: "Invalidation level, position size and reward-to-risk, computed before entry." },
          { title: "Trade history", note: "Your own past trades as context for the current one." },
        ],
      },
      {
        title: "Managing the position",
        items: [
          { title: "Trade management", note: "Partial targets, stop movement and what changed since entry." },
          { title: "Smart Exit", note: "A continuous re-read of an open position, not a fixed target set once." },
        ],
      },
    ],
  },

  ai: {
    eyebrow: "The engine",
    line1: "How SmartPips",
    line2: "reaches a decision.",
    lead: "Six independent inputs, evaluated separately and then reconciled. No single indicator can carry a decision on its own.",
    stepsTitle: "What happens on every read",
    steps: [
      { num: "01", title: "Collect", note: "Price, volume and your trade history for the selected symbol and timeframe." },
      { num: "02", title: "Evaluate separately", note: "Each input is scored on its own terms, so a strong structure read is not hidden by weak volatility." },
      { num: "03", title: "Reconcile", note: "Agreements raise confidence; contradictions lower it and are reported, not hidden." },
      { num: "04", title: "Commit or wait", note: "If the inputs do not agree, the honest output is no trade — and it says so." },
    ],
    honestTitle: "What the confidence number is",
    honestBody: "Signal confidence describes how well the inputs agree with each other on this read. It is a measure of internal consistency, not a probability of profit, and we do not present it as one.",
  },

  scalp: {
    eyebrow: "Scalp engine",
    line1: "Precision for",
    line2: "the fastest markets.",
    lead: "On low timeframes the difference between a good entry and a bad one is a few seconds of patience. The scalp engine enforces that patience.",
    logicTitle: "The confirm-pullback rule",
    logicLead: "The single rule that removes most bad scalp entries: never enter extended.",
    logicItems: [
      { title: "Distance from EMA9", note: "If price is stretched far from the mean, the setup is valid but the entry is not — yet." },
      { title: "Pullback", note: "Wait for price to return toward the mean without breaking the structure that created the setup." },
      { title: "Confirmation", note: "Entry is validated only once the pullback holds and order flow turns back in the direction of the trade." },
    ],
    noteTitle: "Why this matters more on low timeframes",
    noteBody: "A scalp has no room to be wrong. Entering extended means your stop sits where the market is most likely to go next, which turns a correct read into a losing trade.",
  },

  exit: {
    eyebrow: "Smart Exit",
    line1: "Getting in is",
    line2: "only half the trade.",
    lead: "The conditions that justified your entry do not stay true forever. Smart Exit re-reads the market while the position is open and tells you what changed.",
    regimeTitle: "Exits depend on the environment",
    regimeLead: "The same profit in a trending market and a ranging market call for different decisions. Select a regime to see the difference.",
    decisionsTitle: "Four possible answers",
    decisions: [
      { title: "Hold", note: "The original read is intact. Nothing to do, which is a decision too." },
      { title: "Trailing stop", note: "The move has given you something worth protecting without invalidating the target." },
      { title: "Close part", note: "Structure is weakening but not broken. Reduce exposure, keep the position alive." },
      { title: "Exit now", note: "The reason you entered is gone. Waiting for your stop is no longer a plan." },
    ],
  },

  how: {
    eyebrow: "How it works",
    line1: "From connection",
    line2: "to managed trade.",
    lead: "Five stages. You stay in control of the decision at every one of them.",
    faqTitle: "Common questions about the workflow",
    faqs: [
      { q: "Does SmartPips place trades for me?", a: "No. It produces a structured read and, if you choose, sends the order parameters to your exchange for you to confirm. The decision stays yours." },
      { q: "Which markets does it work on?", a: "Crypto perpetuals are the primary focus, plus metals and indices where reliable data is available." },
      { q: "Do I need to connect an exchange?", a: "No. You can use SmartPips purely as an analysis and journalling layer. Connecting an exchange only adds position awareness and order placement." },
    ],
  },

  pricing: {
    eyebrow: "Pricing",
    line1: "Straightforward",
    line2: "and honest.",
    lead: "No performance fees, no profit-sharing, no upsells based on promised returns.",
    monthly: "per month",
    plans: [
      {
        name: "Starter",
        price: "—",
        tagline: "Learn the method on your own charts.",
        cta: "Get started",
        featured: false,
        features: [
          "Market structure and liquidity reads",
          "Signal confirmation",
          "Trade journal",
          "Manual analysis, unlimited symbols",
        ],
      },
      {
        name: "Trader",
        price: "—",
        tagline: "The full intelligence layer, including Smart Exit.",
        cta: "Get started",
        featured: true,
        features: [
          "Everything in Starter",
          "Scalp engine with confirm-pullback",
          "Smart Exit on open positions",
          "Exchange connection and position awareness",
          "Push alerts on confirmed setups",
        ],
      },
      {
        name: "Pro",
        price: "—",
        tagline: "For traders running multiple accounts.",
        cta: "Contact us",
        featured: false,
        features: [
          "Everything in Trader",
          "Multiple exchange accounts",
          "Extended trade history analysis",
          "Priority support",
        ],
      },
    ],
    note: "Prices are being finalised. Until then, reach out and we will tell you exactly what access costs — no sales call required.",
    faqTitle: "Before you ask",
    faqs: [
      { q: "Is there a free trial?", a: "Yes. You can use the analysis layer without connecting an exchange, so you can judge the quality of the reads before paying anything." },
      { q: "Do you take a share of profits?", a: "No. We charge for software access only. A profit share would give us an incentive to encourage more trading, which is the opposite of what this product is for." },
      { q: "Can I cancel any time?", a: "Yes, with no cancellation fee." },
    ],
  },

  faq: {
    eyebrow: "FAQ",
    line1: "Questions worth",
    line2: "answering properly.",
    lead: "If something is missing here, ask us directly and we will add it.",
    groups: [
      {
        title: "The product",
        items: [
          { q: "What is SmartPips, in one sentence?", a: "An intelligent trading assistant that turns complex market information into a structured trading decision." },
          { q: "Is it a trading bot?", a: "No. It does not trade autonomously and it is not designed to. It produces a read and a plan; you decide whether to take it." },
          { q: "Is it a signal group?", a: "No. A signal tells you what to do. SmartPips shows you why, on your chart, so you can disagree with it." },
          { q: "Will it make me profitable?", a: "We cannot honestly promise that and will not. What it can do is make your decisions consistent and your risk explicit, which is the part you control." },
        ],
      },
      {
        title: "How it analyses",
        items: [
          { q: "Which timeframes are supported?", a: "1m through 1d. The scalp engine is tuned for 1m and 5m; structure reads are more reliable higher up." },
          { q: "What is signal confidence?", a: "A measure of how well the six inputs agree with each other on a given read. It is not a probability of profit." },
          { q: "Does it repaint?", a: "Structure levels are drawn from confirmed swing points, so a level does not move once printed. A read can be superseded by new price action, and when that happens Smart Exit tells you." },
        ],
      },
      {
        title: "Accounts and data",
        items: [
          { q: "Which exchanges can I connect?", a: "Bitunix and LBank futures are supported today, with cTrader and MetaTrader bridges for FX and metals." },
          { q: "Can it withdraw my funds?", a: "No. API keys are used for reading positions and placing orders only. Never enable withdrawal permissions on a key you give to any third-party tool, including this one." },
          { q: "Is there a demo mode?", a: "Yes. You can run positions in demo alongside real ones, and the panel labels every position with which it is." },
        ],
      },
    ],
  },

  contact: {
    eyebrow: "Contact",
    line1: "Talk to the people",
    line2: "who built it.",
    lead: "Questions about the method, pricing, or a market you want supported — all of it reaches us directly.",
    formTitle: "Send a message",
    formNote: "This opens your mail app with the message ready to send.",
    name: "Your name",
    email: "Email",
    subject: "Subject",
    message: "Message",
    send: "Compose message",
    directTitle: "Or reach us directly",
    emailLabel: "Email",
    responseLabel: "Response time",
    responseValue: "Usually within one business day",
    topicsTitle: "Good reasons to write",
    topics: [
      "A market or exchange you want supported",
      "A question about how a specific read was formed",
      "Pricing and access",
      "Something on this site that is wrong or unclear",
    ],
  },

  cta: {
    line1: "Trade with context.",
    line2: "Not noise.",
    sub: "Bring structure to every decision with SmartPips.",
    primary: "Get started",
    secondary: "Explore the platform",
  },
};

export default en;
