import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";
import { bitunixApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";
import { BITUNIX_SYMBOLS } from "../lib/symbols.js";

/**
 * Candlestick chart with an optional position overlay.
 *
 * The chart is the primary thing and stands entirely on its own: pick BTCUSDT
 * and you get a normal chart, whether or not you hold anything. When one of
 * your open positions happens to be on the symbol currently displayed, its
 * Entry / TP / SL / Liq are drawn on top as labelled price lines and a live
 * P&L readout appears — exactly like an exchange terminal, but DISPLAY ONLY.
 * Dragging lines to modify orders is deliberately not wired up, so nothing
 * here can ever mutate a position.
 *
 * Positions from BOTH trading modes are loaded together and each is tagged
 * DEMO or REAL, so it is never ambiguous whether the P&L on screen is paper
 * money or the live wallet.
 */

const TIMEFRAMES = [
  ["1m", "1m"], ["5m", "5m"], ["15m", "15m"],
  ["1h", "1h"], ["4h", "4h"], ["1d", "1d"],
];

const COLORS = {
  entry: "#e2b76a",
  tp: "#22c55e",
  sl: "#ef4444",
  liq: "#f97316",
  mark: "#94a3b8",
};

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const money = (n, d = 2) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? "—"
    : Number(n).toLocaleString("en-US", { maximumFractionDigits: d });

// Bitunix perp symbols only — metals (XAUUSD) are not on this venue.
export function toBitunixSymbol(sym) {
  const s = String(sym || "").toUpperCase().replace(/[:\s/-]|PERP/g, "");
  if (!s) return null;
  if (s.endsWith("USDT")) return s;
  if (/^(XAU|XAG|GOLD|SILVER|USOIL|WTI)/.test(s)) return null;   // not a perp
  if (s.endsWith("USD")) return `${s.slice(0, -3)}USDT`;
  return `${s}USDT`;
}

// One position from either mode, flattened to the shape the chart needs.
function normalize(p, mode) {
  const side = String(p.side || "").toUpperCase();
  const isLong = side.includes("BUY") || side === "LONG";
  const entry = num(p.entryPrice) ?? num(p.avgOpenPrice);
  const mark = num(p.markPrice);
  const qty = num(p.qty);
  const margin = num(p.margin);
  let pnl = num(p.unrealizedPNL) ?? num(p.unrealizedPnl);
  if (pnl === null && entry !== null && mark !== null && qty !== null) {
    pnl = (isLong ? mark - entry : entry - mark) * qty;
  }
  const roe = num(p.roe) ?? (pnl !== null && margin ? (pnl / margin) * 100 : null);
  return {
    key: `${mode}:${p.positionId || p.id}`,
    id: p.positionId || p.id,
    mode,
    symbol: String(p.symbol || "").toUpperCase().replace(":PERP", ""),
    side: isLong ? "LONG" : "SHORT",
    isLong,
    entry,
    mark,
    qty,
    margin,
    leverage: num(p.leverage),
    tp: num(p.tpPrice) ?? num(p.takeProfit),
    sl: num(p.slPrice) ?? num(p.stopLoss),
    liq: num(p.liqPrice) ?? num(p.liquidationPrice),
    pnl,
    roe,
  };
}

// Distance from the mark price to a target, as a signed percentage.
function distancePct(mark, target) {
  if (mark === null || target === null || !mark) return null;
  return ((target - mark) / mark) * 100;
}

export function PositionChart({
  symbol: symbolProp,          // optional: drive the symbol from the page
  showSymbolPicker = true,
  refreshKey,
  height = 420,
  storageKey = "pc_tf",
}) {
  const { t } = useI18n();

  // ------------------------------------------------------------- symbol ---
  // The chart owns a symbol at all times, so it renders with or without a
  // position. A `symbol` prop (e.g. the coin selected on the Scalp page)
  // simply steers it.
  const propSymbol = toBitunixSymbol(symbolProp);
  const [symbol, setSymbol] = useState(
    () => propSymbol || localStorage.getItem("pc_symbol") || "BTCUSDT");
  useEffect(() => {
    if (propSymbol) setSymbol(propSymbol);
  }, [propSymbol]);

  function pickSymbol(s) {
    setSymbol(s);
    localStorage.setItem("pc_symbol", s);
  }

  const [tf, setTf] = useState(() => localStorage.getItem(storageKey) || "15m");
  const [positions, setPositions] = useState([]);
  const [selectedKey, setSelectedKey] = useState(null);
  const [candles, setCandles] = useState(null);
  const [markPrice, setMarkPrice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const boxRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const linesRef = useRef([]);

  // ---------------------------------------------------------- positions ---
  // Both modes every 5s. A failing mode (no API keys yet, demo empty, …)
  // contributes nothing instead of blanking the panel — and critically, an
  // empty result never stops the chart from rendering.
  useEffect(() => {
    let stop = false;
    async function pull() {
      const [demo, real] = await Promise.all([
        bitunixApi.positions("demo").catch(() => null),
        bitunixApi.positions("real").catch(() => null),
      ]);
      if (stop) return;
      setPositions([
        ...((demo?.positions) || []).map((p) => normalize(p, "demo")),
        ...((real?.positions) || []).map((p) => normalize(p, "real")),
      ].filter((p) => p.symbol && p.entry !== null));
    }
    pull();
    const id = setInterval(pull, 5000);
    return () => { stop = true; clearInterval(id); };
  }, [refreshKey]);

  // Positions that belong to whatever the chart is currently showing.
  const onChart = useMemo(
    () => positions.filter((p) => p.symbol === symbol),
    [positions, symbol],
  );
  const selected = useMemo(
    () => onChart.find((p) => p.key === selectedKey) || onChart[0] || null,
    [onChart, selectedKey],
  );

  // ------------------------------------------------------------ candles ---
  useEffect(() => {
    if (!symbol) return undefined;
    let stop = false;
    async function pull() {
      try {
        const res = await bitunixApi.klines(symbol, tf, 300);
        if (stop) return;
        setCandles(res.candles || []);
        setMarkPrice(num(res.markPrice));
        setErr(null);
      } catch (e) {
        if (!stop) { setErr(e.message); setCandles([]); }
      } finally {
        if (!stop) setLoading(false);
      }
    }
    setLoading(true);
    pull();
    const id = setInterval(pull, 15000);
    return () => { stop = true; clearInterval(id); };
  }, [symbol, tf]);

  // -------------------------------------------------------------- chart ---
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return undefined;
    const chart = createChart(box, {
      width: box.clientWidth,
      height,
      layout: { background: { color: "#101420" }, textColor: "#94a3b8", fontSize: 11 },
      grid: {
        vertLines: { color: "rgba(34,42,58,0.5)" },
        horzLines: { color: "rgba(34,42,58,0.5)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#222a3a", scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: "#222a3a", timeVisible: true, secondsVisible: false },
      handleScroll: true,
      handleScale: true,
    });
    const series = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      if (boxRef.current) chart.applyOptions({ width: boxRef.current.clientWidth });
    });
    ro.observe(box);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      linesRef.current = [];
    };
  }, [height]);

  // feed candles
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !candles) return;
    series.setData(candles.map((c) => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Draw the overlay. With no position on this symbol we simply clear the
  // lines and leave a plain, fully usable chart behind.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    linesRef.current.forEach((l) => { try { series.removePriceLine(l); } catch { /* gone */ } });
    linesRef.current = [];
    if (!selected) return;

    const add = (price, color, title, style = LineStyle.Solid, width = 1) => {
      if (!Number.isFinite(price)) return;
      linesRef.current.push(series.createPriceLine({
        price, color, lineWidth: width, lineStyle: style,
        axisLabelVisible: true, title,
      }));
    };

    add(selected.entry, COLORS.entry, `${t("pc_entry")} ${fmtPrice(selected.entry)}`, LineStyle.Solid, 2);
    add(selected.tp, COLORS.tp, `TP ${fmtPrice(selected.tp)}`, LineStyle.Dashed);
    add(selected.sl, COLORS.sl, `SL ${fmtPrice(selected.sl)}`, LineStyle.Dashed);
    add(selected.liq, COLORS.liq, `${t("pc_liq")} ${fmtPrice(selected.liq)}`, LineStyle.Dotted);
    add(selected.mark, COLORS.mark, `${t("pc_mark")} ${fmtPrice(selected.mark)}`, LineStyle.LargeDashed);
  }, [selected, candles, t]);

  // ---------------------------------------------------------------- ui ----
  const lastClose = candles?.length ? candles[candles.length - 1].close : null;
  const livePrice = selected?.mark ?? markPrice ?? lastClose;
  const toTp = selected ? distancePct(selected.mark ?? livePrice, selected.tp) : null;
  const toSl = selected ? distancePct(selected.mark ?? livePrice, selected.sl) : null;

  const totals = useMemo(() => {
    const sum = (mode) => positions
      .filter((p) => p.mode === mode && p.pnl !== null)
      .reduce((a, p) => a + p.pnl, 0);
    return { demo: sum("demo"), real: sum("real"), count: positions.length };
  }, [positions]);

  return (
    <div className="space-y-3">
      {/* symbol + timeframe: always available, position or not */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          {showSymbolPicker && (
            <select value={symbol} onChange={(e) => pickSymbol(e.target.value)}
              className="bg-ink-800 border border-ink-500 rounded-lg px-2.5 py-1.5 text-xs
                text-mist-100 tnum focus:outline-none focus:border-gold">
              {[...new Set([symbol, ...BITUNIX_SYMBOLS])].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
          {!showSymbolPicker && (
            <span className="text-sm font-semibold text-mist-100 tnum">{symbol}</span>
          )}
          <span className="tnum text-sm text-mist-300">{fmtPrice(livePrice)}</span>
        </div>

        <div className="flex items-center bg-ink-800 border border-ink-500 rounded-lg p-0.5">
          {TIMEFRAMES.map(([code, label]) => (
            <button key={code}
              onClick={() => { setTf(code); localStorage.setItem(storageKey, code); }}
              className={`px-2.5 py-1 text-[11px] rounded-md transition ${
                tf === code ? "bg-ink-600 text-mist-100 font-semibold" : "text-mist-500"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* position chips — clicking one jumps the chart to that symbol.
          Rendered only when positions exist; their absence must never hide
          the chart itself. */}
      {positions.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          {positions.map((p) => {
            const on = p.key === selected?.key;
            const up = (p.pnl ?? 0) >= 0;
            return (
              <button key={p.key}
                onClick={() => { pickSymbol(p.symbol); setSelectedKey(p.key); }}
                className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs transition ${
                  on ? "border-gold bg-gold/10" : "border-ink-500 bg-ink-800 hover:border-ink-400"}`}>
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                  p.mode === "real" ? "bg-down/20 text-down" : "bg-up/20 text-up"}`}>
                  {p.mode === "real" ? t("pc_real") : t("pc_demo")}
                </span>
                <span className="font-semibold text-mist-100">{p.symbol}</span>
                <span className={p.isLong ? "text-up" : "text-down"}>
                  {p.side}{p.leverage ? ` ${p.leverage}x` : ""}
                </span>
                <span className={`tnum font-semibold ${up ? "text-up" : "text-down"}`}>
                  {up ? "+" : ""}{money(p.pnl)}
                </span>
              </button>
            );
          })}
          <span className="text-[11px] text-mist-500 ms-auto">
            {t("pc_demo")}:{" "}
            <span className={`tnum font-semibold ${totals.demo >= 0 ? "text-up" : "text-down"}`}>
              {totals.demo >= 0 ? "+" : ""}{money(totals.demo)}
            </span>
            <span className="mx-1.5">·</span>
            {t("pc_real")}:{" "}
            <span className={`tnum font-semibold ${totals.real >= 0 ? "text-up" : "text-down"}`}>
              {totals.real >= 0 ? "+" : ""}{money(totals.real)}
            </span>
          </span>
        </div>
      )}

      {err && <p className="text-down text-xs">{err}</p>}

      {/* chart + HUD */}
      <div className="relative rounded-xl overflow-hidden border border-ink-500 bg-ink-800">
        <div ref={boxRef} style={{ height: `${height}px` }} />

        {loading && !candles && (
          <div className="absolute inset-0 grid place-items-center text-xs text-mist-500">
            {t("loading_chart")}
          </div>
        )}

        {selected ? (
          <div className="absolute top-2 start-2 z-10 pointer-events-none
            bg-ink-900/85 backdrop-blur border border-ink-600 rounded-lg px-3 py-2 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-mist-100">{selected.symbol}</span>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                selected.isLong ? "bg-up/20 text-up" : "bg-down/20 text-down"}`}>
                {selected.side}{selected.leverage ? ` ${selected.leverage}x` : ""}
              </span>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                selected.mode === "real" ? "bg-down/20 text-down" : "bg-up/20 text-up"}`}>
                {selected.mode === "real" ? t("pc_real") : t("pc_demo")}
              </span>
            </div>
            <div className={`tnum text-lg font-bold leading-none ${
              (selected.pnl ?? 0) >= 0 ? "text-up" : "text-down"}`}>
              {(selected.pnl ?? 0) >= 0 ? "+" : ""}{money(selected.pnl)} USDT
              {selected.roe !== null && (
                <span className="text-xs ms-1.5 font-semibold">
                  ({selected.roe >= 0 ? "+" : ""}{money(selected.roe)}%)
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] tnum">
              <span style={{ color: COLORS.mark }}>{t("pc_mark")}: {fmtPrice(selected.mark ?? livePrice)}</span>
              <span style={{ color: COLORS.entry }}>{t("pc_entry")}: {fmtPrice(selected.entry)}</span>
              <span style={{ color: COLORS.tp }}>
                TP: {fmtPrice(selected.tp)}{toTp !== null && ` (${money(toTp)}%)`}
              </span>
              <span style={{ color: COLORS.sl }}>
                SL: {fmtPrice(selected.sl)}{toSl !== null && ` (${money(toSl)}%)`}
              </span>
              <span className="text-mist-500">{t("qty_coins")}: {money(selected.qty, 6)}</span>
              <span style={{ color: COLORS.liq }}>{t("pc_liq")}: {fmtPrice(selected.liq)}</span>
            </div>
          </div>
        ) : (
          /* no position on this symbol — plain chart, quiet price badge */
          <div className="absolute top-2 start-2 z-10 pointer-events-none
            bg-ink-900/80 backdrop-blur border border-ink-600 rounded-lg px-2.5 py-1.5">
            <span className="text-xs font-bold text-mist-100 tnum">{symbol}</span>
            <span className="tnum text-xs text-mist-300 ms-2">{fmtPrice(livePrice)}</span>
            <span className="block text-[10px] text-mist-600 mt-0.5">
              {t("pc_no_position_here")}
            </span>
          </div>
        )}
      </div>

      <p className="text-[10px] text-mist-600">{t("pc_display_only")}</p>
    </div>
  );
}

export default PositionChart;
