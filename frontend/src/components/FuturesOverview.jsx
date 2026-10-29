import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { strategyApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { Panel, Spinner } from "./ui.jsx";
import { NextStep } from "./MarketBrief.jsx";

/** Dashboard card: validated trend-pullback state for a few crypto futures. */
export default function FuturesOverview() {
  const { t } = useI18n();
  const [tf, setTf] = useState(() => {
    try { return localStorage.getItem("dash_overview_tf") || "1h"; } catch { return "1h"; }
  });
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const r = await strategyApi.overview(tf);
        if (alive) { setRows(r.results || []); setErr(null); }
      } catch (e) { if (alive) setErr(e.message); }
    }
    setRows(null);
    load();
    const id = setInterval(load, 60000);
    return () => { alive = false; clearInterval(id); };
  }, [tf]);

  function pick(v) {
    setTf(v);
    try { localStorage.setItem("dash_overview_tf", v); } catch { /* ignore */ }
  }

  return (
    <Panel
      title={t("ov_title")}
      action={
        <div className="flex items-center gap-1 rounded-lg bg-ink-800 p-0.5">
          {["15m", "1h"].map((v) => (
            <button key={v} type="button" onClick={() => pick(v)}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold ${tf === v ? "bg-gold text-ink-900" : "text-mist-400 hover:text-mist-200"}`}>
              {v}
            </button>
          ))}
        </div>
      }
    >
      <p className="mb-3 text-xs text-mist-500">{t("ov_hint")}</p>
      {err && <p className="text-sm text-down">{err}</p>}
      {!rows && !err && <Spinner label={t("loading_quotes")} />}
      {rows && (
        <ul className="divide-y divide-ink-600">
          {rows.map((r) => <Row key={r.symbol} r={r} tf={tf} />)}
        </ul>
      )}
    </Panel>
  );
}

function Row({ r, tf }) {
  const { t } = useI18n();
  const base = r.symbol.replace(":PERP", "").replace("USDT", "");
  const facts = Object.fromEntries((r.brief?.facts || []).map((f) => [f.key, f]));
  const trend = facts.h4_trend?.value;
  const vol = facts.volatility;
  const isLimit = r.entry_plan?.type === "limit";
  const status = r.error || !r.brief ? null : r.signal;
  const pill = status === "buy" ? ["border-up/40 bg-up/10 text-up", isLimit ? t("mb_buy_limit") : t("mb_buy")]
    : status === "sell" ? ["border-down/40 bg-down/10 text-down", isLimit ? t("mb_sell_limit") : t("mb_sell")]
    : status === "wait" ? ["border-ink-500 text-mist-300", t("mb_wait")] : ["border-ink-500 text-mist-500", t("ov_unavailable")];
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
      <div className="w-20 shrink-0">
        <p className="text-sm font-bold text-mist-100">{base}</p>
        <p className="text-[10px] text-mist-500">PERP · {tf}</p>
      </div>
      <span className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${pill[0]}`}>{pill[1]}</span>
      {trend !== undefined && (
        <span className="text-xs text-mist-400">
          {t("mb_fact_h4_trend")}:{" "}
          <span className={trend === 1 ? "text-up" : trend === -1 ? "text-down" : "text-mist-300"}>
            {t(trend === 1 ? "mb_up" : trend === -1 ? "mb_down" : "mb_flat")}
          </span>
        </span>
      )}
      {vol && (
        <span className={`text-xs ${vol.state === "ok" ? "text-mist-400" : "text-down"}`}>
          {t("ov_volatility")}: <bdi dir="ltr">{Number(vol.value).toFixed(2)}%</bdi>
        </span>
      )}
      <span className="min-w-[12rem] flex-1 text-xs leading-relaxed text-mist-300">
        {r.brief?.next && <NextStep next={r.brief.next} tf={tf} compact />}
      </span>
      <Link to={`/app/scalp?symbol=${encodeURIComponent(r.symbol)}&tf=${tf}`}
        className="shrink-0 rounded-lg border border-gold/40 px-3 py-1.5 text-xs text-gold-soft hover:bg-gold/10">
        {t("ov_open_scalp")}
      </Link>
    </li>
  );
}
