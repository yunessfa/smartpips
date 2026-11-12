import { useEffect, useState } from "react";
import { marketApi } from "../api/client.js";
import { Panel } from "./ui.jsx";
import { useI18n } from "../i18n/index.jsx";

export function EconomicNewsPanel({ symbol }) {
  const { lang } = useI18n();
  const fa = lang === "fa";
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    let alive = true;
    setData(null); setError(false);
    const pull = async () => {
      try {
        const value = await marketApi.calendar(symbol);
        if (alive) { setData(value); setError(false); }
      } catch { if (alive) setError(true); }
    };
    pull();
    const poll = setInterval(pull, 60000);
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => { alive = false; clearInterval(poll); clearInterval(clock); };
  }, [symbol]);
  // Window comes from the server (NEWS_BLACKOUT_*): N minutes before a high-impact
  // release and a cooldown after it, while spreads are wide and price is erratic.
  const before = data?.blackout?.before_min ?? 30;
  const after = data?.blackout?.after_min ?? 15;
  const events = (data?.events || []).filter((e) => Date.parse(e.time) >= now - after * 60000);
  const event = events[0];
  const rawMinutes = event ? (Date.parse(event.time) - now) / 60000 : 0;
  const minutes = event ? Math.max(0, Math.ceil(rawMinutes)) : 0;
  const sinceRelease = event && rawMinutes < 0 ? Math.floor(-rawMinutes) : null;
  const impact = { high: fa ? "زیاد" : "High", medium: fa ? "متوسط" : "Medium", low: fa ? "کم" : "Low" };
  const unavailable = error || data?.status === "unavailable";
  return <Panel title={fa ? "رویداد اقتصادی بعدی" : "Next economic event"}>
    <div className="space-y-4 text-sm" aria-live="polite">
      <p className="text-mist-300">{symbol} · {fa ? "تقویم اقتصاد کلان دلار" : "USD macro calendar"}</p>
      {(unavailable || data?.status === "stale") && <p role="status" className="text-amber-300">
        {fa ? "دادهٔ خبر در دسترس نیست یا به‌روز نشده؛ نبود هشدار به معنی امن‌بودن بازار نیست." : "Calendar unavailable or stale. No alert does not mean safe conditions."}
      </p>}
      {!data && !error && <p className="text-mist-300">{fa ? "در حال دریافت خبر…" : "Loading calendar…"}</p>}
      {event ? <>
        <div className="border-s-2 border-gold ps-3 space-y-3">
          <h3 className="text-base font-semibold text-mist-100 break-words">{event.title}</h3>
          <p className="text-mist-100">{sinceRelease !== null
            ? (fa ? `${sinceRelease.toLocaleString("fa-IR")} دقیقه از انتشار گذشته` : `Released ${sinceRelease} min ago`)
            : minutes === 0 ? (fa ? "اکنون" : "Now") : (fa ? `${minutes.toLocaleString("fa-IR")} دقیقه تا انتشار` : `In ${minutes} minutes`)}</p>
          <time dateTime={event.time} className="block text-mist-300">
            {new Date(event.time).toLocaleString(fa ? "fa-IR" : "en-US", {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit", timeZoneName:"short"})}
          </time>
          <p className={event.impact === "high" ? "text-red-300" : "text-mist-100"}>
            {fa ? "شدت احتمالی نوسان: " : "Expected volatility impact: "}{impact[event.impact] || (fa ? "نامشخص" : "Unknown")}
          </p>
        </div>
        {event.impact === "high" && minutes <= before && <p className="rounded-lg bg-red-400/10 border border-red-400/40 p-3 text-red-200">
          {fa
            ? `پنجرهٔ خبر مهم: از ${before.toLocaleString("fa-IR")} دقیقه قبل تا ${after.toLocaleString("fa-IR")} دقیقه بعد از انتشار، ورود جدید پیشنهاد نمی‌شود.`
            : `High-impact window: no new entries from ${before} min before to ${after} min after the release.`}
        </p>}
      </> : data && !unavailable && <p>{fa ? "رویداد آینده‌ای در دادهٔ دریافتی نیست؛ پوشش این منبع محدود است." : "No upcoming event in this feed; source coverage is limited."}</p>}
      <p className="text-mist-300 leading-relaxed">{fa ? (symbol.startsWith("XAU") || symbol.startsWith("XAG") ? "اثر بالقوه بر طلا و نقره؛ جهت صعود یا نزول قبل از انتشار مشخص نیست." : "اثر روی کریپتو غیرمستقیم است؛ این تقویم اخبار اختصاصی هر کوین را پوشش نمی‌دهد.") : "Impact is not direction. USD macro events have indirect crypto relevance; coin-specific news is not covered."}</p>
      {data?.fetched_at && <p className="text-mist-300">{fa ? "آخرین دریافت: " : "Last fetched: "}{new Date(data.fetched_at).toLocaleTimeString(fa ? "fa-IR" : "en-US")}</p>}
    </div>
  </Panel>;
}
