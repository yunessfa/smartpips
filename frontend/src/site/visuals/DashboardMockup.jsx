import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";

/**
 * Section 5 visual: the real terminal, floating in 3D space.
 *
 * This is a faithful reconstruction of the actual SmartPips panel — same
 * palette, same panel chrome, same layout — rendered as live DOM rather than a
 * screenshot. That matters for three reasons: it stays sharp on every display,
 * it costs a few KB instead of a heavy PNG, and it mirrors correctly in
 * Persian instead of showing an LTR screenshot to an RTL reader.
 *
 * The rotation unwinds as the section scrolls into view, so the terminal
 * settles from a tilted, distant object into a flat, readable one.
 */

const CANDLES = [
  38, 52, 45, 61, 55, 72, 66, 80, 74, 88, 82, 95, 90, 103, 97, 88,
  94, 108, 101, 115, 109, 122, 116, 130, 124, 137, 131, 145, 138, 152,
];

function MiniCandles() {
  return (
    <div className="flex h-full items-end gap-[3px]">
      {CANDLES.map((v, i) => {
        const up = i === 0 || v >= CANDLES[i - 1];
        return (
          <div
            key={i}
            className={`flex-1 rounded-[1px] ${up ? "bg-up/70" : "bg-down/70"}`}
            style={{ height: `${(v / 152) * 100}%` }}
          />
        );
      })}
    </div>
  );
}

function Row({ symbol, side, pnl, up }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.04] py-1.5 last:border-0">
      <div className="flex items-center gap-1.5">
        <span className="tnum text-[9px] font-semibold text-mist-100">{symbol}</span>
        <span className={`text-[7px] font-bold px-1 py-px rounded ${
          up ? "bg-up/20 text-up" : "bg-down/20 text-down"}`}>{side}</span>
      </div>
      <span className={`tnum text-[9px] font-semibold ${up ? "text-up" : "text-down"}`}>{pnl}</span>
    </div>
  );
}

export function DashboardMockup({ className = "" }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 90%", "center 40%"],
  });
  const p = useSpring(scrollYProgress, { stiffness: 70, damping: 22, mass: 0.6 });

  // Settles from a distant, tilted object into a flat, readable panel.
  const rotateX = useTransform(p, [0, 1], [22, 6]);
  const rotateY = useTransform(p, [0, 1], [-16, -3]);
  const scale = useTransform(p, [0, 1], [0.88, 1]);
  const y = useTransform(p, [0, 1], [70, 0]);
  const opacity = useTransform(p, [0, 0.35], [0, 1]);

  const style = reduced ? {} : { rotateX, rotateY, scale, y, opacity };

  return (
    <div ref={ref} className={`sx-scene ${className}`}>
      <motion.div
        style={style}
        className="relative mx-auto max-w-[1080px] [transform-style:preserve-3d]"
      >
        {/* ground glow beneath the floating panel */}
        <div
          aria-hidden
          className="pointer-events-none absolute -inset-x-16 -bottom-16 h-40 rounded-[50%]
            bg-gold/[0.07] blur-3xl"
        />

        <div className="relative overflow-hidden rounded-2xl border border-white/[0.08]
          bg-ink-900 shadow-mockup">

          {/* title bar */}
          <div className="flex items-center gap-2 border-b border-white/[0.06] bg-ink-800/80 px-4 py-2.5">
            <span className="h-2.5 w-2.5 rounded-full bg-down/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-gold/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-up/60" />
            <span className="ms-3 font-mono text-[10px] text-mist-500">smartpips.app/app</span>
            <span className="ms-auto flex items-center gap-1.5 font-mono text-[9px] text-up">
              <span className="h-1.5 w-1.5 rounded-full bg-up live-dot" />
              LIVE
            </span>
          </div>

          <div className="flex">
            {/* sidebar */}
            <div className="hidden w-40 shrink-0 border-e border-white/[0.06] bg-ink-800/50 p-3 sm:block">
              <div className="mb-4 flex items-center gap-2">
                <div className="grid h-6 w-6 place-items-center rounded-md bg-gold/15">
                  <span className="text-[9px] font-bold text-gold">SP</span>
                </div>
                <span className="text-[10px] font-semibold text-mist-100">SmartPips</span>
              </div>
              {["Dashboard", "Chat", "Scalp", "Bitunix", "Trades", "Sources"].map((n, i) => (
                <div
                  key={n}
                  className={`mb-0.5 rounded-md px-2 py-1.5 text-[9px] ${
                    i === 3 ? "bg-gold/10 text-gold" : "text-mist-500"}`}
                >
                  {n}
                </div>
              ))}
            </div>

            {/* main */}
            <div className="min-w-0 flex-1 p-3 sm:p-4">
              {/* stat strip */}
              <div className="mb-3 grid grid-cols-4 gap-2">
                {[
                  ["Equity", "12,480", "text-mist-100"],
                  ["Today", "+312.40", "text-up"],
                  ["Open", "3", "text-mist-100"],
                  ["Win rate", "68%", "text-gold"],
                ].map(([label, value, tone]) => (
                  <div key={label} className="rounded-lg border border-white/[0.06] bg-ink-700/60 px-2 py-1.5">
                    <div className="text-[7px] uppercase tracking-wider text-mist-500">{label}</div>
                    <div className={`tnum text-[11px] font-semibold ${tone}`}>{value}</div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                {/* chart panel */}
                <div className="rounded-lg border border-white/[0.06] bg-ink-700/40 p-3 lg:col-span-2">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="tnum text-[10px] font-semibold text-mist-100">BTCUSDT</span>
                      <span className="rounded bg-up/20 px-1 py-px text-[7px] font-bold text-up">LONG 20x</span>
                    </div>
                    <span className="tnum text-[10px] font-semibold text-up">+248.60</span>
                  </div>

                  <div className="relative h-28 sm:h-36">
                    <MiniCandles />
                    {/* TP / ENTRY / SL levels drawn over the series */}
                    {[
                      ["TP", "18%", "border-up/60", "text-up", "bg-up/15"],
                      ["ENTRY", "52%", "border-gold/70", "text-gold", "bg-gold/15"],
                      ["SL", "82%", "border-down/60", "text-down", "bg-down/15"],
                    ].map(([label, top, border, text, chip]) => (
                      <div key={label} className="absolute inset-x-0 flex items-center" style={{ top }}>
                        <div className={`h-0 flex-1 border-t border-dashed ${border}`} />
                        <span className={`ms-1 rounded px-1 py-px font-mono text-[7px] ${chip} ${text}`}>
                          {label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* positions panel */}
                <div className="rounded-lg border border-white/[0.06] bg-ink-700/40 p-3">
                  <div className="mb-1.5 text-[8px] uppercase tracking-wider text-mist-500">
                    Open positions
                  </div>
                  <Row symbol="BTCUSDT" side="LONG" pnl="+248.60" up />
                  <Row symbol="ETHUSDT" side="LONG" pnl="+41.20" up />
                  <Row symbol="SOLUSDT" side="SHORT" pnl="-12.80" up={false} />

                  <div className="mt-3 rounded-md border border-gold/20 bg-gold/[0.06] p-2">
                    <div className="mb-1 font-mono text-[7px] uppercase tracking-wider text-gold">
                      AI verdict
                    </div>
                    <div className="text-[9px] font-semibold text-mist-100">Trail your stop</div>
                    <div className="mt-0.5 text-[8px] leading-snug text-mist-500">
                      Momentum expanding. Protect the move without capping it.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

export default DashboardMockup;
