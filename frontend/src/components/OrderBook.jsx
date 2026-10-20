import { useEffect, useRef, useState } from "react";
import { Panel } from "./ui.jsx";
import { bitunixApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { fmtPrice } from "../lib/num.js";

/**
 * Exchange-style order book (asks on top in red, spread row, bids below in
 * green, depth bars behind sizes) — data from LBank's public futures depth.
 * Rendered only for crypto symbols; metals have no public order book.
 */
const ROWS = 8;
const POLL_MS = 3000;

function normalizeSide(side) {
  // rows arrive either as [price, qty] pairs or as {price, qty} objects —
  // our backend proxy sends {price, qty} (the DevTools capture confirmed it;
  // reading r.volume here was why the book stayed empty forever).
  return (side || [])
    .map((r) => ({ price: Number(r[0] ?? r.price), qty: Number(r[1] ?? r.qty ?? r.volume) }))
    .filter((r) => Number.isFinite(r.price) && Number.isFinite(r.qty));
}

export function OrderBook({ symbol, lastPrice }) {
  const { t } = useI18n();
  const [book, setBook] = useState(null);
  const [err, setErr] = useState(null);
  const timer = useRef(null);
  const lbSymbol = symbol.toUpperCase().replace(":PERP", "");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        // depth comes from Bitunix — the venue we actually execute on — so
        // the book you see is the book your order hits.
        const res = await bitunixApi.depth(lbSymbol, 15);
        if (!alive) return;
        const d = res.book || {};
        const asks = normalizeSide(d.asks).sort((a, b) => a.price - b.price).slice(0, ROWS);
        const bids = normalizeSide(d.bids).sort((a, b) => b.price - a.price).slice(0, ROWS);
        if (asks.length || bids.length) { setBook({ asks, bids }); setErr(null); }
      } catch (e) { if (alive) setErr(e.message); }
    }
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer.current); };
  }, [lbSymbol]);

  if (err && !book) {
    return (
      <Panel title={t("order_book")}>
        <p className="text-xs text-mist-500">{t("order_book_unavailable")}</p>
      </Panel>
    );
  }
  if (!book) {
    return (
      <Panel title={t("order_book")}>
        <p className="text-xs text-mist-500">
          {err ? t("order_book_unavailable") : "…"}
        </p>
        {err && <p className="text-[10px] text-down mt-1 break-all">{err}</p>}
      </Panel>
    );
  }

  const maxQty = Math.max(...book.asks.map((r) => r.qty), ...book.bids.map((r) => r.qty), 1);
  const bestAsk = book.asks[0]?.price;
  const bestBid = book.bids[0]?.price;
  const spread = bestAsk && bestBid ? bestAsk - bestBid : null;
  const mid = lastPrice ?? (bestAsk && bestBid ? (bestAsk + bestBid) / 2 : null);

  const Row = ({ r, tone }) => (
    <div className="relative flex items-center justify-between px-2 py-[3px] text-[11px]">
      <span className={`depth-bar ${tone === "up" ? "bg-up end-0" : "bg-down end-0"}`}
        style={{ width: `${Math.min(100, (r.qty / maxQty) * 100)}%` }} />
      <span className={`tnum relative ${tone === "up" ? "text-up" : "text-down"}`}>{fmtPrice(r.price)}</span>
      <span className="tnum relative text-mist-300">{r.qty >= 1000 ? `${(r.qty / 1000).toFixed(1)}K` : r.qty}</span>
    </div>
  );

  return (
    <Panel title={`${t("order_book")} · ${lbSymbol}`}>
      <div className="-m-2">
        <div className="flex items-center justify-between px-2 pb-1 text-[10px] text-mist-500">
          <span>{t("price_col")} (USDT)</span><span>{t("amount_col")}</span>
        </div>
        {/* asks: lowest ask nearest the middle */}
        <div className="flex flex-col-reverse">
          {book.asks.map((r) => <Row key={`a${r.price}`} r={r} tone="down" />)}
        </div>
        {/* spread / last price row */}
        <div className="flex items-center justify-between px-2 py-1.5 my-0.5 bg-ink-800 rounded">
          <span className="tnum text-sm font-semibold text-mist-100">{mid ? fmtPrice(mid) : "—"}</span>
          {spread != null && (
            <span className="tnum text-[10px] text-mist-500">{t("spread")}: {fmtPrice(spread)}</span>
          )}
        </div>
        {book.bids.map((r) => <Row key={`b${r.price}`} r={r} tone="up" />)}
      </div>
    </Panel>
  );
}
