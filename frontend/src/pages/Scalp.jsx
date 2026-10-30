import { DecisionAudit } from "../components/DecisionAudit.jsx";
import MarketBrief from "../components/MarketBrief.jsx";
import { fill } from "../lib/fill.jsx";
import { BacktestReasons } from "../components/BacktestReasons.jsx";
import BacktestEvidence, { Cell as EvidenceCell } from "../components/BacktestEvidence.jsx";
import { BT_PERIODS, barsFor } from "../lib/backtestPeriods.js";
import { useChartHeight } from "../lib/chartSize.js";
import { useMemo, useState, useEffect, useRef } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Button } from "../components/ui.jsx";
import { SignalChart } from "../components/TradingView.jsx";
import { EconomicNewsPanel } from "../components/EconomicNewsPanel.jsx";
import { PositionChart } from "../components/PositionChart.jsx";

// The chart is deliberately indicator-free: price action only. Module-level
// const because a new array on every render would change the widget config
// identity and tear down / rebuild the iframe on every tick.
const NO_STUDIES = [];

import { LogTradeModal } from "../components/TradeModal.jsx";
import { TradingAccountPanel } from "../components/TradingAccountPanel.jsx";
import { OrderBook } from "../components/OrderBook.jsx";
import { OrderTicket, signalExpired } from "../components/OrderTicket.jsx";
import { scalpApi, tradesApi, strategyApi, alertsApi, mt5Api, marketApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { useMetalTick } from "../live/useMetalTick.js";
import { CRYPTO_BASE } from "../lib/symbols.js";
import { fmtPrice, parsePrice } from "../lib/num.js";
import { createRequestGate } from "../lib/requestGate.js";
import { pushSupported, isIOS, isStandalone, enablePush, disablePush } from "../live/push.js";

// Same ~50 liquid coins the backend supports (apps/market/crypto_symbols.py) —
// kept in sync manually since frontend/backend are separate codebases here.
// crypto universe moved to lib/symbols.js (shared with the Bitunix panel)

// Crypto futures first: they are the product's focus and the default symbol.
const METALS = [
  // crypto futures / perpetual (Bitunix execution venue) — the default group
  ...CRYPTO_BASE.map((b) => ({
    symbol: `${b}USDT:PERP`, tv: `BINANCE:${b}USDT.P`, label: `${b} futures`, group: "futures",
  })),
  // crypto spot
  ...CRYPTO_BASE.map((b) => ({
    symbol: `${b}USDT`, tv: `BINANCE:${b}USDT`, label: `${b} spot`, group: "spot",
  })),
  { symbol: "XAUUSD", tv: "TVC:GOLD", label: "XAU/USD", group: "metals" },
  { symbol: "XAGUSD", tv: "TVC:SILVER", label: "XAG/USD", group: "metals" },
];
const VALIDATED_TFS = ["5m", "15m", "1h"];

// label shown to user -> TradingView interval code
const TIMEFRAMES = [
  ["1m", "1"], ["5m", "5"], ["15m", "15"], ["1h", "60"], ["4h", "240"],
];

const GROUP_KEY = { metals: "metals", spot: "spot", futures: "futures" };

// ---------------------------------------------------------------------------
// STICKY OPEN-TRADES BAR
// Requirement: while a trade is open it must ALWAYS be visible on a phone,
// pinned to the bottom, and it must not get pushed off screen.
//
// Positioning: `.trades-bar-offset` (index.css) = calc(3.5rem + safe-area
// inset), so it clears the mobile tab bar in Layout.jsx INCLUDING the iOS
// home-indicator inset that `.tabbar-safe` adds. On md+ that nav is hidden,
// so the bar drops flush to bottom-0.
//
// Renders null when nothing is open, so it never steals space for nothing.
// ---------------------------------------------------------------------------
function OpenTradesBar({ symbol, price, refreshKey, onCount }) {
  const { t } = useI18n();
  const [trades, setTrades] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const rows = await tradesApi.list();
        // Same defensive unwrap the Trades page uses: the endpoint returns a
        // plain array today but may be paginated later.
        const list = (Array.isArray(rows) ? rows : rows?.results || [])
          .filter((r) => r.status === "open");
        if (alive) setTrades(list);
      } catch { /* keep showing the last known list */ }
    }
    load();
    // 20s: same cadence as the rest of the page.
    const id = setInterval(load, 20000);
    return () => { alive = false; clearInterval(id); };
  }, [refreshKey]);

  // Lets the page add bottom padding ONLY when the bar is actually showing.
  useEffect(() => { if (onCount) onCount(trades.length); }, [trades.length, onCount]);

  // ROI on margin = price move % x leverage. That identity is scale-free, so
  // it is correct for both metals and crypto without needing contract sizes
  // or the size-means-margin convention. Only computable for the symbol
  // currently on screen, because that is the only live price we hold.
  function roi(tr) {
    const entry = Number(tr.entry_price);
    const p = Number(price);
    if (!entry || !p || tr.symbol !== symbol) return null;
    const dir = tr.direction === "long" ? 1 : -1;
    return ((p - entry) / entry) * 100 * dir * (Number(tr.leverage) || 1);
  }

  const live = trades.map(roi).filter((v) => v !== null);
  // AVERAGE, not sum: adding the ROI percentages of differently sized
  // positions produces a number that means nothing.
  const avg = live.length ? live.reduce((a, b) => a + b, 0) / live.length : null;

  if (!trades.length) return null;

  const tone = (v) => (v > 0 ? "text-up" : v < 0 ? "text-down" : "text-mist-500");

  return (
    <div className="fixed inset-x-0 trades-bar-offset z-30 border-t border-ink-500 glass">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left"
        aria-expanded={open}
      >
        <span className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 rounded-full bg-gold/20 text-gold text-xs font-semibold tabular-nums">
          {trades.length}
        </span>
        <span className="text-sm font-medium">{t("sc_open_trades")}</span>
        <span className="flex-1 truncate text-xs text-mist-500">
          {trades.slice(0, 3).map((x) => x.symbol).join(" · ")}
          {trades.length > 3 ? " …" : ""}
        </span>
        {avg !== null && (
          <span className={`text-sm font-semibold tabular-nums ${tone(avg)}`}>
            {avg > 0 ? "+" : ""}{avg.toFixed(2)}%
          </span>
        )}
        <span className="text-mist-500 text-xs">{open ? "▾" : "▴"}</span>
      </button>

      {open && (
        <div className="max-h-52 overflow-y-auto border-t border-ink-500 divide-y divide-ink-600">
          {trades.map((tr) => {
            const r = roi(tr);
            return (
              <div key={tr.id} className="flex items-center gap-2 px-4 py-2 text-xs">
                <span className="font-medium">{tr.symbol}</span>
                <span className={tr.direction === "long" ? "text-up" : "text-down"}>
                  {tr.direction === "long" ? "▲" : "▼"}
                </span>
                <span className="text-mist-500">@ {fmtPrice(tr.entry_price)}</span>
                {Number(tr.leverage) > 1 && (
                  <span className="text-mist-500">×{tr.leverage}</span>
                )}
                <span className="flex-1" />
                {r === null ? (
                  // Dash, not 0%: we genuinely do not know this symbol's price
                  // right now, and showing 0% would read as break-even.
                  <span className="text-mist-500">—</span>
                ) : (
                  <span className={`font-semibold tabular-nums ${tone(r)}`}>
                    {r > 0 ? "+" : ""}{r.toFixed(2)}%
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Scalp() {
  const { t, isRTL } = useI18n();

  // If we arrived from a push notification (?symbol=..&tf=..&quick=1), jump
  // straight to that symbol/timeframe and skip the tick-warmup wait — the
  // engine already works from candles, not the live tick buffer.
  const urlParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const quickSymbol = urlParams.get("symbol");
  const quickTf = urlParams.get("tf");
  const isQuick = urlParams.get("quick") === "1";

  const [metal, setMetal] = useState(() => {
    if (quickSymbol) {
      const found = METALS.find((m) => m.symbol === quickSymbol.toUpperCase());
      if (found) return found;
    }
    try {
      const saved = METALS.find((m) => m.symbol === localStorage.getItem("sp_symbol"));
      if (saved) return saved;
    } catch { /* ignore */ }
    return METALS[0];
  });
  const [tf, setTf] = useState(() => {
    if (quickTf) {
      const found = TIMEFRAMES.find((t) => t[0] === quickTf);
      if (found) return found;
    }
    try {
      const saved = TIMEFRAMES.find((x) => x[0] === localStorage.getItem("sp_tf"));
      if (saved) return saved;
    } catch { /* ignore */ }
    return TIMEFRAMES[2]; // 15m: validated and fast enough to scalp
  });
  const { price, series, status } = useMetalTick(metal.symbol, { intervalMs: 1000, history: 300 });
  const chartHeight = useChartHeight();


  const [ai, setAi] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(null);
  const [logging, setLogging] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  // bumped after every trade logged from this page so the embedded positions
  // panel reloads immediately instead of only on a manual page refresh.
  const [tradesVersion, setTradesVersion] = useState(0);
  // How many trades the sticky bar is showing (0 = bar hidden).
  const [openCount, setOpenCount] = useState(0);
  const [balance, setBalance] = useState(() => localStorage.getItem("sp_balance") || "");
  const [balanceSource, setBalanceSource] = useState("manual");
  const [bxMode, setBxMode] = useState(() => localStorage.getItem("bx_mode") || "demo");
  // per-user market access (admin-managed): {metals, spot, futures}
  const [marketAccess, setMarketAccess] = useState({ metals: true, spot: true, futures: true });
  useEffect(() => {
    import("../api/client.js").then(({ prefsApi }) =>
      prefsApi.myAccess().then(setMarketAccess).catch(() => {}));
  }, []);
  const allowedMetals = METALS.filter((m) => marketAccess[GROUP_KEY[m.group]] !== false);
  useEffect(() => {
    if (marketAccess[GROUP_KEY[metal.group]] === false && allowedMetals.length) {
      switchMetal(allowedMetals[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketAccess]);
  // MODE-AWARE balance:
  //   real -> sizing runs on the account's actual available USDT from Bitunix;
  //   demo -> sizing runs on the number the USER typed (sp_balance_manual),
  //           never the real wallet.
  useEffect(() => {
    const onMode = () => setBxMode(localStorage.getItem("bx_mode") || "demo");
    window.addEventListener("bx-mode-changed", onMode);
    return () => window.removeEventListener("bx-mode-changed", onMode);
  }, []);
  useEffect(() => {
    let alive = true;
    if (bxMode !== "real") {
      const manual = localStorage.getItem("sp_balance_manual")
        ?? localStorage.getItem("sp_balance") ?? "";
      setBalance(manual);
      setBalanceSource("manual");
      return;
    }
    (async () => {
      try {
        const { bitunixApi } = await import("../api/client.js");
        const st = await bitunixApi.status();
        if (!st.connected || !alive) return;
        const acct = await bitunixApi.account();
        const row = Array.isArray(acct?.account) ? acct.account[0] : acct?.account;
        const avail = Number(row?.available);
        if (alive && Number.isFinite(avail) && avail > 0) {
          setBalance(String(avail));
          setBalanceSource("bitunix");
        }
      } catch { /* stay manual */ }
    })();
    return () => { alive = false; };
  }, [bxMode]);
  const [riskPct, setRiskPct] = useState(() => localStorage.getItem("sp_risk") || "1");
  // Default = the validated trend-pullback playbook. One-time migration: the
  // legacy score engine showed no edge in the 2019-2026 study, so earlier
  // "safe" defaults move to "trend" once; an explicit later choice is kept.
  const [scalpMode, setScalpMode] = useState(() => {
    try {
      if (localStorage.getItem("sp_mode_v2") !== "1") {
        localStorage.setItem("sp_mode_v2", "1");
        localStorage.setItem("sp_mode", "trend");
        return "trend";
      }
      return localStorage.getItem("sp_mode") || "trend";
    } catch { return "trend"; }
  });

  function switchMode(m) { setScalpMode(m); localStorage.setItem("sp_mode", m); }

  function saveRisk(b, r) {
    setBalance(b); setRiskPct(r); setBalanceSource("manual");
    localStorage.setItem("sp_balance", b);
    localStorage.setItem("sp_balance_manual", b);
    localStorage.setItem("sp_risk", r);
  }

  const signalGate = useRef(null);
  if (!signalGate.current) signalGate.current = createRequestGate();
  const snapshot = useRef(null);
  snapshot.current = { symbol: metal.symbol, price, timeframe: tf[0], series,
    balance, riskPct, mode: scalpMode };
  useEffect(() => {
    signalGate.current.invalidate();
    setAi(null); setAiError(null); setAiLoading(false);
  }, [metal.symbol, tf[0], scalpMode, balance, riskPct]);
  useEffect(() => {
    const invalidate = () => { signalGate.current.invalidate(); setAi(null); setAiLoading(false); };
    const onStorage = (e) => { if (e.key === "smartpips-strategy-changed") invalidate(); };
    window.addEventListener("smartpips-strategy-changed", invalidate);
    window.addEventListener("storage", onStorage);
    return () => { signalGate.current.invalidate();
      window.removeEventListener("smartpips-strategy-changed", invalidate);
      window.removeEventListener("storage", onStorage); };
  }, []);

  // Same closed candle + same facts = same answer. Mark it instead of
  // presenting a repeated reading as a fresh analysis.
  const lastPrint = useRef(null);
  const [unchanged, setUnchanged] = useState(false);
  function acceptDecision(res) {
    const fp = res?.brief?.fingerprint || null;
    setUnchanged(Boolean(fp && lastPrint.current === fp));
    lastPrint.current = fp;
    setAi(res);
  }

  async function getAiSignal(explain = true) {
    const snap = snapshot.current;
    if (!snap.price) return;
    const seq = signalGate.current.begin();
    if (seq === null) return;
    if (explain) { setAiLoading(true); setAiError(null); }
    try {
      // Publish the fast deterministic analysis before waiting for optional AI
      // prose. Automatic polling stays out while this request is in flight.
      const fetchSignal = () => scalpApi.signal(snap.symbol, snap.price, snap.timeframe, snap.series,
        snap.balance ? Number(snap.balance) : undefined,
        snap.riskPct ? Number(snap.riskPct) : undefined, snap.mode, false, explain);
      const res = await fetchSignal();
      if (signalGate.current.current(seq)) { acceptDecision(res); setAiError(null); }
      if (explain && signalGate.current.current(seq) && res.explanation_token) {
        const extra = await scalpApi.explain(res.explanation_token);
        if (signalGate.current.current(seq) && extra.decision_id === res.decision_id) {
          setAi({ ...res, ...extra });
        }
      }
    } catch (e) { if (signalGate.current.current(seq)) setAiError(e.message); }
    finally {
      if (signalGate.current.current(seq)) setAiLoading(false);
      signalGate.current.finish(seq);
    }
  }
  const [autoRefresh, setAutoRefresh] = useState(() => localStorage.getItem("sp_auto") === "1");
  function toggleAuto() {
    const v = !autoRefresh; setAutoRefresh(v);
    localStorage.setItem("sp_auto", v ? "1" : "0");
  }
  useEffect(() => {
    if (!autoRefresh) return;
    let running = false;
    const id = setInterval(async () => {
      if (running || document.hidden || !snapshot.current?.price) return;
      running = true;
      try { await getAiSignal(false); } finally { running = false; }
    }, 20000);
    return () => clearInterval(id);
  }, [autoRefresh]);

  // QUICK PATH (from a push notification tap): the engine works off candles,
  // not the live tick buffer, so we don't need to wait for 30 ticks — just get
  // one fresh price from the backend and ask for the signal immediately.
  async function getAiSignalQuick() {
    const seq = signalGate.current.begin();
    if (seq === null) return;
    const snap = snapshot.current;
    setAiLoading(true); setAiError(null);
    try {
      const p = await marketApi.metal(snap.symbol);
      const px = p && p.ok ? p.price : snap.price;
      if (!px) throw new Error(t("metal_unavailable"));
      const res = await scalpApi.signal(snap.symbol, px, snap.timeframe, [],
        snap.balance ? Number(snap.balance) : undefined, snap.riskPct ? Number(snap.riskPct) : undefined,
        snap.mode, false);
      if (signalGate.current.current(seq)) acceptDecision(res);
    } catch (e) { if (signalGate.current.current(seq)) setAiError(e.message); }
    finally {
      if (signalGate.current.current(seq)) setAiLoading(false);
      signalGate.current.finish(seq);
    }
  }

  // fire the quick path once, right after landing from a notification
  const [quickTried, setQuickTried] = useState(false);
  useEffect(() => {
    if (isQuick && !quickTried) {
      setQuickTried(true);
      getAiSignalQuick();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isQuick]);

  const [quickLogging, setQuickLogging] = useState(false);
  const [quickLogged, setQuickLogged] = useState(false);

  // ONE-TAP LOG: used from the notification quick-path — skips the modal and
  // logs the trade immediately with the engine's suggested size/entry/SL/TP,
  // since balance & risk are already saved.
  async function quickLogTrade() {
    if (!tradeInitial) return;
    setQuickLogging(true);
    try {
      await tradesApi.create({
        symbol: tradeInitial.symbol,
        tradingview_symbol: tradeInitial.tradingview_symbol,
        direction: tradeInitial.direction,
        entry_price: tradeInitial.entry_price,
        take_profit: tradeInitial.take_profit,
        stop_loss: tradeInitial.stop_loss,
        tp1_price: tradeInitial.tp_levels?.[0]?.price,
        tp1_pct: tradeInitial.tp_levels?.[0]?.pct,
        tp2_price: tradeInitial.tp_levels?.[1]?.price,
        tp2_pct: tradeInitial.tp_levels?.[1]?.pct,
        tp3_price: tradeInitial.tp_levels?.[2]?.price,
        tp3_pct: tradeInitial.tp_levels?.[2]?.pct,
        size: tradeInitial.size || 0,
        leverage: tradeInitial.leverage || 1,
        source: tradeInitial.source,
        setup_class: tradeInitial.setup_class,
        strategy: tradeInitial.strategy,
        entry_strategy_version: tradeInitial.strategy_version,
        timeframe: tradeInitial.timeframe,
        confidence: tradeInitial.confidence,
        decision_token: tradeInitial.decision_token,
        notes: "",
        balance: balance ? Number(balance) : undefined,
      });
      setQuickLogged(true);
      setTradesVersion((v) => v + 1);
    } catch (e) { setAiError(e.message); }
    finally { setQuickLogging(false); }
  }

  function switchMetal(m) {
    setMetal(m); setAi(null); setAiError(null); setQuickLogged(false); lastPrint.current = null;
    try { localStorage.setItem("sp_symbol", m.symbol); } catch { /* ignore */ }
  }
  function switchTf(f) {
    setTf(f); lastPrint.current = null;
    try { localStorage.setItem("sp_tf", f[0]); } catch { /* ignore */ }
  }



  const tradeInitial = ai && {
    symbol: metal.symbol,
    tradingview_symbol: metal.tv,
    direction: ai.signal === "sell" ? "short" : "long",
    entry_price: parsePrice(ai.entry ?? price),
    take_profit: parsePrice(ai.take_profit),
    stop_loss: parsePrice(ai.stop_loss),
    tp_levels: ai.tp_levels || null,
    // prefill the sizing the engine suggested (coin qty/lots, leverage, margin)
    size: ai.position_size?.mode === "crypto"
      ? ai.position_size?.margin
      : ai.position_size?.lots,
    quantity: ai.position_size?.quantity,
    position_value: ai.position_size?.position_value,
    leverage: ai.leverage?.leverage || 1,
    mode: ai.position_size?.mode,
    unit: ai.position_size?.unit,
    setup_class: ai.setup_class?.class || "",
    source: "scalp",
    strategy: ai.strategy_id || undefined,
    strategy_version: ai.strategy_version || undefined,
    timeframe: tf[0],
    confidence: ai.score ?? undefined,
    decision_token: ai.decision_token || undefined,
  };

  return (
    <>
      <PageHeader
        title={t("scalp_title")}
        subtitle={t("scalp_sub")}
        right={<SymbolPicker current={metal} onPick={switchMetal} access={marketAccess} />}
      />

      <div className={`flex-1 overflow-y-auto min-h-0 p-4 md:p-6 space-y-4 ${
        openCount ? "pb-28 md:pb-24" : ""}`}>
        {/* ---------------------------------------------------- controls */}
        <section className="rounded-2xl border border-ink-500 bg-ink-700/70 p-3 md:p-4 shadow-panel space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-xs text-mist-500">
                <span className={`h-1.5 w-1.5 rounded-full ${status === "live" ? "bg-up live-dot" : "bg-mist-500"}`} />
                {metal.label}
              </p>
              {price ? (
                <p className="tnum text-2xl md:text-3xl font-bold text-mist-100" dir="ltr">${fmtPrice(price)}</p>
              ) : (
                <p className="text-sm text-mist-500 mt-1">
                  {status === "unavailable" ? t("metal_unavailable") : t("waiting_ticks")}
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg bg-ink-800 p-0.5" role="group" aria-label={t("timeframe")}>
                {TIMEFRAMES.map((f) => {
                  const ok = scalpMode !== "trend" || VALIDATED_TFS.includes(f[0]);
                  return (
                    <button key={f[0]} onClick={() => switchTf(f)}
                      title={ok ? undefined : t("pb_tf_hint")}
                      className={`px-2.5 py-1.5 rounded-md text-xs font-semibold transition ${
                        f[0] === tf[0] ? "bg-gold text-ink-900" : ok ? "text-mist-300 hover:bg-ink-600" : "text-mist-600 hover:bg-ink-600"
                      }`}>{f[0]}</button>
                  );
                })}
              </div>
              <div className="flex items-center gap-1 rounded-lg bg-ink-800 p-0.5" role="group" aria-label={t("mode_label")}>
                {[["trend", `✓ ${t("mode_trend")}`], ["safe", t("mode_safe_legacy")], ["aggressive", t("mode_aggressive_legacy")]].map(([m, label]) => (
                  <button key={m} onClick={() => switchMode(m)} title={m === "trend" ? t("mode_trend_hint") : t("mode_legacy_hint")}
                    className={`text-xs px-2.5 py-1.5 rounded-md ${scalpMode === m
                      ? (m === "trend" ? "bg-up/20 text-up" : "bg-ink-600 text-mist-100")
                      : "text-mist-500 hover:text-mist-300"}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button className="min-h-11 flex-1 sm:flex-none sm:min-w-[12rem]" onClick={() => getAiSignal(true)} disabled={!price || aiLoading}>
              {aiLoading ? t("thinking") : t("sc_analyze")}
            </Button>
            <button onClick={toggleAuto} title={t("auto_refresh")}
              className={`min-h-11 text-xs px-3 rounded-lg border transition ${
                autoRefresh ? "bg-up/15 text-up border-up/30" : "bg-ink-800 text-mist-500 border-ink-500 hover:text-mist-300"
              }`}>
              {autoRefresh ? `● ${t("auto_on")}` : `○ ${t("auto_off")}`}
            </button>
            <div className="ms-auto"><RiskBar balance={balance} riskPct={riskPct} onSave={saveRisk} source={balanceSource} /></div>
          </div>
          {scalpMode === "trend" && !VALIDATED_TFS.includes(tf[0]) && (
            <p className="text-xs text-gold-soft">{t("pb_tf_hint")}</p>
          )}
          {scalpMode !== "trend" && <p className="text-xs text-gold-soft">{t("mode_legacy_warning")}</p>}
        </section>

        {aiError && (
          <div className="text-down text-sm bg-down/10 border border-down/30 rounded-lg px-3 py-2">{aiError}</div>
        )}
        {!ai && !aiLoading && !aiError && (
          <p className="rounded-2xl border border-dashed border-ink-500 px-4 py-6 text-center text-sm text-mist-500">
            {t("sc_empty_hint")}
          </p>
        )}

        {/* ---------------------------------------------------- decision */}
        {ai && (
          <section className="space-y-3">
            <MarketBrief ai={ai} unchanged={unchanged} />
            {ai.strategy_name && (
              <p className="text-xs text-mist-500">
                {t("sc_active_strategy")}: <span className="text-mist-300">{ai.strategy_name} · v{ai.strategy_version}</span>
                {ai.strategy_note && <span className="text-gold-soft"> — {ai.strategy_note}</span>}
              </p>
            )}
            {ai.signal !== "wait" && (
              <Panel title={t("sc_trade_plan")}>
                {ai.signal_source === "playbook" && <PlaybookCard ai={ai} timeframe={tf[0]} />}
                {!ai.order_ticket && (
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    <Level label={t("entry")} value={ai.entry} tone="info" />
                    <Level label={t("take_profit")} value={ai.take_profit} tone="up" />
                    <Level label={t("stop_loss")} value={ai.stop_loss} tone="down" />
                  </div>
                )}
                {ai.order_ticket && (
                  <div className="mt-4">
                    <OrderTicket ai={{ ...ai, timeframe: tf[0] }} livePrice={price} demoBalance={balance ? Number(balance) : undefined} onExecute={() => setLogging(true)} />
                  </div>
                )}
                <ExecuteOrder
                  symbol={metal.symbol}
                  action={ai.signal}
                  sl={parsePrice(ai.stop_loss)}
                  tp={parsePrice(ai.take_profit)}
                  suggestedQty={ai.position_size?.mode === "lots" ? ai.position_size.lots : ai.position_size?.quantity}
                />
                {ai.position_size && <PositionSizeCard ps={ai.position_size} lev={ai.leverage} action={ai.signal} />}
                <div className="mt-3 flex items-center gap-2 flex-wrap">
                  <Button onClick={() => setLogging(true)}>{t("log_this")}</Button>
                  {isQuick && !quickLogged && (
                    <Button variant="primary" onClick={quickLogTrade} disabled={quickLogging}>
                      {quickLogging ? t("thinking") : `⚡ ${t("quick_log")}`}
                    </Button>
                  )}
                  {quickLogged && <span className="text-up text-sm">✓ {t("trade_logged")}</span>}
                </div>
              </Panel>
            )}
            {ai.ai_explanation && (
              <div className="rounded-xl border border-ink-500 bg-ink-800/60 px-4 py-3 text-sm leading-relaxed text-mist-200 whitespace-pre-line">
                <p className="mb-1 text-xs text-mist-500">{t("sc_ai_commentary")}</p>
                {ai.ai_explanation}
              </div>
            )}
            <details className="sp-disclosure">
              <summary>{t("sc_technical_details")}</summary>
              <div className="space-y-3 pt-2">
                {ai.explanation && <p className="text-xs text-mist-300 leading-relaxed whitespace-pre-line">{ai.explanation}</p>}
                <LegacyReadings ai={ai} />
                <DecisionAudit decision={ai} />
              </div>
            </details>
          </section>
        )}

        {/* ---------------------------------------------------- chart */}
        <Panel title={`${t("analysis_chart_title")} · ${metal.label} · ${tf[0]}`}>
          <PositionChart symbol={metal.symbol} analysisMode analysis={ai} analysisTimeframe={tf[0]}
            showSymbolPicker={false} storageKey="pc_tf_scalp" />
        </Panel>

        {/* ---------------------------------------------------- secondary */}
        <Collapse title={`💼 ${t("sc_account_section")}`} defaultOpen>
          <TradingAccountPanel balance={balance} defaultInitial={tradeInitial} refreshKey={tradesVersion} />
        </Collapse>
        <Collapse title={`📈 ${t("sc_tradingview")}`} lazy>
          <SignalChart symbol={metal.tv} interval={tf[1]} height={chartHeight} studies={NO_STUDIES} hideVolume />
        </Collapse>
        <Collapse title={`📚 ${t("sc_market_context")}`}>
          <div className="grid gap-4 lg:grid-cols-2">
            {metal.group !== "metals" && <OrderBook symbol={metal.symbol} lastPrice={price} />}
            <EconomicNewsPanel symbol={metal.symbol} />
          </div>
        </Collapse>
        <Collapse title={`📊 ${t("sc_backtest_section")}`}>
          <BacktestPanel symbol={metal.symbol} timeframe={tf[0]} series={series} mode={scalpMode} />
        </Collapse>
        <Collapse title={`🔔 ${t("sc_watchlist_alerts")}`}>
          <div className="space-y-4">
            <AlertsToggle />
            <WatchlistPanel current={metal} />
          </div>
        </Collapse>
      </div>

      <OpenTradesBar
        symbol={metal.symbol}
        price={price}
        refreshKey={tradesVersion}
        onCount={setOpenCount}
      />

      {logging && tradeInitial && (
        <LogTradeModal
          initial={tradeInitial}
          onClose={() => setLogging(false)}
          onSaved={async (payload) => { await tradesApi.create({ ...payload, strategy: tradeInitial?.strategy, entry_strategy_version: tradeInitial?.strategy_version, timeframe: tradeInitial?.timeframe, confidence: tradeInitial?.confidence, decision_token: tradeInitial?.decision_token, balance: balance ? Number(balance) : undefined }); setTradesVersion((v) => v + 1); }}
        />
      )}
    </>
  );
}

/** Old score-engine readings, kept for transparency inside "technical
 *  details" and labelled: the 2026-10 study found no measurable edge in them. */
function LegacyReadings({ ai }) {
  const { t } = useI18n();
  const bd = ai.score_breakdown;
  const pros = ai.reasons_plain?.pros || [];
  const cons = ai.reasons_plain?.cons || [];
  if (!bd && !pros.length && !cons.length) return null;
  return (
    <div className="rounded-lg border border-ink-500 p-3 text-xs">
      <p className="mb-2 text-mist-500">{t("sc_legacy_readings")}</p>
      {typeof ai.score === "number" && (
        <p className="mb-2 text-mist-300">{fill(t("sc_legacy_score"), { score: `${ai.score}/100`, conv: `${ai.conviction ?? "—"}%` })}</p>
      )}
      {bd && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(bd).map(([k, v]) => (
            <span key={k} className={`px-2 py-0.5 rounded-md border ${
              v > 0 ? "border-up/30 text-up" : v < 0 ? "border-down/30 text-down" : "border-ink-500 text-mist-500"
            }`}>{t(`bd_${k}`)} <bdi dir="ltr">{v > 0 ? `+${v}` : v}</bdi></span>
          ))}
        </div>
      )}
      {(pros.length > 0 || cons.length > 0) && (
        <ul className="mt-2 space-y-0.5 text-mist-400">
          {pros.map((k) => <li key={k}>+ {t(`r_${k}`)}</li>)}
          {cons.map((k) => <li key={k}>− {t(`r_${k}`)}</li>)}
        </ul>
      )}
    </div>
  );
}

function PositionSizeCard({ ps, lev, action }) {
  const { t } = useI18n();
  const verb = action === "buy" ? t("buy_signal") : t("sell_signal");

  if (ps.mode === "crypto") {
    return (
      <div className="mt-3 bg-gold/10 border border-gold/30 rounded-lg px-3 py-2.5">
        <div className="flex items-center gap-2 text-sm flex-wrap">
          <span className="text-gold-soft">📊</span>
          <span className="text-mist-100 font-semibold">
            {verb} {ps.quantity} {ps.unit}
          </span>
          {lev && (
            <span className="text-mist-200 border-s border-ink-500 ps-2">
              ⚡ {ps.leverage}x <span className="text-mist-500 text-xs">({t("leverage_safe")})</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-mist-500 mt-1.5 flex-wrap">
          <span>{t("position_value")}: <span className="text-mist-300 tnum">${ps.position_value}</span></span>
          <span>{t("margin_needed")}: <span className="text-mist-300 tnum">${ps.margin}</span></span>
          <span>{t("risk_amount")}: <span className="text-mist-300 tnum">${ps.risk_dollars}</span> ({ps.risk_pct}%)</span>
        </div>
        {ps.capped_by_available_margin && (
          <p className="text-[11px] text-gold-soft mt-1.5">⚠️ {t("size_capped_margin")}</p>
        )}
      </div>
    );
  }

  // metals: lots
  return (
    <div className="mt-3 flex items-center gap-2 text-sm bg-gold/10 border border-gold/30 rounded-lg px-3 py-2 flex-wrap">
      <span className="text-gold-soft">📊</span>
      <span className="text-mist-200">
        {t("suggested_size")}: <span className="font-semibold tnum">{ps.lots}</span> {t("lots")}
        <span className="text-mist-500 text-xs"> · {t("risk_amount")}: ${ps.risk_dollars} ({ps.risk_pct}%)</span>
      </span>
      {lev && (
        <span className="text-mist-200 border-s border-ink-500 ps-2">
          ⚡ {t("leverage")}: <span className="font-semibold">{lev.leverage}x</span>
          <span className="text-mist-500 text-xs"> ({t("leverage_safe")})</span>
        </span>
      )}
    </div>
  );
}

function WatchlistPanel({ current }) {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setItems(await alertsApi.watchlist()); } catch { /* ignore */ }
  }
  useEffect(() => { load(); }, []);

  const watched = items.some((i) => i.symbol === current.symbol);

  async function toggle() {
    setBusy(true);
    try {
      if (watched) await alertsApi.watchRemove(current.symbol);
      else await alertsApi.watchAdd(current.symbol, 68);
      await load();
    } catch { /* ignore */ } finally { setBusy(false); }
  }

  async function remove(sym) {
    try { await alertsApi.watchRemove(sym); await load(); } catch { /* ignore */ }
  }

  return (
    <Panel
      title={t("watchlist_title")}
      action={
        <Button variant={watched ? "ghost" : "primary"} onClick={toggle} disabled={busy}>
          {watched ? t("watch_remove") : `👁 ${t("watch_add")} ${current.label}`}
        </Button>
      }
    >
      <p className="text-xs text-mist-500 mb-3">{t("watchlist_hint")}</p>
      {items.length === 0 ? (
        <p className="text-sm text-mist-500">{t("watchlist_empty")}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {items.map((i) => (
            <span key={i.symbol} className="flex items-center gap-2 bg-ink-800 border border-ink-500 rounded-lg px-3 py-1.5 text-sm">
              <span className="text-up">👁</span>
              <span className="text-mist-200">{i.symbol}</span>
              <span className="text-mist-600 text-xs">≥{i.min_score}</span>
              <button onClick={() => remove(i.symbol)} className="text-mist-500 hover:text-down ms-1">✕</button>
            </span>
          ))}
        </div>
      )}
    </Panel>
  );
}

// `lazy`: children mount only once the section is opened (and stay mounted).
// Third-party widgets such as TradingView measure their container when they
// load; inside a closed <details> that width is 0 and the chart stays broken.
function Collapse({ title, children, defaultOpen = false, lazy = false }) {
  const [opened, setOpened] = useState(defaultOpen);
  return (
    <details open={defaultOpen} onToggle={(e) => { if (e.currentTarget.open) setOpened(true); }}
      className="group bg-ink-700/60 border border-ink-500 rounded-xl overflow-hidden">
      <summary className="cursor-pointer select-none list-none px-4 py-2.5 text-[13px] font-medium text-mist-300 hover:text-mist-100 flex items-center justify-between">
        {title}
        <span className="text-mist-500 transition group-open:rotate-180">▾</span>
      </summary>
      <div className="px-4 pb-4">{!lazy || opened ? children : null}</div>
    </details>
  );
}

function RiskBar({ balance, riskPct, onSave, source }) {
  const { t } = useI18n();
  const [b, setB] = useState(balance);
  const [r, setR] = useState(riskPct);
  const dirty = b !== balance || r !== riskPct;

  const riskAmount = b && r ? (Number(b) * Number(r) / 100) : null;

  return (
    <details className="sp-disclosure">
      <summary className="flex flex-wrap items-center justify-between gap-2">
        <span>{t("risk_panel_title")}</span>
        <span className="tnum text-gold-soft" dir="ltr">${Number(balance || 0).toLocaleString()} · {riskPct}%</span>
      </summary>
      <div>
      <p className="text-xs text-mist-500 mb-3">{t("risk_panel_hint")}</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-mist-400">{t("balance_label")}</span>
          {source === "bitunix" && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-up/15 text-up border border-up/25">
              ⚡ {t("bx_balance_live")}
            </span>
          )}
          <input type="number" inputMode="decimal" value={b} onChange={(e) => setB(e.target.value)}
            placeholder="1000"
            className="w-32 bg-ink-800 border border-ink-500 rounded-lg px-3 py-2 text-sm text-mist-100 focus:border-gold/50 outline-none" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-mist-400">{t("risk_pct_label")}</span>
          <select value={r} onChange={(e) => setR(e.target.value)}
            className="w-28 bg-ink-800 border border-ink-500 rounded-lg px-3 py-2 text-sm text-mist-100 focus:border-gold/50 outline-none">
            {["0.5", "1", "1.5", "2", "3", "5"].map((v) => <option key={v} value={v}>{v}%</option>)}
          </select>
        </label>
        {riskAmount != null && (
          <div className="text-sm text-mist-300 pb-2">
            {t("risk_amount")}: <span className="text-gold-soft font-semibold tnum">${riskAmount.toFixed(2)}</span>
          </div>
        )}
        <Button variant={dirty ? "primary" : "ghost"} onClick={() => onSave(b, r)} disabled={!dirty}>
          {t("save")}
        </Button>
      </div>
      </div>
    </details>
  );
}

function SymbolPicker({ current, onPick, access = {} }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [group, setGroup] = useState(current.group || "futures");
  const [query, setQuery] = useState("");
  // groups the admin disabled for this user simply don't exist here
  const groups = [
    ["futures", t("grp_futures")],
    ["spot", t("grp_spot")],
    ["metals", t("grp_metals")],
  ].filter(([g]) => access[g] !== false);
  useEffect(() => {
    if (access[group] === false && groups.length) setGroup(groups[0][0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [access]);
  const q = query.trim().toUpperCase();
  const symbols = METALS.filter((m) => m.group === group)
    .filter((m) => !q || m.symbol.toUpperCase().includes(q) || m.label.toUpperCase().includes(q));

  function pick(m) { onPick(m); setOpen(false); setQuery(""); }

  return (
    <div className="relative">
      <Button variant="ghost" className="whitespace-nowrap shrink-0" onClick={() => setOpen((v) => !v)}>
        {current.label} <span className="text-mist-500 ms-1">▾</span>
      </Button>

      {open && (
        <>
          {/* backdrop to close on outside click */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute end-0 mt-2 w-80 max-w-[90vw] bg-ink-800 border border-ink-500 rounded-xl shadow-panel z-50 overflow-hidden">
            <div className="p-2 border-b border-ink-600">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("search_symbol")}
                className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-sm text-mist-100 outline-none focus:border-gold/50"
              />
            </div>
            <div className="flex items-center gap-1 px-2 pt-2">
              {groups.map(([g, label]) => (
                <button key={g} onClick={() => setGroup(g)}
                  className={`text-xs px-2.5 py-1 rounded-md ${group === g ? "bg-ink-600 text-mist-100" : "text-mist-500 hover:text-mist-300"}`}>
                  {label}
                </button>
              ))}
            </div>
            <div className="max-h-72 overflow-y-auto p-2">
              {symbols.length === 0 ? (
                <p className="text-xs text-mist-500 text-center py-4">{t("no_results")}</p>
              ) : symbols.map((m) => (
                <button key={m.symbol} onClick={() => pick(m)}
                  className={`w-full flex items-center justify-between text-start px-3 py-2 rounded-lg text-sm transition ${
                    m.symbol === current.symbol ? "bg-gold/15 text-gold-soft" : "text-mist-200 hover:bg-ink-700"
                  }`}>
                  <span className="tnum font-medium">{m.symbol.replace(":PERP", "")}</span>
                  {m.group === "futures" && <span className="text-[10px] text-mist-500">PERP</span>}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ExecuteOrder({ symbol, action, sl, tp, suggestedQty }) {
  const { t } = useI18n();
  const isCrypto = symbol.replace(":PERP", "").endsWith("USDT");
  const [vol, setVol] = useState(suggestedQty != null ? String(suggestedQty) : "0.01");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [connected, setConnected] = useState(null);

  useEffect(() => {
    if (isCrypto) { setConnected(false); return; }
    mt5Api.account().then((a) => setConnected(a.connected)).catch(() => setConnected(false));
  }, [isCrypto]);

  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return undefined;
    const id = setTimeout(() => setArmed(false), 6000);
    return () => clearTimeout(id);
  }, [armed]);

  async function send() {
    // Two-step: this queues a REAL broker order. First click arms, second sends.
    if (!armed) { setArmed(true); setMsg(null); return; }
    setArmed(false);
    setBusy(true); setMsg(null);
    try {
      await mt5Api.placeOrder({ symbol, action, volume: parseFloat(vol) || 0.01, sl, tp, confirm: true });
      setMsg({ ok: true, text: t("mt5_sent") });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  }

  // Crypto orders go through the order ticket above (Bitunix demo/real);
  // this MT5 path is for metals only.
  if (isCrypto) return null;
  if (connected === false) {
    return <p className="text-xs text-mist-500 mt-2">{t("mt5_not_connected")}</p>;
  }
  return (
    <div className="mt-3 flex items-center gap-2 flex-wrap">
      <label className="text-xs text-mist-400">{t("mt5_volume")}</label>
      <input
        value={vol} onChange={(e) => setVol(e.target.value)}
        inputMode="decimal"
        className="w-20 bg-ink-800 border border-ink-500 rounded-lg px-2 py-1 text-sm text-mist-100 tnum"
      />
      <Button onClick={send} disabled={busy}>
        {busy ? "…" : armed ? `${t("confirm_real_order")} (${action.toUpperCase()})` : `${t("mt5_execute")} (${action.toUpperCase()})`}
      </Button>
      {msg && <span className={`text-xs ${msg.ok ? "text-up" : "text-down"}`}>{msg.text}</span>}
    </div>
  );
}

function AlertsToggle() {
  const { t } = useI18n();
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState(null);

  useEffect(() => {
    alertsApi.status().then((s) => setOn(s.subscriptions > 0)).catch(() => {});
  }, []);

  async function enable() {
    setBusy(true); setInfo(null);
    try {
      await enablePush();
      setOn(true);
      setInfo({ ok: true, msg: t("alerts_on") });
    } catch (e) {
      const map = {
        not_supported: t("alerts_not_supported"),
        permission_denied: t("alerts_denied"),
        server_not_configured: t("alerts_server_off"),
        ios_needs_install: t("ios_install_hint"),
      };
      setInfo({ ok: false, msg: map[e.message] || e.message });
    } finally { setBusy(false); }
  }
  async function disable() {
    setBusy(true);
    try { await disablePush(); setOn(false); setInfo(null); } finally { setBusy(false); }
  }
  async function test() {
    try {
      const r = await alertsApi.test();
      if (r.sent > 0) {
        setInfo({ ok: true, msg: `✓ ${r.sent}/${r.total}` });
      } else {
        const why = (r.errors && r.errors[0]) ? ` — ${r.errors[0]}` : "";
        setInfo({ ok: false, msg: `0/${r.total}${why}` });
      }
    } catch (e) { setInfo({ ok: false, msg: e.message }); }
  }

  const iosNeedsInstall = isIOS() && !isStandalone();

  return (
    <div className="bg-ink-700/80 border border-ink-500 rounded-2xl px-4 py-3 flex flex-wrap items-center gap-3 justify-between">
      <div className="flex items-center gap-2 text-sm text-mist-200">
        <span className="text-gold-soft">🔔</span>
        <span>{on ? t("alerts_on") : t("enable_alerts")}</span>
      </div>
      <div className="flex items-center gap-2">
        {on ? (
          <>
            <Button variant="ghost" onClick={test}>{t("test_alert")}</Button>
            <Button variant="ghost" onClick={disable} disabled={busy}>{t("disable_alerts")}</Button>
          </>
        ) : (
          <Button onClick={enable} disabled={busy || !pushSupported()}>
            {busy ? "…" : t("enable_alerts")}
          </Button>
        )}
      </div>
      {(info || iosNeedsInstall) && (
        <p className={`w-full text-xs ${info && !info.ok ? "text-down" : "text-mist-500"}`}>
          {info ? info.msg : t("ios_install_hint")}
        </p>
      )}
    </div>
  );
}


function PlaybookCard({ ai, timeframe }) {
  const { t } = useI18n();
  const exit = ai.exit_plan;
  const ev = ai.playbook?.evidence;
  return (
    <div className="rounded-lg border border-up/25 bg-up/[0.05] p-3 text-xs leading-relaxed text-mist-300 space-y-2">
      {exit && <p>⏱ {fill(t("pb_exit_line"), { r: `${exit.target_r}R`, bars: exit.max_hold_bars,
        hours: Math.round(exit.max_hold_minutes / 60) })}</p>}
      {ev && (
        <div className="grid grid-cols-3 gap-2">
          <EvidenceCell ltr label={t("bt_ev_years_pos")} value={ev.positive_years} tone="up" />
          <EvidenceCell ltr label={t("bt_ev_period_holdout")} value={`+${ev.expectancy_r?.holdout}R`} tone="up" />
          <EvidenceCell ltr label={t("bt_ev_tpy")} value={`≈${ev.trades_per_year}`} />
        </div>
      )}
      {ev && <p className="text-[11px] text-mist-500">{t("pb_evidence_title")} · {timeframe}</p>}
    </div>
  );
}

function BacktestPanel({ symbol, timeframe, series, mode }) {
  const { t } = useI18n();
  const [period, setPeriod] = useState(() => localStorage.getItem("sp_bt_period") || "medium");
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const gate = useRef(null);
  if (!gate.current) gate.current = createRequestGate();
  useEffect(() => {
    const clear = () => {
      gate.current.invalidate();
      setRes(null); setErr(null); setLoading(false);
    };
    clear();
    const storage = (e) => { if (e.key === "smartpips-strategy-changed") clear(); };
    window.addEventListener("smartpips-strategy-changed", clear);
    window.addEventListener("storage", storage);
    return () => {
      gate.current.invalidate();
      window.removeEventListener("smartpips-strategy-changed", clear);
      window.removeEventListener("storage", storage);
    };
  }, [symbol, timeframe, mode, period]);

  async function run() {
    const id = gate.current.begin();
    if (id === null) return;
    setLoading(true); setErr(null); setRes(null);
    try {
      const bars = barsFor(timeframe, period);
      const result = await strategyApi.backtest(symbol, timeframe, series, { mode, bars });
      if (gate.current.current(id)) setRes(result);
    }
    catch (e) { if (gate.current.current(id)) setErr(e.message); }
    finally {
      if (gate.current.current(id)) setLoading(false);
      gate.current.finish(id);
    }
  }

  return (
    <Panel
      title={`${t("backtest")} · ${symbol} ${timeframe}`}
      action={<Button onClick={run} disabled={loading}>{loading ? t("thinking") : t("run_backtest")}</Button>}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-mist-500">{t("bt_period")}:</span>
        {["short", "medium", "long"].map((p) => (
          <button key={p} type="button"
            onClick={() => { setPeriod(p); try { localStorage.setItem("sp_bt_period", p); } catch { /* ignore */ } }}
            className={`rounded-md border px-2 py-1 ${period === p ? "border-gold/50 bg-gold/10 text-gold-soft" : "border-ink-500 text-mist-500"}`}>
            {t(`bt_period_${p}`)} · {(BT_PERIODS[timeframe] || BT_PERIODS["5m"])[p].toLocaleString()}
          </button>
        ))}
        <span className="text-mist-600">{t("bt_mode_label")}: {mode === "trend" ? t("mode_trend") : t(`mode_${mode}`)}</span>
      </div>
      {loading && <p className="mb-2 text-xs text-mist-500">{t("bt_loading_history")}</p>}
      {err && <p className="text-down text-sm">{err}</p>}
      {res?.strategy && <p className="mb-2 text-xs text-mist-500">{res.strategy}</p>}
      {res?.data_diagnostics?.partial_history && (
        <p className="mb-2 text-xs text-gold-soft">
          {t("bt_partial_history")}: {res.data_diagnostics.used} / {res.data_diagnostics.received}
        </p>
      )}
      {res?.data_diagnostics?.short_window && (
        <p className="mb-2 text-xs text-gold-soft">{t("bt_short_window")}</p>
      )}
      {res?.diagnostics && (
        <p className="mb-2 text-xs text-mist-500">
          {t("bt_evaluated")}: {res.diagnostics.bars_evaluated} · {t("bt_base_wait")}: {res.diagnostics.base_engine_wait} · {t("bt_strategy_veto")}: {res.diagnostics.strategy_veto}
        </p>
      )}
        <BacktestReasons diagnostics={res?.diagnostics} />
      {!res && !err && <p className="text-mist-500 text-sm">{t("engine_decided")}</p>}
      {res && res.trades === 0 && (
        <div className="text-sm text-mist-500 space-y-1">
          <p>{t("bt_no_setups")}</p>
          {res.candles_used != null && (
            <p className="text-[11px] text-mist-600">
              {res.candles_used} candles · {res.data_quality === "ticks" ? "tick-based (set TWELVEDATA_KEY for real candles)" : "real candles"}
            </p>
          )}
        </div>
      )}
      {res && res.trades > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <Mini label={t("bt_trades")} value={res.trades} />
            <Mini label={t("bt_winrate")} value={`${res.win_rate}%`} tone={res.win_rate >= 45 ? "up" : res.win_rate >= 35 ? "neutral" : "down"} />
            <Mini label={t("bt_pf")} value={res.profit_factor ?? "—"} tone={(res.profit_factor ?? 0) >= 1.3 ? "up" : (res.profit_factor ?? 0) >= 1 ? "neutral" : "down"} />
            <Mini label={t("bt_exp")} value={res.expectancy_r} tone={(res.expectancy_r ?? 0) > 0 ? "up" : "down"} />
            <Mini label={t("bt_dd")} value={res.max_drawdown_r} tone="neutral" />
          </div>
          {!res.evidence && <p className="text-[11px] text-mist-500 mt-3">{t("bt_verdict")}: {
            (res.profit_factor ?? 0) >= 1.3 && (res.expectancy_r ?? 0) > 0
              ? `✅ ${t("bt_good")}`
              : (res.profit_factor ?? 0) >= 1
                ? `🟡 ${t("bt_ok")}`
                : `🔴 ${t("bt_bad")}`
          }</p>}
        </>
      )}
      {res && <BacktestEvidence result={res} />}
    </Panel>
  );
}

function Mini({ label, value, tone = "neutral" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
      <p className="text-[11px] text-mist-500">{label}</p>
      <p className={`tnum text-base font-semibold mt-0.5 ${color}`}><bdi dir="ltr">{value}</bdi></p>
    </div>
  );
}

function Level({ label, value, tone }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-info";
  return (
    <div className="bg-ink-700 border border-ink-500 rounded-lg px-2 py-2 text-center">
      <p className="text-[11px] text-mist-500">{label}</p>
      <p className={`tnum text-sm font-medium mt-0.5 ${color}`}>{value || "—"}</p>
    </div>
  );
}
