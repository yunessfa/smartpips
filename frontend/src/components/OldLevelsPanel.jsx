import { useEffect, useState } from "react";
import { strategyApi } from "../api/client.js";
import { Panel } from "./ui.jsx";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";

/**
 * Old levels around price: untaken highs/lows of past days, weeks and months
 * plus confirmed swings. Reference prices for the trader, NOT signals — the
 * 2026-11 study (QA/old-levels-research) found no edge in trading them.
 */
const SOURCE_FA = { M: "ماه", W: "هفته", D: "روز", PD: "سوئینگ روزانه", P4: "سوئینگ ۴ساعته" };
const SOURCE_EN = { M: "month", W: "week", D: "day", PD: "daily swing", P4: "4h swing" };

export function OldLevelsPanel({ symbol }) {
  const { lang } = useI18n();
  const fa = lang === "fa";
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    setData(null); setError(false);
    const pull = async () => {
      try {
        const value = await strategyApi.levels(symbol);
        if (alive) { setData(value); setError(false); }
      } catch { if (alive) setError(true); }
    };
    pull();
    const id = setInterval(pull, 60000);
    return () => { alive = false; clearInterval(id); };
  }, [symbol]);

  const levels = data?.levels || [];
  const above = levels.filter((l) => l.kind === "high").sort((a, b) => b.price - a.price);
  const below = levels.filter((l) => l.kind === "low").sort((a, b) => b.price - a.price);
  const previous = Object.entries(data?.previous || {});
  const names = fa ? SOURCE_FA : SOURCE_EN;
  const age = (d) => (d < 1 ? (fa ? "امروز" : "today") : fa ? `${Math.round(d).toLocaleString("fa-IR")} روز` : `${Math.round(d)}d`);

  const Row = ({ l }) => (
    <tr className="border-t border-ink-600/60">
      <td className="py-1.5 pe-2">
        <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold ${
          l.major ? "bg-gold/15 text-gold-soft" : "bg-ink-600 text-mist-300"}`}>{l.label}</span>
      </td>
      <td className="py-1.5 pe-2"><bdi dir="ltr" className="tnum font-semibold text-mist-100">{fmtPrice(l.price)}</bdi></td>
      <td className="py-1.5 pe-2">
        <bdi dir="ltr" className={`tnum ${l.kind === "high" ? "text-down" : "text-up"}`}>
          {l.distance_pct > 0 ? "+" : ""}{Number(l.distance_pct).toFixed(2)}%
        </bdi>
      </td>
      <td className="py-1.5 pe-2 text-mist-400">{age(l.age_days)}</td>
      <td className="py-1.5 text-mist-500 text-[11px]">{(l.sources || []).map((s) => names[s] || s).join(fa ? "، " : ", ")}</td>
    </tr>
  );

  return (
    <Panel title={fa ? "سطوح قدیمی دست‌نخورده" : "Untaken old levels"}>
      <div className="space-y-3 text-sm" aria-live="polite">
        {!data && !error && <p className="text-mist-300">{fa ? "در حال دریافت سطوح…" : "Loading levels…"}</p>}
        {(error || data?.status === "unavailable") && (
          <p role="status" className="text-amber-300">
            {fa ? "تاریخچهٔ روزانه در دسترس نیست؛ سطوح قدیمی نمایش داده نمی‌شوند." : "Daily history unavailable; old levels are not shown."}
          </p>
        )}
        {data && levels.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-mist-500 text-start">
                  <th className="pb-1 text-start font-medium">{fa ? "سطح" : "Level"}</th>
                  <th className="pb-1 text-start font-medium">{fa ? "قیمت" : "Price"}</th>
                  <th className="pb-1 text-start font-medium">{fa ? "فاصله" : "Distance"}</th>
                  <th className="pb-1 text-start font-medium">{fa ? "قدمت" : "Age"}</th>
                  <th className="pb-1 text-start font-medium">{fa ? "منبع" : "Source"}</th>
                </tr>
              </thead>
              <tbody>
                {above.map((l) => <Row key={`h${l.price}`} l={l} />)}
                <tr className="border-t border-ink-500">
                  <td colSpan={5} className="py-1.5 text-center text-mist-400">
                    {fa ? "قیمت فعلی" : "Current price"} · <bdi dir="ltr" className="tnum text-mist-100">{fmtPrice(data.price)}</bdi>
                  </td>
                </tr>
                {below.map((l) => <Row key={`l${l.price}`} l={l} />)}
              </tbody>
            </table>
          </div>
        )}
        {data && data.status !== "unavailable" && levels.length === 0 && (
          <p className="text-mist-300">{fa ? "سطح دست‌نخورده‌ای اطراف قیمت نیست." : "No untaken level around price."}</p>
        )}
        {previous.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {previous.map(([name, v]) => (
              <span key={name} className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${
                v.taken ? "border-ink-600 text-mist-500" : "border-ink-500 text-mist-200"}`}>
                <span className="font-semibold">{name}</span>
                <bdi dir="ltr" className={`tnum ${v.taken ? "line-through" : ""}`}>{fmtPrice(v.price)}</bdi>
                {v.taken && <span>{fa ? "زده‌شده" : "taken"}</span>}
              </span>
            ))}
          </div>
        )}
        <p className="text-mist-400 leading-relaxed text-xs">
          {fa
            ? "این سطوح فقط مرجع قیمتی‌اند. در تست ۲۰۱۹ تا ۲۰۲۶ روی BTC، ورود بر اساس شکار یا شکست این سطوح بعد از کارمزد سودده نبود؛ موتور از آن‌ها برای سیگنال استفاده نمی‌کند."
            : "Reference prices only. On BTC 2019-2026, entries on sweeps or breaks of these levels were not profitable after fees; the engine does not use them for signals."}
          {data?.history_days ? (fa ? ` · ${Number(data.history_days).toLocaleString("fa-IR")} روز تاریخچه` : ` · ${data.history_days} days of history`) : ""}
        </p>
      </div>
    </Panel>
  );
}
