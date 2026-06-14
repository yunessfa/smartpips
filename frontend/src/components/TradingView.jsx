import { useEffect, useRef } from "react";

// Map our indicator keys -> TradingView built-in study IDs.
const STUDY_MAP = {
  rsi: "STD;RSI",
  macd: "STD;MACD",
  ema: "STD;EMA",
  sma: "STD;SMA",
  bollinger: "STD;Bollinger_Bands",
  stoch: "STD;Stochastic",
  ichimoku: "STD;Ichimoku%1Cloud",
  volume: "STD;Volume",
};

export function indicatorsToStudies(indicators = []) {
  const studies = [];
  for (const ind of indicators) {
    const id = STUDY_MAP[ind.key];
    if (id && !studies.includes(id)) studies.push(id);
  }
  return studies;
}

// Resolve a robust TradingView symbol from a recommendation, fixing common
// mistakes (e.g. metals wrongly placed on BINANCE, which renders a blank chart).
const SYMBOL_FIXES = {
  XAUUSD: "TVC:GOLD", GOLD: "TVC:GOLD", XAU: "TVC:GOLD",
  XAGUSD: "TVC:SILVER", SILVER: "TVC:SILVER", XAG: "TVC:SILVER",
  WTI: "TVC:USOIL", OIL: "TVC:USOIL", USOIL: "TVC:USOIL",
};

export function resolveTVSymbol(rec) {
  const sym = String(rec?.symbol || "").toUpperCase().replace(/\s/g, "");
  const raw = String(rec?.tradingview_symbol || "").trim();

  if (SYMBOL_FIXES[sym]) return SYMBOL_FIXES[sym];

  // A non-crypto symbol mistakenly prefixed with BINANCE -> repair it.
  const isMetalLike = /XAU|XAG|GOLD|SILVER|USOIL|WTI/.test(raw.toUpperCase());
  if (raw && raw.includes(":") && !isMetalLike) return raw;
  if (isMetalLike) {
    if (/XAU|GOLD/.test(raw.toUpperCase())) return "TVC:GOLD";
    if (/XAG|SILVER/.test(raw.toUpperCase())) return "TVC:SILVER";
  }

  if (sym.endsWith("USDT")) return `BINANCE:${sym}`;
  if (sym.endsWith("USD")) return `OANDA:${sym}`;
  return raw || (sym ? `BINANCE:${sym}` : "BINANCE:BTCUSDT");
}

// Injects a TradingView embed. Key fix: the wrapper has an explicit pixel height
// (and matching minHeight) so the chart can never collapse to zero height.
function TVEmbed({ src, config, height = 460 }) {
  const ref = useRef(null);

  useEffect(() => {
    const container = ref.current;
    if (!container) return;
    container.innerHTML = "";

    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    widget.style.height = "100%";
    widget.style.width = "100%";
    container.appendChild(widget);

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.type = "text/javascript";
    script.innerHTML = JSON.stringify(config);
    container.appendChild(script);

    return () => { container.innerHTML = ""; };
  }, [src, JSON.stringify(config)]);

  return (
    <div
      ref={ref}
      className="tradingview-widget-container w-full rounded-xl overflow-hidden border border-ink-500 bg-ink-800"
      style={{ height: `${height}px`, minHeight: `${height}px` }}
    />
  );
}

export function AdvancedChart({ symbol, height = 500, interval = "240", studies = [] }) {
  return (
    <TVEmbed
      height={height}
      src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
      config={{
        autosize: true,
        symbol,
        interval,
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        backgroundColor: "rgba(16, 20, 30, 1)",
        gridColor: "rgba(34, 42, 58, 0.5)",
        hide_top_toolbar: false,
        hide_legend: false,
        allow_symbol_change: false,
        calendar: false,
        withdateranges: true,
        studies,
        support_host: "https://www.tradingview.com",
      }}
    />
  );
}

export function MiniChart({ symbol, height = 220 }) {
  return (
    <TVEmbed
      height={height}
      src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js"
      config={{
        symbol,
        width: "100%",
        height: "100%",
        locale: "en",
        dateRange: "3M",
        colorTheme: "dark",
        isTransparent: true,
        autosize: true,
        chartOnly: false,
      }}
    />
  );
}

// Compact advanced chart with indicators, used inside chat recommendation cards.
export function SignalChart({ symbol, studies = [], height = 260 }) {
  return (
    <TVEmbed
      height={height}
      src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
      config={{
        autosize: true,
        symbol,
        interval: "240",
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        backgroundColor: "rgba(16, 20, 30, 1)",
        gridColor: "rgba(34, 42, 58, 0.5)",
        hide_top_toolbar: true,
        hide_legend: false,
        allow_symbol_change: false,
        calendar: false,
        studies,
        support_host: "https://www.tradingview.com",
      }}
    />
  );
}

export function TickerTape({ symbols }) {
  return (
    <TVEmbed
      height={46}
      src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js"
      config={{
        symbols: symbols.map((s) => ({ proName: s.proName, title: s.title })),
        showSymbolLogo: true,
        colorTheme: "dark",
        isTransparent: true,
        displayMode: "compact",
        locale: "en",
      }}
    />
  );
}
