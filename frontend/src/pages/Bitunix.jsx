import { useEffect, useState } from "react";
import { Panel, Badge, Button, Spinner } from "../components/ui.jsx";
import { bitunixApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";
import { BITUNIX_SYMBOLS } from "../lib/symbols.js";
import { PositionChart } from "../components/PositionChart.jsx";

/**
 * Bitunix futures management panel.
 * Demo mode fills locally against live Bitunix prices; Real mode places on
 * the exchange and always demands an explicit confirmation step — the two
 * modes share one form so what you rehearse in demo is exactly what fires
 * in real.
 */
const fmt = (n, d = 4) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d });

const th = "text-left text-[11px] text-mist-500 font-normal px-2 py-1";
const td = "px-2 py-1 text-[12px] text-mist-100 tnum whitespace-nowrap";

export default function Bitunix() {
  const { t } = useI18n();
  const [status, setStatus] = useState(null);
  const [account, setAccount] = useState(null);
  const [mode, setMode] = useState(() => localStorage.getItem("bx_mode") || "demo");
  const [positions, setPositions] = useState(null);
  const [orders, setOrders] = useState(null);
  const [selfTest, setSelfTest] = useState(null);
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [notice, setNotice] = useState(null);

  function switchMode(m) {
    setMode(m); localStorage.setItem("bx_mode", m);
    window.dispatchEvent(new Event("bx-mode-changed"));
  }

  async function loadAll(m = mode) {
    setErr(null);
    try {
      const st = await bitunixApi.status(); setStatus(st);
      const jobs = [bitunixApi.positions(m).then(setPositions).catch(() => setPositions(null))];
      if (st.connected) {
        jobs.push(bitunixApi.account().then(setAccount).catch(() => setAccount(null)));
        jobs.push(bitunixApi.orders().then(setOrders).catch(() => setOrders(null)));
      }
      await Promise.all(jobs);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { bitunixApi.positions(mode).then(setPositions).catch(() => {}); }, [mode]);
  // LIVE PnL: poll positions (and the real wallet) every 5s like a terminal.
  useEffect(() => {
    const id = setInterval(() => {
      bitunixApi.positions(mode).then(setPositions).catch(() => {});
      if (status?.connected && mode === "real")
        bitunixApi.account().then(setAccount).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [mode, status?.connected]);

  async function runSelfTest() {
    setTesting(true); setSelfTest(null);
    try { setSelfTest(await bitunixApi.selfTest()); }
    catch (e) { setSelfTest({ ok: false, steps: [{ step: "request", ok: false, detail: e.message }] }); }
    finally { setTesting(false); }
  }

  async function closePos(p) {
    const isReal = mode === "real";
    if (isReal && !window.confirm(t("bx_close_confirm"))) return;
    setPositions((prev) => prev ? { ...prev, positions:
      (prev.positions || []).filter((x) => (x.positionId || x.id) !== (p.positionId || p.id)) } : prev);
    try {
      await bitunixApi.closePosition({
        mode, positionId: p.positionId || p.id, confirm: isReal ? true : undefined,
      });
      setNotice(t("bx_closed"));
    } catch (e) { setErr(e.message); }
    finally { loadAll(); }
  }

  if (loading) return <div className="p-6"><Spinner label="…" /></div>;

  const acctRow = Array.isArray(account?.account) ? account.account[0] : account?.account;
  const posRows = positions?.positions || [];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto w-full">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-lg font-bold text-mist-100">Bitunix Futures</h1>
        <div className="flex items-center gap-2">
          {/* demo/real master switch */}
          <div className="flex items-center bg-ink-800 border border-ink-500 rounded-lg p-0.5">
            {["demo", "real"].map((m) => (
              <button key={m} onClick={() => switchMode(m)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition ${
                  mode === m
                    ? m === "real" ? "bg-down text-white" : "bg-up text-white"
                    : "text-mist-500"
                }`}>
                {m === "demo" ? t("bx_demo") : t("bx_real")}
              </button>
            ))}
          </div>
          {status?.connected
            ? <Badge tone="up">● {t("lbank_connected")}</Badge>
            : <Badge tone="down">○ {t("bx_not_connected")}</Badge>}
        </div>
      </div>

      {mode === "real" && (
        <p className="text-xs text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-3 py-2">
          ⚠️ {t("bx_real_warning")}
        </p>)}
      {err && <p className="text-down text-xs">{err}</p>}
      {notice && <p className="text-up text-xs">{notice}</p>}

      {/* connection + self test */}
      <Panel title={t("bx_connection")}
        action={<Button variant="ghost" onClick={runSelfTest} disabled={testing}>
          {testing ? "…" : `🔬 ${t("bx_run_self_test")}`}</Button>}>
        {!status?.configured ? (
          <div className="text-sm text-mist-300 space-y-2">
            <p>{t("bx_not_configured")}</p>
            <pre className="text-[11px] bg-ink-900 border border-ink-600 rounded-lg p-3 text-mist-300 overflow-x-auto">
{`BITUNIX_API_KEY=...
BITUNIX_SECRET_KEY=...`}</pre>
          </div>
        ) : (
          <div className="text-[12px] text-mist-300 space-y-1">
            <p>API key: <span className="tnum">{status.diagnostics?.api_key_preview}</span></p>
            <p>Base: <span className="tnum">{status.diagnostics?.base_url}</span></p>
            {status.error && <p className="text-down">{status.error}</p>}
          </div>
        )}
        {selfTest && (
          <div className="mt-3 space-y-1">
            {selfTest.steps.map((s) => (
              <div key={s.step} className={`text-[11px] rounded-md px-2.5 py-1.5 border ${
                s.ok ? "bg-up/10 border-up/25 text-up" : "bg-down/10 border-down/25 text-down"}`}>
                {s.ok ? "✅" : "✗"} <span className="text-mist-300">{s.step}</span>
                <span className="text-mist-500 ms-2 break-all">{s.detail}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* demo balance (the user's own number from the Scalp page) */}
      {mode === "demo" && (
        <Panel title={t("bx_demo_balance")}>
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
              <p className="text-[11px] text-mist-500">{t("bx_demo_balance")}</p>
              <p className="tnum text-sm text-mist-100">
                {fmt(Number(localStorage.getItem("sp_balance_manual") ?? localStorage.getItem("sp_balance")), 2)} USDT
              </p>
            </div>
            <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
              <p className="text-[11px] text-mist-500">{t("bx_free_margin")}</p>
              <p className="tnum text-sm text-mist-100">
                {fmt(Number(localStorage.getItem("sp_balance_manual") ?? localStorage.getItem("sp_balance")) - (positions?.marginUsed || 0), 2)}
              </p>
            </div>
            <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
              <p className="text-[11px] text-mist-500">PnL {t("bx_live")}</p>
              <p className={`tnum text-sm ${Number(positions?.unrealizedPNL) >= 0 ? "text-up" : "text-down"}`}>
                {fmt(positions?.unrealizedPNL, 2)}
              </p>
            </div>
          </div>
        </Panel>
      )}

      {/* real wallet */}
      {mode === "real" && status?.connected && (
        <Panel title={t("bx_futures_balance")}>
          {acctRow ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(() => {
                const free = Number(acctRow.available || 0);
                const inTrade = Number(acctRow.margin || acctRow.frozen || 0);
                const cards = [
                  [t("bx_total"), (free + inTrade).toFixed(2), "text-mist-100"],
                  [t("bx_in_trade"), inTrade.toFixed(2), "text-gold-soft"],
                  [t("bx_free"), free.toFixed(2), "text-up"],
                  ["PnL", Number(acctRow.crossUnrealizedPNL || 0).toFixed(2),
                    Number(acctRow.crossUnrealizedPNL) >= 0 ? "text-up" : "text-down"],
                ];
                return cards.map(([label, val, tone]) => (
                  <div key={label} className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
                    <p className="text-[11px] text-mist-500">{label}</p>
                    <p className={`tnum text-sm ${tone}`}>{val} <span className="text-[10px] text-mist-500">USDT</span></p>
                  </div>
                ));
              })()}
            </div>
          ) : <p className="text-xs text-mist-500">—</p>}
        </Panel>
      )}

      {/* position chart: entry / TP / SL / liq drawn on real candles, for
          BOTH demo and real positions at once (display only) */}
      <Panel title={t("pc_title")}>
        <PositionChart refreshKey={`${mode}-${posRows.length}`} />
      </Panel>

      {/* order form */}
      <OrderForm mode={mode} onDone={() => { setNotice(t("bx_order_ok")); loadAll(); }}
        onError={setErr} available={acctRow?.available} />

      {/* positions */}
      <Panel title={`${t("bx_positions")} (${mode === "demo" ? t("bx_demo") : t("bx_real")})`}
        action={<Button variant="ghost" onClick={() => loadAll()}>{t("retry")}</Button>}>
        {posRows.length ? (
          <div className="overflow-x-auto border border-ink-600 rounded-lg">
            <table className="w-full">
              <thead className="bg-ink-800"><tr>
                <th className={th}>symbol</th><th className={th}>{t("lbank_side")}</th>
                <th className={th}>{t("bx_leverage")}</th>
                <th className={th}>{t("bx_margin_mode")}</th>
                <th className={th}>qty</th><th className={th}>{t("entry")}</th>
                <th className={th}>{t("margin_needed")}</th>
                <th className={th}>{t("est_liquidation")}</th>
                <th className={th}>PnL</th><th className={th}>TP/SL</th><th className={th}></th>
              </tr></thead>
              <tbody>
                {posRows.map((p) => {
                  const side = (p.side || "").toUpperCase().includes("BUY") ||
                    (p.side || "").toUpperCase() === "LONG" ? "LONG" : "SHORT";
                  const pnl = p.unrealizedPNL ?? p.unrealizedPnl;
                  return (
                    <tr key={p.positionId || p.id} className="border-t border-ink-700">
                      <td className={`${td} font-semibold`}>{p.symbol}</td>
                      <td className={`${td} ${side === "LONG" ? "text-up" : "text-down"}`}>{side}</td>
                      <td className={td}>{p.leverage ? `${p.leverage}x` : "—"}</td>
                      <td className={td}>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-ink-600 text-mist-300">
                          {String(p.marginMode || p.margin_mode || "").toUpperCase().includes("CROSS")
                            ? t("bx_cross") : t("isolated")}
                        </span>
                      </td>
                      <td className={td}>{fmt(p.qty)}</td>
                      <td className={td}>{fmtPrice(p.entryPrice ?? p.avgOpenPrice)}</td>
                      <td className={td}>{fmt(p.margin, 2)}</td>
                      <td className={`${td} text-down/80`}>{fmtPrice(p.liqPrice ?? p.liquidationPrice)}</td>
                      <td className={`${td} ${Number(pnl) >= 0 ? "text-up" : "text-down"}`}>{fmt(pnl, 2)}</td>
                      <td className={td}>{fmtPrice(p.tpPrice)} / {fmtPrice(p.slPrice)}</td>
                      <td className={td}>
                        <button onClick={() => closePos(p)}
                          className="text-[11px] px-2 py-1 rounded bg-down/15 text-down border border-down/30 hover:bg-down/25">
                          {t("bx_close")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <p className="text-xs text-mist-500">{t("bx_no_positions")}</p>}

        {mode === "demo" && positions?.history?.length > 0 && (
          <>
            <p className="text-xs text-mist-500 mt-4 mb-1">{t("bx_demo_history")}</p>
            <div className="overflow-x-auto border border-ink-600 rounded-lg">
              <table className="w-full"><tbody>
                {positions.history.map((h) => (
                  <tr key={h.id} className="border-t border-ink-700 first:border-0">
                    <td className={td}>{h.symbol}</td>
                    <td className={`${td} ${h.side === "LONG" ? "text-up" : "text-down"}`}>{h.side}</td>
                    <td className={td}>{fmtPrice(h.entryPrice)} → {fmtPrice(h.closePrice)}</td>
                    <td className={td}>{h.closeReason}</td>
                    <td className={`${td} ${Number(h.realizedPNL) >= 0 ? "text-up" : "text-down"}`}>
                      {fmt(h.realizedPNL, 2)}</td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          </>
        )}
      </Panel>

      {/* pending orders (real) */}
      {status?.connected && orders?.pending?.length > 0 && (
        <Panel title={t("bx_pending_orders")}>
          <div className="overflow-x-auto border border-ink-600 rounded-lg">
            <table className="w-full"><tbody>
              {orders.pending.map((o) => (
                <tr key={o.orderId} className="border-t border-ink-700 first:border-0">
                  <td className={td}>{o.symbol}</td>
                  <td className={td}>{o.side}</td>
                  <td className={td}>{fmt(o.qty)}</td>
                  <td className={td}>{fmtPrice(o.price)}</td>
                  <td className={td}>
                    <button onClick={async () => {
                      try { await bitunixApi.cancelOrders({ symbol: o.symbol, orderIds: [o.orderId] }); loadAll(); }
                      catch (e) { setErr(e.message); }
                    }} className="text-[11px] px-2 py-1 rounded bg-ink-600 text-mist-300 hover:text-down">
                      {t("bx_cancel")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody></table>
          </div>
        </Panel>
      )}
      </div>
    </div>
  );
}

function OrderForm({ mode, onDone, onError, available }) {
  const { t } = useI18n();
  const [f, setF] = useState({ symbol: "BTCUSDT", side: "BUY", orderType: "MARKET",
    qty: "", price: "", leverage: 5, tpPrice: "", slPrice: "", sizeBy: "margin", margin: "" });
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [localErr, setLocalErr] = useState(null);   // shown right at the button
  const set = (k) => (e) => setF({ ...f, [k]: e.target?.value ?? e });
  useEffect(() => {
    let alive = true;
    bitunixApi.ticker(f.symbol).then((r) => { if (alive && r?.price) setF((s) => ({ ...s, livePx: r.price })); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.symbol]);

  // exchange-style: reference price for market = live ticker; leverage only
  // scales the position, it never shrinks the margin you chose.
  const refPx = f.orderType === "LIMIT" ? Number(f.price) : Number(f.livePx || f.price);
  const lev = Math.max(1, Number(f.leverage) || 1);
  // effective qty: from margin input (margin×lev/price) or the direct qty input
  const effQty = f.sizeBy === "margin"
    ? (refPx > 0 && f.margin ? (Number(f.margin) * lev) / refPx : 0)
    : Number(f.qty) || 0;
  const estMargin = f.sizeBy === "margin"
    ? (Number(f.margin) || 0)
    : (effQty && refPx ? (effQty * refPx) / lev : null);

  async function submit() {
    setBusy(true); onError(null); setLocalErr(null);
    try {
      await bitunixApi.placeOrder({
        mode, confirm: mode === "real" ? true : undefined,
        demoBalance: mode === "demo"
          ? Number(localStorage.getItem("sp_balance_manual") ?? localStorage.getItem("sp_balance")) || undefined
          : undefined,
        symbol: f.symbol.toUpperCase(), side: f.side,
        orderType: f.orderType, qty: Number(effQty.toFixed(effQty < 1 ? 6 : 3)),
        price: f.orderType === "LIMIT" ? Number(f.price) : undefined,
        leverage: Number(f.leverage) || undefined,
        tpPrice: f.tpPrice ? Number(f.tpPrice) : undefined,
        slPrice: f.slPrice ? Number(f.slPrice) : undefined,
      });
      setConfirming(false);
      onDone();
    } catch (e) { setLocalErr(e.message); onError(e.message); setConfirming(false); }
    finally { setBusy(false); }
  }

  const inp = "w-full bg-ink-800 border border-ink-500 rounded-md px-2.5 py-2 text-sm text-mist-100 tnum focus:border-gold/60 outline-none";
  const lbl = "text-[11px] text-mist-500 mb-1 block";

  return (
    <Panel title={`${t("bx_new_order")} — ${mode === "demo" ? t("bx_demo") : t("bx_real")}`}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><label className={lbl}>Symbol</label>
          <select className={inp} value={f.symbol} onChange={set("symbol")}>
            {BITUNIX_SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></div>
        <div><label className={lbl}>{t("lbank_side")}</label>
          <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5">
            {["BUY", "SELL"].map((s) => (
              <button key={s} onClick={() => setF({ ...f, side: s })}
                className={`flex-1 py-1.5 text-xs font-bold rounded ${
                  f.side === s ? (s === "BUY" ? "bg-up text-white" : "bg-down text-white") : "text-mist-500"}`}>
                {s === "BUY" ? t("open_long") : t("open_short")}
              </button>))}
          </div></div>
        <div><label className={lbl}>{t("bx_order_type")}</label>
          <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5">
            {["MARKET", "LIMIT"].map((o) => (
              <button key={o} onClick={() => setF({ ...f, orderType: o })}
                className={`flex-1 py-1.5 text-xs font-semibold rounded ${
                  f.orderType === o ? "bg-ink-600 text-mist-100" : "text-mist-500"}`}>
                {o === "MARKET" ? t("market_order") : t("limit_order")}
              </button>))}
          </div></div>
        <div><label className={lbl}>{t("bx_leverage")}</label>
          <input className={inp} type="number" min="1" max="125" value={f.leverage} onChange={set("leverage")} /></div>
        <div><label className={lbl}>{t("bx_margin_mode")}</label>
          <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5">
            {["ISOLATION", "CROSS"].map((mm) => (
              <button key={mm} onClick={async () => {
                  setF({ ...f, marginMode: mm });
                  try { await bitunixApi.setMarginMode({ symbol: f.symbol.toUpperCase(), marginMode: mm }); }
                  catch (e) { setLocalErr(e.message); }
                }}
                className={`flex-1 py-1.5 text-xs font-semibold rounded ${
                  (f.marginMode || "ISOLATION") === mm ? "bg-ink-600 text-mist-100" : "text-mist-500"}`}>
                {mm === "ISOLATION" ? t("isolated") : t("bx_cross")}
              </button>))}
          </div></div>
        <div className="col-span-2"><label className={lbl}>{t("bx_sizing")}</label>
          <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5 mb-2 w-fit">
            {[["margin", t("bx_by_margin")], ["qty", t("bx_by_qty")]].map(([m, label]) => (
              <button key={m} onClick={() => setF({ ...f, sizeBy: m })}
                className={`px-3 py-1 text-xs font-semibold rounded ${f.sizeBy === m ? "bg-ink-600 text-mist-100" : "text-mist-500"}`}>
                {label}</button>))}
          </div>
          {f.sizeBy === "margin" ? (
            <input className={inp} type="number" step="any" value={f.margin} onChange={set("margin")}
              placeholder={`${t("bx_margin_amount")} (USDT)`} />
          ) : (
            <input className={inp} type="number" step="any" value={f.qty} onChange={set("qty")}
              placeholder={`${t("qty_coins")} (${t("bx_base_coin")})`} />
          )}
          {f.sizeBy === "margin" && effQty > 0 && (
            <p className="text-[11px] text-mist-500 mt-1 tnum">≈ {effQty.toFixed(effQty < 1 ? 6 : 3)} {f.symbol.replace("USDT","")}</p>
          )}
        </div>
        {f.orderType === "LIMIT" && (
          <div><label className={lbl}>{t("limit_price")}</label>
            <input className={inp} type="number" step="any" value={f.price} onChange={set("price")} /></div>)}
        <div><label className={lbl}>TP</label>
          <input className={inp} type="number" step="any" value={f.tpPrice} onChange={set("tpPrice")} /></div>
        <div><label className={lbl}>SL</label>
          <input className={inp} type="number" step="any" value={f.slPrice} onChange={set("slPrice")} /></div>
      </div>

      {estMargin != null && (
        <p className="text-[11px] text-mist-500 mt-2 tnum">
          {t("margin_needed")} ≈ {estMargin.toFixed(2)} USDT
          {available != null && Number(estMargin) > Number(available) &&
            <span className="text-down"> — {t("bx_over_available")}</span>}
        </p>)}

      {localErr && (
        <p className="mt-3 text-xs text-down bg-down/10 border border-down/30 rounded-lg px-3 py-2">
          ⚠️ {localErr}
        </p>
      )}

      {!confirming ? (
        <button disabled={busy || !(effQty > 0)}
          onClick={() => (mode === "real" ? setConfirming(true) : submit())}
          className={`mt-3 w-full md:w-auto px-8 py-2.5 rounded-lg text-sm font-bold text-white disabled:opacity-40 ${
            f.side === "BUY" ? "bg-up" : "bg-down"}`}>
          {busy ? "…" : mode === "real" ? t("bx_place_real") : t("bx_place_demo")}
        </button>
      ) : (
        <div className="mt-3 flex items-center gap-2 flex-wrap bg-down/10 border border-down/30 rounded-lg p-3">
          <p className="text-xs text-down font-semibold flex-1">{t("bx_confirm_text")}</p>
          <button onClick={submit} disabled={busy}
            className="px-4 py-2 rounded-md bg-down text-white text-xs font-bold">
            {busy ? "…" : t("bx_confirm_yes")}</button>
          <button onClick={() => setConfirming(false)}
            className="px-4 py-2 rounded-md bg-ink-600 text-mist-300 text-xs">{t("bx_confirm_no")}</button>
        </div>
      )}
    </Panel>
  );
}
