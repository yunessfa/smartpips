import { useEffect, useState } from "react";
import { marketApi } from "../api/client.js";
import { Panel } from "./ui.jsx";
import { useI18n } from "../i18n/index.jsx";

/**
 * Real futures order flow: taker buy/sell delta, open interest, funding and
 * resting book size. Reference venue is Binance USD-M (Bitunix does not publish
 * taker volume or OI history). Display only — the engine does not read it yet;
 * the data is being recorded so it can be tested first.
 */
const fmt = (n, d = 2) => (n === null || n === undefined || !Number.isFinite(Number(n))
  ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d }));
const signed = (n, d = 2) => (n === null || n === undefined || !Number.isFinite(Number(n))
  ? "—" : `${Number(n) > 0 ? "+" : ""}${Number(n).toFixed(d)}`);
const tone = (n) => (Number(n) > 0 ? "text-up" : Number(n) < 0 ? "text-down" : "text-mist-200");

function Sparkline({ values }) {
  if (!values || values.length < 3) return null;
  const min = Math.min(...values); const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / span) * 26}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="w-full h-10" role="img" aria-label="CVD">
      <polyline points={pts} fill="none" stroke={up ? "#22c55e" : "#ef4444"} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Stat({ label, children, hint }) {
  return (
    <div className="rounded-lg border border-ink-600 bg-ink-800/60 px-3 py-2">
      <p className="text-[11px] text-mist-500">{label}</p>
      <p className="text-sm font-semibold tnum" dir="ltr">{children}</p>
      {hint && <p className="text-[11px] text-mist-500 mt-0.5">{hint}</p>}
    </div>
  );
}

export function FlowPanel({ symbol, timeframe = "5m" }) {
  const { lang } = useI18n();
  const fa = lang === "fa";
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    setData(null); setError(false);
    const pull = async () => {
      if (document.hidden) return;                 // do not poll a background tab
      try {
        const value = await marketApi.flow(symbol, timeframe);
        if (alive) { setData(value); setError(false); }
      } catch { if (alive) setError(true); }
    };
    pull();
    const id = setInterval(pull, 30000);
    return () => { alive = false; clearInterval(id); };
  }, [symbol, timeframe]);

  const w = data?.delta?.windows || [];
  const oi = data?.open_interest;
  const f = data?.funding;
  const bands = data?.book?.bands || [];
  const base = String(symbol || "").replace(":PERP", "").replace("USDT", "");
  const down = error || data?.status === "unavailable";
  const next = f?.next_funding_time ? Math.max(0, Math.round((f.next_funding_time * 1000 - Date.now()) / 60000)) : null;

  return (
    <Panel title={fa ? "جریان سفارش واقعی (فیوچرز)" : "Real order flow (futures)"}>
      <div className="space-y-3 text-sm" aria-live="polite">
        {!data && !error && <p className="text-mist-300">{fa ? "در حال دریافت…" : "Loading…"}</p>}
        {down && (
          <p role="status" className="text-amber-300">
            {fa ? "دادهٔ جریان سفارش در دسترس نیست." : "Order-flow data is unavailable."}
          </p>
        )}
        {data && !down && (
          <>
            {w.length > 0 && (
              <div>
                <p className="text-xs text-mist-400 mb-1.5">
                  {fa ? `دلتای خریدار/فروشندهٔ مهاجم · کندل‌های بستهٔ ${timeframe}` : `Taker buy/sell delta · closed ${timeframe} bars`}
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {w.map((x) => (
                    <Stat key={x.bars} label={fa ? `${x.bars.toLocaleString("fa-IR")} کندل آخر` : `last ${x.bars} bars`}
                      hint={`${fa ? "قیمت" : "price"} ${signed(x.price_change_pct, 2)}%`}>
                      <span className={tone(x.delta_pct)}>{signed(x.delta_pct, 1)}%</span>
                      <span className="text-mist-500 text-[11px] font-normal"> · {signed(x.delta, 1)} {base}</span>
                    </Stat>
                  ))}
                </div>
                <Sparkline values={data.delta.cvd} />
                <p className="text-[11px] text-mist-500">
                  {fa ? "CVD (دلتای تجمعی) روی همین بازه" : "CVD (cumulative delta) over the same window"}
                </p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              {oi && (
                <Stat label={fa ? "اوپن اینترست" : "Open interest"}
                  hint={(oi.changes || []).map((c) => `${c.window} ${signed(c.change_pct, 2)}%`).join("  ·  ")}>
                  {fmt(oi.oi, 0)} <span className="text-mist-500 text-[11px] font-normal">{base}</span>
                </Stat>
              )}
              {f && (
                <Stat label={fa ? "فاندینگ" : "Funding"}
                  hint={`${fa ? "بیسیس" : "basis"} ${signed(f.basis_bps, 1)} bps${next !== null ? ` · ${fa ? "بعدی" : "next"} ${next}m` : ""}`}>
                  <span className={tone(f.rate_pct)}>{signed(f.rate_pct, 4)}%</span>
                </Stat>
              )}
            </div>
            {bands.length > 0 && (
              <div>
                <p className="text-xs text-mist-400 mb-1.5">
                  {fa ? "عدم‌تعادل سفارش‌های منتظر در اردربوک" : "Resting-order imbalance in the book"}
                  {data.book.spread_bps != null && <span className="text-mist-500"> · spread {fmt(data.book.spread_bps, 2)} bps</span>}
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {bands.map((b) => (
                    <Stat key={b.band_pct} label={`±${b.band_pct}%`} hint={b.complete ? null : (fa ? "عمق ناقص" : "partial depth")}>
                      <span className={tone(b.imbalance)}>{b.imbalance === null ? "—" : signed(b.imbalance * 100, 0)}%</span>
                    </Stat>
                  ))}
                </div>
              </div>
            )}
            {data.errors?.length > 0 && (
              <p className="text-[11px] text-amber-300">
                {fa ? "بخشی از داده دریافت نشد: " : "Some sections failed: "}{data.errors.join(", ")}
              </p>
            )}
          </>
        )}
        <p className="text-mist-400 leading-relaxed text-xs">
          {fa
            ? "منبع: بایننس فیوچرز (بازار مرجع)؛ اجرای سفارش روی Bitunix است. مثبت یعنی خریدار مهاجم یا سفارش خرید بیشتر. سفارش‌های اردربوک قبل از معامله قابل برداشتن‌اند. این داده‌ها فعلاً فقط نمایشی‌اند و موتور از آن‌ها استفاده نمی‌کند."
            : "Source: Binance USD-M (reference market); orders execute on Bitunix. Positive = aggressive buyers or more resting bids. Book orders can be pulled before trading. Display only for now; the engine does not use this data."}
        </p>
      </div>
    </Panel>
  );
}
