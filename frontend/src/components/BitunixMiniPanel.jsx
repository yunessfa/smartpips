import { useEffect, useState } from "react";
import { Badge, Spinner } from "./ui.jsx";
import { bitunixApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";

/**
 * Compact Bitunix account panel embedded in the Scalp page — replaces the
 * old LBank tab. One demo/real switch (shared with the /bitunix page via
 * localStorage) showing the real futures balance and open positions with a
 * close action. Full management lives at /bitunix.
 */
const fmt = (n, d = 4) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d });

export function BitunixMiniPanel({ refreshKey, demoBalance }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(() => localStorage.getItem("bx_mode") || "demo");
  const [status, setStatus] = useState(null);
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  function switchMode(m) {
    setMode(m); localStorage.setItem("bx_mode", m);
    window.dispatchEvent(new Event("bx-mode-changed"));
  }

  async function load(m = mode) {
    setErr(null);
    try {
      const st = await bitunixApi.status(); setStatus(st);
      const jobs = [bitunixApi.positions(m).then(setPositions).catch(() => setPositions(null))];
      if (st.connected) jobs.push(bitunixApi.account().then(setAccount).catch(() => setAccount(null)));
      await Promise.all(jobs);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(mode); /* eslint-disable-next-line */ }, [mode, refreshKey]);
  // LIVE PnL: refresh positions every 5s so unrealized PnL moves like a real
  // terminal (demo PnL is computed server-side against the live price).
  useEffect(() => {
    const id = setInterval(() => {
      bitunixApi.positions(mode).then(setPositions).catch(() => {});
      if (mode === "real") bitunixApi.account().then(setAccount).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [mode]);

  async function closePos(p) {
    const isReal = mode === "real";
    if (isReal && !window.confirm(t("bx_close_confirm"))) return;
    // optimistic: drop it from the list immediately so closing feels instant,
    // then reconcile with the server.
    setPositions((prev) => prev ? { ...prev, positions:
      (prev.positions || []).filter((x) => (x.positionId || x.id) !== (p.positionId || p.id)) } : prev);
    try {
      await bitunixApi.closePosition({ mode, positionId: p.positionId || p.id,
        confirm: isReal ? true : undefined });
    } catch (e) { setErr(e.message); }
    finally { load(); }
  }

  if (loading) return <Spinner label="…" />;

  const acctRow = Array.isArray(account?.account) ? account.account[0] : account?.account;
  const rows = positions?.positions || [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center bg-ink-800 border border-ink-500 rounded-lg p-0.5">
          {["demo", "real"].map((m) => (
            <button key={m} onClick={() => switchMode(m)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition ${
                mode === m
                  ? m === "real" ? "bg-down text-white" : "bg-up text-white"
                  : "text-mist-500"}`}>
              {m === "demo" ? t("bx_demo") : t("bx_real")}
            </button>
          ))}
        </div>
        {status?.connected
          ? <Badge tone="up">● Bitunix</Badge>
          : <Badge tone="down">○ {t("bx_not_connected")}</Badge>}
      </div>

      {mode === "real" && (
        <p className="text-[11px] text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-2.5 py-1.5">
          ⚠️ {t("bx_real_warning")}
        </p>)}
      {err && <p className="text-down text-xs">{err}</p>}

      {mode === "demo" ? (
        /* demo runs on the USER's top balance — never the real wallet */
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
            <p className="text-[11px] text-mist-500">{t("bx_demo_balance")}</p>
            <p className="tnum text-sm text-mist-100">{fmt(demoBalance, 2)} USDT</p>
          </div>
          <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
            <p className="text-[11px] text-mist-500">{t("bx_free_margin")}</p>
            <p className="tnum text-sm text-mist-100">
              {demoBalance != null ? fmt(demoBalance - (positions?.marginUsed || 0), 2) : "—"}
            </p>
          </div>
          <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
            <p className="text-[11px] text-mist-500">PnL {t("bx_live")}</p>
            <p className={`tnum text-sm ${Number(positions?.unrealizedPNL) >= 0 ? "text-up" : "text-down"}`}>
              {fmt(positions?.unrealizedPNL, 2)}
            </p>
          </div>
        </div>
      ) : status?.connected && acctRow && (
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
            <p className="text-[11px] text-mist-500">{t("bx_available")}</p>
            <p className="tnum text-sm text-mist-100">{fmt(acctRow.available, 2)} USDT</p>
          </div>
          <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
            <p className="text-[11px] text-mist-500">PnL {t("bx_live")}</p>
            <p className={`tnum text-sm ${Number(acctRow.crossUnrealizedPNL) >= 0 ? "text-up" : "text-down"}`}>
              {fmt(acctRow.crossUnrealizedPNL, 2)}
            </p>
          </div>
        </div>
      )}

      {rows.length ? (
        <div className="space-y-2">
          {rows.map((p) => {
            const side = (p.side || "").toUpperCase().includes("BUY") ||
              (p.side || "").toUpperCase() === "LONG" ? "LONG" : "SHORT";
            const pnl = p.unrealizedPNL ?? p.unrealizedPnl;
            const cell = "bg-ink-900/60 rounded-md px-2 py-1.5";
            const lab = "block text-[10px] text-mist-500 mb-0.5";
            const val = "tnum text-[12px] text-mist-100";
            return (
              <div key={p.positionId || p.id}
                className="bg-ink-800 border border-ink-500 rounded-lg p-2.5">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-mist-100">{p.symbol}</span>
                    <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${
                      side === "LONG" ? "bg-up/15 text-up" : "bg-down/15 text-down"}`}>
                      {side}{p.leverage ? ` · ${p.leverage}x` : ""}
                    </span>
                  </div>
                  <button onClick={() => closePos(p)}
                    className="text-[11px] px-2.5 py-1 rounded bg-down/15 text-down border border-down/30">
                    {t("bx_close")}
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  <div className={cell}>
                    <span className={lab}>{t("qty_coins")}</span>
                    <span className={val}>{fmt(p.qty)}</span>
                  </div>
                  <div className={cell}>
                    <span className={lab}>{t("entry")}</span>
                    <span className={val}>{fmtPrice(p.entryPrice ?? p.avgOpenPrice)}</span>
                  </div>
                  <div className={cell}>
                    <span className={lab}>{t("bx_mark")}</span>
                    <span className={val}>{fmtPrice(p.markPrice)}</span>
                  </div>
                  <div className={cell}>
                    <span className={lab}>{t("margin_needed")}</span>
                    <span className={val}>{fmt(p.margin, 2)}</span>
                  </div>
                  <div className={cell}>
                    <span className={lab}>{t("est_liquidation")}</span>
                    <span className={`${val} text-down/90`}>{fmtPrice(p.liqPrice ?? p.liquidationPrice)}</span>
                  </div>
                  <div className={cell}>
                    <span className={lab}>PnL {t("bx_live")}</span>
                    <span className={`${val} font-semibold ${Number(pnl) >= 0 ? "text-up" : "text-down"}`}>
                      {Number(pnl) >= 0 ? "+" : ""}{fmt(pnl, 2)}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-mist-500">{t("bx_no_positions")}</p>
      )}

      <a href="/bitunix" className="inline-block text-[11px] text-gold-soft hover:underline">
        {t("bx_full_panel")} ←
      </a>
    </div>
  );
}
