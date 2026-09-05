import { useI18n } from "../i18n/index.jsx";

/**
 * Public-site copy deck.
 *
 * Editorial rules this file follows:
 *   1. Every line describes something the product actually does. No
 *      "revolutionary", no "next generation", no "transform your trading".
 *   2. No invented proof. There are no user counts, win rates or returns
 *      anywhere in here, because we cannot substantiate them and a trading
 *      audience punishes unearned claims harder than any other.
 *   3. Each section answers exactly one reader question, noted in a comment.
 *
 * Persian is authored as a translation of intent, not of words — a literal
 * rendering of English trading copy reads like a machine wrote it.
 */

const en = {
  nav: {
    features: "Features",
    ai: "AI",
    scalp: "Scalp",
    how: "How It Works",
    pricing: "Pricing",
    login: "Log in",
    openApp: "Open App",
    start: "Get Started",
    menu: "Menu",
    close: "Close",
  },

  // Q: What is SmartPips?
  hero: {
    eyebrow: "AI Trading Intelligence",
    line1: "Turn Market Complexity",
    line2: "Into Clear Decisions.",
    sub: "SmartPips combines market structure, liquidity, order flow, risk and trade management into one intelligent trading assistant.",
    ctaPrimary: "Start Trading Smarter",
    ctaSecondary: "Explore SmartPips",
    status: [
      "Market structure detected",
      "Liquidity sweep detected",
      "Signal confidence 94%",
    ],
    chart: {
      symbol: "BTCUSDT",
      timeframe: "5m",
      engine: "AI Engine",
      structure: "Market Structure",
      liquidity: "Liquidity",
      mss: "MSS",
      entry: "Entry",
      tp: "TP",
      sl: "SL",
      ai: "AI",
      rr: "R:R",
      rrValue: "1:2.4",
      confidence: "Signal Confidence",
      orderFlow: "Order Flow",
    },
  },

  // Q: Why do I need it?
  context: {
    eyebrow: "The Problem",
    line1: "Trading Doesn't Lack Data.",
    line2: "It Lacks Context.",
    sub: "Markets generate thousands of signals every second. SmartPips filters the noise and connects the information that actually matters.",
    rawLabel: "Raw Market Data",
    outLabel: "SmartPips Intelligence",
    rawTags: ["Ticks", "Volatility", "Events", "Noise"],
    outputs: [
      { title: "Structure", note: "Trend intact, or broken" },
      { title: "Liquidity", note: "Where resting orders sit" },
      { title: "Bias", note: "A direction you can act on" },
      { title: "Risk", note: "Size and invalidation, up front" },
      { title: "Exit", note: "Hold, trail, trim or leave" },
    ],
  },

  // Q: How does it think?
  engine: {
    eyebrow: "The Engine",
    line1: "Six Inputs.",
    line2: "One Decision.",
    sub: "SmartPips doesn't rely on a single indicator. It evaluates multiple independent views of the market before forming a trading decision.",
    core: "AI Core",
    verdict: "One Structured Decision",
    inputs: [
      { title: "Market Structure", note: "Higher highs, breaks of structure, trend integrity" },
      { title: "Liquidity", note: "Resting orders, sweeps and voids" },
      { title: "Order Flow", note: "Which side is actually aggressive" },
      { title: "Volatility", note: "Expansion and contraction regimes" },
      { title: "Risk", note: "Exposure, leverage and account health" },
      { title: "Trade History", note: "What has actually worked for you" },
    ],
  },

  // Q: What does it analyse?
  layers: {
    eyebrow: "Market Intelligence",
    line1: "From Market Noise",
    line2: "to Market Structure.",
    sub: "Five layers of analysis, applied to one chart. Turn them on and the same price action reads completely differently.",
    hint: "Select a layer",
    items: [
      {
        id: "structure",
        num: "01",
        title: "Market Structure",
        note: "Swing points, break of structure and the trend they define.",
      },
      {
        id: "liquidity",
        num: "02",
        title: "Liquidity",
        note: "Zones where stops rest, and the sweeps that collect them.",
      },
      {
        id: "orderflow",
        num: "03",
        title: "Order Flow",
        note: "Delta between aggressive buyers and sellers, bar by bar.",
      },
      {
        id: "risk",
        num: "04",
        title: "Risk",
        note: "Invalidation, position size and reward, defined before entry.",
      },
      {
        id: "exit",
        num: "05",
        title: "Exit",
        note: "Targets, trailing logic and the point where the idea is done.",
      },
    ],
  },

  // Q: How does it help me trade?
  scalp: {
    eyebrow: "Scalp Engine",
    line1: "Precision for the",
    line2: "Fastest Markets.",
    sub: "SmartPips identifies structure, liquidity and confirmation before a scalp setup becomes actionable.",
    replay: "Replay",
    checks: [
      { state: "wait", text: "Price too far from EMA9" },
      { state: "progress", text: "Pullback confirmed" },
      { state: "done", text: "Entry validated" },
    ],
    steps: [
      { tag: "LIQ", title: "Liquidity", note: "Resting stops identified below the range" },
      { tag: "MSS", title: "Structure Shift", note: "Market structure breaks to the upside" },
      { tag: "PB", title: "Pullback", note: "Price returns toward the EMA9" },
      { tag: "CONF", title: "Confirmation", note: "Order flow turns with the break" },
      { tag: "IN", title: "Entry", note: "Setup becomes actionable" },
      { tag: "TP", title: "TP / SL", note: "Target and invalidation set together" },
    ],
  },

  // Q: How does it manage the position?
  exit: {
    eyebrow: "Smart Exit",
    line1: "Getting In Is Only",
    line2: "Half the Trade.",
    sub: "An open position is a live question. SmartPips re-reads structure, order flow, liquidity and position strength, then commits to one answer.",
    positionLabel: "Open Position",
    verdict: "AI Verdict",
    reads: ["Structure", "Order Flow", "Liquidity", "Strength"],
    states: [
      { label: "Hold", tone: "info", note: "Structure intact. The thesis still stands." },
      { label: "Trailing Stop", tone: "gold", note: "Move the stop up. Protect what the move has given." },
      { label: "Close Part", tone: "up", note: "Take partial size off into the liquidity above." },
      { label: "Exit Now", tone: "down", note: "Order flow flipped. The reason for the trade is gone." },
    ],
  },

  // Q: Does it understand the conditions I'm trading in?
  regime: {
    eyebrow: "Market Regime",
    line1: "The Same Setup Isn't",
    line2: "Valid in Every Market.",
    sub: "SmartPips classifies the environment first, then changes what it looks for. A breakout in a range is not a breakout.",
    items: [
      { id: "trend", label: "Trend", note: "Directional continuation. Structure leads, pullbacks are entries." },
      { id: "range", label: "Range", note: "Mean reversion. Edges matter, breakouts are suspect." },
      { id: "highvol", label: "High Volatility", note: "Wider stops, smaller size, faster invalidation." },
      { id: "lowvol", label: "Low Volatility", note: "Compression. Wait for expansion rather than force a trade." },
    ],
  },

  // Q: What does it actually look like?
  product: {
    eyebrow: "The Product",
    line1: "One Intelligence Layer",
    line2: "Across Your Workflow.",
    sub: "Analysis, signals, position management and your trade journal live in the same place — so the decision and the record of it never drift apart.",
    cta: "Open the App",
    bullets: ["Live analysis", "Position tracking", "Trade journal", "Exit guidance"],
  },

  // Q: How do I use it?
  how: {
    eyebrow: "How It Works",
    line1: "Connect. Analyse.",
    line2: "Decide. Manage. Exit.",
    sub: "One continuous loop, from account connection to closed trade.",
    steps: [
      { num: "01", title: "Connect", note: "Link your exchange account or run in demo mode." },
      { num: "02", title: "Analyse", note: "SmartPips reads structure, liquidity and order flow live." },
      { num: "03", title: "Decide", note: "You get a structured setup with entry, invalidation and target." },
      { num: "04", title: "Manage", note: "The position is monitored as conditions change." },
      { num: "05", title: "Exit", note: "Hold, trail, trim or close — with the reason attached." },
    ],
  },

  // Q: Can I trust this?
  trust: {
    eyebrow: "Positioning",
    line1: "Built Around Process,",
    line2: "Not Prediction.",
    sub: "SmartPips does not promise outcomes. It enforces a method: the same questions asked in the same order, on every trade, without the parts you skip when you're in a hurry.",
    pillars: [
      { title: "Market Structure", note: "Read the trend before the setup" },
      { title: "Liquidity", note: "Know where the orders are" },
      { title: "Risk", note: "Define the loss before the entry" },
      { title: "Confirmation", note: "Wait for the market to agree" },
      { title: "Trade Management", note: "Decide again while it's open" },
    ],
    disclaimer:
      "SmartPips is an analysis and decision-support tool. It is not financial advice, and it does not guarantee results. Trading carries risk of loss.",
  },

  // Q: Why should I try it?
  cta: {
    line1: "Trade With Context.",
    line2: "Not Noise.",
    sub: "Bring structure to every decision with SmartPips.",
    primary: "Get Started",
    secondary: "Explore the Platform",
    reassure: "Demo mode included · No exchange keys required to start",
  },

  footer: {
    tagline: "An intelligent trading assistant that turns complex market information into a structured trading decision.",
    product: "Product",
    company: "Company",
    resources: "Resources",
    rights: "All rights reserved.",
    risk: "Trading involves substantial risk. SmartPips provides analysis, not financial advice.",
  },
};

const fa = {
  nav: {
    features: "امکانات",
    ai: "هوش م��نوعی",
    scalp: "اسکلپ",
    how: "چگونه کار می‌کند",
    pricing: "تعرفه‌ها",
    login: "ورود",
    openApp: "ورود به پنل",
    start: "شروع کنید",
    menu: "منو",
    close: "بستن",
  },

  hero: {
    eyebrow: "هوش معاملاتی",
    line1: "پیچیدگی بازار را",
    line2: "به تصمیم روشن تبدیل کنید.",
    sub: "اسمارت‌پیپس ساختار بازار، نقدینگی، جریان سفارشات، ریسک و مدیریت معامله را در یک دستیار معاملاتی هوشمند جمع می‌کند.",
    ctaPrimary: "هوشمندتر معامله کنید",
    ctaSecondary: "معرفی اسمارت‌پیپس",
    status: [
      "ساختار بازار شناسایی شد",
      "جمع‌آوری نقدینگی تشخیص داده شد",
      "اطمینان سیگنال ۹۴٪",
    ],
    chart: {
      symbol: "BTCUSDT",
      timeframe: "5m",
      engine: "موتور هوشمند",
      structure: "ساختار بازار",
      liquidity: "نقدینگی",
      mss: "MSS",
      entry: "ورود",
      tp: "حد سود",
      sl: "حد ضرر",
      ai: "AI",
      rr: "ریسک به ریوارد",
      rrValue: "1:2.4",
      confidence: "اطمینان سیگنال",
      orderFlow: "جریان سفارشات",
    },
  },

  context: {
    eyebrow: "صورت مسئله",
    line1: "معامله‌گر کمبود داده ندارد؛",
    line2: "کمبود زمینه دارد.",
    sub: "بازار هر ثانیه هزاران نشانه تولید می‌کند. اسمارت‌پیپس نویز را حذف می‌کند و فقط اطلاعاتی را به هم وصل می‌کند که واقعاً اهمیت دارند.",
    rawLabel: "داده خام بازار",
    outLabel: "تحلیل اسمارت‌پیپس",
    rawTags: ["تیک", "نوسان", "رویداد", "نویز"],
    outputs: [
      { title: "ساختار", note: "روند پابرجاست یا شکسته" },
      { title: "نقدینگی", note: "جایی که سفارش‌ها نشسته‌اند" },
      { title: "جهت", note: "سویی که می‌توان رویش عمل کرد" },
      { title: "ریسک", note: "حجم و نقطه ابطال، از همان اول" },
      { title: "خروج", note: "نگه دار، تریل کن، کم کن یا ببند" },
    ],
  },

  engine: {
    eyebrow: "موتور تحلیل",
    line1: "شش ورودی.",
    line2: "یک تصمیم.",
    sub: "اسمارت‌پیپس به یک اندیکاتور تکیه نمی‌کند. قبل از رسیدن به یک تصمیم معاملاتی، چند نمای مستقل از بازار را هم‌زمان می‌سنجد.",
    core: "هسته هوشمند",
    verdict: "یک تصمیم ساختاریافته",
    inputs: [
      { title: "ساختار بازار", note: "سقف‌ها و کف‌ها، شکست ساختار، سلامت روند" },
      { title: "نقدینگی", note: "سفارش‌های نشسته، جمع‌آوری و خلأ" },
      { title: "جریان سفارشات", note: "اینکه واقعاً کدام سمت تهاجمی است" },
      { title: "نوسان", note: "دوره‌های انبساط و فشردگی" },
      { title: "ریسک", note: "میزان درگیری، اهرم و سلامت حساب" },
      { title: "تاریخچه معاملات", note: "آنچه واقعاً برای شما جواب داده" },
    ],
  },

  layers: {
    eyebrow: "هوش بازار",
    line1: "از نویز بازار",
    line2: "تا ساختار بازار.",
    sub: "پنج لایه تحلیل، روی یک چارت. هر لایه را که روشن کنید، همان حرکت قیمت طور دیگری خوانده می‌شود.",
    hint: "یک لایه را انتخاب کنید",
    items: [
      { id: "structure", num: "01", title: "ساختار بازار", note: "نقاط سویینگ، شکست ساختار و روندی که تعریف می‌کنند." },
      { id: "liquidity", num: "02", title: "نقدینگی", note: "نواحی‌ای که حد ضررها نشسته‌اند و جاروبی که جمعشان می‌کند." },
      { id: "orderflow", num: "03", title: "جریان سفارشات", note: "اختلاف خریدار و فروشنده تهاجمی، کندل به کندل." },
      { id: "risk", num: "04", title: "ریسک", note: "نقطه ابطال، حجم و پاداش، مشخص‌شده پیش از ورود." },
      { id: "exit", num: "05", title: "خروج", note: "اهداف، منطق تریل و جایی که ایده تمام می‌شود." },
    ],
  },

  scalp: {
    eyebrow: "موتور اسکلپ",
    line1: "دقت، برای",
    line2: "سریع‌ترین بازارها.",
    sub: "اسمارت‌پیپس پیش از اینکه یک موقعیت اسکلپ قابل اجرا شود، ساختار، نقدینگی و تأیید را مشخص می‌کند.",
    replay: "پخش دوباره",
    checks: [
      { state: "wait", text: "قیمت از EMA9 خیلی دور است" },
      { state: "progress", text: "پول‌بک تأیید شد" },
      { state: "done", text: "ورود معتبر است" },
    ],
    steps: [
      { tag: "LIQ", title: "نقدینگی", note: "حد ضررهای نشست�� زیر محدوده شناسایی شد" },
      { tag: "MSS", title: "تغییر ساختار", note: "ساختار بازار رو به بالا می‌شکند" },
      { tag: "PB", title: "پول‌بک", note: "قیمت به سمت EMA9 برمی‌گردد" },
      { tag: "CONF", title: "تأیید", note: "جریان سفارشات هم‌جهت با شکست می‌شود" },
      { tag: "IN", title: "ورود", note: "موقعیت قابل اجرا می‌شود" },
      { tag: "TP", title: "حد سود و ضرر", note: "هدف و نقطه ابطال با هم تعیین می‌شوند" },
    ],
  },

  exit: {
    eyebrow: "خروج هوشمند",
    line1: "ورود، فقط نیمی",
    line2: "از معامله است.",
    sub: "پوزیشن باز یک پرسش زنده است. اسمارت‌پیپس ساختار، جریان سفارشات، نقدینگی و قدرت پوزیشن را دوباره می‌خواند و به یک پاسخ می‌رسد.",
    positionLabel: "پوزیشن باز",
    verdict: "تصمیم هوش مصنوعی",
    reads: ["ساختار", "جریان سفارشات", "نقدینگی", "قدرت"],
    states: [
      { label: "نگه‌داری", tone: "info", note: "ساختار سالم است. فرضیه معامله هنوز برقرار است." },
      { label: "تریل حد ضرر", tone: "gold", note: "حد ضرر را بالا بیاورید و سود به‌دست‌آمده را حفظ کنید." },
      { label: "بستن بخشی", tone: "up", note: "بخشی از حجم را در نقدینگی بالا بردارید." },
      { label: "خروج فوری", tone: "down", note: "جریان سفارشات برگشت. دلیل ورود دیگر وجود ندارد." },
    ],
  },

  regime: {
    eyebrow: "رژیم بازار",
    line1: "یک ستاپ، در هر بازاری",
    line2: "معتبر نیست.",
    sub: "اسمارت‌پیپس اول محیط بازار را دسته‌بندی می‌کند، بعد تصمیم می‌گیرد دنبال چه بگردد. شکست در یک رنج، شکست نیست.",
    items: [
      { id: "trend", label: "رونددار", note: "ادامه جهتی. ساختار جلودار است و پول‌بک‌ها محل ورودند." },
      { id: "range", label: "رنج", note: "بازگشت به میانگین. لبه‌ها مهم‌اند و شکست‌ها مشکوک." },
      { id: "highvol", label: "نوسان بالا", note: "حد ضرر بازتر، حجم کمتر، ابطال سریع‌تر." },
      { id: "lowvol", label: "نوسان پایین", note: "فشردگی. به جای ساختن معامله، منتظر انبساط بمانید." },
    ],
  },

  product: {
    eyebrow: "محصول",
    line1: "یک لایه هوشمند",
    line2: "روی تمام جریان کاری شما.",
    sub: "تحلیل، سیگنال، مدیریت پوزیشن و ژورنال معاملاتی در یک جا قرار دارند — تا تصمیم و ثبتش از هم جدا نیفتند.",
    cta: "ورود به پنل",
    bullets: ["تحلیل زنده", "رصد پوزیشن", "ژورنال معاملات", "راهنمای خروج"],
  },

  how: {
    eyebrow: "چگونه کار می‌کند",
    line1: "اتصال. تحلیل.",
    line2: "تصمیم. مدیریت. خروج.",
    sub: "یک چرخه پیوسته، از اتصال حساب تا بسته شدن معامله.",
    steps: [
      { num: "01", title: "اتصال", note: "حساب صرافی را وصل کنید یا در حالت دمو شروع کنید." },
      { num: "02", title: "تحلیل", note: "ساختار، نقدینگی و جریان سفارشات زنده خوانده می‌شوند." },
      { num: "03", title: "تصمیم", note: "یک ستاپ ساختاریافته با ورود، ابطال و هدف می‌گیرید." },
      { num: "04", title: "مدیریت", note: "پوزیشن همزمان با تغییر شرایط رصد می‌شود." },
      { num: "05", title: "خروج", note: "نگه‌داری، تریل، کاهش یا بستن — همراه با دلیلش." },
    ],
  },

  trust: {
    eyebrow: "جایگاه محصول",
    line1: "ساخته‌شده برای فرآیند،",
    line2: "نه پیش‌بینی.",
    sub: "اسمارت‌پیپس نتیجه را تضمین نمی‌کند؛ یک روش را پایبند می‌کند: همان پرسش‌ها، با همان ترتیب، در هر معامله — بدون آن بخش‌هایی که در عجله حذف می‌کنید.",
    pillars: [
      { title: "ساختار بازار", note: "اول روند، بعد ستاپ" },
      { title: "نقدینگی", note: "بدانید سفارش‌ها کجا هستند" },
      { title: "ریسک", note: "ضرر را پیش از ورود تعریف کنید" },
      { title: "تأیید", note: "صبر کنید تا بازار موافقت کند" },
      { title: "مدیریت معامله", note: "در حین باز بودن، دوباره تصمیم بگیرید" },
    ],
    disclaimer:
      "اسمارت‌پیپس یک ابزار تحلیل و پشتیبانی تصمیم است. مشاوره مالی نیست و نتیجه‌ای را تضمین نمی‌کند. معامله با ریسک زیان همراه است.",
  },

  cta: {
    line1: "با زمینه معامله کنید،",
    line2: "نه با نویز.",
    sub: "با اسمارت‌پیپس به هر تصمیم ساختار بدهید.",
    primary: "شروع کنید",
    secondary: "معرفی پلتفرم",
    reassure: "حالت دمو موجود است · برای شروع نیازی به کلید صرافی نیست",
  },

  footer: {
    tagline: "دستیاری هوشمند که اطلاعات پیچیده بازار را به یک تصمیم معاملاتی ساختاریافته تبدیل می‌کند.",
    product: "محصول",
    company: "شرکت",
    resources: "منابع",
    rights: "تمامی حقوق محفوظ است.",
    risk: "معامله ریسک قابل توجهی دارد. اسمارت‌پیپس تحلیل ارائه می‌دهد، نه مشاوره مالی.",
  },
};

export const siteCopy = { en, fa };

/** Returns the copy deck for the active language, defaulting to Persian. */
export function useCopy() {
  const { lang } = useI18n();
  return lang === "en" ? en : fa;
}
