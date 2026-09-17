import { useState } from "react";
import { Button, Field, Input, Select } from "./ui.jsx";
import { useI18n } from "../i18n/index.jsx";
import { parsePrice } from "../lib/num.js";

// Modal to LOG a new trade (optionally prefilled from an assistant recommendation).
export function LogTradeModal({ initial, onClose, onSaved }) {
  const { t, isRTL } = useI18n();
  const isCrypto = (initial?.symbol || "").replace(":PERP", "").endsWith("USDT");
  const [form, setForm] = useState({
    symbol: initial?.symbol || "",
    tradingview_symbol: initial?.tradingview_symbol || "",
    direction: initial?.direction || "long",
    entry_price: initial?.entry_price || "",
    take_profit: initial?.take_profit || "",
    stop_loss: initial?.stop_loss || "",
    size: initial?.size || "",                 // crypto: margin (USDT); metals: lots
    quantity: initial?.quantity || "",          // crypto coin amount
    leverage: initial?.leverage || 1,
    tp_levels: initial?.tp_levels || null,      // 3-level partial TP plan from the engine
    source: initial?.source || "manual",
    setup_class: initial?.setup_class || "",
    notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  // live position value = margin * leverage (crypto)
  const posValue = isCrypto && form.size && form.leverage
    ? (Number(parsePrice(form.size)) * Number(parsePrice(form.leverage))).toFixed(2)
    : null;

  async function save() {
    setBusy(true); setError(null);
    try {
      const payload = {
        symbol: form.symbol,
        tradingview_symbol: form.tradingview_symbol,
        direction: form.direction,
        entry_price: Number(parsePrice(form.entry_price)),
        take_profit: form.take_profit ? Number(parsePrice(form.take_profit)) : null,
        stop_loss: form.stop_loss ? Number(parsePrice(form.stop_loss)) : null,
        tp1_price: form.tp_levels?.[0]?.price,
        tp1_pct: form.tp_levels?.[0]?.pct,
        tp2_price: form.tp_levels?.[1]?.price,
        tp2_pct: form.tp_levels?.[1]?.pct,
        tp3_price: form.tp_levels?.[2]?.price,
        tp3_pct: form.tp_levels?.[2]?.pct,
        size: Number(parsePrice(form.size)) || 0,
        leverage: Number(parsePrice(form.leverage)) || 1,
        source: form.source,
        setup_class: form.setup_class,
        notes: form.notes,
      };
      await onSaved(payload);
      onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <Overlay onClose={onClose} isRTL={isRTL} title={t("log_trade")}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("symbol")}><Input value={form.symbol} onChange={(e) => set("symbol", e.target.value)} placeholder="BTCUSDT" /></Field>
          <Field label={t("direction")}>
            <Select value={form.direction} onChange={(e) => set("direction", e.target.value)}>
              <option value="long">{t("long")}</option>
              <option value="short">{t("short")}</option>
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("entry_price")}><Input type="number" value={form.entry_price} onChange={(e) => set("entry_price", e.target.value)} /></Field>
          <Field label={isCrypto ? t("margin_usdt") : t("size_lots")}>
            <Input type="number" value={form.size} onChange={(e) => set("size", e.target.value)} placeholder={isCrypto ? "100" : "0.05"} />
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label={t("take_profit")}><Input type="number" value={form.take_profit} onChange={(e) => set("take_profit", e.target.value)} /></Field>
          <Field label={t("stop_loss")}><Input type="number" value={form.stop_loss} onChange={(e) => set("stop_loss", e.target.value)} /></Field>
          <Field label={t("leverage")}><Input type="number" min={1} value={form.leverage} onChange={(e) => set("leverage", e.target.value)} /></Field>
        </div>
        {form.tp_levels && form.tp_levels.length === 3 && (
          <div className="text-xs bg-ink-800 border border-ink-500 rounded-lg px-3 py-2 space-y-1">
            <p className="text-mist-400 mb-1">🎯 {t("tp_plan_3level")}</p>
            {form.tp_levels.map((lv, i) => (
              <div key={i} className="flex justify-between text-mist-300">
                <span>TP{i + 1} · {lv.pct}% {t("of_position")}</span>
                <span className="tnum">{lv.price} <span className="text-mist-500">({lv.r}R)</span></span>
              </div>
            ))}
          </div>
        )}
        {isCrypto && form.quantity && (
          <p className="text-xs text-mist-400 bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
            📊 {t("suggested")}: <span className="text-mist-100 font-semibold">{form.quantity} {initial?.unit}</span>
            {posValue && <span className="text-mist-500"> · {t("position_value")}: ${posValue}</span>}
          </p>
        )}
        {error && <p className="text-down text-sm">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button onClick={save} disabled={busy || !form.symbol || !form.entry_price}>{t("save_trade")}</Button>
          <Button variant="ghost" onClick={onClose}>{t("cancel")}</Button>
        </div>
      </div>
    </Overlay>
  );
}

// Modal to CLOSE an open trade by entering the exit price.
export function CloseTradeModal({ trade, currentPrice, onClose, onClosed }) {
  const { t, isRTL } = useI18n();
  const [exitPrice, setExitPrice] = useState(currentPrice ? String(currentPrice) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // estimated P&L at the entered exit price
  const px = Number(parsePrice(exitPrice));
  let estPct = null, estPnl = null;
  if (Number.isFinite(px) && trade.entry_price) {
    const move = trade.direction === "long"
      ? (px - trade.entry_price) / trade.entry_price
      : (trade.entry_price - px) / trade.entry_price;
    estPct = move * 100 * (trade.leverage || 1);
    estPnl = (trade.size || 0) * (trade.leverage || 1) * move;
  }
  const up = (estPct ?? 0) >= 0;

  async function submit() {
    setBusy(true); setError(null);
    try { await onClosed(Number(parsePrice(exitPrice))); onClose(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <Overlay onClose={onClose} isRTL={isRTL} title={`${t("close_trade")} · ${trade.symbol}`}>
      <div className="space-y-3">
        <p className="text-sm text-mist-300">
          {t("direction")}: {trade.direction === "long" ? t("long") : t("short")} ·
          {" "}{t("entry_price")}: <span className="tnum">{trade.entry_price}</span> ·
          {" "}{t("leverage")}: <span className="tnum">{trade.leverage}x</span>
        </p>

        {currentPrice != null && (
          <Button variant="primary" onClick={() => setExitPrice(String(currentPrice))}>
            {t("close_at_current")} ({Number(currentPrice).toLocaleString("en-US", { maximumFractionDigits: 4 })})
          </Button>
        )}

        <Field label={t("exit_price")}><Input type="number" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} autoFocus /></Field>

        {estPct != null && exitPrice && (
          <p className={`text-sm tnum ${up ? "text-up" : "text-down"}`}>
            {t("pnl")}: {up ? "+" : ""}{estPnl.toFixed(2)} ({up ? "+" : ""}{estPct.toFixed(2)}%)
          </p>
        )}

        {error && <p className="text-down text-sm">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={busy || !exitPrice}>{t("close")}</Button>
          <Button variant="ghost" onClick={onClose}>{t("cancel")}</Button>
        </div>
      </div>
    </Overlay>
  );
}

function Overlay({ children, onClose, title, isRTL }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4" dir={isRTL ? "rtl" : "ltr"}>
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative w-full max-w-md bg-ink-700 border border-ink-500 rounded-2xl shadow-panel">
        <header className="px-5 py-3 border-b border-ink-500">
          <h3 className="font-semibold text-mist-100">{title}</h3>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
