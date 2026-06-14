import { useState } from "react";
import { Button, Field, Input, Select } from "./ui.jsx";
import { useI18n } from "../i18n/index.jsx";

// Modal to LOG a new trade (optionally prefilled from an assistant recommendation).
export function LogTradeModal({ initial, onClose, onSaved }) {
  const { t, isRTL } = useI18n();
  const [form, setForm] = useState({
    symbol: initial?.symbol || "",
    tradingview_symbol: initial?.tradingview_symbol || "",
    direction: initial?.direction || "long",
    entry_price: initial?.entry_price || "",
    take_profit: initial?.take_profit || "",
    stop_loss: initial?.stop_loss || "",
    size: "",
    leverage: 1,
    source: initial?.source || "manual",
    notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function save() {
    setBusy(true); setError(null);
    try {
      const payload = {
        ...form,
        entry_price: Number(form.entry_price),
        take_profit: form.take_profit ? Number(form.take_profit) : null,
        stop_loss: form.stop_loss ? Number(form.stop_loss) : null,
        size: Number(form.size) || 0,
        leverage: Number(form.leverage) || 1,
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
          <Field label={t("size_margin")}><Input type="number" value={form.size} onChange={(e) => set("size", e.target.value)} placeholder="100" /></Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label={t("take_profit")}><Input type="number" value={form.take_profit} onChange={(e) => set("take_profit", e.target.value)} /></Field>
          <Field label={t("stop_loss")}><Input type="number" value={form.stop_loss} onChange={(e) => set("stop_loss", e.target.value)} /></Field>
          <Field label={t("leverage")}><Input type="number" min={1} value={form.leverage} onChange={(e) => set("leverage", e.target.value)} /></Field>
        </div>
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
export function CloseTradeModal({ trade, onClose, onClosed }) {
  const { t, isRTL } = useI18n();
  const [exitPrice, setExitPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit() {
    setBusy(true); setError(null);
    try { await onClosed(Number(exitPrice)); onClose(); }
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
        <Field label={t("exit_price")}><Input type="number" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} autoFocus /></Field>
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
