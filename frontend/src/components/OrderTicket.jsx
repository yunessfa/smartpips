import { useEffect, useState } from "react";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";
import { TradeConfirmModal } from "./TradeConfirmModal.jsx";

/**
 * The signal rendered the way the exchange app itself frames an order —
 * margin mode, leverage, order type (market/limit), amount, margin, estimated
 * liquidation, TP/SL — plus a freshness guard: shows the signal's age and
 * flips to "expired, don't chase" once price has run past max_chase_price.
 */
function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(id); }, [ms]);
  return now;
}

export function signalExpired(ai, livePrice) {
  const chase = ai?.order_ticket?.max_chase_price;
  if (!chase || !livePrice) return false;
  return ai.signal === "buy" ? livePrice > chase : livePrice < chase;
}

export function OrderTicket({ ai, livePrice, onExecute, demoBalance }) {
  const { t } = useI18n();
  const now = useNow();
  const [placing, setPlacing] = useState(false);
  const [choice, setChoice] = useState(false);   // execution mode chooser
  const [modalMode, setModalMode] = useState(null);  // 'demo' | 'real' -> opens confirm modal
  const [result, setResult] = useState(null);
  const tk = ai.order_ticket || {};
  const isBuy = ai.signal === "buy";
  const ageSec = ai.generated_at ? Math.max(0, Math.round((now - ai.generated_at) / 1000)) : null;
  const expired = signalExpired(ai, livePrice);
  const isCrypto = /USDT/i.test(ai.symbol || "");

  const Row = ({ label, children, tone }) => (
    <div className="flex items-center justify-between py-1.5 text-[13px] border-b border-ink-600/60 last:border-0">
      <span className="text-mist-500">{label}</span>
      <span className={`tnum font-medium ${tone || "text-mist-100"}`}>{children}</span>
    </div>
  );

  return (
    <div className={`rounded-xl border p-3.5 ${expired ? "border-down/40 bg-down/5" : "border-ink-500 bg-ink-800"}`}>
      {/* header: side + mode chips + freshness */}
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold ${isBuy ? "text-up" : "text-down"}`}>
            {isBuy ? `▲ ${t("open_long")}` : `▼ ${t("open_short")}`}
          </span>
          {tk.margin_mode && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-ink-600 text-mist-300">{t("isolated")}</span>
          )}
          {tk.leverage && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gold/15 text-gold-soft tnum">{tk.leverage}x</span>
          )}
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${tk.order_type === "limit" ? "bg-info/15 text-info" : "bg-ink-600 text-mist-300"}`}>
            {tk.order_type === "limit" ? t("limit_order") : t("market_order")}
          </span>
        </div>
        {ageSec != null && (
          <span className={`text-[10px] tnum ${expired ? "text-down" : ageSec > 60 ? "text-gold-soft" : "text-mist-500"}`}>
            {expired ? `⛔ ${t("signal_expired")}` : `⏱ ${ageSec < 60 ? `${ageSec}s` : `${Math.round(ageSec / 60)}m`} ${t("signal_age")}`}
          </span>
        )}
      </div>

      {expired && (
        <p className="text-[11px] text-down bg-down/10 border border-down/30 rounded-lg px-2.5 py-1.5 mb-2">
          {t("signal_expired_hint")}
        </p>
      )}

      <Row label={tk.order_type === "limit" ? t("limit_price") : t("entry")}>
        {fmtPrice(tk.limit_price ?? ai.entry)}
      </Row>
      {tk.quantity != null && (
        <Row label={t("qty_coins")}>
          {tk.quantity} {tk.unit}
        </Row>
      )}
      {tk.position_value != null && <Row label={t("position_value")}>${tk.position_value}</Row>}
      {tk.margin != null && (
        <Row label={t("margin_needed")} tone={ai.position_size?.capped_by_available_margin ? "text-gold-soft" : undefined}>
          ${tk.margin}{ai.position_size?.capped_by_available_margin ? ` · ${t("capped_to_balance")}` : ""}
        </Row>
      )}
      <Row label={t("take_profit")} tone="text-up">{fmtPrice(ai.take_profit)}</Row>
      <Row label={t("stop_loss")} tone="text-down">{fmtPrice(ai.stop_loss)}</Row>
      {tk.est_liquidation != null && (
        <Row label={`${t("est_liquidation")} *`} tone="text-down">{fmtPrice(tk.est_liquidation)}</Row>
      )}

      {!choice ? (
        <button
          onClick={() => (isCrypto ? setChoice(true) : onExecute())}
          disabled={expired || placing}
          className={`mt-3 w-full py-2.5 rounded-lg text-sm font-bold text-white transition active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed ${
            isBuy ? "bg-up hover:brightness-110" : "bg-down hover:brightness-110"
          }`}
        >
          {placing ? "…" : expired ? t("signal_expired") : isBuy ? t("open_long") : t("open_short")}
        </button>
      ) : (
        <div className="mt-3 grid grid-cols-3 gap-2">
          <button onClick={() => { setChoice(false); setModalMode("demo"); }} disabled={placing}
            className="py-2 rounded-lg text-xs font-bold bg-up/15 text-up border border-up/30">
            {t("bx_demo")}
          </button>
          <button onClick={() => { setChoice(false); setModalMode("real"); }} disabled={placing}
            className="py-2 rounded-lg text-xs font-bold bg-down text-white">
            {t("bx_real")} ⚠️
          </button>
          <button onClick={() => { setChoice(false); onExecute(); }} disabled={placing}
            className="py-2 rounded-lg text-xs font-semibold bg-ink-600 text-mist-300">
            {t("bx_journal_only")}
          </button>
        </div>
      )}
      {result && (
        <p className={`text-[11px] mt-2 ${result.ok ? "text-up" : "text-down"}`}>
          {result.ok ? "✅" : "✗"} {result.detail}
        </p>
      )}

      {modalMode && (
        <TradeConfirmModal
          mode={modalMode}
          signal={ai}
          livePrice={livePrice}
          demoBalance={demoBalance}
          onClose={() => setModalMode(null)}
          onDone={(res) => {
            setModalMode(null);
            setResult({ ok: true, mode: modalMode, detail: res.mode === "demo"
              ? `${t("bx_demo_filled")} @ ${res.entryPrice}` : t("bx_order_ok") });
          }}
        />
      )}

      {tk.est_liquidation != null && (
        <p className="text-[10px] text-mist-500 mt-2">* {t("liq_estimate_note")}</p>
      )}
    </div>
  );
}
