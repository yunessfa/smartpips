import { useEffect, useState } from "react";
import { bitunixApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";

/**
 * Pre-trade confirmation modal (used by the Scalp order ticket AND the Bitunix
 * panel). Shows the trade the way an exchange does and lets the user adjust
 * BEFORE it fires: leverage, order type (market / limit @ live price), margin
 * mode (isolated / cross, real only), and position size. It also shows the
 * balance for THIS mode broken into free vs already-in-trade.
 *
 * props:
 *   mode      "demo" | "real"
 *   signal    { symbol, signal:'buy'|'sell', entry, take_profit, stop_loss,
 *               order_ticket:{ leverage, quantity, unit, order_type, limit_price } }
 *   livePrice current market price
 *   demoBalance  the user's top balance (demo sizing base)
 *   onClose(), onDone(result)
 */
const fee = (notional) => notional * 0.0006;

export function TradeConfirmModal({ mode, signal, livePrice, demoBalance, onClose, onDone }) {
  const { t } = useI18n();
  const tk = signal.order_ticket || {};
  const isBuy = signal.signal === "buy";
  const symbol = (signal.symbol || "").replace(":PERP", "").toUpperCase();

  const [orderType, setOrderType] = useState(tk.order_type === "limit" ? "LIMIT" : "MARKET");
  const [limitPrice, setLimitPrice] = useState(tk.limit_price ?? signal.entry ?? livePrice ?? "");
  const [leverage, setLeverage] = useState(tk.leverage || 5);
  const [marginMode, setMarginMode] = useState("ISOLATION");
  // exchange-style sizing: pick ONE input (margin / qty / percent). Changing
  // leverage recomputes the OTHER numbers but never touches your chosen input
  // amount — set $300 margin at 50x and it stays $300, the position just grows.
  const [sizeMode, setSizeMode] = useState("margin");   // margin | qty | percent
  const [marginInput, setMarginInput] = useState("");
  const [qtyInput, setQtyInput] = useState(tk.quantity ? String(tk.quantity) : "");
  const [pctInput, setPctInput] = useState(25);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // live balance for this mode, split into free vs in-trade
  const [bal, setBal] = useState(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (mode === "real") {
          const acct = await bitunixApi.account();
          const row = Array.isArray(acct?.account) ? acct.account[0] : acct?.account;
          if (alive && row) setBal({
            total: Number(row.available || 0) + Number(row.margin || row.frozen || 0),
            inTrade: Number(row.margin || row.frozen || 0),
            free: Number(row.available || 0),
          });
        } else {
          const pos = await bitunixApi.positions("demo");
          const used = pos?.marginUsed || 0;
          const total = Number(demoBalance || 0);
          if (alive) setBal({ total, inTrade: used, free: Math.max(0, total - used) });
        }
      } catch { /* leave null */ }
    })();
    return () => { alive = false; };
  }, [mode, demoBalance]);

  const entryPx = orderType === "LIMIT" ? Number(limitPrice) : (livePrice ?? signal.entry);
  const lev = Math.max(1, Number(leverage) || 1);

  // Derive the three linked quantities from whichever the user is driving.
  // KEY: margin/qty/percent are the INPUTS; leverage only scales the others.
  let margin = 0, qty = 0, notional = 0;
  if (entryPx > 0) {
    if (sizeMode === "margin") {
      margin = Math.max(0, Number(marginInput) || 0);
      notional = margin * lev;                 // more leverage -> bigger position, SAME margin
      qty = notional / entryPx;
    } else if (sizeMode === "qty") {
      qty = Math.max(0, Number(qtyInput) || 0);
      notional = qty * entryPx;
      margin = notional / lev;
    } else { // percent of FREE balance committed as margin
      const free = bal?.free || 0;
      margin = free * (Number(pctInput) || 0) / 100;
      notional = margin * lev;
      qty = notional / entryPx;
    }
  }
  qty = Number(qty.toFixed(qty < 1 ? 6 : 3));
  const estFee = fee(notional);
  const liqFrac = 0.95 / lev;
  const estLiq = entryPx ? (isBuy ? entryPx * (1 - liqFrac) : entryPx * (1 + liqFrac)) : null;
  const overFree = bal && margin > bal.free * 1.001;

  async function submit() {
    setBusy(true); setErr(null);
    try {
      if (mode === "real" && marginMode) {
        try { await bitunixApi.setMarginMode({ symbol, marginMode }); } catch { /* non-fatal */ }
      }
      const res = await bitunixApi.placeOrder({
        mode, confirm: mode === "real" ? true : undefined,
        demoBalance: mode === "demo" ? demoBalance : undefined,
        symbol, side: isBuy ? "BUY" : "SELL",
        orderType, qty,
        price: orderType === "LIMIT" ? Number(limitPrice) : undefined,
        leverage: lev,
        tpPrice: signal.take_profit || undefined,
        slPrice: signal.stop_loss || undefined,
      });
      onDone(res);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  const inp = "w-full bg-ink-800 border border-ink-500 rounded-md px-2.5 py-2 text-sm text-mist-100 tnum focus:border-gold/60 outline-none";
  const lbl = "text-[11px] text-mist-500 mb-1 block";
  const seg = (on, tone) => `flex-1 py-1.5 text-xs font-semibold rounded ${
    on ? (tone === "up" ? "bg-up text-white" : tone === "down" ? "bg-down text-white" : "bg-ink-600 text-mist-100") : "text-mist-500"}`;
  const Row = ({ k, v, tone }) => (
    <div className="flex items-center justify-between py-1.5 text-[13px] border-b border-ink-600/50 last:border-0">
      <span className="text-mist-500">{k}</span>
      <span className={`tnum font-medium ${tone || "text-mist-100"}`}>{v}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-end md:items-center justify-center p-0 md:p-4"
      onClick={onClose}>
      <div className="bg-ink-700 border border-ink-500 rounded-t-2xl md:rounded-2xl p-4 md:p-5 w-full max-w-lg max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        {/* header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-bold ${isBuy ? "text-up" : "text-down"}`}>
              {isBuy ? `▲ ${t("open_long")}` : `▼ ${t("open_short")}`}
            </span>
            <span className="text-mist-100 font-semibold">{symbol}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
              mode === "real" ? "bg-down/15 text-down" : "bg-up/15 text-up"}`}>
              {mode === "real" ? t("bx_real") : t("bx_demo")}
            </span>
          </div>
          <button onClick={onClose} className="text-mist-500 hover:text-mist-100 text-lg">✕</button>
        </div>

        {/* balance breakdown for this mode */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          {[["bx_total", bal?.total], ["bx_in_trade", bal?.inTrade], ["bx_free", bal?.free]].map(([k, v], i) => (
            <div key={k} className="bg-ink-800 border border-ink-500 rounded-lg px-2.5 py-2">
              <p className="text-[10px] text-mist-500">{t(k)}</p>
              <p className={`tnum text-[13px] ${i === 2 ? "text-mist-100 font-semibold" : "text-mist-300"}`}>
                {bal ? `${(v ?? 0).toFixed(2)}` : "…"}<span className="text-[10px] text-mist-500"> USDT</span>
              </p>
            </div>
          ))}
        </div>

        {/* order type */}
        <label className={lbl}>{t("bx_order_type")}</label>
        <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5 mb-3">
          <button onClick={() => setOrderType("MARKET")} className={seg(orderType === "MARKET")}>
            {t("market_order")} · {fmtPrice(livePrice)}
          </button>
          <button onClick={() => setOrderType("LIMIT")} className={seg(orderType === "LIMIT")}>
            {t("limit_order")}
          </button>
        </div>
        {orderType === "LIMIT" && (
          <div className="mb-3">
            <label className={lbl}>{t("limit_price")}</label>
            <input className={inp} type="number" step="any" value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)} />
          </div>
        )}

        {/* leverage + margin mode */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className={lbl}>{t("bx_leverage")}</label>
            <input className={inp} type="number" min="1" max="125" value={leverage}
              onChange={(e) => setLeverage(e.target.value)} />
          </div>
          <div>
            <label className={lbl}>{t("bx_margin_mode")}{mode === "demo" ? "" : ""}</label>
            <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5">
              {["ISOLATION", "CROSS"].map((mm) => (
                <button key={mm} onClick={() => setMarginMode(mm)}
                  disabled={mode === "demo"}
                  className={`${seg(marginMode === mm)} disabled:opacity-50`}>
                  {mm === "ISOLATION" ? t("isolated") : t("bx_cross")}
                </button>))}
            </div>
          </div>
        </div>

        {/* sizing — exchange style: you set margin (or qty / % of balance),
            leverage only scales the position, never your margin */}
        <label className={lbl}>{t("bx_sizing")}</label>
        <div className="flex bg-ink-800 border border-ink-500 rounded-md p-0.5 mb-2">
          {[["margin", t("bx_by_margin")], ["qty", t("bx_by_qty")], ["percent", t("bx_by_percent")]].map(([m, label]) => (
            <button key={m} onClick={() => setSizeMode(m)} className={seg(sizeMode === m)}>{label}</button>
          ))}
        </div>
        {sizeMode === "margin" && (
          <div className="mb-4">
            <input className={inp} type="number" step="any" inputMode="decimal"
              value={marginInput} onChange={(e) => setMarginInput(e.target.value)}
              placeholder={`${t("bx_margin_amount")} (USDT)`} />
            <div className="flex gap-1.5 mt-1.5">
              {[25, 50, 75, 100].map((p) => (
                <button key={p} onClick={() => setMarginInput(((bal?.free || 0) * p / 100).toFixed(2))}
                  className="flex-1 text-[11px] py-1 rounded bg-ink-800 border border-ink-500 text-mist-400 hover:text-mist-100">
                  {p}%
                </button>))}
            </div>
          </div>
        )}
        {sizeMode === "qty" && (
          <div className="mb-4">
            <input className={inp} type="number" step="any" inputMode="decimal"
              value={qtyInput} onChange={(e) => setQtyInput(e.target.value)}
              placeholder={`${t("qty_coins")} (${tk.unit || symbol.replace("USDT", "")})`} />
          </div>
        )}
        {sizeMode === "percent" && (
          <div className="mb-4">
            <input type="range" min="1" max="100" value={pctInput}
              onChange={(e) => setPctInput(Number(e.target.value))} className="w-full accent-gold" />
            <div className="flex justify-between text-[11px] text-mist-500 mt-1">
              <span>{pctInput}% {t("bx_of_free")}</span>
              <span className="tnum text-mist-300">{((bal?.free || 0) * pctInput / 100).toFixed(2)} USDT</span>
            </div>
          </div>
        )}

        {/* summary */}
        <div className="bg-ink-800/60 rounded-lg px-3 py-2 mb-3">
          <Row k={t("qty_coins")} v={`${qty} ${tk.unit}`} />
          <Row k={t("entry")} v={fmtPrice(entryPx)} />
          <Row k={t("take_profit")} v={fmtPrice(signal.take_profit)} tone="text-up" />
          <Row k={t("stop_loss")} v={fmtPrice(signal.stop_loss)} tone="text-down" />
          <Row k={t("position_value")} v={`${notional.toFixed(2)} USDT`} />
          <Row k={t("margin_needed")} v={`${margin.toFixed(2)} USDT`}
            tone={overFree ? "text-down" : sizeMode === "margin" ? "text-gold-soft" : undefined} />
          <Row k={`${t("est_liquidation")} *`} v={fmtPrice(estLiq)} tone="text-down" />
          <Row k={t("bx_est_fee")} v={`${estFee.toFixed(4)} USDT`} tone="text-mist-400" />
        </div>

        {overFree && <p className="text-[11px] text-down mb-2">⚠️ {t("bx_over_available")}</p>}
        {err && <p className="text-xs text-down bg-down/10 border border-down/30 rounded-lg px-3 py-2 mb-2">⚠️ {err}</p>}

        <button onClick={submit} disabled={busy || !qty || overFree}
          className={`w-full py-3 rounded-lg text-sm font-bold text-white disabled:opacity-40 ${
            isBuy ? "bg-up" : "bg-down"}`}>
          {busy ? "…" : mode === "real"
            ? `${t("bx_place_real")} — ${isBuy ? t("open_long") : t("open_short")}`
            : `${t("bx_place_demo")} — ${isBuy ? t("open_long") : t("open_short")}`}
        </button>
        <p className="text-[10px] text-mist-500 mt-2">* {t("liq_estimate_note")}</p>
      </div>
    </div>
  );
}
