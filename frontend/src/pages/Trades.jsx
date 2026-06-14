import { useEffect, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Badge, Button, Spinner } from "../components/ui.jsx";
import { LogTradeModal, CloseTradeModal } from "../components/TradeModal.jsx";
import { tradesApi, marketApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

function fmt(n) {
  if (n == null || n === "") return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export default function Trades() {
  const { t } = useI18n();
  const [trades, setTrades] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [logging, setLogging] = useState(false);
  const [closing, setClosing] = useState(null);
  const [prices, setPrices] = useState({}); // symbol -> {price, source}

  async function loadPrices() {
    try {
      const quotes = await marketApi.quotes();
      const map = {};
      for (const q of quotes) map[q.symbol.toUpperCase()] = q;
      setPrices(map);
    } catch { /* ignore */ }
  }

  async function load() {
    setLoading(true);
    try {
      const [list, st] = await Promise.all([tradesApi.list(), tradesApi.stats()]);
      setTrades(list); setStats(st);
    } catch { /* ignore */ } finally { setLoading(false); }
  }
  useEffect(() => {
    load();
    loadPrices();
    const id = setInterval(loadPrices, 30000); // refresh live prices
    return () => clearInterval(id);
  }, []);

  // Live price + unrealised P&L for an open trade (if we have a quote).
  function liveFor(tr) {
    const q = prices[tr.symbol?.toUpperCase()];
    if (!q) return null;
    const cur = q.price;
    const move = tr.direction === "long"
      ? (cur - tr.entry_price) / tr.entry_price
      : (tr.entry_price - cur) / tr.entry_price;
    const pct = move * 100 * (tr.leverage || 1);
    const pnl = (tr.size || 0) * (tr.leverage || 1) * move;
    return { cur, pct, pnl, source: q.source };
  }

  async function createTrade(payload) { await tradesApi.create(payload); await load(); }
  async function closeTrade(id, exitPrice) { await tradesApi.close(id, exitPrice); await load(); }
  async function remove(id) { if (!confirm(t("delete_trade") + "?")) return; await tradesApi.remove(id); load(); }

  return (
    <>
      <PageHeader
        title={t("trades_title")}
        subtitle={t("trades_sub")}
        right={<Button onClick={() => setLogging(true)}>+ {t("new_trade")}</Button>}
      />
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {/* stat strip */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Stat label={t("open_trades")} value={stats?.open ?? "—"} />
          <Stat label={t("closed_trades")} value={stats?.closed ?? "—"} />
          <Stat label={t("total_pnl")} value={stats ? `${stats.total_pnl >= 0 ? "+" : ""}${fmt(stats.total_pnl)}` : "—"} tone={stats && stats.total_pnl >= 0 ? "up" : "down"} />
          <Stat label={t("win_rate")} value={stats ? `${stats.win_rate}%` : "—"} />
        </div>

        <Panel title={t("trades_title")}>
          {loading ? <Spinner label="…" /> : trades.length === 0 ? (
            <p className="text-mist-500 text-sm">{t("no_trades")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-mist-500 text-xs border-b border-ink-500">
                    <Th>{t("symbol")}</Th><Th>{t("direction")}</Th><Th>{t("entry_price")}</Th>
                    <Th>{t("current_price")}</Th><Th>{t("exit_price")}</Th><Th>{t("leverage")}</Th><Th>{t("pnl")}</Th>
                    <Th>{t("status")}</Th><Th></Th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((tr) => {
                    const up = (tr.pnl_percent ?? 0) >= 0;
                    const live = tr.status === "open" ? liveFor(tr) : null;
                    const liveUp = (live?.pct ?? 0) >= 0;
                    return (
                      <tr key={tr.id} className="border-b border-ink-600/60">
                        <Td><span className="font-medium text-mist-100 tnum">{tr.symbol}</span></Td>
                        <Td><Badge tone={tr.direction === "long" ? "up" : "down"}>{tr.direction === "long" ? t("long") : t("short")}</Badge></Td>
                        <Td className="tnum">{fmt(tr.entry_price)}</Td>
                        <Td>
                          {live ? (
                            <span className="tnum text-mist-100">{fmt(live.cur)}</span>
                          ) : <span className="text-mist-500">—</span>}
                        </Td>
                        <Td className="tnum">{fmt(tr.exit_price)}</Td>
                        <Td className="tnum">{tr.leverage}x</Td>
                        <Td>
                          {tr.status === "closed" ? (
                            <span className={`tnum ${up ? "text-up" : "text-down"}`}>
                              {up ? "+" : ""}{fmt(tr.pnl)} ({up ? "+" : ""}{fmt(tr.pnl_percent)}%)
                            </span>
                          ) : live ? (
                            <span className={`tnum ${liveUp ? "text-up" : "text-down"}`}>
                              {liveUp ? "+" : ""}{fmt(live.pnl)} ({liveUp ? "+" : ""}{fmt(live.pct)}%)
                            </span>
                          ) : <span className="text-mist-500">—</span>}
                        </Td>
                        <Td><Badge tone={tr.status === "open" ? "info" : "neutral"}>{tr.status === "open" ? t("open_status") : t("closed_status")}</Badge></Td>
                        <Td>
                          <div className="flex gap-1.5 justify-end">
                            {tr.status === "open" && <Button variant="ghost" onClick={() => setClosing(tr)}>{t("close")}</Button>}
                            <Button variant="danger" onClick={() => remove(tr.id)}>{t("delete_trade")}</Button>
                          </div>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      {logging && <LogTradeModal onClose={() => setLogging(false)} onSaved={createTrade} />}
      {closing && <CloseTradeModal trade={closing} onClose={() => setClosing(null)} onClosed={(price) => closeTrade(closing.id, price)} />}
    </>
  );
}

function Stat({ label, value, tone = "neutral" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="bg-ink-700 border border-ink-500 rounded-xl px-4 py-3 shadow-panel">
      <p className="text-xs text-mist-500">{label}</p>
      <p className={`tnum text-2xl font-semibold mt-1 ${color}`}>{value}</p>
    </div>
  );
}
function Th({ children }) { return <th className="text-start font-medium px-2 py-2 whitespace-nowrap">{children}</th>; }
function Td({ children, className = "" }) { return <td className={`px-2 py-2.5 ${className}`}>{children}</td>; }
