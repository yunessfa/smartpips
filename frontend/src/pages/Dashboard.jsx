import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Badge, Spinner, Button } from "../components/ui.jsx";
import { TickerTape } from "../components/TradingView.jsx";
import FuturesOverview from "../components/FuturesOverview.jsx";
import { PositionChart, toBitunixSymbol } from "../components/PositionChart.jsx";
import { marketApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { useLiveCtx, useLivePricesFor, isCryptoSymbol } from "../live/LivePrices.jsx";
import { fmtPrice } from "../lib/num.js";

const TICKER_SYMBOLS = [
  { proName: "BINANCE:BTCUSDT", title: "BTC" },
  { proName: "BINANCE:ETHUSDT", title: "ETH" },
  { proName: "BINANCE:SOLUSDT", title: "SOL" },
  { proName: "TVC:GOLD", title: "Gold" },
  { proName: "TVC:SILVER", title: "Silver" },
  { proName: "FOREXCOM:SPXUSD", title: "S&P 500" },
];

function fmt(n) {
  if (n == null) return "—";
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}


export default function Dashboard() {
  const { t } = useI18n();
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);

  async function load() {
    try {
      const data = await marketApi.quotes();
      setQuotes(data);
      setUpdatedAt(new Date());
      // crypto futures first: they are the product focus
      setSelected((cur) => cur || data.find((q) => isCryptoSymbol(q.symbol)) || data[0] || null);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live crypto prices from the WebSocket; metals fall back to the server quote.
  const live = useLiveCtx();
  const cryptoSymbols = quotes.filter((q) => isCryptoSymbol(q.symbol)).map((q) => q.symbol);
  useLivePricesFor(cryptoSymbols);

  // Effective price/change for a quote: prefer live when we have it.
  function eff(q) {
    const l = live?.prices?.[q.symbol?.toUpperCase()];
    if (l && Number.isFinite(l.price)) {
      return { price: l.price, change: l.changePercent, isLive: true };
    }
    return { price: q.price, change: q.change_percent, isLive: false };
  }

  const totalUp = quotes.filter((q) => eff(q).change >= 0).length;
  const totalDown = quotes.length - totalUp;
  const isMock = quotes.some((q) => q.source === "mock" && !live?.prices?.[q.symbol?.toUpperCase()]);
  const selEff = selected ? eff(selected) : null;

  return (
    <>
      <PageHeader
        title={t("dash_title")}
        subtitle={t("dash_subtitle")}
        right={
          <div className="flex items-center gap-3 text-xs text-mist-500 shrink-0">
            <LiveBadge status={live?.status} />
            <Button variant="ghost" onClick={load}>{t("refresh")}</Button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="border-b border-ink-500 bg-ink-800/40">
          <TickerTape symbols={TICKER_SYMBOLS} />
        </div>

        {isMock && (
          <div className="mx-4 md:mx-6 mt-4 text-xs text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-3 py-2">
            {t("mock_notice")}
          </div>
        )}

        <div className="p-4 md:p-6 space-y-6">
          {/* stat strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
            <Stat label={t("tracked_assets")} value={quotes.length} />
            <Stat label={t("advancing")} value={totalUp} tone="up" />
            <Stat label={t("declining")} value={totalDown} tone="down" />
            <Stat label={t("dash_scalp_link")} value={<Link to="/app/scalp" className="text-gold-soft hover:underline">{t("open")} →</Link>} />
          </div>

          <FuturesOverview />

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            {/* One chart only: real exchange candles (+ your position lines when
                you hold the displayed symbol). It follows the list selection. */}
            <Panel className="xl:col-span-2"
              title={selected ? `${selected.name} · ${toBitunixSymbol(selected.symbol) || selected.symbol}` : t("pc_title")}
              action={selEff && Number.isFinite(selEff.change) && (
                <Badge tone={selEff.change >= 0 ? "up" : "down"}>
                  <span className="tnum" dir="ltr">{selEff.change >= 0 ? "▲" : "▼"} {fmt(selEff.change)}%</span>
                </Badge>
              )}>
              <PositionChart symbol={toBitunixSymbol(selected?.symbol) || undefined}
                height={480} storageKey="pc_tf_dash" />
            </Panel>

            <Panel title={t("watchlist")}>
              {loading ? (
                <Spinner label={t("loading_quotes")} />
              ) : error ? (
                <p className="text-down text-sm">{error}</p>
              ) : quotes.length === 0 ? (
                <p className="text-sm text-mist-500">{t("dash_no_quotes")}</p>
              ) : (
                <ul className="space-y-1 max-h-[540px] overflow-y-auto">
                  {[...quotes].sort((a, b) => Number(isCryptoSymbol(b.symbol)) - Number(isCryptoSymbol(a.symbol))).map((q) => {
                    const e = eff(q);
                    const up = e.change >= 0;
                    const active = selected?.symbol === q.symbol;
                    return (
                      <li key={q.symbol}>
                        <button
                          onClick={() => setSelected(q)}
                          className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-start transition ${active ? "bg-ink-600" : "hover:bg-ink-700"}`}
                        >
                          <div>
                            <p className="text-sm font-medium text-mist-100 flex items-center gap-1.5">
                              {q.name}
                              {e.isLive && <span className="h-1.5 w-1.5 rounded-full bg-up live-dot" title="live" />}
                            </p>
                            <p className="text-xs text-mist-500 tnum">{q.symbol}</p>
                          </div>
                          <div className="text-end" dir="ltr">
                            <p className="tnum text-sm text-mist-100">${fmt(e.price)}</p>
                            <p className={`tnum text-xs ${up ? "text-up" : "text-down"}`}>{up ? "+" : ""}{fmt(e.change)}%</p>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      </div>
    </>
  );
}

function LiveBadge({ status }) {
  const { t } = useI18n();
  const live = status === "live";
  return (
    <span className="hidden sm:flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-up live-dot" : "bg-mist-500"}`} />
      {live ? t("live_prices") : t("connecting")}
    </span>
  );
}

function Stat({ label, value, tone = "neutral" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="bg-ink-700/80 border border-ink-500 rounded-2xl px-4 py-3 shadow-panel card-lift">
      <p className="text-xs text-mist-500">{label}</p>
      <p className={`tnum text-2xl font-semibold mt-1 ${color}`}>{value}</p>
    </div>
  );
}
