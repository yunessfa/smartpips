import { motion, useReducedMotion } from "framer-motion";
import { IntelCanvas } from "./RawIntel.jsx";

/**
 * The visual companion to the login form.
 *
 * It reuses the landing page's `IntelCanvas`, which means the chart a user sees
 * while signing in is literally the same series, levels and R:R the marketing
 * site showed them a moment earlier. That continuity is the whole point — a
 * generic gradient here would quietly undo the product identity work.
 *
 * Desktop only; the login page drops it entirely on narrow screens rather than
 * squeezing it into a decorative band.
 */

const COPY = {
  en: {
    badge: "SmartPips Engine",
    symbol: "BTCUSDT",
    timeframe: "5m",
    tp: "TP",
    entry: "ENTRY",
    sl: "SL",
    rr: "R:R",
    rrValue: "1:2.4",
    confidence: "Signal confidence",
    status: [
      "Market structure detected",
      "Liquidity sweep detected",
      "Signal confidence 94%",
    ],
    footer: "Structure · Liquidity · Order flow · Risk · Exit",
  },
  fa: {
    badge: "\u0645\u0648\u062a\u0648\u0631 SmartPips",
    symbol: "BTCUSDT",
    timeframe: "5m",
    tp: "TP",
    entry: "ENTRY",
    sl: "SL",
    rr: "R:R",
    rrValue: "1:2.4",
    confidence: "\u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0633\u06cc\u06af\u0646\u0627\u0644",
    status: [
      "\u0633\u0627\u062e\u062a\u0627\u0631 \u0628\u0627\u0632\u0627\u0631 \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0634\u062f",
      "\u062c\u0645\u0639\u200c\u0622\u0648\u0631\u06cc \u0646\u0642\u062f\u06cc\u0646\u06af\u06cc \u062a\u0634\u062e\u06cc\u0635 \u062f\u0627\u062f\u0647 \u0634\u062f",
      "\u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0633\u06cc\u06af\u0646\u0627\u0644 \u06f9\u06f4\u066a",
    ],
    footer:
      "\u0633\u0627\u062e\u062a\u0627\u0631 · \u0646\u0642\u062f\u06cc\u0646\u06af\u06cc · \u062c\u0631\u06cc\u0627\u0646 \u0633\u0641\u0627\u0631\u0634 · \u0631\u06cc\u0633\u06a9 · \u062e\u0631\u0648\u062c",
  },
};

export function AuthAside({ isRTL = false, className = "" }) {
  const reduced = useReducedMotion();
  const c = isRTL ? COPY.fa : COPY.en;

  return (
    <div className={`relative ${className}`}>
      <div className="relative overflow-hidden rounded-2xl border border-white/[0.07] bg-sp-s1/60 shadow-[0_24px_70px_-30px_rgba(0,0,0,0.95)] backdrop-blur-sm">
        {/* Instrument header, matched to the landing hero frame. */}
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 rounded-md border border-signal/20 bg-signal/[0.06] px-2 py-1">
              <span className="h-1 w-1 rounded-full bg-signal" />
              <span className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-signal-soft">
                {c.badge}
              </span>
            </span>
            <span className="font-mono text-[12px] font-medium tabular-nums text-sp-t1">
              {c.symbol}
            </span>
            <span className="font-mono text-[11px] text-sp-t4">{c.timeframe}</span>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-sp-t4">
            {c.rr} <span className="text-signal">{c.rrValue}</span>
          </span>
        </div>

        <div className="h-[300px] xl:h-[360px]">
          <IntelCanvas labels={c} />
        </div>

        {/* Confidence readout. */}
        <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-sp-t4">
            {c.confidence}
          </span>
          <div className="flex items-center gap-3">
            <div className="h-1 w-28 overflow-hidden rounded-full bg-sp-s3">
              <motion.div
                className="h-full rounded-full bg-signal"
                initial={{ width: 0 }}
                animate={{ width: "94%" }}
                transition={{ duration: 1.2, delay: 0.9, ease: [0.2, 0.7, 0.3, 1] }}
              />
            </div>
            <span className="font-mono text-[12px] font-semibold tabular-nums text-signal">94%</span>
          </div>
        </div>
      </div>

      {/* Status rail. Monospace machine output, not a feature bullet list. */}
      <div className="mt-6 border-s border-sp-line ps-4">
        {c.status.map((line, i) => (
          <motion.div
            key={line}
            className="flex items-center gap-2.5 py-1"
            initial={reduced ? false : { opacity: 0, x: isRTL ? 8 : -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.6 + i * 0.3, ease: [0.2, 0.7, 0.3, 1] }}
          >
            <motion.span
              className="h-1 w-1 rounded-full bg-signal"
              animate={reduced ? {} : { opacity: [0.35, 1, 0.35] }}
              transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.5 }}
            />
            <span className="font-mono text-[11px] tracking-wide text-sp-t3">{line}</span>
          </motion.div>
        ))}
      </div>

      <p className="mt-5 font-mono text-[10.5px] uppercase tracking-[0.16em] text-sp-t4">
        {c.footer}
      </p>
    </div>
  );
}

export default AuthAside;
