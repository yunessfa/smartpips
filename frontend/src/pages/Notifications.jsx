import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/Layout.jsx";
import { Badge, Button, Field, Input, Panel, Select, Spinner } from "../components/ui.jsx";
import { alertsApi, tradesApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { enablePush, disablePush, isIOS, isStandalone, pushSupported } from "../live/push.js";

/**
 * Notification centre.
 *
 * Two independent things live here on purpose:
 *   1. The inbox  — internal notification rows from the server. These always
 *      work, even when browser push is unavailable or denied.
 *   2. Alert rules — user-defined conditions on their own open positions.
 *      Rules only ever notify. They never close or modify a trade.
 */

const SECTIONS = [
  { id: "all", key: "notif_all" },
  { id: "unread", key: "notif_unread" },
  { id: "trading", key: "notif_trading" },
  { id: "pnl", key: "notif_pnl" },
  { id: "signal", key: "notif_signals" },
  { id: "position", key: "notif_position" },
  { id: "risk", key: "notif_risk" },
  { id: "system", key: "notif_system" },
];

const LEVEL_DOT = {
  success: "bg-up",
  danger: "bg-down",
  warning: "bg-gold",
  info: "bg-info",
};

const CATEGORY_TONE = {
  pnl: "gold",
  signal: "info",
  risk: "down",
  position: "neutral",
  trading: "neutral",
  system: "neutral",
};

function timeAgo(iso, lang) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return lang === "fa" ? "همین حالا" : "just now";
  if (mins < 60) return lang === "fa" ? `${mins} دقیقه پیش` : `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return lang === "fa" ? `${hours} ساعت پیش` : `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return lang === "fa" ? `${days} روز پیش` : `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

/* ------------------------------------------------------------------ inbox */

function NotificationRow({ note, onRead, onDelete, onOpen, t, lang }) {
  return (
    <div
      className={`flex items-start gap-3 rounded-xl border p-3 transition ${
        note.read
          ? "border-ink-500 bg-ink-700/40"
          : "border-gold/25 bg-ink-600/40"
      }`}
    >
      <span
        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${LEVEL_DOT[note.level] || "bg-info"}`}
        aria-hidden="true"
      />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-sm font-medium text-mist-100 break-words">{note.title}</span>
          <Badge tone={CATEGORY_TONE[note.category] || "neutral"}>
            {t(`notif_${note.category === "signal" ? "signals" : note.category}`)}
          </Badge>
          {!note.read && (
            <span className="h-1.5 w-1.5 rounded-full bg-gold" aria-label={t("notif_unread")} />
          )}
        </div>

        {note.body && (
          <p className="mt-1 text-[13px] leading-relaxed text-mist-300 break-words">{note.body}</p>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-mist-500">
          <span>{timeAgo(note.created, lang)}</span>
          {note.url && (
            <button type="button" className="text-gold hover:underline" onClick={() => onOpen(note)}>
              {t("notif_open")}
            </button>
          )}
          <button type="button" className="hover:text-mist-100" onClick={() => onRead(note)}>
            {note.read ? t("notif_mark_unread") : t("notif_mark_read")}
          </button>
          <button type="button" className="hover:text-down" onClick={() => onDelete(note)}>
            {t("delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- push status */

function PushPanel({ t }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      setStatus(await alertsApi.status());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const supported = pushSupported();
  const iosBlocked = isIOS() && !isStandalone();
  const active = (status?.subscriptions || 0) > 0;

  async function run(fn, okMsg) {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await fn();
      setMsg(okMsg);
      await load();
    } catch (e) {
      const code = e?.message || "";
      const map = {
        not_supported: t("notif_push_unsupported"),
        ios_needs_install: t("notif_push_ios"),
        permission_denied: t("notif_push_denied"),
        server_not_configured: t("notif_push_not_configured"),
      };
      setErr(map[code] || code || t("notif_push_failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title={t("notif_push_title")}>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={active ? "up" : "neutral"}>
            {active ? t("notif_push_on") : t("notif_push_off")}
          </Badge>
          {status && !status.configured && (
            <Badge tone="down">{t("notif_push_not_configured")}</Badge>
          )}
        </div>

        <p className="text-[12px] leading-relaxed text-mist-500">{t("notif_push_note")}</p>

        {!supported && (
          <p className="text-[12px] text-mist-500">{t("notif_push_unsupported")}</p>
        )}
        {supported && iosBlocked && (
          <p className="text-[12px] text-mist-500">{t("notif_push_ios")}</p>
        )}

        <div className="flex flex-wrap gap-2">
          {!active ? (
            <Button
              disabled={busy || !supported}
              onClick={() => run(enablePush, t("notif_push_enabled_ok"))}
            >
              {t("notif_push_enable")}
            </Button>
          ) : (
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => run(disablePush, t("notif_push_disabled_ok"))}
            >
              {t("notif_push_disable")}
            </Button>
          )}
          <Button
            variant="ghost"
            disabled={busy || !active}
            onClick={() => run(() => alertsApi.test(), t("notif_push_sent"))}
          >
            {t("notif_push_test")}
          </Button>
        </div>

        {msg && <p className="text-[12px] text-up">{msg}</p>}
        {err && <p className="text-[12px] text-down">{err}</p>}
      </div>
    </Panel>
  );
}

/* -------------------------------------------------------------- alert rules */

const EMPTY_RULE = {
  name: "",
  scope: "any",
  symbol: "",
  trade: "",
  condition: "pnl_above",
  threshold: 25,
  push: true,
};

function RulesPanel({ t, onFired }) {
  const [rules, setRules] = useState([]);
  const [options, setOptions] = useState({ scopes: [], conditions: [] });
  const [openTrades, setOpenTrades] = useState([]);
  const [form, setForm] = useState(EMPTY_RULE);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, o] = await Promise.all([alertsApi.rules(), alertsApi.ruleOptions()]);
      setRules(Array.isArray(r) ? r : r?.results || []);
      setOptions(o || { scopes: [], conditions: [] });
    } catch (e) {
      setErr(e?.message || "");
    }
    try {
      const list = await tradesApi.list();
      setOpenTrades((Array.isArray(list) ? list : []).filter((x) => x.status === "open"));
    } catch {
      setOpenTrades([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const needsThreshold = useMemo(() => {
    const found = options.conditions?.find((c) => c.value === form.condition);
    return found ? found.needs_threshold : true;
  }, [options, form.condition]);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const payload = {
        name: form.name,
        scope: form.scope,
        condition: form.condition,
        threshold: needsThreshold ? Number(form.threshold) || 0 : 0,
        push: !!form.push,
      };
      if (form.scope === "symbol") payload.symbol = form.symbol;
      if (form.scope === "trade") payload.trade = Number(form.trade) || null;
      await alertsApi.createRule(payload);
      setForm(EMPTY_RULE);
      setShowForm(false);
      setMsg(t("saved"));
      await load();
    } catch (e2) {
      setErr(e2?.message || "");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(rule) {
    await alertsApi.toggleRule(rule.id);
    await load();
  }

  async function remove(rule) {
    await alertsApi.removeRule(rule.id);
    await load();
  }

  async function checkNow() {
    setBusy(true);
    setErr("");
    try {
      const res = await alertsApi.evaluateNow();
      // Explain silence. "0 fired" has very different meanings depending on
      // whether there were rules, open trades, or a usable price at all.
      let text = t("notif_checked").replace("{n" + "}", res?.fired ?? 0);
      if (!res?.fired) {
        if (!res?.rules) text += ` ${t("notif_why_no_rules")}`;
        else if (!res?.open_trades) text += ` ${t("notif_why_no_trades")}`;
        else if (res?.no_price && res.no_price >= res.checked)
          text += ` ${t("notif_why_no_price").replace(
            "{s" + "}",
            (res.symbols_without_price || []).join(", ")
          )}`;
        else text += ` ${t("notif_why_not_met")}`;
      }
      setMsg(text);
      onFired?.();
    } catch (e) {
      setErr(e?.message || "");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title={t("notif_rules_title")}
      action={
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" disabled={busy} onClick={checkNow}>
            {t("notif_check_now")}
          </Button>
          <Button variant="ghost" onClick={() => setShowForm((v) => !v)}>
            {showForm ? t("cancel") : t("notif_rule_new")}
          </Button>
        </div>
      }
    >
      <p className="mb-1 text-[12px] leading-relaxed text-mist-500">{t("notif_no_autoclose")}</p>
      <p className="mb-3 text-[12px] leading-relaxed text-mist-500">{t("notif_auto_note")}</p>

      {showForm && (
        <form onSubmit={save} className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("notif_rule_name")}>
            <Input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder={t("notif_rule_name_ph")}
            />
          </Field>

          <Field label={t("notif_rule_scope")}>
            <Select value={form.scope} onChange={(e) => set("scope", e.target.value)}>
              {(options.scopes || []).map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>

          {form.scope === "symbol" && (
            <Field label={t("notif_rule_symbol")}>
              <Input
                value={form.symbol}
                onChange={(e) => set("symbol", e.target.value.toUpperCase())}
                placeholder="BTCUSDT"
                dir="ltr"
              />
            </Field>
          )}

          {form.scope === "trade" && (
            <Field label={t("notif_rule_trade")}>
              <Select value={form.trade} onChange={(e) => set("trade", e.target.value)}>
                <option value="">—</option>
                {openTrades.map((tr) => (
                  <option key={tr.id} value={tr.id}>
                    #{tr.id} · {tr.symbol} · {tr.direction}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <Field label={t("notif_rule_condition")}>
            <Select value={form.condition} onChange={(e) => set("condition", e.target.value)}>
              {(options.conditions || []).map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </Field>

          {needsThreshold && (
            <Field label={t("notif_rule_threshold")}>
              <Input
                type="number"
                step="any"
                value={form.threshold}
                onChange={(e) => set("threshold", e.target.value)}
                dir="ltr"
              />
            </Field>
          )}

          <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-[13px] text-mist-300">
              <input
                type="checkbox"
                checked={form.push}
                onChange={(e) => set("push", e.target.checked)}
                className="h-4 w-4 accent-[#F0B90B]"
              />
              {t("notif_rule_push")}
            </label>
            <Button type="submit" disabled={busy}>
              {t("notif_rule_save")}
            </Button>
          </div>
        </form>
      )}

      {msg && <p className="mb-2 text-[12px] text-up">{msg}</p>}
      {err && <p className="mb-2 text-[12px] text-down">{err}</p>}

      {rules.length === 0 ? (
        <p className="text-[13px] text-mist-500">{t("notif_rule_none")}</p>
      ) : (
        <div className="space-y-2">
          {rules.map((r) => (
            <div
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-ink-500 bg-ink-700/40 p-3"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-mist-100 break-words">
                    {r.name || r.description}
                  </span>
                  <Badge tone={r.enabled ? "up" : "neutral"}>
                    {r.enabled ? t("notif_rule_on") : t("notif_rule_off")}
                  </Badge>
                </div>
                <p className="mt-1 text-[12px] text-mist-500 break-words">
                  {r.description}
                  {r.scope === "symbol" && r.symbol ? ` · ${r.symbol}` : ""}
                  {r.scope === "trade" && r.trade ? ` · #${r.trade}` : ""}
                  {r.trigger_count
                    ? ` · ${t("notif_rule_triggered").replace("{n}", r.trigger_count)}`
                    : ""}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="ghost" onClick={() => toggle(r)}>
                  {r.enabled ? t("notif_rule_off") : t("notif_rule_on")}
                </Button>
                <Button variant="danger" onClick={() => remove(r)}>
                  {t("delete")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

/* --------------------------------------------------------------------- page */

export default function Notifications() {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [section, setSection] = useState("all");
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (sec) => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (sec === "unread") params.unread = true;
      else if (sec !== "all") params.category = sec;
      const res = await alertsApi.notifications(params);
      setRows(res?.results || []);
      setCounts(res?.counts || {});
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(section);
  }, [load, section]);

  async function toggleRead(note) {
    await alertsApi.markRead(note.id, !note.read);
    // Tell the sidebar badge to refresh without a full page reload.
    window.dispatchEvent(new Event("sp-notifications-changed"));
    load(section);
  }

  async function remove(note) {
    await alertsApi.removeNotification(note.id);
    window.dispatchEvent(new Event("sp-notifications-changed"));
    load(section);
  }

  async function markAll() {
    await alertsApi.markAllRead();
    window.dispatchEvent(new Event("sp-notifications-changed"));
    load(section);
  }

  async function clearRead() {
    await alertsApi.clearNotifications("read");
    window.dispatchEvent(new Event("sp-notifications-changed"));
    load(section);
  }

  function open(note) {
    if (!note.read) toggleRead(note);
    if (!note.url) return;
    // The panel routes live in a nested <Routes> under "/app/*", but navigate()
    // still resolves an absolute path against the ROOT router. Stripping the
    // "/app" prefix here sent "/app/scalp" to the public marketing page at
    // "/scalp". Pass the stored path through untouched.
    if (/^https?:\/\//i.test(note.url)) {
      window.open(note.url, "_blank", "noopener");
      return;
    }
    navigate(note.url.startsWith("/") ? note.url : `/app/${note.url}`);
  }

  return (
    <>
      <PageHeader
        title={t("notif_title")}
        subtitle={t("notif_sub")}
        right={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={markAll} disabled={!counts.unread}>
              {t("notif_mark_all")}
            </Button>
            <Button variant="ghost" onClick={clearRead}>
              {t("notif_clear_read")}
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto min-h-0 p-4 md:p-6 space-y-4 md:space-y-6">
        {/* Section rail. Scrolls inside itself so it can never widen the page. */}
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <div className="flex w-max gap-2">
            {SECTIONS.map((s) => {
              const count = counts[s.id];
              const activeTab = section === s.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSection(s.id)}
                  className={`shrink-0 rounded-lg border px-3 py-1.5 text-[12px] transition ${
                    activeTab
                      ? "border-gold/40 bg-gold/10 text-gold"
                      : "border-ink-500 bg-ink-700/50 text-mist-300 hover:text-mist-100"
                  }`}
                >
                  {t(s.key)}
                  {count ? <span className="ms-1.5 tnum opacity-70">{count}</span> : null}
                </button>
              );
            })}
          </div>
        </div>

        <Panel title={t("notif_inbox")}>
          {loading ? (
            <Spinner label={t("notif_loading")} />
          ) : rows.length === 0 ? (
            <p className="text-[13px] text-mist-500">{t("notif_empty")}</p>
          ) : (
            <div className="space-y-2">
              {rows.map((n) => (
                <NotificationRow
                  key={n.id}
                  note={n}
                  t={t}
                  lang={lang}
                  onRead={toggleRead}
                  onDelete={remove}
                  onOpen={open}
                />
              ))}
            </div>
          )}
        </Panel>

        <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <RulesPanel t={t} onFired={() => load(section)} />
          </div>
          <PushPanel t={t} />
        </div>
      </div>
    </>
  );
}
