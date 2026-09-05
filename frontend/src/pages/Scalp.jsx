import { useMemo, useState, useEffect } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Badge, Button, Spinner } from "../components/ui.jsx";
import { SignalChart, indicatorsToStudies } from "../components/TradingView.jsx";
import { PositionChart, toBitunixSymbol } from "../components/PositionChart.jsx";

// Indicators the scalp engine actually computes (see lib/scalp.js), mapped to
// TradingView built-in study IDs so the chart shows the same picture the
// signal is based on. Module-level const: a new array every render would make
// the embed tear down and rebuild the iframe on every tick.
const SCALP_STUDIES = indicatorsToStudies([
  { key: "ema" }, { key: "rsi" }, { key: "macd" }, { key: "stoch" },
]);
import { LogTradeModal } from "../components/TradeModal.jsx";
import { TradingAccountPanel } from "../components/TradingAccountPanel.jsx";
import { OrderBook } from "../components/OrderBook.jsx";
import { OrderTicket, signalExpired } from "../components/OrderTicket.jsx";
import { scalpApi, tradesApi, strategyApi, alertsApi, mt5Api, marketApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { useMetalTick } from "../live/useMetalTick.js";
import { CRYPTO_BASE } from "../lib/symbols.js";
import { computeScalp } from "../lib/scalp.js";
import { fmtPrice, parsePrice } from "../lib/num.js";
import { pushSupported, isIOS, isStandalone, enablePush, disablePush } from "../live/push.js";

// Same ~50 liquid coins the backend supports (apps/market/crypto_symbols.py) —
// kept in sync manually since frontend/backend are separate codebases here.
// crypto universe moved to lib/symbols.js (shared with the Bitunix panel)

const METALS = [
  { symbol: "XAUUSD", tv: "TVC:GOLD", label: "XAU/USD", group: "metals" },
  { symbol: "XAGUSD", tv: "TVC:SILVER", label: "XAG/USD", group: "metals" },
  // crypto spot (Binance) — ~50 liquid pairs, exchange-style
  ...CRYPTO_BASE.map((b) => ({
    symbol: `${b}USDT`, tv: `BINANCE:${b}USDT`, label: `${b} spot`, group: "spot",
  })),
  // crypto futures / perpetual (Binance USD-M) — real volume + funding-driven moves
  ...CRYPTO_BASE.map((b) => ({
    symbol: `${b}USDT:PERP`, tv: `BINANCE:${b}USDT.P`, label: `${b} futures`, group: "futures",
  })),
];

// label shown to user -> TradingView interval code
const TIMEFRAMES = [
  ["1m", "1"], ["5m", "5"], ["15m", "15"], ["1h", "60"], ["4h", "240"],
];

function signalTone(sig) {
  return sig === "buy" ? "up" : sig === "sell" ? "down" : "gold";
}

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
  const { t } = useI18n();

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
    return METALS[0];
  });
  const [tf, setTf] = useState(() => {
    if (quickTf) {
      const found = TIMEFRAMES.find((t) => t[0] === quickTf);
      if (found) return found;
    }
    return TIMEFRAMES[0];
  });
  const { price, series, status } = useMetalTick(metal.symbol, { intervalMs: 1000, history: 300 });

  const scalp = useMemo(() => computeScalp(series), [series]);

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
  const [scalpMode, setScalpMode] = useState(() => localStorage.getItem("sp_mode") || "safe");

  function switchMode(m) { setScalpMode(m); localStorage.setItem("sp_mode", m); }

  function saveRisk(b, r) {
    setBalance(b); setRiskPct(r); setBalanceSource("manual");
    localStorage.setItem("sp_balance", b);
    localStorage.setItem("sp_balance_manual", b);
    localStorage.setItem("sp_risk", r);
  }

  async function getAiSignal() {
    if (!price) return;
    setAiLoading(true); setAiError(null);
    try {
      const res = await scalpApi.signal(metal.symbol, price, tf[0], series,
        balance ? Number(balance) : undefined, riskPct ? Number(riskPct) : undefined,
        scalpMode);
      setAi(res);
    } catch (e) { setAiError(e.message); }
    finally { setAiLoading(false); }
  }

  // AUTO-REFRESH (the "signal arrives late" fix): when enabled, re-run the
  // decision engine every 20s WITHOUT the slow AI explanation (explain=false —
  // the engine itself answers in <1s), so the shown signal tracks the market
  // instead of aging while the user isn't clicking.
  const [autoRefresh, setAutoRefresh] = useState(() => localStorage.getItem("sp_auto") === "1");
  function toggleAuto() {
    const v = !autoRefresh; setAutoRefresh(v);
    localStorage.setItem("sp_auto", v ? "1" : "0");
  }
  useEffect(() => {
    if (!autoRefresh || !price || series.length < 30) return;
    let alive = true;
    const id = setInterval(async () => {
      try {
        const res = await scalpApi.signal(metal.symbol, price, tf[0], series,
          balance ? Number(balance) : undefined, riskPct ? Number(riskPct) : undefined,
          scalpMode, /* explain */ false);
        if (alive) setAi((prev) => ({ ...res, explanation: prev?.explanation, summary: prev?.summary }));
      } catch { /* keep last signal on transient errors */ }
    }, 20000);
    return () => { alive = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, metal.symbol, tf, scalpMode, balance, riskPct, price && series.length >= 30]);

  // QUICK PATH (from a push notification tap): the engine works off candles,
  // not the live tick buffer, so we don't need to wait for 30 ticks — just get
  // one fresh price from the backend and ask for the signal immediately.
  async function getAiSignalQuick() {
    setAiLoading(true); setAiError(null);
    try {
      const p = await marketApi.metal(metal.symbol);
      const px = p && p.ok ? p.price : price;
      if (!px) throw new Error(t("metal_unavailable"));
      const res = await scalpApi.signal(metal.symbol, px, tf[0], [],
        balance ? Number(balance) : undefined, riskPct ? Number(riskPct) : undefined,
        scalpMode);
      setAi(res);
    } catch (e) { setAiError(e.message); }
    finally { setAiLoading(false); }
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
        notes: "",
        balance: balance ? Number(balance) : undefined,
      });
      setQuickLogged(true);
      setTradesVersion((v) => v + 1);
    } catch (e) { setAiError(e.message); }
    finally { setQuickLogging(false); }
  }

  function switchMetal(m) { setMetal(m); setAi(null); setAiError(null); setQuickLogged(false); }


  const localTone = signalTone(scalp.signal);
  const aiTone = ai ? signalTone(ai.signal) : "neutral";

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
        <RiskBar balance={balance} riskPct={riskPct} onSave={saveRisk} source={balanceSource} />
        <Collapse title={`👁 ${t("sc_watchlist_alerts")}`}>
          <div className="space-y-4">
            <AlertsToggle />
            <WatchlistPanel current={metal} />
          </div>
        </Collapse>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {/* timeframe selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-mist-500">{t("timeframe")}:</span>
            {TIMEFRAMES.map((f) => (
              <button
                key={f[0]}
                onClick={() => setTf(f)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition ${
                  f[0] === tf[0] ? "bg-gold text-ink-900" : "bg-ink-700 text-mist-300 hover:bg-ink-600"
                }`}
              >{f[0]}</button>
            ))}
          </div>
        </div>

        {/* live tick + composite + AI button */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-ink-700 border border-ink-500 rounded-xl px-4 py-3 shadow-panel">
            <p className="text-xs text-mist-500 flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${status === "live" ? "bg-up live-dot" : "bg-mist-500"}`} />
              {t("live_tick")} · {metal.label}
            </p>
            {price ? (
              <>
                <p className="tnum text-3xl font-semibold text-mist-100 mt-1">${fmtPrice(price)}</p>
                <p className="text-[11px] text-mist-500 mt-0.5">{t("price_source")}</p>
              </>
            ) : (
              <p className="text-sm text-mist-500 mt-2">
                {status === "unavailable" ? t("metal_unavailable") : t("waiting_ticks")}
              </p>
            )}
          </div>

          <div className="bg-ink-700 border border-ink-500 rounded-xl px-4 py-3 shadow-panel">
            <p className="text-xs text-mist-500">{t("composite_signal")}</p>
            <div className="mt-1 flex items-center gap-2 flex-wrap">
              <Badge tone={localTone}>{t(`signal_${scalp.signal}`)}</Badge>
              <span className="tnum text-sm text-mist-300">{t("score")}: {scalp.score}/100</span>
              {scalp.regime && <Badge tone="info">{scalp.regime}</Badge>}
            </div>
            <div className="mt-2 h-1.5 w-full bg-ink-800 rounded-full overflow-hidden">
              <div className={`h-full ${scalp.score >= 70 ? "bg-up" : scalp.score <= 30 ? "bg-down" : "bg-gold"}`} style={{ width: `${scalp.score}%` }} />
            </div>
          </div>

          <div className="bg-ink-700 border border-ink-500 rounded-xl px-4 py-3 shadow-panel flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs text-mist-500">{t("ai_scalp_signal")} · {tf[0]}</p>
              <p className="text-sm text-mist-300 mt-1">{ai ? t(`signal_${ai.signal}`) : "—"}</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={toggleAuto}
                title={t("auto_refresh")}
                className={`text-xs px-2.5 py-1.5 rounded-md border transition ${
                  autoRefresh ? "bg-up/15 text-up border-up/30" : "bg-ink-800 text-mist-500 border-ink-500 hover:text-mist-300"
                }`}>
                {autoRefresh ? `● ${t("auto_on")}` : `○ ${t("auto_off")}`}
              </button>
              <div className="flex items-center gap-1 bg-ink-800 rounded-lg p-0.5">
                {[["safe", t("mode_safe")], ["aggressive", t("mode_aggressive")]].map(([m, label]) => (
                  <button key={m} onClick={() => switchMode(m)}
                    className={`text-xs px-2.5 py-1 rounded-md ${scalpMode === m ? "bg-ink-600 text-mist-100" : "text-mist-500 hover:text-mist-300"}`}>
                    {label}
                  </button>
                ))}
              </div>
              <Button onClick={getAiSignal} disabled={!price || series.length < 30 || aiLoading}>
                {aiLoading ? t("thinking") : series.length < 30 ? `${t("waiting_ticks")} ${series.length}/30` : t("get_ai_signal")}
              </Button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <Panel title={`${metal.label} · ${tf[0]}`} className="xl:col-span-2">
            <SignalChart symbol={metal.tv} interval={tf[1]} height={380}
              studies={SCALP_STUDIES} />
          </Panel>

          <div className="flex flex-col gap-6">
            {metal.group !== "metals" && (
              <OrderBook symbol={metal.symbol} lastPrice={price} />
            )}
            <Panel title={t("numeric_panel")}>
              {!price ? (
                <Spinner label={t("waiting_ticks")} />
              ) : (
                <ul className="divide-y divide-ink-600/60">
                  {Object.entries(scalp.indicators).map(([k, v]) => (
                    <li key={k} className="flex items-center justify-between py-2 text-sm">
                      <span className="text-mist-300">{k}</span>
                      <span className="tnum text-mist-100">{v}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            {ai && ai.signal !== "wait" && (
              <PriceLadder ai={ai} currentPrice={price} />
            )}
          </div>
        </div>

        {/* Position chart: real Bitunix candles with Entry / TP / SL / Liq drawn
            on top. It renders on its own even with no open position, and metals
            (not a Bitunix perp) simply fall back to the symbol picker. */}
        <Panel title={t("pc_title")}>
          <PositionChart symbol={toBitunixSymbol(metal.symbol) || undefined}
            height={420} storageKey="pc_tf_scalp" />
        </Panel>

        {aiError && (
          <div className="text-down text-sm bg-down/10 border border-down/30 rounded-lg px-3 py-2">{aiError}</div>
        )}
        {ai && (
          <Panel title={`${t("ai_scalp_signal")} · ${tf[0]}`}
            action={
              <button onClick={() => setAdvanced(!advanced)}
                className="text-xs text-mist-400 hover:text-mist-100 border border-ink-500 rounded-lg px-2 py-1">
                {advanced ? t("mode_advanced") : t("mode_beginner")}
              </button>
            }>
            <SignalHeadline ai={ai} />

            {ai.signal !== "wait" && (
              <div className="grid grid-cols-3 gap-2 mt-4">
                <Level label={t("entry")} value={ai.entry} tone="info" />
                <Level label={t("take_profit")} value={ai.take_profit} tone="up" />
                <Level label={t("stop_loss")} value={ai.stop_loss} tone="down" />
              </div>
            )}
            {ai.signal !== "wait" && ai.order_ticket && (
              <div className="mt-4">
                <OrderTicket ai={ai} livePrice={price} demoBalance={balance ? Number(balance) : undefined} onExecute={() => setLogging(true)} />
              </div>
            )}
            {ai.signal !== "wait" && (
              <ExecuteOrder
                symbol={metal.symbol}
                action={ai.signal}
                sl={parsePrice(ai.stop_loss)}
                tp={parsePrice(ai.take_profit)}
                suggestedQty={ai.position_size?.mode === "lots" ? ai.position_size.lots : ai.position_size?.quantity}
              />
            )}
            {ai.position_size && ai.signal !== "wait" && (
              <PositionSizeCard ps={ai.position_size} lev={ai.leverage} action={ai.signal} />
            )}
            {ai.risk_block && (
              <div className="mt-3 text-sm bg-down/10 border border-down/30 rounded-lg px-3 py-2 text-down">
                ⛔ {t("risk_blocked")}: {ai.risk_block}
              </div>
            )}
            {ai.summary && (
              <p className="text-sm text-mist-100 bg-ink-700/60 border border-ink-500 rounded-lg px-3 py-2 mt-3 leading-relaxed">
                💬 {ai.summary}
              </p>
            )}
            {ai.explanation && <p className="text-xs text-mist-300 leading-relaxed mt-3">{ai.explanation}</p>}
            {ai.signal === "wait" && ai.reason && (
              <p className="text-xs text-gold-soft mt-2">⏳ {ai.reason}</p>
            )}

            {advanced && (
              <>
                <div className="flex items-center gap-2 flex-wrap mt-4 pt-3 border-t border-ink-600">
                  {ai.risk_reward && <Badge tone="info">{t("risk_reward")}: {ai.risk_reward}</Badge>}
                  {ai.htf_bias != null && (
                    <Badge tone="neutral">HTF: {ai.htf_bias > 0 ? "↑" : ai.htf_bias < 0 ? "↓" : "→"}</Badge>
                  )}
                  {ai.data_quality === "ticks" && <Badge tone="down">tick-based</Badge>}
                  {ai.session && <Badge tone={ai.session.score >= 6 ? "up" : "neutral"}>🕐 {ai.session.name}</Badge>}
                  {ai.regime && <Badge tone="neutral">vol: {ai.regime}</Badge>}
                  {ai.indicators?.OrderFlow && (
                    <Badge tone={ai.indicators.OrderFlow.delta > 0 ? "up" : ai.indicators.OrderFlow.delta < 0 ? "down" : "neutral"}>
                      Δ {ai.indicators.OrderFlow.delta}
                    </Badge>
                  )}
                  {ai.indicators?.LiquiditySweep && <Badge tone="info">sweep: {ai.indicators.LiquiditySweep}</Badge>}
                  {ai.indicators?.OrderBlock && <Badge tone={ai.indicators.OrderBlock === "bullish" ? "up" : "down"}>OB {ai.indicators.OrderBlock}</Badge>}
                  {ai.indicators?.MSS && <Badge tone={ai.indicators.MSS === "bullish" ? "up" : "down"}>MSS {ai.indicators.MSS}</Badge>}
                  {ai.indicators?.LevelSweep && <Badge tone="info">{ai.indicators.LevelSweep}</Badge>}
                  {ai.indicators?.PremiumDiscount && ai.indicators.PremiumDiscount.zone !== "equilibrium" && (
                    <Badge tone="neutral">{ai.indicators.PremiumDiscount.zone}</Badge>
                  )}
                  {ai.news_guard && <Badge tone="down">📅 {ai.news_guard}</Badge>}
                </div>
                {ai.score_breakdown && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {Object.entries(ai.score_breakdown).map(([k, v]) => (
                      <span key={k} className={`text-[11px] px-2 py-0.5 rounded-md border ${
                        v > 0 ? "border-up/30 text-up bg-up/10" : v < 0 ? "border-down/30 text-down bg-down/10" : "border-ink-500 text-mist-500"
                      }`}>{k} {v > 0 ? `+${v}` : v}</span>
                    ))}
                  </div>
                )}
              </>
            )}
            {ai.signal !== "wait" && (
              <div className="mt-3 flex items-center gap-2 flex-wrap">
                <Button onClick={() => setLogging(true)}>{t("log_this")}</Button>
                {isQuick && !quickLogged && (
                  <Button variant="primary" onClick={quickLogTrade} disabled={quickLogging}>
                    {quickLogging ? t("thinking") : `⚡ ${t("quick_log")}`}
                  </Button>
                )}
                {quickLogged && (
                  <span className="text-up text-sm">✓ {t("trade_logged")}</span>
                )}
              </div>
            )}
          </Panel>
        )}

        <Collapse title={`💼 ${t("sc_account_section")}`} defaultOpen>
          <TradingAccountPanel balance={balance} defaultInitial={tradeInitial} refreshKey={tradesVersion} />
        </Collapse>

        <Collapse title={`📊 ${t("sc_backtest_section")}`}>
          <BacktestPanel symbol={metal.symbol} timeframe={tf[0]} series={series} />
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
          onSaved={async (payload) => { await tradesApi.create({ ...payload, balance: balance ? Number(balance) : undefined }); setTradesVersion((v) => v + 1); }}
        />
      )}
    </>
  );
}

function SignalHeadline({ ai }) {
  const { t } = useI18n();
  const isWait = ai.signal === "wait";
  const dir = ai.signal === "buy" ? "up" : ai.signal === "sell" ? "down" : "neutral";
  const grade = ai.grade || { grade: "—", stars: 0 };
  const score = ai.score ?? 0;

  const headline = isWait ? t("wait_signal")
    : ai.signal === "buy" ? (score >= 80 ? t("strong_buy") : t("buy_signal"))
    : (score >= 80 ? t("strong_sell") : t("sell_signal"));
  const dot = isWait ? "🟡" : ai.signal === "buy" ? "🟢" : "🔴";
  const riskWord = score >= 80 ? t("risk_low") : score >= 65 ? t("risk_medium") : t("risk_high");

  const pros = ai.reasons_plain?.pros || [];
  const cons = ai.reasons_plain?.cons || [];

  const regime = ai.market_regime?.regime;
  const setupClass = ai.setup_class;
  const sessStars = ai.session_quality?.stars || 0;

  return (
    <div>
      {/* market context chips: regime · setup class · session quality */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        {regime && (
          <span className="text-xs px-2 py-1 rounded-md bg-ink-800 text-mist-300">
            {t("regime_label")}: <span className="text-mist-100">{t(`regime_${regime}`)}</span>
          </span>
        )}
        {setupClass && !isWait && (
          <span className="text-xs px-2 py-1 rounded-md bg-ink-800 text-mist-300">
            {setupClass.emoji} {t(`setup_${setupClass.class}`)}
          </span>
        )}
        {sessStars > 0 && (
          <span className="text-xs px-2 py-1 rounded-md bg-ink-800 text-mist-400">
            {ai.session_quality?.name} <span className="text-gold-soft">{"★".repeat(sessStars)}<span className="text-ink-500">{"★".repeat(5 - sessStars)}</span></span>
          </span>
        )}
      </div>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{dot}</span>
          <div>
            <p className={`text-xl font-bold ${dir === "up" ? "text-up" : dir === "down" ? "text-down" : "text-gold-soft"}`}>
              {headline}
            </p>
            {!isWait && (
              <p className="text-xs text-mist-500 mt-0.5">
                {t("grade_label")}: <span className="text-mist-200 font-semibold">{grade.grade}</span>
                {"  ·  "}{t("risk_level")}: {riskWord}
              </p>
            )}
          </div>
        </div>
        {!isWait && (
          <div className="text-end">
            <div className="text-lg tracking-tight" title={`${score}/100`}>
              {"★".repeat(grade.stars)}<span className="text-ink-500">{"★".repeat(5 - grade.stars)}</span>
            </div>
            <p className="text-xs text-mist-500 mt-0.5">{t("system_confidence")}: {score}%
              {typeof ai.conviction === "number" && (
                <span className="ms-2">· {t("conviction")}: <span className={ai.conviction >= 40 ? "text-up" : "text-gold-soft"}>{ai.conviction}%</span></span>
              )}
            </p>
            {ai.confidence_calibrated?.calibrated && (
              <p className="text-xs text-up mt-0.5">
                {t("real_confidence")}: {ai.confidence_calibrated.value}%
                <span className="text-mist-600"> ({ai.confidence_calibrated.sample} {t("past_trades")})</span>
              </p>
            )}
          </div>
        )}
      </div>

      {/* confidence meter bar */}
      {!isWait && (
        <div className="mt-3 h-2 rounded-full bg-ink-700 overflow-hidden">
          <div className={`h-full rounded-full ${score >= 80 ? "bg-up" : score >= 65 ? "bg-gold" : "bg-down"}`}
            style={{ width: `${Math.max(8, Math.min(100, score))}%` }} />
        </div>
      )}

      {pros.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-mist-500 mb-1">{t("entry_reasons")}</p>
          <ul className="space-y-1">
            {pros.map((k) => (
              <li key={k} className="text-sm text-mist-200 flex items-start gap-2">
                <span className="text-up">✅</span><span>{t(`r_${k}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {cons.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-mist-500 mb-1">{t("risk_factors")}</p>
          <ul className="space-y-1">
            {cons.map((k) => (
              <li key={k} className="text-sm text-mist-300 flex items-start gap-2">
                <span className="text-down">⚠️</span><span>{t(`r_${k}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Exchange-style price ladder: a precise vertical price scale showing exactly
// where the entry, each take-profit level, and the stop-loss sit relative to
// the current price — the same information an exchange's order/price panel
// gives you, without needing to draw lines on the chart widget itself.
function PriceLadder({ ai, currentPrice }) {
  const { t } = useI18n();
  const isBuy = ai.signal === "buy";
  const cur = currentPrice ?? ai.entry;

  const rows = [];
  if (ai.tp_levels && ai.tp_levels.length) {
    ai.tp_levels.forEach((lv, i) => rows.push({ key: `tp${i + 1}`, label: `TP${i + 1}`, price: lv.price, pct: lv.pct, tone: "up" }));
  } else if (ai.take_profit) {
    rows.push({ key: "tp", label: "TP", price: ai.take_profit, tone: "up" });
  }
  rows.push({ key: "entry", label: t("entry"), price: ai.entry, tone: "info", isEntry: true });
  if (ai.stop_loss) rows.push({ key: "sl", label: "SL", price: ai.stop_loss, tone: "down" });

  // sort by price so it reads top-to-bottom like a real order book / price ladder
  rows.sort((a, b) => (isBuy ? b.price - a.price : a.price - b.price));

  return (
    <Panel title={t("price_ladder")}>
      <div className="space-y-1">
        {rows.map((r) => {
          const dist = ai.entry ? ((r.price - cur) / cur) * 100 : 0;
          return (
            <div key={r.key} className={`flex items-center justify-between px-2.5 py-2 rounded-lg text-sm ${
              r.isEntry ? "bg-info/10 border border-info/30" : r.tone === "up" ? "bg-up/5" : "bg-down/5"
            }`}>
              <span className={`text-xs font-medium ${r.tone === "up" ? "text-up" : r.tone === "down" ? "text-down" : "text-info"}`}>
                {r.label}{r.pct ? ` · ${r.pct}%` : ""}
              </span>
              <span className="tnum text-mist-100 font-semibold">{fmtPrice(r.price)}</span>
              <span className={`tnum text-[11px] ${dist >= 0 ? "text-up" : "text-down"}`}>
                {dist >= 0 ? "+" : ""}{dist.toFixed(2)}%
              </span>
            </div>
          );
        })}
        {Number.isFinite(cur) && (
          <div className="flex items-center justify-between px-2.5 py-1.5 mt-1 border-t border-dashed border-ink-500">
            <span className="text-[11px] text-mist-500">{t("current_price")}</span>
            <span className="tnum text-gold-soft font-semibold">{fmtPrice(cur)}</span>
          </div>
        )}
      </div>
    </Panel>
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

function Collapse({ title, children, defaultOpen = false }) {
  return (
    <details open={defaultOpen}
      className="group bg-ink-700/60 border border-ink-500 rounded-xl overflow-hidden">
      <summary className="cursor-pointer select-none list-none px-4 py-2.5 text-[13px] font-medium text-mist-300 hover:text-mist-100 flex items-center justify-between">
        {title}
        <span className="text-mist-500 transition group-open:rotate-180">▾</span>
      </summary>
      <div className="px-4 pb-4">{children}</div>
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
    <Panel title={t("risk_panel_title")}>
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
    </Panel>
  );
}

function SymbolPicker({ current, onPick, access = {} }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [group, setGroup] = useState(current.group || "metals");
  const [query, setQuery] = useState("");
  // groups the admin disabled for this user simply don't exist here
  const groups = [
    ["metals", t("grp_metals")],
    ["spot", t("grp_spot")],
    ["futures", t("grp_futures")],
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
      <Button variant="ghost" onClick={() => setOpen((v) => !v)}>
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

  async function send() {
    setBusy(true); setMsg(null);
    try {
      await mt5Api.placeOrder({ symbol, action, volume: parseFloat(vol) || 0.01, sl, tp });
      setMsg({ ok: true, text: t("mt5_sent") });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  }

  // Crypto execution needs an exchange connection (LBank/Binance) — not wired yet.
  if (isCrypto) {
    return <p className="text-xs text-mist-500 mt-2">🔌 {t("crypto_exec_soon")}</p>;
  }
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
        {busy ? "…" : `${t("mt5_execute")} (${action.toUpperCase()})`}
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

function BacktestPanel({ symbol, timeframe, series }) {
  const { t } = useI18n();
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  async function run() {
    setLoading(true); setErr(null); setRes(null);
    try { setRes(await strategyApi.backtest(symbol, timeframe, series)); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  return (
    <Panel
      title={`${t("backtest")} · ${symbol} ${timeframe}`}
      action={<Button onClick={run} disabled={loading}>{loading ? t("thinking") : t("run_backtest")}</Button>}
    >
      {err && <p className="text-down text-sm">{err}</p>}
      {!res && !err && <p className="text-mist-500 text-sm">{t("engine_decided")}</p>}
      {res && res.trades === 0 && (
        <div className="text-sm text-mist-500 space-y-1">
          <p>{res.note || t("bt_none")}</p>
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
          <p className="text-[11px] text-mist-500 mt-3">{t("bt_verdict")}: {
            (res.profit_factor ?? 0) >= 1.3 && (res.expectancy_r ?? 0) > 0
              ? `✅ ${t("bt_good")}`
              : (res.profit_factor ?? 0) >= 1
                ? `🟡 ${t("bt_ok")}`
                : `🔴 ${t("bt_bad")}`
          }</p>
        </>
      )}
    </Panel>
  );
}

function Mini({ label, value, tone = "neutral" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
      <p className="text-[11px] text-mist-500">{label}</p>
      <p className={`tnum text-base font-semibold mt-0.5 ${color}`}>{value}</p>
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
