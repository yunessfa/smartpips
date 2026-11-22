import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout.jsx";
import { Badge, Button, Panel, Spinner } from "../components/ui.jsx";
import { marketApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { pushSupported } from "../live/push.js";

const REFRESH_MS = 60000;
const TIMEFRAMES = ["5m", "15m", "1h"];

const num = (v, digits = 2) => (v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: digits }));
const signed = (v, digits = 2) => {
  if (v == null) return "—";
  const text = num(Math.abs(v), digits);
  const zero = Number(text.replace(/,/g, "")) === 0;
  return `${zero ? "" : v > 0 ? "+" : "-"}${text}%`;
};
const tone = (v) => (v == null || v === 0 ? "text-mist-300" : v > 0 ? "text-up" : "text-down");
const price = (v) => (v == null ? "—" : num(v, v >= 100 ? 2 : v >= 1 ? 4 : 6));

function compact(v) {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function Tile({ label, source, children, foot }) {
  const missing = !source || source.status === "unavailable";
  return (
    <div className="rounded-xl border border-ink-500 bg-ink-700/80 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-xs text-mist-500">{label}</p>
        {source?.status === "stale" && <RadarStale />}
      </div>
      {missing ? <RadarMissing /> : (
        <>
          <div dir="ltr" className="mt-1.5 text-end text-xl font-semibold text-mist-100 rtl:text-start">{children}</div>
          {foot && <p className="mt-1 text-[11px] text-mist-500">{foot}</p>}
        </>
      )}
    </div>
  );
}

function RadarStale() {
  const { t } = useI18n();
  return <span className="shrink-0 text-[10px] text-gold-soft">{t("rd_stale")}</span>;
}

function RadarMissing() {
  const { t } = useI18n();
  return <p className="mt-2 text-sm text-mist-500">{t("rd_unavailable")}</p>;
}

function Context({ context }) {
  const { t } = useI18n();
  const { fear_greed: fg, dvol, global: g, macro } = context || {};
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Tile label={t("rd_fear_greed")} source={fg}
        foot={fg?.label ? <>{t(`rd_fg_${fg.label.toLowerCase().replace(/\s+/g, "_")}`)}{fg.week_ago != null && <> · {t("rd_week_ago")}: <span dir="ltr">{fg.week_ago}</span></>}</> : null}>
        {fg?.value}
      </Tile>
      <Tile label={t("rd_dvol")} source={dvol}
        foot={dvol?.percentile_180d != null ? <><span dir="ltr">{dvol.percentile_180d}%</span> {t("rd_percentile")}</> : null}>
        {num(dvol?.value, 1)}
      </Tile>
      <Tile label={t("rd_market_cap")} source={g}
        foot={g ? <span dir="ltr" className={tone(g.change_24h_pct)}>{signed(g.change_24h_pct)} 24h</span> : null}>
        {compact(g?.total_market_cap)}
      </Tile>
      <Tile label={t("rd_btc_dom")} source={g}
        foot={g?.eth_dominance != null ? <>{t("rd_eth")}: <span dir="ltr">{num(g.eth_dominance, 1)}%</span></> : null}>
        {num(g?.btc_dominance, 1)}%
      </Tile>
      <div className="col-span-2 rounded-xl border border-ink-500 bg-ink-700/80 p-3.5 lg:col-span-1">
        <p className="truncate text-xs text-mist-500">{t("rd_macro")}</p>
        {macro?.rows?.length ? (
          <div dir="ltr" className="mt-1.5 space-y-0.5 text-sm">
            {macro.rows.map((r) => (
              <div key={r.ticker} className="flex justify-between gap-2">
                <span className="text-mist-300">{r.ticker}</span>
                <span className={tone(r.change_pct)}>{signed(r.change_pct)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs leading-relaxed text-mist-500">
            {macro?.status === "needs_key" ? t("rd_macro_key") : t("rd_unavailable")}
          </p>
        )}
      </div>
    </div>
  );
}

function TimeframeRow({ tf, state, symbol }) {
  const { t } = useI18n();
  const live = state?.signal === "buy" || state?.signal === "sell";
  const label = !state ? t("rd_not_checked")
    : live ? t(state.signal === "buy" ? "rd_buy" : "rd_sell") : t(`rd_wait_${state.code || "other"}`);
  const row = (
    <>
      <span dir="ltr" className="w-8 shrink-0 font-mono text-[11px] text-mist-500">{tf}</span>
      <span className={`min-w-0 truncate ${live ? (state.signal === "buy" ? "font-semibold text-up" : "font-semibold text-down") : "text-mist-400"}`}>
        {label}
      </span>
    </>
  );
  if (!live) return <div className="flex items-center gap-2 px-2 py-1 text-xs">{row}</div>;
  return (
    <Link to={`/app/scalp?symbol=${encodeURIComponent(symbol)}&tf=${tf}&quick=1`}
      className={`flex items-center gap-2 rounded-md px-2 py-1 text-xs ${state.signal === "buy" ? "bg-up/10" : "bg-down/10"}`}>
      {row}
    </Link>
  );
}

function CoinCard({ coin }) {
  const { t } = useI18n();
  const spike = coin.spikes?.[0];
  const live = Object.values(coin.playbook || {}).some((p) => p.signal !== "wait");
  return (
    <article className={`rounded-xl border p-3.5 ${live ? "border-up/40 bg-up/[0.04]" : "border-ink-500 bg-ink-800/60"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-mist-100">{coin.base}</h3>
        <div dir="ltr" className="flex items-baseline gap-2 text-xs">
          <span className="font-mono text-mist-200">{price(coin.price)}</span>
          <span className={tone(coin.change_24h_pct)}>{signed(coin.change_24h_pct)}</span>
        </div>
      </div>
      <dl className="mt-2 flex gap-4 text-[11px] text-mist-500">
        <div className="flex gap-1"><dt>{t("rd_funding")}</dt><dd dir="ltr" className={tone(coin.funding_pct)}>{signed(coin.funding_pct, 4)}</dd></div>
        <div className="flex gap-1"><dt>{t("rd_oi")}</dt><dd dir="ltr" className={tone(coin.oi_change_24h_pct)}>{signed(coin.oi_change_24h_pct, 1)}</dd></div>
      </dl>
      <div className="mt-2.5 space-y-0.5">
        {TIMEFRAMES.map((tf) => <TimeframeRow key={tf} tf={tf} state={coin.playbook?.[tf]} symbol={coin.symbol} />)}
      </div>
      {spike && (
        <p className="mt-2.5 rounded-md border border-gold/30 bg-gold/10 px-2 py-1.5 text-[11px] leading-relaxed text-gold-soft">
          {t(`rd_spike_${spike.kind}`)} · <span dir="ltr">{spike.timeframe}</span> ·{" "}
          <span dir="ltr">{signed(spike.move_pct)}</span> · {t("rd_vol")} <span dir="ltr">×{spike.volume_x}</span> ·{" "}
          <span dir="ltr">{spike.minutes_ago}</span> {t("rd_min_ago")}
        </p>
      )}
    </article>
  );
}

function Polymarket({ data }) {
  const { t, lang } = useI18n();
  const events = data?.events || [];
  return (
    <Panel title={t("rd_polymarket")}>
      <p className="mb-3 text-xs text-mist-500">{t("rd_polymarket_hint")}</p>
      {data?.status === "unavailable" ? <RadarMissing /> : !events.length ? (
        <p className="text-sm text-mist-500">{t("rd_polymarket_empty")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {events.map((e) => (
            <a key={e.url} href={e.url} target="_blank" rel="noopener noreferrer"
              className="block rounded-xl border border-ink-500 bg-ink-800/60 p-3 transition hover:border-mist-500">
              <p dir="ltr" className="text-start text-xs font-medium leading-relaxed text-mist-200">{e.title}</p>
              <div className="mt-2 space-y-1.5">
                {e.markets.map((m) => (
                  <div key={m.label} dir="ltr" className="text-[11px]">
                    <div className="flex justify-between gap-2 text-mist-400">
                      <span className="truncate">{m.label}</span><span className="font-mono text-mist-200">{m.yes_pct}%</span>
                    </div>
                    <div className="mt-0.5 h-1 overflow-hidden rounded bg-ink-600">
                      <div className="h-full rounded bg-info" style={{ width: `${m.yes_pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 flex justify-between gap-2 text-[10px] text-mist-500">
                <span>{t("rd_vol_24h")} <span dir="ltr">{compact(e.volume_24h)}</span></span>
                {e.ends && <span>{t("rd_ends")} {new Date(e.ends).toLocaleDateString(lang === "fa" ? "fa-IR" : "en-US")}</span>}
              </p>
            </a>
          ))}
        </div>
      )}
    </Panel>
  );
}

function usePushOff() {
  const [off, setOff] = useState(false);
  useEffect(() => {
    let alive = true;
    if (!pushSupported()) return undefined;
    navigator.serviceWorker.getRegistration()
      .then((reg) => (reg ? reg.pushManager.getSubscription() : null))
      .then((sub) => { if (alive) setOff(!sub); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  return off;
}

export default function Radar() {
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const pushOff = usePushOff();

  const load = useCallback(async () => {
    try {
      setData(await marketApi.radar());
      setErr(null);
    } catch (e) {
      setErr(e.message || t("rd_load_error"));
    }
  }, [t]);

  useEffect(() => {
    load();
    const id = setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const coins = data?.coins || [];
  const activeCount = coins.filter((c) => Object.values(c.playbook || {}).some((p) => p.signal !== "wait")).length;
  const spikeCount = coins.filter((c) => c.spikes?.length).length;

  return (
    <>
      <PageHeader title={t("rd_title")} subtitle={t("rd_subtitle")}
        right={data?.as_of ? (
          <span className="shrink-0 text-xs text-mist-500">
            {t("rd_updated")} <span dir="ltr">{new Date(data.as_of * 1000).toLocaleTimeString("en-GB")}</span>
          </span>
        ) : null} />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
        {err && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-down/30 bg-down/10 px-3 py-2 text-xs text-down">
            <span>{err}</span>
            <Button variant="ghost" onClick={load}>{t("rd_retry")}</Button>
          </div>
        )}
        {pushOff && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gold/30 bg-gold/10 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-gold-soft">{t("rd_push_title")}</p>
              <p className="mt-0.5 text-xs text-mist-300">{t("rd_push_body")}</p>
            </div>
            <Link to="/app/notifications"><Button>{t("rd_push_cta")}</Button></Link>
          </div>
        )}
        {!data && !err && <Spinner label="…" />}
        {data && (
          <>
            <Context context={data.context} />
            <Panel title={t("rd_board")} action={(
              <div className="flex flex-wrap justify-end gap-1.5">
                <Badge tone={activeCount ? "up" : "neutral"}>{t("rd_active")}: <span dir="ltr">{activeCount}</span></Badge>
                <Badge tone={spikeCount ? "gold" : "neutral"}>{t("rd_spiking")}: <span dir="ltr">{spikeCount}</span></Badge>
                <Badge>{t("rd_coins")}: <span dir="ltr">{coins.length}</span></Badge>
              </div>
            )}>
              <p className="mb-3 text-xs leading-relaxed text-mist-500">{t("rd_display_only")}</p>
              {coins.length ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                  {coins.map((c) => <CoinCard key={c.symbol} coin={c} />)}
                </div>
              ) : <p className="text-sm text-mist-500">{t("rd_no_coins")}</p>}
            </Panel>
            <Polymarket data={data.context?.polymarket} />
          </>
        )}
      </div>
    </>
  );
}
