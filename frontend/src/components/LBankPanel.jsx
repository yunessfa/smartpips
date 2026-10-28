import { useEffect, useState } from "react";
import { Panel, Badge, Button, Spinner } from "./ui.jsx";
import { lbankApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

/**
 * Real LBank account panel.
 *  - Spot: connection status, normalized balances, order history, recent fills.
 *  - Futures: public market data + read-only account.
 *
 * Futures ORDER placement is intentionally not exposed: LBank does not publish
 * a verifiable private contract-trading endpoint, so no leveraged real-money
 * orders are sent from here (see backend client for the full note).
 */
const fmt = (n, d = 8) =>
  n === null || n === undefined || n === "" || Number.isNaN(Number(n))
    ? "—"
    : Number(n).toLocaleString(undefined, { maximumFractionDigits: d });

const fmtTime = (ms) => (ms ? new Date(Number(ms)).toLocaleString() : "—");

export function LBankPanel() {
  const { t } = useI18n();
  const [status, setStatus] = useState(null);
  const [account, setAccount] = useState(null);      // {uid, canTrade, balances:[]}
  const [symbol, setSymbol] = useState("btc_usdt");
  const [orders, setOrders] = useState(null);        // {orders:[]}
  const [fills, setFills] = useState(null);          // {trades:[]}
  const [futMarket, setFutMarket] = useState(null);  // {market:[]}
  const [futAccount, setFutAccount] = useState(null);// {account:{...}}
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [diag, setDiag] = useState(null);
  const [diagBusy, setDiagBusy] = useState(false);

  async function loadAll() {
    setLoading(true); setErr(null);
    try {
      const st = await lbankApi.status();
      setStatus(st);
      if (st.connected) {
        try { setAccount(await lbankApi.balance()); } catch (e) { setErr(e.message); }
        try { setOrders(await lbankApi.orders(symbol)); } catch { /* ignore */ }
        try { setFills(await lbankApi.trades(symbol)); } catch { /* ignore */ }
        try { setFutMarket(await lbankApi.futuresMarket()); } catch { /* ignore */ }
        try { setFutAccount(await lbankApi.futuresAccount()); } catch { /* ignore */ }
      }
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);

  async function reloadSymbol() {
    try { setOrders(await lbankApi.orders(symbol)); } catch { /* ignore */ }
    try { setFills(await lbankApi.trades(symbol)); } catch { /* ignore */ }
  }

  async function runDiagnosis() {
    setDiagBusy(true); setDiag(null);
    try { setDiag(await lbankApi.debugSignatures()); }
    catch (e) { setDiag({ error: e.message }); }
    finally { setDiagBusy(false); }
  }

  if (loading) return <Panel title={t("lbank_title")}><Spinner label="…" /></Panel>;

  if (!status?.configured) {
    return (
      <Panel title={t("lbank_title")}>
        <div className="text-sm text-mist-400 space-y-2">
          <p>🔌 {t("lbank_not_configured")}</p>
          <p className="text-xs text-mist-500">{t("lbank_setup_hint")}</p>
          <pre className="text-[11px] bg-ink-900 border border-ink-600 rounded-lg p-3 text-mist-400 overflow-x-auto">
{`LBANK_API_KEY=...
LBANK_SECRET_KEY=...`}
          </pre>
        </div>
      </Panel>
    );
  }

  if (!status?.connected) {
    return (
      <Panel title={t("lbank_title")} action={<Button variant="ghost" onClick={loadAll}>{t("retry")}</Button>}>
        <div className="text-sm text-down space-y-2">
          <p>⚠️ {t("lbank_connect_failed")}</p>
          {status?.error && (
            <pre className="text-[11px] bg-down/10 border border-down/30 rounded-lg p-3 text-down overflow-x-auto whitespace-pre-wrap">
              {status.error}
            </pre>
          )}
          {status?.diagnostics && (
            <div className="text-[11px] bg-ink-800 border border-ink-500 rounded-lg p-3 text-mist-400 space-y-1">
              <p className="text-mist-500">{t("lbank_diagnostics")}</p>
              <p>API key: <span className="tnum text-mist-300">{status.diagnostics.api_key_preview || "—"}</span></p>
              <p>Secret key: <span className="tnum text-mist-300">{status.diagnostics.secret_key_preview || "—"}</span></p>
              <p>Base URL: <span className="text-mist-300">{status.diagnostics.base_url}</span></p>
              <p>{t("lbank_sign_method")}: <span className="text-gold-soft tnum">{status.diagnostics.sign_method}</span></p>
            </div>
          )}
          <p className="text-xs text-mist-500">{t("lbank_debug_hint")}</p>
          <Button onClick={runDiagnosis} disabled={diagBusy}>
            {diagBusy ? t("thinking") : `🔬 ${t("lbank_run_diagnosis")}`}
          </Button>
          {diag?.results && (
            <div className="space-y-1.5 mt-2">
              {diag.results.map((r) => (
                <div key={r.variant} className={`text-[11px] rounded-lg px-3 py-2 border ${
                  r.ok ? "bg-up/10 border-up/30" : "bg-ink-800 border-ink-600"
                }`}>
                  <p className={r.ok ? "text-up font-semibold" : "text-mist-400"}>
                    {r.ok ? "✅" : "✗"} {r.variant}
                  </p>
                  <p className="text-mist-500 mt-0.5 break-all">{JSON.stringify(r.detail)}</p>
                </div>
              ))}
            </div>
          )}
          {diag?.error && <p className="text-down text-xs">{diag.error}</p>}
        </div>
      </Panel>
    );
  }

  // ---------------- connected ----------------
  const balances = account?.balances ?? [];
  const orderRows = orders?.orders ?? [];
  const fillRows = fills?.trades ?? [];
  const market = (futMarket?.market ?? []).slice(0, 8);

  const th = "text-left text-[11px] text-mist-500 font-normal px-2 py-1";
  const td = "px-2 py-1 text-[12px] text-mist-200 tnum whitespace-nowrap";

  return (
    <Panel title={t("lbank_title")} action={<Badge tone="up">● {t("lbank_connected")}</Badge>}>
      <p className="text-xs text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-3 py-2 mb-4">
        ⚠️ {t("lbank_real_money_warning")}
      </p>

      {/* Balances */}
      <p className="text-xs text-mist-500 mb-2">{t("balance_label")}</p>
      {balances.length ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-5">
          {balances.map((b) => (
            <div key={b.asset} className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
              <p className="text-[11px] text-mist-500 uppercase">{b.asset}</p>
              <p className="tnum text-sm text-mist-100">{fmt(b.total)}</p>
              <p className="text-[10px] text-mist-500">
                {t("lbank_free")} {fmt(b.free)} · {t("lbank_locked")} {fmt(b.locked)}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-mist-500 mb-5">{t("lbank_no_balances")}</p>
      )}

      {/* Symbol picker */}
      <div className="flex items-center gap-2 mb-2">
        <p className="text-xs text-mist-500">{t("order_history")}</p>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value.toLowerCase())}
          onBlur={reloadSymbol}
          className="text-xs bg-ink-800 border border-ink-500 rounded-md px-2 py-1 text-mist-200 w-28"
          placeholder="btc_usdt" />
      </div>

      {/* Order history */}
      {orderRows.length ? (
        <div className="overflow-x-auto mb-5 border border-ink-600 rounded-lg">
          <table className="w-full">
            <thead className="bg-ink-800"><tr>
              <th className={th}>{t("opened_at")}</th><th className={th}>{t("lbank_side")}</th>
              <th className={th}>{t("current_price")}</th><th className={th}>{t("qty_coins")}</th>
              <th className={th}>{t("lbank_status") || "status"}</th>
            </tr></thead>
            <tbody>
              {orderRows.map((o) => (
                <tr key={o.orderId} className="border-t border-ink-700">
                  <td className={td}>{fmtTime(o.time)}</td>
                  <td className={`${td} ${String(o.type).startsWith("buy") ? "text-up" : "text-down"}`}>{o.type}</td>
                  <td className={td}>{fmt(o.price)}</td>
                  <td className={td}>{fmt(o.executedQty)}/{fmt(o.origQty)}</td>
                  <td className={td}>{o.status_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-xs text-mist-500 mb-5">{t("lbank_no_orders")}</p>}

      {/* Recent fills */}
      <p className="text-xs text-mist-500 mb-2">{t("lbank_fills")}</p>
      {fillRows.length ? (
        <div className="overflow-x-auto mb-5 border border-ink-600 rounded-lg">
          <table className="w-full">
            <thead className="bg-ink-800"><tr>
              <th className={th}>{t("opened_at")}</th><th className={th}>{t("lbank_side")}</th>
              <th className={th}>{t("current_price")}</th><th className={th}>{t("qty_coins")}</th>
              <th className={th}>fee</th>
            </tr></thead>
            <tbody>
              {fillRows.map((f) => (
                <tr key={f.tradeId} className="border-t border-ink-700">
                  <td className={td}>{fmtTime(f.time)}</td>
                  <td className={`${td} ${f.side === "buy" ? "text-up" : "text-down"}`}>{f.side}</td>
                  <td className={td}>{fmt(f.price)}</td>
                  <td className={td}>{fmt(f.qty)}</td>
                  <td className={td}>{fmt(f.commission)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-xs text-mist-500 mb-5">{t("lbank_no_fills")}</p>}

      {/* Futures */}
      <div className="border-t border-ink-600 pt-4 mt-1">
        <p className="text-xs text-mist-400 mb-1 font-semibold">{t("lbank_futures")}</p>
        <p className="text-[11px] text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-3 py-2 mb-3">
          ⚠️ {t("lbank_futures_trading_disabled")}
        </p>

        <p className="text-xs text-mist-500 mb-2">{t("lbank_futures_market")}</p>
        {market.length ? (
          <div className="overflow-x-auto mb-4 border border-ink-600 rounded-lg">
            <table className="w-full">
              <thead className="bg-ink-800"><tr>
                <th className={th}>symbol</th><th className={th}>{t("lbank_last")}</th>
                <th className={th}>{t("lbank_mark")}</th><th className={th}>{t("lbank_funding")}</th>
              </tr></thead>
              <tbody>
                {market.map((m) => (
                  <tr key={m.symbol} className="border-t border-ink-700">
                    <td className={`${td} uppercase`}>{m.symbol}</td>
                    <td className={td}>{fmt(m.last)}</td>
                    <td className={td}>{fmt(m.mark)}</td>
                    <td className={td}>{fmt(m.fundingRate, 6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-xs text-mist-500 mb-4">—</p>}

        <p className="text-xs text-mist-500 mb-2">{t("lbank_futures_account")}</p>
        <pre className="text-[11px] bg-ink-900 border border-ink-600 rounded-lg p-3 text-mist-400 overflow-x-auto max-h-40">
          {JSON.stringify(futAccount?.account ?? futAccount?.error ?? {}, null, 2)}
        </pre>
      </div>

      {err && <p className="text-down text-xs mt-2">{err}</p>}
    </Panel>
  );
}
