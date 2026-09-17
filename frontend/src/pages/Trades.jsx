import { useEffect, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel } from "../components/ui.jsx";
import { TradingAccountPanel } from "../components/TradingAccountPanel.jsx";
import { tradesApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { AllTradesPanel } from "../components/TradeJournalTable.jsx";

function fmt(n) {
  if (n == null || n === "") return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export default function Trades() {
  const { t } = useI18n();
  const [stats, setStats] = useState(null);
  const [profile, setProfile] = useState(null);
  const [trades, setTrades] = useState([]);
  const balance = localStorage.getItem("sp_balance") || "";

  useEffect(() => {
    tradesApi.stats().then(setStats).catch(() => {});
    tradesApi.profile().then(setProfile).catch(() => {});
    tradesApi.list().then((rows) => setTrades(Array.isArray(rows) ? rows : rows?.results || [])).catch(() => {});
  }, []);

  return (
    <>
      <PageHeader title={t("trades_title")} subtitle={t("trades_sub")} />
      <div className="flex-1 overflow-y-auto min-h-0 p-4 md:p-6 space-y-6">
        {/* overall — every trade from every source */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Stat label={t("open_trades")} value={stats?.open ?? "—"} />
          <Stat label={t("closed_trades")} value={stats?.closed ?? "—"} />
          <Stat label={t("total_pnl")} value={stats ? `${stats.total_pnl >= 0 ? "+" : ""}${fmt(stats.total_pnl)}` : "—"} tone={stats && stats.total_pnl >= 0 ? "up" : "down"} />
          <Stat label={t("win_rate")} value={stats ? `${stats.win_rate}%` : "—"} />
        </div>

        <AllTradesPanel trades={trades} />

        <ProfilePanel profile={profile} />
        <JournalPanel />

        <TradingAccountPanel balance={balance} />
      </div>
    </>
  );
}


function Stat({ label, value, tone = "neutral" }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-mist-100";
  return (
    <div className="bg-ink-700 border border-ink-500 rounded-xl px-4 py-3 shadow-panel">
      <p className="text-xs text-mist-500">{label}</p>
      <p className={`tnum text-2xl font-semibold mt-1 ${color}`}>{value}</p>
    </div>
  );
}

function JournalPanel() {
  const { t } = useI18n();
  const [j, setJ] = useState(null);
  useEffect(() => { tradesApi.journal().then(setJ).catch(() => {}); }, []);
  if (!j) return null;
  if (!j.enough) {
    return (
      <Panel title={t("journal")}>
        <p className="text-sm text-mist-500">{t("journal_need")} ({j.trades}/{j.min_trades})</p>
      </Panel>
    );
  }
  const o = j.overall;
  const SessRow = ({ name, st }) => (
    <div className="flex items-center justify-between text-sm py-1.5 border-b border-ink-600/40">
      <span className="text-mist-300">{name}</span>
      <span className="flex items-center gap-3 tnum">
        <span className={st.win_rate >= 50 ? "text-up" : "text-down"}>{st.win_rate}%</span>
        <span className="text-mist-500 text-xs">{st.trades} {t("nav_trades").toLowerCase()}</span>
      </span>
    </div>
  );
  return (
    <Panel title={t("journal")}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Mini label={t("j_winrate")} value={`${o.win_rate}%`} tone={o.win_rate >= 50 ? "up" : "down"} />
        <Mini label={t("j_pf")} value={o.profit_factor ?? "—"} tone={(o.profit_factor ?? 0) >= 1 ? "up" : "down"} />
        <Mini label={t("j_best_session")} value={j.best_session || "—"} tone="up" />
        <Mini label={t("j_worst_session")} value={j.worst_session || "—"} tone="down" />
      </div>
      <p className="text-xs text-mist-500 mb-1">{t("j_by_session")}</p>
      {Object.entries(j.by_session).map(([name, st]) => <SessRow key={name} name={name} st={st} />)}
      <p className="text-xs text-mist-500 mt-3 mb-1">{t("j_by_direction")}</p>
      {Object.entries(j.by_direction).map(([d, st]) => (
        <SessRow key={d} name={d === "long" ? t("j_long") : t("j_short")} st={st} />
      ))}
    </Panel>
  );
}

function ProfilePanel({ profile }) {
  const { t } = useI18n();
  if (!profile || profile.total_trades === 0) {
    return (
      <Panel title={t("trader_profile")} action={<span className="text-xs text-mist-500">{t("profile_sub")}</span>}>
        <p className="text-mist-500 text-sm">{t("no_profile")}</p>
      </Panel>
    );
  }
  const pf = profile.profit_factor;
  return (
    <Panel title={t("trader_profile")} action={<span className="hidden sm:block text-xs text-mist-500">{t("profile_sub")}</span>}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Mini label={t("win_rate")} value={`${profile.win_rate}%`} />
        <Mini label={t("profit_factor")} value={pf == null ? "—" : pf} tone={pf >= 1 ? "up" : "down"} />
        <Mini label={t("direction_bias")} value={profile.direction_bias} />
        <Mini label={t("avg_leverage")} value={profile.avg_leverage ? `${profile.avg_leverage}x` : "—"} />
        <Mini label={t("avg_rr")} value={profile.avg_rr ?? "—"} />
        <Mini label={t("best_symbol")} value={profile.best_symbol || "—"} tone="up" />
      </div>
      {profile.tendencies && profile.tendencies.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-mist-300 mb-1.5">⚠️ {t("tendencies")}</p>
          <ul className="space-y-1">
            {profile.tendencies.map((tip, i) => (
              <li key={i} className="text-xs text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-3 py-1.5">{tip}</li>
            ))}
          </ul>
        </div>
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
