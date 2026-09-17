import { useMemo, useState } from "react";
import { Panel, Button } from "./ui.jsx";
import { useI18n } from "../i18n/index.jsx";
import { buildXlsxBlob, buildCsvBlob, downloadBlob, timestampSlug } from "../lib/export.js";

/* Every trade -- journal, assistant, bitunix demo, bitunix real -- in one
   filterable view, with stats recomputed for the current filter.

   Desktop keeps the dense table a trading journal wants. Mobile gets real
   cards instead: a nine-column table on a 390px screen is either unreadable
   or forces the page to scroll sideways, and the brief forbids both. */

export const SOURCE_LABELS = {
  manual: "src_manual",
  assistant: "src_assistant",
  bitunix_demo: "src_bx_demo",
  bitunix_real: "src_bx_real",
};

const BADGE_TONE = {
  bitunix_real: "bg-down/15 text-down",
  bitunix_demo: "bg-up/15 text-up",
  assistant: "bg-gold/15 text-gold-soft",
  manual: "bg-ink-600 text-mist-300",
};

function fmt(n) {
  if (n == null || n === "") return "\u2014";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 4 });
}

function signed(n) {
  if (n == null) return "\u2014";
  return `${n >= 0 ? "+" : ""}${fmt(n)}`;
}

function num(v) {
  // Export helper: keep real numbers numeric so Excel can sum and sort them,
  // and leave blanks blank rather than writing the string "null".
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function durationLabel(a, b) {
  if (!a || !b) return null;
  const ms = new Date(b) - new Date(a);
  if (!Number.isFinite(ms) || ms < 0) return null;
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ${mins % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

function Mini({ label, value, tone = "neutral" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="min-w-0 bg-ink-800 border border-ink-500 rounded-lg px-3 py-2">
      <p className="text-[11px] text-mist-500 truncate">{label}</p>
      <p className={`tnum text-base font-semibold mt-0.5 truncate ${color}`}>{value}</p>
    </div>
  );
}

export function AllTradesPanel({ trades }) {
  const { t } = useI18n();
  const [src, setSrc] = useState("all");
  const [dir, setDir] = useState("all");
  const [status, setStatus] = useState("all");
  const [sym, setSym] = useState("");
  const [detail, setDetail] = useState(null);

  const q = sym.trim().toUpperCase();
  const rows = useMemo(
    () =>
      trades.filter(
        (tr) =>
          (src === "all" || (tr.source || "manual") === src) &&
          (dir === "all" || tr.direction === dir) &&
          (status === "all" || tr.status === status) &&
          (!q || (tr.symbol || "").toUpperCase().includes(q)),
      ),
    [trades, src, dir, status, q],
  );

  const closed = rows.filter((r) => r.status === "closed");
  const wins = closed.filter((r) => (r.pnl ?? 0) > 0);
  const pnlSum = closed.reduce((a, r) => a + (r.pnl ?? 0), 0);
  const winRate = closed.length ? Math.round((wins.length / closed.length) * 100) : null;

  /* ---- export -------------------------------------------------------- */

  // Only fields the Trade model actually stores. Nothing here is invented,
  // and the rows are whatever the active filter produced -- so an export of
  // "BTCUSDT / long / closed / Bitunix real" contains exactly those trades.
  const exportColumns = [
    { key: "id", label: t("f_trade_id") },
    { key: "symbol", label: "Symbol" },
    { key: "source", label: t("f_source") },
    { key: "direction", label: t("lbank_side") },
    { key: "status", label: t("f_status") },
    { key: "entry_price", label: t("entry") },
    { key: "exit_price", label: t("f_exit") },
    { key: "size", label: t("f_size") },
    { key: "leverage", label: t("bx_leverage") },
    { key: "pnl", label: "PnL" },
    { key: "pnl_percent", label: t("f_pnl_pct") },
    { key: "realized_pnl", label: t("f_realized") },
    { key: "take_profit", label: t("f_tp") },
    { key: "stop_loss", label: t("f_sl") },
    { key: "tp1_price", label: "TP1" },
    { key: "tp2_price", label: "TP2" },
    { key: "tp3_price", label: "TP3" },
    { key: "remaining_pct", label: t("f_remaining") },
    { key: "setup_class", label: t("f_setup") },
    // Strategy attribution: recorded on the trade at creation time, so the
    // export answers "which strategy produced this?" without a join.
    { key: "strategy_name", label: t("tr_strategy") },
    { key: "strategy_version", label: `${t("tr_strategy")} v` },
    { key: "timeframe", label: t("tr_timeframe") },
    { key: "confidence", label: t("tr_confidence") },
    { key: "exit_reason", label: t("tr_exit_reason") },
    { key: "opened_at", label: t("opened_at") },
    { key: "closed_at", label: t("f_closed_at") },
    { key: "duration", label: t("f_duration") },
    { key: "notes", label: t("f_notes") },
  ];

  const exportRows = () =>
    rows.map((tr) => ({
      id: tr.id,
      symbol: tr.symbol || "",
      source: t(SOURCE_LABELS[tr.source] || "src_manual"),
      direction: tr.direction === "long" ? t("j_long") : t("j_short"),
      status: tr.status === "open" ? t("open_trades") : t("closed_trades"),
      entry_price: num(tr.entry_price),
      exit_price: num(tr.exit_price),
      size: num(tr.size),
      leverage: num(tr.leverage),
      pnl: num(tr.pnl),
      pnl_percent: num(tr.pnl_percent),
      realized_pnl: num(tr.realized_pnl),
      take_profit: num(tr.take_profit),
      stop_loss: num(tr.stop_loss),
      tp1_price: num(tr.tp1_price),
      tp2_price: num(tr.tp2_price),
      tp3_price: num(tr.tp3_price),
      remaining_pct: num(tr.remaining_pct),
      setup_class: tr.setup_class || "",
      opened_at: tr.opened_at ? new Date(tr.opened_at).toISOString() : "",
      closed_at: tr.closed_at ? new Date(tr.closed_at).toISOString() : "",
      duration: durationLabel(tr.opened_at, tr.closed_at) || "",
      notes: tr.notes || "",
    }));

  const doExport = (kind) => {
    const data = exportRows();
    const name = `smartpips-trades-${timestampSlug()}`;
    if (kind === "xlsx") {
      downloadBlob(buildXlsxBlob("Trades", exportColumns, data), `${name}.xlsx`);
    } else {
      downloadBlob(buildCsvBlob(exportColumns, data), `${name}.csv`);
    }
  };

  /* ---- render -------------------------------------------------------- */

  const chip = (on) =>
    `shrink-0 text-xs px-2.5 py-1 rounded-md border transition ${
      on ? "bg-ink-600 text-mist-100 border-ink-500" : "text-mist-500 border-transparent hover:text-mist-300"
    }`;
  const td = "px-2 py-1.5 text-[12px] tnum whitespace-nowrap";

  const exportBar = (
    <div className="flex items-center gap-2">
      <Button variant="ghost" className="px-2.5 py-1.5 text-xs" disabled={!rows.length} onClick={() => doExport("xlsx")}>
        {t("export_xlsx")}
      </Button>
      <Button variant="ghost" className="px-2.5 py-1.5 text-xs" disabled={!rows.length} onClick={() => doExport("csv")}>
        {t("export_csv")}
      </Button>
    </div>
  );

  return (
    <Panel title={t("all_trades")} action={exportBar}>
      {/* Filters scroll inside their own rail on narrow screens; the page
          itself must never gain a horizontal scrollbar. */}
      <div className="-mx-1 mb-3 overflow-x-auto px-1 pb-1">
        <div className="flex w-max items-center gap-2">
          <div className="flex items-center gap-1 bg-ink-800 rounded-lg p-0.5">
            {["all", "manual", "assistant", "bitunix_demo", "bitunix_real"].map((s) => (
              <button key={s} onClick={() => setSrc(s)} className={chip(src === s)}>
                {s === "all" ? t("f_all") : t(SOURCE_LABELS[s])}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 bg-ink-800 rounded-lg p-0.5">
            {["all", "long", "short"].map((d) => (
              <button key={d} onClick={() => setDir(d)} className={chip(dir === d)}>
                {d === "all" ? t("f_all") : d === "long" ? t("j_long") : t("j_short")}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 bg-ink-800 rounded-lg p-0.5">
            {["all", "open", "closed"].map((s) => (
              <button key={s} onClick={() => setStatus(s)} className={chip(status === s)}>
                {s === "all" ? t("f_all") : s === "open" ? t("open_trades") : t("closed_trades")}
              </button>
            ))}
          </div>
          <input
            value={sym}
            onChange={(e) => setSym(e.target.value)}
            placeholder={t("f_symbol")}
            className="w-28 shrink-0 rounded-md border border-ink-500 bg-ink-800 px-2 py-1.5 text-xs text-mist-200"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <Mini label={t("f_count")} value={rows.length} />
        <Mini label={t("closed_trades")} value={closed.length} />
        <Mini
          label={t("total_pnl")}
          value={closed.length ? signed(pnlSum) : "\u2014"}
          tone={pnlSum >= 0 ? "up" : "down"}
        />
        <Mini
          label={t("win_rate")}
          value={winRate == null ? "\u2014" : `${winRate}%`}
          tone={(winRate ?? 0) >= 50 ? "up" : "down"}
        />
      </div>

      {rows.length ? (
        <>
          {/* mobile: cards */}
          <div className="space-y-2 md:hidden">
            {rows.slice(0, 100).map((tr) => (
              <button
                key={tr.id}
                onClick={() => setDetail(tr)}
                className="w-full rounded-xl border border-ink-600 bg-ink-800/60 p-3 text-start transition active:scale-[0.995]"
              >
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-semibold text-mist-100">{tr.symbol}</span>
                    <span className={`text-[11px] font-medium ${tr.direction === "long" ? "text-up" : "text-down"}`}>
                      {tr.direction === "long" ? t("j_long") : t("j_short")}
                    </span>
                  </div>
                  <span
                    className={`tnum shrink-0 text-sm font-semibold ${(tr.pnl ?? 0) >= 0 ? "text-up" : "text-down"}`}
                  >
                    {tr.pnl != null ? signed(tr.pnl) : "\u2014"}
                  </span>
                </div>

                <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                  <div className="min-w-0">
                    <p className="text-mist-500">{t("entry")}</p>
                    <p className="tnum truncate text-mist-200">{fmt(tr.entry_price)}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-mist-500">{t("f_exit")}</p>
                    <p className="tnum truncate text-mist-200">
                      {tr.exit_price != null ? fmt(tr.exit_price) : "\u2014"}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-mist-500">{t("bx_leverage")}</p>
                    <p className="tnum truncate text-mist-200">{tr.leverage ? `${tr.leverage}x` : "\u2014"}</p>
                  </div>
                </div>

                <div className="mt-2 flex min-w-0 flex-wrap items-center gap-1.5">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${BADGE_TONE[tr.source] || BADGE_TONE.manual}`}>
                    {t(SOURCE_LABELS[tr.source] || "src_manual")}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] ${
                      tr.status === "open" ? "bg-gold/10 text-gold-soft" : "bg-ink-600 text-mist-500"
                    }`}
                  >
                    {tr.status === "open" ? t("open_trades") : t("closed_trades")}
                  </span>
                  <span className="truncate text-[10px] text-mist-500">
                    {tr.opened_at ? new Date(tr.opened_at).toLocaleString() : "\u2014"}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* desktop: table */}
          <div className="hidden overflow-x-auto rounded-lg border border-ink-600 md:block">
            <table className="w-full">
              <thead className="bg-ink-800">
                <tr>
                  {[
                    t("f_source"),
                    "symbol",
                    t("lbank_side"),
                    t("entry"),
                    t("f_exit"),
                    t("bx_leverage"),
                    "PnL",
                    t("f_status"),
                    t("opened_at"),
                    "",
                  ].map((h, i) => (
                    <th key={`${h}-${i}`} className="px-2 py-1.5 text-start text-[11px] font-normal text-mist-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 100).map((tr) => (
                  <tr
                    key={tr.id}
                    onClick={() => setDetail(tr)}
                    className="cursor-pointer border-t border-ink-700 transition hover:bg-ink-800/60"
                  >
                    <td className={td}>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${BADGE_TONE[tr.source] || BADGE_TONE.manual}`}>
                        {t(SOURCE_LABELS[tr.source] || "src_manual")}
                      </span>
                    </td>
                    <td className={`${td} font-semibold text-mist-100`}>{tr.symbol}</td>
                    <td className={`${td} ${tr.direction === "long" ? "text-up" : "text-down"}`}>
                      {tr.direction === "long" ? t("j_long") : t("j_short")}
                    </td>
                    <td className={`${td} text-mist-300`}>{fmt(tr.entry_price)}</td>
                    <td className={`${td} text-mist-300`}>{tr.exit_price != null ? fmt(tr.exit_price) : "\u2014"}</td>
                    <td className={`${td} text-mist-300`}>{tr.leverage ? `${tr.leverage}x` : "\u2014"}</td>
                    <td className={`${td} font-semibold ${(tr.pnl ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                      {tr.pnl != null ? signed(tr.pnl) : "\u2014"}
                    </td>
                    <td className={`${td} ${tr.status === "open" ? "text-gold-soft" : "text-mist-500"}`}>
                      {tr.status === "open" ? t("open_trades") : t("closed_trades")}
                    </td>
                    <td className={`${td} text-mist-500`}>
                      {tr.opened_at ? new Date(tr.opened_at).toLocaleString() : "\u2014"}
                    </td>
                    <td className={`${td} text-mist-500`}>{t("f_view")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-2 text-[11px] text-mist-500">
            {t("f_showing")} {Math.min(rows.length, 100)}/{rows.length} · {t("td_export_note")}
          </p>
        </>
      ) : (
        <p className="text-xs text-mist-500">{t("f_empty")}</p>
      )}

      {detail && <TradeDetail trade={detail} onClose={() => setDetail(null)} />}
    </Panel>
  );
}

/* Detail sheet. Every row below maps to a field the backend actually returns;
   anything the model does not store is simply absent rather than faked. */
function TradeDetail({ trade, onClose }) {
  const { t } = useI18n();

  const Row = ({ label, value, tone }) => {
    if (value == null || value === "" || value === "\u2014") return null;
    const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
    return (
      <div className="flex items-start justify-between gap-3 border-b border-ink-700/60 py-2">
        <span className="shrink-0 text-[12px] text-mist-500">{label}</span>
        <span className={`tnum min-w-0 break-words text-end text-[13px] font-medium ${color}`}>{value}</span>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative max-h-[85vh] w-full overflow-y-auto rounded-t-2xl border border-ink-500 bg-ink-800 shadow-2xl sm:max-w-lg sm:rounded-2xl">
        <header className="sticky top-0 flex items-center justify-between gap-3 border-b border-ink-500 bg-ink-800 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-mist-100">{trade.symbol}</p>
            <p className="text-[11px] text-mist-500">{t("td_details")}</p>
          </div>
          <button onClick={onClose} className="shrink-0 px-2 py-1 text-sm text-mist-500">
            {t("cancel")}
          </button>
        </header>

        <div className="px-4 pb-5">
          <Row label={t("f_trade_id")} value={trade.id} />
          <Row label={t("f_source")} value={t(SOURCE_LABELS[trade.source] || "src_manual")} />
          <Row
            label={t("lbank_side")}
            value={trade.direction === "long" ? t("j_long") : t("j_short")}
            tone={trade.direction === "long" ? "up" : "down"}
          />
          <Row label={t("f_status")} value={trade.status === "open" ? t("open_trades") : t("closed_trades")} />
          <Row label={t("entry")} value={fmt(trade.entry_price)} />
          <Row label={t("f_exit")} value={trade.exit_price != null ? fmt(trade.exit_price) : null} />
          <Row label={t("f_size")} value={trade.size ? fmt(trade.size) : null} />
          <Row label={t("bx_leverage")} value={trade.leverage ? `${trade.leverage}x` : null} />
          <Row
            label="PnL"
            value={trade.pnl != null ? signed(trade.pnl) : null}
            tone={(trade.pnl ?? 0) >= 0 ? "up" : "down"}
          />
          <Row
            label={t("f_pnl_pct")}
            value={trade.pnl_percent != null ? `${signed(trade.pnl_percent)}%` : null}
            tone={(trade.pnl_percent ?? 0) >= 0 ? "up" : "down"}
          />
          <Row label={t("f_realized")} value={trade.realized_pnl ? signed(trade.realized_pnl) : null} />
          <Row label={t("f_tp")} value={trade.take_profit != null ? fmt(trade.take_profit) : null} />
          <Row label={t("f_sl")} value={trade.stop_loss != null ? fmt(trade.stop_loss) : null} />
          <Row
            label="TP1"
            value={trade.tp1_price != null ? `${fmt(trade.tp1_price)} \u00b7 ${trade.tp1_pct}%${trade.tp1_done ? " \u2713" : ""}` : null}
          />
          <Row
            label="TP2"
            value={trade.tp2_price != null ? `${fmt(trade.tp2_price)} \u00b7 ${trade.tp2_pct}%${trade.tp2_done ? " \u2713" : ""}` : null}
          />
          <Row
            label="TP3"
            value={trade.tp3_price != null ? `${fmt(trade.tp3_price)} \u00b7 ${trade.tp3_pct}%${trade.tp3_done ? " \u2713" : ""}` : null}
          />
          <Row
            label={t("f_remaining")}
            value={trade.remaining_pct != null ? `${trade.remaining_pct}%` : null}
          />
          <Row label={t("f_setup")} value={trade.setup_class || null} />
          <Row
            label={t("tr_strategy")}
            value={
              trade.strategy_name
                ? trade.strategy_version
                  ? `${trade.strategy_name} v${trade.strategy_version}`
                  : trade.strategy_name
                : null
            }
          />
          <Row label={t("tr_timeframe")} value={trade.timeframe || null} />
          <Row
            label={t("tr_confidence")}
            value={trade.confidence != null ? `${trade.confidence}%` : null}
          />
          <Row label={t("tr_exit_reason")} value={trade.exit_reason || null} />
          <Row label={t("opened_at")} value={trade.opened_at ? new Date(trade.opened_at).toLocaleString() : null} />
          <Row label={t("f_closed_at")} value={trade.closed_at ? new Date(trade.closed_at).toLocaleString() : null} />
          <Row label={t("f_duration")} value={durationLabel(trade.opened_at, trade.closed_at)} />
          <Row label={t("f_notes")} value={trade.notes || null} />
        </div>
      </div>
    </div>
  );
}
