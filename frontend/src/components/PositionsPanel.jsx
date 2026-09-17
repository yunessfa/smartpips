import { useEffect, useState } from "react";
import { Panel, Badge, Button, Spinner } from "./ui.jsx";
import { LogTradeModal, CloseTradeModal } from "./TradeModal.jsx";
import { tradesApi, marketApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { useLivePricesFor, isCryptoSymbol, baseSymbol } from "../live/LivePrices.jsx";

function fmt(n) {
  if (n == null || n === "") return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 4 });
}

// Exchange-style date+time, e.g. "Jul 3, 14:05"
function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function isCrypto(symbol) {
  return (symbol || "").toUpperCase().replace(":PERP", "").endsWith("USDT");
}

// Position value & quantity are DERIVED for display only — never stored — so
// they can never drift out of sync with the P&L math. For crypto, `size` is
// the margin (USD) committed, so notional = size * leverage and qty = notional
// / entry. For metals `size` is already lots, so we just show that.
function derivedSize(tr) {
  if (isCrypto(tr.symbol)) {
    const notional = (tr.size || 0) * (tr.leverage || 1);
    const qty = tr.entry_price ? notional / tr.entry_price : null;
    return { value: notional, qty, unit: tr.symbol.replace(":PERP", "").replace("USDT", "") };
  }
  return { value: null, qty: null, unit: null };
}

/**
 * Exchange-style positions block: tabs for Open Positions / History, a table
 * with everything a Bybit/Binance positions tab shows (entry, TP/SL ladder,
 * current price, qty, position value, leverage, P&L, opened/closed time), plus
 * a margin-usage strip and the log/close trade modals. Used on both the Scalp
 * page (embedded, exchange-style) and the dedicated Trades page.
 */
export function PositionsPanel({ balance, defaultInitial = null, compact = false, refreshKey }) {
  const { t } = useI18n();
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("open"); // "open" | "history"
  const [logging, setLogging] = useState(false);
  const [closing, setClosing] = useState(null);
  const [exitAdvice, setExitAdvice] = useState({});
  const [margin, setMargin] = useState(null);

  const openTrades = trades.filter((tr) => tr.status === "open");
  const closedTrades = trades.filter((tr) => tr.status === "closed");

  // Live prices for every open-trade symbol (crypto via WS; metals via backend poll).
  const openSymbols = openTrades.filter((tr) => isCryptoSymbol(tr.symbol)).map((tr) => baseSymbol(tr.symbol));
  const livePrices = useLivePricesFor(openSymbols);

  const [polled, setPolled] = useState({});
  const openAllSymbols = openTrades.map((tr) => tr.symbol);
  const openKey = openAllSymbols.join(",");
  useEffect(() => {
    if (!openAllSymbols.length) return undefined;
    let stop = false;
    async function tick() {
      const out = {};
      await Promise.all(openAllSymbols.map(async (sym) => {
        try {
          const r = await marketApi.metal(sym);
          if (r && r.ok && Number.isFinite(r.price)) out[sym.toUpperCase()] = r.price;
        } catch { /* ignore */ }
      }));
      if (!stop) setPolled(out);
    }
    tick();
    const id = setInterval(tick, 4000);
    return () => { stop = true; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openKey]);

  async function load() {
    setLoading(true);
    try {
      try { await tradesApi.autoClose(); } catch { /* ignore */ }
      const list = await tradesApi.list();
      setTrades(list);
      try {
        const res = await tradesApi.exitAdvice();
        const map = {};
        (res.advice || []).forEach((a) => { map[a.trade_id] = a; });
        setExitAdvice(map);
      } catch { /* ignore */ }
    } catch { /* ignore */ } finally { setLoading(false); }
  }
  // reloads on mount and whenever refreshKey bumps (a trade logged elsewhere
  // on the page), so newly logged trades appear immediately.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [refreshKey]);

  // Margin usage strip: how much of the balance is already committed to open
  // crypto positions, and how much is actually free for a new one.
  useEffect(() => {
    if (!balance) { setMargin(null); return; }
    tradesApi.marginStatus(balance).then(setMargin).catch(() => setMargin(null));
  }, [balance, trades]);

  useEffect(() => {
    if (!openTrades.length) return undefined;
    const id = setInterval(async () => {
      try {
        const res = await tradesApi.exitAdvice();
        const map = {};
        (res.advice || []).forEach((a) => { map[a.trade_id] = a; });
        setExitAdvice(map);
      } catch { /* ignore */ }
    }, 20000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trades]);

  function liveFor(tr) {
    const wsQ = livePrices[baseSymbol(tr.symbol)];
    const cur = (wsQ && Number.isFinite(wsQ.price)) ? wsQ.price : polled[tr.symbol?.toUpperCase()];
    if (!Number.isFinite(cur) || !tr.entry_price) return null;
    const move = tr.direction === "long"
      ? (cur - tr.entry_price) / tr.entry_price
      : (tr.entry_price - cur) / tr.entry_price;
    const pct = move * 100 * (tr.leverage || 1);
    const pnl = (tr.size || 0) * (tr.leverage || 1) * move;
    return { cur, pct, pnl };
  }

  async function createTrade(payload) {
    await tradesApi.create({ ...payload, balance: balance ? Number(balance) : undefined });
    await load();
  }
  async function closeTrade(id, exitPrice) { await tradesApi.close(id, exitPrice); await load(); }
  async function remove(id) { if (!confirm(t("delete_trade") + "?")) return; await tradesApi.remove(id); load(); }

  const rows = tab === "open" ? openTrades : closedTrades;

  return (
    <Panel
      title={t("positions_title")}
      action={<Button onClick={() => setLogging(true)}>+ {t("new_trade")}</Button>}
    >
      {/* margin usage strip */}
      {margin && margin.balance > 0 && (
        <div className="mb-4 bg-ink-800 border border-ink-500 rounded-lg px-3 py-2.5">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-mist-400">{t("margin_used")}: <span className="text-mist-100 tnum">${fmt(margin.used_margin)}</span></span>
            <span className="text-mist-400">{t("margin_available")}: <span className={`tnum font-semibold ${margin.available_margin > 0 ? "text-up" : "text-down"}`}>${fmt(margin.available_margin)}</span></span>
          </div>
          <div className="h-1.5 bg-ink-700 rounded-full overflow-hidden">
            <div className={`h-full ${margin.used_margin / margin.balance > 0.85 ? "bg-down" : "bg-gold"}`}
              style={{ width: `${Math.min(100, (margin.used_margin / margin.balance) * 100)}%` }} />
          </div>
        </div>
      )}

      {/* tabs */}
      <div className="flex items-center gap-1 mb-4 border-b border-ink-600">
        {[["open", `${t("open_positions")} (${openTrades.length})`],
          ["history", `${t("order_history")} (${closedTrades.length})`]].map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`text-sm px-3 py-2 border-b-2 -mb-px transition ${
              tab === k ? "border-gold text-mist-100 font-medium" : "border-transparent text-mist-500 hover:text-mist-300"
            }`}>
            {label}
          </button>
        ))}
      </div>

      {loading ? <Spinner label="…" /> : rows.length === 0 ? (
        <p className="text-mist-500 text-sm py-4">{tab === "open" ? t("no_open_positions") : t("no_trades")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-mist-500 text-xs border-b border-ink-500">
                <Th>{t("symbol")}</Th><Th>{t("direction")}</Th><Th>{t("entry_price")}</Th>
                <Th>{t("sl_tp")}</Th>
                <Th>{t("current_price")}</Th><Th>{t("exit_price")}</Th>
                <Th>{t("qty_coins")}</Th><Th>{t("position_value")}</Th>
                <Th>{t("leverage")}</Th><Th>{t("pnl")}</Th>
                <Th>{t("opened_at")}</Th>
                {tab === "history" && <Th>{t("closed_at")}</Th>}
                {tab === "open" && <Th>{t("exit_advice")}</Th>}
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((tr) => {
                const up = (tr.pnl_percent ?? 0) >= 0;
                const live = tr.status === "open" ? liveFor(tr) : null;
                const liveUp = (live?.pct ?? 0) >= 0;
                const derived = derivedSize(tr);
                return (
                  <tr key={tr.id} className="border-b border-ink-600/60">
                    <Td><span className="font-medium text-mist-100 tnum">{tr.symbol}</span></Td>
                    <Td><Badge tone={tr.direction === "long" ? "up" : "down"}>{tr.direction === "long" ? t("long") : t("short")}</Badge></Td>
                    <Td className="tnum">{fmt(tr.entry_price)}</Td>
                    <Td>
                      {(tr.tp1_price || tr.tp2_price || tr.tp3_price) ? (
                        <div className="flex flex-col gap-0.5 text-xs tnum leading-tight">
                          {[["tp1", tr.tp1_price, tr.tp1_done, tr.tp1_pct],
                            ["tp2", tr.tp2_price, tr.tp2_done, tr.tp2_pct],
                            ["tp3", tr.tp3_price, tr.tp3_done, tr.tp3_pct]]
                            .filter(([, p]) => p)
                            .map(([k, p, done, pct]) => (
                              <span key={k} className={done ? "text-mist-500 line-through" : "text-up"}>
                                {done ? "✓ " : ""}{k.toUpperCase()} {fmt(p)} ({pct}%)
                              </span>
                            ))}
                          <span className="text-down">SL {fmt(tr.stop_loss)}</span>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-0.5 text-xs tnum leading-tight">
                          <span className="text-up">TP {fmt(tr.take_profit)}</span>
                          <span className="text-down">SL {fmt(tr.stop_loss)}</span>
                        </div>
                      )}
                    </Td>
                    <Td>{live ? <span className="tnum text-mist-100">{fmt(live.cur)}</span> : <span className="text-mist-500">—</span>}</Td>
                    <Td className="tnum">{fmt(tr.exit_price)}</Td>
                    <Td className="tnum text-mist-300">
                      {derived.qty != null ? `${fmt(derived.qty)} ${derived.unit}` : (tr.size ? fmt(tr.size) : "—")}
                    </Td>
                    <Td className="tnum text-mist-300">{derived.value != null ? `$${fmt(derived.value)}` : "—"}</Td>
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
                    <Td className="text-xs text-mist-400 whitespace-nowrap">{fmtDateTime(tr.opened_at)}</Td>
                    {tab === "history" && (
                      <Td className="text-xs text-mist-400 whitespace-nowrap">{fmtDateTime(tr.closed_at)}</Td>
                    )}
                    {tab === "open" && <Td>{<ExitAdviceCell advice={exitAdvice[tr.id]} />}</Td>}
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

      {logging && (
        <LogTradeModal initial={defaultInitial} onClose={() => setLogging(false)} onSaved={createTrade} />
      )}
      {closing && (
        <CloseTradeModal trade={closing} currentPrice={liveFor(closing)?.cur}
          onClose={() => setClosing(null)} onClosed={(price) => closeTrade(closing.id, price)} />
      )}
    </Panel>
  );
}

function ExitAdviceCell({ advice }) {
  const { t } = useI18n();
  if (!advice) return <span className="text-mist-600 text-xs">—</span>;
  const { action, reasons = [], urgency, new_stop, progress_pct } = advice;
  const cfg = {
    hold:    { label: t("ex_hold"),    tone: "text-mist-400", icon: "✓" },
    trail:   { label: t("ex_trail"),   tone: "text-info",     icon: "↗" },
    partial: { label: t("ex_partial"), tone: "text-gold-soft", icon: "½" },
    exit:    { label: t("ex_exit"),    tone: "text-down",     icon: "⚠" },
  }[action] || { label: action, tone: "text-mist-400", icon: "" };
  const reasonText = reasons.map((r) => t(`exr_${r}`)).filter(Boolean).join("، ");
  return (
    <div className="flex flex-col gap-0.5 min-w-[130px]">
      <span className={`text-xs font-semibold ${cfg.tone}`}>
        {cfg.icon} {cfg.label}
        {urgency === "high" && <span className="ms-1 text-down">●</span>}
      </span>
      {new_stop && <span className="text-[11px] text-mist-500 tnum">{t("ex_new_stop")}: {new_stop}</span>}
      {reasonText && <span className="text-[11px] text-mist-600 leading-tight">{reasonText}</span>}
      {typeof progress_pct === "number" && progress_pct > 0 && (
        <div className="h-1 bg-ink-700 rounded-full overflow-hidden mt-0.5">
          <div className="h-full bg-up" style={{ width: `${progress_pct}%` }} />
        </div>
      )}
    </div>
  );
}

function Th({ children }) { return <th className="text-start font-medium px-2 py-2 whitespace-nowrap">{children}</th>; }
function Td({ children, className = "" }) { return <td className={`px-2 py-2.5 whitespace-nowrap ${className}`}>{children}</td>; }
