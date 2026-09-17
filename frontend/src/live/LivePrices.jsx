import {
  createContext, useContext, useEffect, useRef, useState, useCallback,
} from "react";
import { marketApi } from "../api/client.js";

/*
 * Live crypto prices, straight from the browser (independent of our backend).
 *  - Opens a Binance combined WebSocket for sub-second updates.
 *  - Seeds + falls back to Binance REST (CORS-enabled) when the socket is down.
 * Only crypto pairs (…USDT etc.) stream here; metals/forex fall back to the
 * server quote + the live TradingView chart.
 *
 * If Binance is blocked in your region, change WS_BASE / REST_BASE below to a
 * reachable mirror or another OpenAI-compatible exchange stream.
 */
const WS_BASE = "wss://stream.binance.com:9443/stream?streams=";
const REST_BASE = "https://api.binance.com/api/v3/ticker/24hr";

const Ctx = createContext(null);

export function isCryptoSymbol(sym) {
  const s = (sym || "").toUpperCase().replace(":PERP", "");
  return /^[A-Z0-9]{2,}(USDT|USDC|FDUSD|BTC|ETH|BNB)$/.test(s);
}

// Binance stream/REST want the bare pair (ETHUSDT), not our ETHUSDT:PERP label.
// Spot and perpetual share the same mark price closely enough for live P&L here.
export function baseSymbol(sym) {
  return (sym || "").toUpperCase().replace(":PERP", "");
}

export function LivePriceProvider({ children }) {
  const [prices, setPrices] = useState({}); // SYMBOL -> { price, changePercent, ts }
  const [status, setStatus] = useState("idle"); // idle | live | reconnecting
  const counts = useRef(new Map()); // SYMBOL -> refcount
  const [symbolsKey, setSymbolsKey] = useState("");
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const pollRef = useRef(null);

  const rebuild = useCallback(() => {
    const syms = [...counts.current.keys()].filter(isCryptoSymbol).sort();
    setSymbolsKey(syms.join(","));
  }, []);

  const subscribe = useCallback((sym) => {
    sym = baseSymbol(sym);
    if (!sym) return () => {};
    counts.current.set(sym, (counts.current.get(sym) || 0) + 1);
    rebuild();
    return () => {
      const n = (counts.current.get(sym) || 1) - 1;
      if (n <= 0) counts.current.delete(sym);
      else counts.current.set(sym, n);
      rebuild();
    };
  }, [rebuild]);

  // REST snapshot from the browser (seed + fallback).
  const fetchSnapshot = useCallback(async (syms) => {
    if (!syms.length) return;
    try {
      const q = encodeURIComponent(JSON.stringify(syms));
      const res = await fetch(`${REST_BASE}?symbols=${q}`);
      if (!res.ok) return;
      const data = await res.json();
      setPrices((p) => {
        const next = { ...p };
        for (const d of data) {
          next[d.symbol] = {
            price: parseFloat(d.lastPrice),
            changePercent: parseFloat(d.priceChangePercent),
            ts: Date.now(),
            src: "ws",
          };
        }
        return next;
      });
    } catch { /* ignore (blocked / offline) */ }
  }, []);

  useEffect(() => {
    clearTimeout(reconnectRef.current);
    clearInterval(pollRef.current);
    if (wsRef.current) { try { wsRef.current.close(); } catch { /* */ } wsRef.current = null; }

    const syms = symbolsKey ? symbolsKey.split(",") : [];
    if (syms.length === 0) { setStatus("idle"); return; }

    fetchSnapshot(syms); // immediate values

    let closed = false;
    function connect() {
      setStatus("reconnecting");
      const streams = syms.map((s) => `${s.toLowerCase()}@ticker`).join("/");
      let ws;
      try { ws = new WebSocket(WS_BASE + streams); }
      catch { startPolling(); return; }
      wsRef.current = ws;

      ws.onopen = () => { setStatus("live"); clearInterval(pollRef.current); };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          const d = msg.data || msg;
          if (d && d.s) {
            setPrices((p) => ({
              ...p,
              [d.s]: { price: parseFloat(d.c), changePercent: parseFloat(d.P), ts: Date.now(), src: "ws" },
            }));
          }
        } catch { /* */ }
      };
      ws.onclose = () => {
        if (closed) return;
        setStatus("reconnecting");
        startPolling();
        reconnectRef.current = setTimeout(connect, 4000);
      };
      ws.onerror = () => { try { ws.close(); } catch { /* */ } };
    }

    function startPolling() {
      clearInterval(pollRef.current);
      pollRef.current = setInterval(() => fetchSnapshot(syms), 12000);
    }

    connect();
    return () => {
      closed = true;
      clearTimeout(reconnectRef.current);
      clearInterval(pollRef.current);
      try { wsRef.current?.close(); } catch { /* */ }
    };
  }, [symbolsKey, fetchSnapshot]);

  // Poll our own backend every 12s for metals (and as a crypto fallback when the
  // browser can't reach Binance directly, e.g. in restricted regions). Crypto
  // values from a fresh WebSocket tick always take precedence.
  useEffect(() => {
    let timer;
    const poll = async () => {
      if (!localStorage.getItem("smartpips_token")) return;
      try {
        const quotes = await marketApi.quotes();
        const now = Date.now();
        setPrices((p) => {
          const next = { ...p };
          for (const q of quotes) {
            const sym = (q.symbol || "").toUpperCase();
            if (!sym || !Number.isFinite(q.price)) continue;
            const ex = next[sym];
            const wsFresh = ex && ex.src === "ws" && now - ex.ts < 15000;
            if (!wsFresh) {
              next[sym] = {
                price: q.price,
                changePercent: q.change_percent,
                ts: now,
                src: "backend",
              };
            }
          }
          return next;
        });
      } catch { /* not logged in yet / offline */ }
    };
    poll();
    timer = setInterval(poll, 12000);
    return () => clearInterval(timer);
  }, []);

  // Metals fallback straight from the browser. Now gated two ways so it does
  // NOT flood the server: (1) skipped entirely when the user has no metals
  // access, (2) paused when the browser tab is hidden. This is the XAU/XAG
  // request storm the user saw in DevTools.
  useEffect(() => {
    let timer = null;
    let metalsAllowed = true;   // default on until we learn otherwise
    // read the user's access once; the flag is cached by the prefs endpoint
    import("../api/client.js")
      .then(({ prefsApi }) => prefsApi.myAccess())
      .then((a) => { metalsAllowed = a?.metals !== false; if (!metalsAllowed) stop(); })
      .catch(() => {});

    const pull = async () => {
      if (!metalsAllowed) return;
      const out = {};
      await Promise.all(
        [["XAUUSD", "XAU"], ["XAGUSD", "XAG"]].map(async ([sym, code]) => {
          try {
            const r = await fetch(`https://api.gold-api.com/price/${code}`);
            if (!r.ok) return;
            const p = parseFloat((await r.json()).price);
            if (Number.isFinite(p)) out[sym] = p;
          } catch { /* ignore */ }
        })
      );
      if (Object.keys(out).length) {
        const now = Date.now();
        setPrices((p) => {
          const next = { ...p };
          for (const [sym, price] of Object.entries(out)) {
            const ex = next[sym];
            if (!ex || now - ex.ts > 4000) {
              next[sym] = { price, changePercent: ex?.changePercent ?? 0, ts: now, src: "metal" };
            }
          }
          return next;
        });
      }
    };
    const start = () => { if (timer == null && metalsAllowed && !document.hidden) { pull(); timer = setInterval(pull, 15000); } };
    const stop = () => { if (timer != null) { clearInterval(timer); timer = null; } };
    const onVis = () => (document.hidden ? stop() : start());
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
  }, []);

  return (
    <Ctx.Provider value={{ prices, status, subscribe }}>
      {children}
    </Ctx.Provider>
  );
}

export function useLiveCtx() {
  return useContext(Ctx);
}

// Subscribe to a single symbol; returns { price, changePercent } or null.
export function useLivePrice(symbol) {
  const ctx = useContext(Ctx);
  useEffect(() => {
    if (!ctx || !symbol) return undefined;
    return ctx.subscribe(symbol);
  }, [ctx, symbol]);
  return ctx?.prices?.[(symbol || "").toUpperCase()] || null;
}

// Subscribe to a list of symbols; returns the whole price map.
export function useLivePricesFor(symbols) {
  const ctx = useContext(Ctx);
  const key = (symbols || []).map((s) => (s || "").toUpperCase()).sort().join(",");
  useEffect(() => {
    if (!ctx) return undefined;
    const unsubs = (symbols || []).map((s) => ctx.subscribe(s));
    return () => unsubs.forEach((u) => u && u());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx, key]);
  return ctx?.prices || {};
}
