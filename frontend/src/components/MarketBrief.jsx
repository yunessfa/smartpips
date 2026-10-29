import { useEffect, useState } from "react";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";
import { fill } from "../lib/fill.jsx";

/**
 * Decision-first market brief (server: apps/strategy/market_brief.py).
 *
 * Shows only what the 2026-10 indicator study found to matter — HTF trend,
 * EMA alignment, distance from EMA21, volatility vs the cost floor — plus the
 * single next step, and WHEN the reading can change: the engine reads closed
 * candles, so repeated requests inside one candle return the same answer and
 * are marked "unchanged" instead of looking like a fresh analysis.
 */
const STATE_ICON = { ok: "✓", bad: "✗", neutral: "•" };
const STATE_TONE = { ok: "text-up", bad: "text-down", neutral: "text-mist-500" };

function useNow(active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

function clock(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export default function MarketBrief({ ai, unchanged }) {
  const { t } = useI18n();
  const brief = ai?.brief;
  const now = useNow(Boolean(brief?.next_update_at));
  if (!ai) return null;

  const status = ai.signal;
  const isTrade = status === "buy" || status === "sell";
  const isLimit = ai.entry_plan?.type === "limit";
  const headline = status === "buy" ? (isLimit ? t("mb_buy_limit") : t("mb_buy"))
    : status === "sell" ? (isLimit ? t("mb_sell_limit") : t("mb_sell")) : t("mb_wait");
  const tone = status === "buy" ? "text-up" : status === "sell" ? "text-down" : "text-gold-soft";
  const ring = status === "buy" ? "border-up/40 bg-up/[0.06]" : status === "sell" ? "border-down/40 bg-down/[0.06]"
    : "border-ink-500 bg-ink-800/60";
  const validated = ai.signal_source === "playbook";
  const left = brief?.next_update_at ? Math.max(0, brief.next_update_at - Math.floor(now / 1000)) : null;
  const mmss = left != null ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : null;

  return (
    <div className={`rounded-2xl border p-4 ${ring}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`text-2xl font-extrabold leading-tight ${tone}`}>{headline}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className={`rounded-md border px-2 py-0.5 ${validated ? "border-up/40 text-up" : "border-gold/40 text-gold-soft"}`}>
              {validated ? `✓ ${t("mb_src_playbook")}` : t("mb_src_engine")}
            </span>
            {brief?.timeframe && <span className="rounded-md border border-ink-500 px-2 py-0.5 text-mist-400">{brief.timeframe}</span>}
            {unchanged && <span className="rounded-md border border-ink-500 px-2 py-0.5 text-mist-400">{t("mb_unchanged")}</span>}
          </div>
        </div>
        {brief?.bar_time && (
          <div className="text-end text-[11px] leading-relaxed text-mist-500">
            <p>{fill(t("mb_bar_closed"), { time: clock(brief.bar_time + stepOf(brief.timeframe)) })}</p>
            {mmss && <p>{fill(t("mb_next_update"), { left: mmss })}</p>}
          </div>
        )}
      </div>

      {brief?.next && <NextStep next={brief.next} tf={brief.timeframe} />}
      {!brief && status === "wait" && ai.reason && (
        <p className="mt-3 rounded-lg border border-ink-500 bg-ink-900/50 px-3 py-2 text-sm text-mist-200">{ai.reason}</p>
      )}

      {brief?.facts?.length > 0 && (
        <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
          {brief.facts.map((f) => (
            <li key={f.key} className="flex items-center justify-between gap-2 rounded-lg bg-ink-900/40 px-3 py-2 text-sm">
              <span className="flex items-center gap-2 text-mist-300">
                <span className={`w-4 text-center font-bold ${STATE_TONE[f.state]}`}>{STATE_ICON[f.state]}</span>
                {t(`mb_fact_${f.key}`)}
              </span>
              <span className={`text-[13px] font-semibold ${STATE_TONE[f.state] === "text-mist-500" ? "text-mist-200" : STATE_TONE[f.state]}`}>
                <FactValue f={f} />
              </span>
            </li>
          ))}
        </ul>
      )}

      {!isTrade && brief && (
        <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
          {brief.pullback_level && <LevelChip label={t("mb_lvl_pullback")} value={brief.pullback_level} tone="gold" />}
          {brief.support && <LevelChip label={t("mb_lvl_support")} value={brief.support} tone="up" />}
          {brief.resistance && <LevelChip label={t("mb_lvl_resistance")} value={brief.resistance} tone="down" />}
        </div>
      )}
      {(ai.risk_block || ai.news_guard) && (
        <p className="mt-3 rounded-lg border border-down/40 bg-down/10 px-3 py-2 text-sm text-down">
          ⛔ {ai.risk_block || ai.news_guard}
        </p>
      )}
    </div>
  );
}

function stepOf(tf) {
  return { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400 }[tf] || 300;
}

function FactValue({ f }) {
  const { t } = useI18n();
  if (f.key === "h4_trend" || f.key === "h1_trend") {
    return t(f.value === 1 ? "mb_up" : f.value === -1 ? "mb_down" : "mb_flat");
  }
  if (f.key === "ema_stack") return t(f.value === 1 ? "mb_stack_up" : f.value === -1 ? "mb_stack_down" : "mb_stack_mixed");
  if (f.key === "stretch") return <bdi dir="ltr">{Math.abs(f.value).toFixed(1)} / {f.need} ATR</bdi>;
  if (f.key === "volatility") return <bdi dir="ltr">{Number(f.value).toFixed(2)}% / ≥{f.need}%</bdi>;
  return String(f.value);
}

function LevelChip({ label, value, tone }) {
  const c = tone === "up" ? "border-up/30 text-up" : tone === "down" ? "border-down/30 text-down" : "border-gold/40 text-gold-soft";
  return (
    <span className={`rounded-lg border px-2.5 py-1 ${c}`}>
      <span className="text-mist-500">{label}</span> <bdi dir="ltr" className="font-semibold">{fmtPrice(value)}</bdi>
    </span>
  );
}

export function NextStep({ next, tf, compact = false }) {
  const { t } = useI18n();
  const side = (d) => t(d === 1 ? "mb_side_buy" : "mb_side_sell");
  const map = {
    limit_active: () => fill(t("mb_next_limit_active"), { price: fmtPrice(next.price), bars: next.valid_bars ?? "—",
      min: next.valid_minutes ?? "—" }),
    signal_active: () => fill(t("mb_next_signal_active"), { price: fmtPrice(next.price) }),
    wait_stretch: () => fill(t(next.dir === 1 ? "mb_next_stretch_up" : "mb_next_stretch_down"),
      { trigger: fmtPrice(next.trigger), limit: fmtPrice(next.limit), side: side(next.dir) }),
    wait_volatility: () => fill(t("mb_next_volatility"), { now: `${next.now_pct}%`, need: `${next.need_pct}%` }),
    wait_trend: () => t("mb_next_trend"),
    wait_h1: () => t("mb_next_h1"),
    wait_stack: () => fill(t("mb_next_stack"), { side: side(next.dir), tf }),
    tf_not_validated: () => t("mb_next_tf"),
    blocked: () => t("mb_next_blocked"),
    no_data: () => t("mb_next_no_data"),
  };
  const body = (map[next.code] || (() => null))();
  if (!body) return null;
  if (compact) return <span>{body}</span>;
  return (
    <p className="mt-3 rounded-lg border border-gold/25 bg-gold/[0.06] px-3 py-2 text-sm leading-relaxed text-mist-100">
      <span className="text-gold-soft">→ </span>{body}
    </p>
  );
}
