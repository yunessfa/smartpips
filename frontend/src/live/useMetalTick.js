import { useEffect, useRef, useState } from "react";
import { marketApi } from "../api/client.js";

// gold-api codes for a browser-side fallback (it allows CORS).
const GOLD_CODE = { XAUUSD: "XAU", XAGUSD: "XAG" };
const CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

async function fetchFromBackend(symbol) {
  try {
    const res = await marketApi.metal(symbol);
    if (res && res.ok && Number.isFinite(res.price)) return res.price;
  } catch { /* fall through */ }
  return null;
}

async function fetchFromGoldApi(symbol) {
  const code = GOLD_CODE[symbol];
  if (!code) return null;
  try {
    const res = await fetch(`https://api.gold-api.com/price/${code}`);
    if (!res.ok) return null;
    const data = await res.json();
    const p = parseFloat(data.price);
    return Number.isFinite(p) ? p : null;
  } catch { return null; }
}

// Browser fallback for crypto: Binance spot or USD-M futures ticker (CORS-enabled).
async function fetchFromBinance(symbol) {
  const isPerp = symbol.endsWith(":PERP");
  const base = symbol.replace(":PERP", "");
  if (!CRYPTO.includes(base)) return null;
  const host = isPerp
    ? `https://fapi.binance.com/fapi/v1/ticker/price?symbol=${base}`
    : `https://api.binance.com/api/v3/ticker/price?symbol=${base}`;
  try {
    const res = await fetch(host);
    if (!res.ok) return null;
    const data = await res.json();
    const p = parseFloat(data.price);
    return Number.isFinite(p) ? p : null;
  } catch { return null; }
}

/*
 * Fast metal tick for scalping. Polls our backend (~1.5s); if that fails it tries
 * gold-api.com directly from the browser. Keeps a rolling price series.
 */
export function useMetalTick(symbol, { intervalMs = 1500, history = 150 } = {}) {
  const [price, setPrice] = useState(null);
  const [series, setSeries] = useState([]);
  const [status, setStatus] = useState("connecting");
  const seriesRef = useRef([]);

  useEffect(() => {
    seriesRef.current = [];
    setSeries([]);
    setPrice(null);
    setStatus("connecting");
    let stop = false;
    let timer;

    async function tick() {
      let p = await fetchFromBackend(symbol);
      if (p == null) p = await fetchFromBinance(symbol);
      if (p == null) p = await fetchFromGoldApi(symbol);
      if (stop) return;
      if (Number.isFinite(p)) {
        setPrice(p);
        setStatus("live");
        const next = [...seriesRef.current, p].slice(-history);
        seriesRef.current = next;
        setSeries(next);
      } else {
        setStatus("unavailable");
      }
    }

    tick();
    // pause polling while the tab is hidden — no reason to hammer the server
    // every second when the user isn't looking.
    const startTimer = () => { if (!timer) timer = setInterval(tick, intervalMs); };
    const stopTimer = () => { if (timer) { clearInterval(timer); timer = null; } };
    const onVis = () => { if (document.hidden) stopTimer(); else { tick(); startTimer(); } };
    if (!document.hidden) startTimer();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop = true; stopTimer(); document.removeEventListener("visibilitychange", onVis); };
  }, [symbol, intervalMs, history]);

  return { price, series, status };
}
