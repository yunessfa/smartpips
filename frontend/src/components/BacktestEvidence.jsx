import { useI18n } from "../i18n/index.jsx";

/**
 * How much can a backtest be trusted?
 *
 * Shows the server's sample-size verdict (95% confidence interval for the
 * expectancy), the early/late split, costs, the window length and — for the
 * validated trend-pullback playbook — the multi-year research it was chosen on.
 * A profit factor above 1 on twelve trades is not shown as "profitable".
 */
const VERDICT_TONE = {
  positive_edge: "border-up/40 bg-up/10 text-up",
  negative_edge: "border-down/40 bg-down/10 text-down",
  inconclusive: "border-gold/40 bg-gold/10 text-gold-soft",
  insufficient_sample: "border-gold/40 bg-gold/10 text-gold-soft",
  no_trades: "border-ink-500 bg-ink-800 text-mist-400",
};

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}`;
}

export default function BacktestEvidence({ result }) {
  const { t } = useI18n();
  if (!result) return null;
  const ev = result.evidence;
  const diag = result.data_diagnostics || {};
  const trades = result.trades || 0;
  const feePerTrade = trades ? (result.est_fee_r || 0) / trades : null;
  const research = result.research_evidence;
  const summary = research?.summary;

  return (
    <div className="mt-3 space-y-3 text-xs">
      {ev && (
        <div className={`rounded-lg border px-3 py-2 ${VERDICT_TONE[ev.verdict] || VERDICT_TONE.no_trades}`}>
          <p className="font-semibold">{t(`bt_ev_${ev.verdict}`)}</p>
          <p className="mt-1 leading-relaxed text-mist-300">
            {t(`bt_ev_${ev.verdict}_hint`)}
          </p>
          {ev.expectancy_95ci && (
            <p className="tnum mt-1 text-mist-300">
              {t("bt_ev_ci")}:{" "}
              <bdi dir="ltr">{fmt(ev.expectancy_95ci[0], 3)}R … {fmt(ev.expectancy_95ci[1], 3)}R</bdi>
              {ev.t_stat != null && <span className="text-mist-500"> · <bdi dir="ltr">t = {ev.t_stat}</bdi></span>}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Cell label={t("bt_ev_window")}
          value={diag.days_covered != null ? `${diag.days_covered} ${t("bt_ev_days")}` : `${result.candles_used ?? "—"}`} />
        <Cell ltr label={t("bt_ev_fee_per_trade")} value={feePerTrade != null ? `${feePerTrade.toFixed(2)}R` : "—"}
          tone={feePerTrade != null && feePerTrade > 0.25 ? "down" : "neutral"} />
        {ev?.in_sample && (
          <Cell ltr label={t("bt_ev_early")} value={`${fmt(ev.in_sample.expectancy_r, 3)}R · ${ev.in_sample.n}`}
            tone={(ev.in_sample.expectancy_r ?? 0) > 0 ? "up" : "down"} />
        )}
        {ev?.out_of_sample?.n > 0 && (
          <Cell ltr label={t("bt_ev_late")} value={`${fmt(ev.out_of_sample.expectancy_r, 3)}R · ${ev.out_of_sample.n}`}
            tone={(ev.out_of_sample.expectancy_r ?? 0) > 0 ? "up" : "down"} />
        )}
        {result.exit_reasons && (
          <Cell ltr label={t("bt_ev_exits")}
            value={`🎯${result.exit_reasons.target} · 🛑${result.exit_reasons.stop} · ⏱${result.exit_reasons.timeout}`} />
        )}
        {ev?.positive_months_pct != null && (
          <Cell label={t("bt_ev_months")} value={`${ev.positive_months_pct}%`} />
        )}
      </div>

      {feePerTrade != null && feePerTrade > 0.25 && (
        <p className="rounded-lg border border-down/30 bg-down/10 px-3 py-2 leading-relaxed text-mist-300">
          {t("bt_ev_fee_warning")}
        </p>
      )}

      {summary && (
        <details className="sp-disclosure rounded-lg border border-up/25 bg-up/[0.05] px-3 py-2">
          <summary className="cursor-pointer font-semibold text-up">{t("bt_ev_research_title")}</summary>
          <p className="mt-2 leading-relaxed text-mist-300">{t("bt_ev_research_hint")}</p>
          <div className="tnum mt-2 grid grid-cols-3 gap-2">
            {["train", "validation", "holdout"].map((k) => (
              <Cell ltr key={k} label={t(`bt_ev_period_${k}`)} value={`${fmt(summary.expectancy_r?.[k], 3)}R`}
                tone={(summary.expectancy_r?.[k] ?? 0) > 0 ? "up" : "down"} />
            ))}
          </div>
          <div className="tnum mt-2 grid grid-cols-3 gap-2">
            <Cell ltr label={t("bt_ev_years_pos")} value={summary.positive_years} tone="up" />
            <Cell ltr label={t("bt_ev_tpy")} value={`≈${summary.trades_per_year}`} />
            <Cell ltr label={t("bt_ev_worst_dd")} value={`${summary.max_drawdown_r}R`} tone="down" />
          </div>
          <ul className="mt-2 list-disc space-y-1 ps-4 text-mist-500">
            {(research.caveats || []).map((c) => <li key={c}>{c}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

export function Cell({ label, value, tone = "neutral", ltr = false }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="rounded-lg border border-ink-500 bg-ink-800 px-2.5 py-1.5">
      <p className="text-[10px] text-mist-500">{label}</p>
      <p className={`tnum mt-0.5 text-[13px] font-semibold ${color}`}>
        {ltr ? <bdi dir="ltr">{value}</bdi> : value}
      </p>
    </div>
  );
}
