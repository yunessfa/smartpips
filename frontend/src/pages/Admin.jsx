import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Button, Input, Field, Spinner } from "../components/ui.jsx";
import { adminApi, authApi, ctraderApi, prefsApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

/**
 * User administration.
 *
 * 2026-09 rewrite. The previous version rendered a single seven-column table
 * with no mobile treatment at all, inside a `lg:grid-cols-3` parent. On a
 * phone every column collapsed to a few pixels: the market toggles became
 * unreadable slivers and the "new user" inputs were too narrow to type into,
 * which is why adding or editing a user was effectively impossible.
 *
 * What changed:
 *   - Below `md` each user is a stacked card. Above `md` the table returns,
 *     because a table genuinely is the better shape on a wide screen.
 *   - The create-user form is full width on mobile instead of a squeezed
 *     third column.
 *   - Fixed a real off-by-one: the header order was
 *     username | email | active | admin | markets | risk | actions
 *     but the cells rendered the risk button 4th and the admin star 5th, so
 *     both columns were mislabelled. Cells now follow the headers.
 *   - New super-admin block: change someone's username and/or password, and
 *     reset their data. See CredentialsEditor.
 */

const EMPTY = { username: "", email: "", password: "", is_admin: false };
const DEFAULT_ACCESS = { metals: true, spot: true, futures: true };
const MARKETS = [["metals", "\U0001f947"], ["spot", "\U0001f4b0"], ["futures", "\u26a1"]];

export default function Admin() {
  const { t } = useI18n();
  const [users, setUsers] = useState([]);
  const [access, setAccess] = useState({});
  const [limits, setLimits] = useState({});
  const [editUser, setEditUser] = useState(null);
  const [credUser, setCredUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [query, setQuery] = useState("");
  // Whether *I* am a super admin. The server is the real gate (it answers 403);
  // this only decides whether to render controls that would be refused.
  const [amSuper, setAmSuper] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setUsers(await adminApi.users());
      try { setAccess(await prefsApi.allAccess()); } catch { /* non-admin safe */ }
      try { setLimits(await prefsApi.allLimits()); } catch { /* non-admin safe */ }
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    authApi.me().then((me) => setAmSuper(!!me.is_superuser)).catch(() => {});
  }, []);

  async function create() {
    setErr(null); setMsg(null);
    try {
      await adminApi.createUser(form);
      setForm(EMPTY); setMsg(t("u_created")); load();
    } catch (e) { setErr(e.message); }
  }
  async function toggleActive(u) {
    try { await adminApi.updateUser(u.id, { is_active: !u.is_active }); load(); }
    catch (e) { setErr(e.message); }
  }
  async function toggleAccess(u, key) {
    const cur = access[String(u.id)] || DEFAULT_ACCESS;
    try {
      const next = await prefsApi.setUserAccess(u.id, { [key]: !cur[key] });
      setAccess({ ...access, [String(u.id)]: next });
    } catch (e) { setErr(e.message); }
  }
  async function toggleAdmin(u) {
    try { await adminApi.updateUser(u.id, { is_admin: !u.is_admin }); load(); }
    catch (e) { setErr(e.message); }
  }
  async function remove(u) {
    if (!window.confirm(`${t("u_delete")} ${u.username}?`)) return;
    try { await adminApi.deleteUser(u.id); load(); } catch (e) { setErr(e.message); }
  }

  const shown = useMemo(() => {
    const s = query.trim().toLowerCase();
    if (!s) return users;
    return users.filter((u) =>
      u.username.toLowerCase().includes(s) || (u.email || "").toLowerCase().includes(s));
  }, [users, query]);

  // ---- shared cell renderers (used by both the card and the table) ----
  const ActiveDot = ({ u }) => (
    <span className={u.is_active ? "text-up" : "text-down"}>{u.is_active ? "\u25cf" : "\u25cb"}</span>
  );

  const RiskButton = ({ u }) => {
    const l = limits[String(u.id)] || {};
    const off = l.real_trading_enabled === false;
    return (
      <button onClick={() => setEditUser(editUser === u.id ? null : u.id)}
        className={`text-[11px] px-2 py-1 rounded border whitespace-nowrap ${
          off ? "bg-down/10 border-down/30 text-down"
              : "bg-ink-800 border-ink-500 text-mist-300 hover:text-mist-100"}`}>
        {off ? `\u26d4 ${t("rl_real_off")}` : `\u2699 ${l.max_leverage ?? "\u2014"}x \u00b7 ${l.max_position_usdt ?? "\u2014"}$`}
      </button>
    );
  };

  const MarketToggles = ({ u }) => (
    // flex-wrap, not a fixed row: three buttons plus labels do not fit a phone
    // width, and squeezing them was what made them unreadable.
    <div className="flex flex-wrap gap-1">
      {MARKETS.map(([k, icon]) => {
        const on = (access[String(u.id)] || DEFAULT_ACCESS)[k];
        return (
          <button key={k} onClick={() => toggleAccess(u, k)} title={t(`mk_${k}`)}
            className={`text-[11px] px-1.5 py-1 rounded border transition whitespace-nowrap ${
              on ? "bg-up/10 border-up/30 text-up"
                 : "bg-ink-800 border-ink-500 text-mist-500 line-through opacity-60"}`}>
            {icon} {t(`mk_${k}`)}
          </button>
        );
      })}
    </div>
  );

  const Actions = ({ u }) => (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <button onClick={() => toggleActive(u)} className="text-xs text-mist-300 hover:text-mist-100 underline">
        {u.is_active ? t("u_disable") : t("u_enable")}
      </button>
      <button onClick={() => toggleAdmin(u)} className="text-xs text-gold-soft hover:text-gold underline">
        {u.is_admin ? `\u2212 ${t("u_admin")}` : `+ ${t("u_admin")}`}
      </button>
      {amSuper && (
        <button onClick={() => setCredUser(u)} className="text-xs text-mist-300 hover:text-mist-100 underline">
          \U0001f511 {t("u_credentials")}
        </button>
      )}
      <button onClick={() => remove(u)} className="text-xs text-down hover:underline">
        {t("u_delete")}
      </button>
    </div>
  );

  return (
    <>
      <PageHeader title={t("admin_title")} subtitle={t("admin_sub")} />

      {/* min-w-0 on the grid children below matters: without it a wide table
          forces the whole grid track open and the page scrolls sideways. */}
      <div className="flex-1 overflow-y-auto min-h-0 p-4 md:p-6 space-y-6">

        {/* ------------------------- users ------------------------- */}
        <Panel title={`${t("admin_title")}${users.length ? ` \u00b7 ${users.length}` : ""}`}>
          <div className="mb-3">
            <Input value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder={t("u_search")} className="sm:max-w-xs" />
          </div>

          {err && <p className="text-down text-xs mb-3 break-words">{err}</p>}

          {loading ? <Spinner label="\u2026" /> : !shown.length ? (
            <p className="text-xs text-mist-500">{t("u_none")}</p>
          ) : (
            <>
              {/* ---------- mobile: one card per user ---------- */}
              <ul className="md:hidden space-y-3">
                {shown.map((u) => (
                  <li key={u.id} className="rounded-xl border border-ink-500 bg-ink-800/60 p-3 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-mist-100 break-all">
                          {u.username}
                          {u.is_superuser && <span className="ms-1 text-gold" title="super admin">\u2605\u2605</span>}
                          {!u.is_superuser && u.is_admin && <span className="ms-1 text-gold-soft">\u2605</span>}
                        </p>
                        <p className="text-xs text-mist-500 break-all">{u.email || "\u2014"}</p>
                      </div>
                      <ActiveDot u={u} />
                    </div>

                    <div className="mt-3 space-y-2.5">
                      <div>
                        <p className="text-[11px] text-mist-500 mb-1">{t("u_markets")}</p>
                        <MarketToggles u={u} />
                      </div>
                      <div>
                        <p className="text-[11px] text-mist-500 mb-1">{t("u_risk")}</p>
                        <RiskButton u={u} />
                      </div>
                      <div className="pt-2 border-t border-ink-600/60">
                        <Actions u={u} />
                      </div>
                    </div>
                  </li>
                ))}
              </ul>

              {/* ---------- desktop: the table, columns now aligned ---------- */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-mist-500 text-xs border-b border-ink-500">
                    <tr>
                      <th className="text-start py-2 px-2">{t("u_username")}</th>
                      <th className="text-start py-2 px-2">{t("u_email")}</th>
                      <th className="text-start py-2 px-2">{t("u_active")}</th>
                      <th className="text-start py-2 px-2">{t("u_admin")}</th>
                      <th className="text-start py-2 px-2">{t("u_markets")}</th>
                      <th className="text-start py-2 px-2">{t("u_risk")}</th>
                      <th className="text-start py-2 px-2">{t("u_actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((u) => (
                      <tr key={u.id} className="border-b border-ink-600/50 align-top">
                        <td className="py-2.5 px-2 text-mist-100 break-all">{u.username}</td>
                        <td className="py-2.5 px-2 text-mist-300 break-all">{u.email || "\u2014"}</td>
                        <td className="py-2.5 px-2"><ActiveDot u={u} /></td>
                        {/* was rendering the risk button here \u2014 wrong column */}
                        <td className="py-2.5 px-2">
                          {u.is_superuser ? <span className="text-gold" title="super admin">\u2605\u2605</span>
                            : u.is_admin ? <span className="text-gold-soft">\u2605</span> : "\u2014"}
                        </td>
                        <td className="py-2.5 px-2"><MarketToggles u={u} /></td>
                        <td className="py-2.5 px-2"><RiskButton u={u} /></td>
                        <td className="py-2.5 px-2"><Actions u={u} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Panel>

        {editUser != null && (
          <RiskLimitEditor
            userId={editUser}
            value={limits[String(editUser)] || {}}
            onClose={() => setEditUser(null)}
            onSaved={(next) => { setLimits({ ...limits, [String(editUser)]: next }); setEditUser(null); }}
          />
        )}

        {credUser && (
          <CredentialsEditor
            user={credUser}
            onClose={() => setCredUser(null)}
            onDone={() => { setCredUser(null); load(); }}
          />
        )}

        {/* --------------------- create user --------------------- */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Panel title={t("new_user")} className="min-w-0">
            <div className="space-y-3">
              <Field label={t("u_username")}>
                <Input value={form.username} autoComplete="off"
                  onChange={(e) => setForm({ ...form, username: e.target.value })} />
              </Field>
              <Field label={t("u_email")}>
                <Input type="email" value={form.email} autoComplete="off"
                  onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </Field>
              <Field label={t("u_password")}>
                <Input type="password" value={form.password} autoComplete="new-password"
                  onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </Field>
              <label className="flex items-center gap-2 text-sm text-mist-300">
                <input type="checkbox" checked={form.is_admin}
                  onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} />
                {t("u_admin")}
              </label>
              {err && <p className="text-down text-xs break-words">{err}</p>}
              {msg && <p className="text-up text-xs">{msg}</p>}
              {/* w-full on mobile: a narrow centred button next to full-width
                  inputs is an awkward tap target on a phone. */}
              <Button onClick={create} disabled={!form.username || !form.password}
                className="w-full sm:w-auto">
                {t("create")}
              </Button>
            </div>
          </Panel>

          <div className="min-w-0 space-y-6">
            <RegistrationPanel />
            <CTraderPanel />
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * Super-admin account recovery: change a username, change a password, or wipe
 * a user's data.
 *
 * Design notes:
 *  - Username and password are separate submits. Bundling them into one "save"
 *    makes it too easy to change a username by accident while resetting a
 *    password.
 *  - The reset requires typing the username to confirm. A yes/no dialog is not
 *    enough friction for an irreversible wipe of somebody's trade journal.
 *  - Both credential changes invalidate the user's tokens server-side, so they
 *    are logged out immediately. That is stated in the UI rather than being a
 *    surprise.
 */
function CredentialsEditor({ user, onClose, onDone }) {
  const { t } = useI18n();
  const [username, setUsername] = useState(user.username);
  const [password, setPassword] = useState("");
  const [confirmName, setConfirmName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  async function run(label, fn) {
    setBusy(true); setErr(null); setMsg(null);
    try { await fn(); setMsg(label); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  const saveUsername = () => run(t("u_creds_saved"), async () => {
    await adminApi.changeCredentials(user.id, { username: username.trim() });
    onDone();
  });

  const savePassword = () => run(t("u_creds_saved"), async () => {
    await adminApi.changeCredentials(user.id, { password });
    setPassword("");
  });

  const resetData = () => run(t("u_reset_done"), async () => {
    await adminApi.resetUser(user.id);
    onDone();
  });

  return (
    <div className="fixed inset-0 z-40 bg-black/60 flex items-start sm:items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}>
      {/* max-h + overflow: on a short screen (or with the keyboard open on a
          phone) a fixed-height modal put the buttons out of reach. */}
      <div className="bg-ink-700 border border-ink-500 rounded-xl p-5 w-full max-w-md my-auto max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-mist-100">
          {t("u_credentials")} \u00b7 <span className="break-all">{user.username}</span>
        </h3>
        <p className="mt-1 text-[11px] leading-relaxed text-mist-500">{t("u_creds_hint")}</p>

        {/* ---- username ---- */}
        <div className="mt-4 space-y-2">
          <Field label={t("u_new_username")}>
            <Input value={username} autoComplete="off"
              onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Button variant="ghost" onClick={saveUsername}
            disabled={busy || !username.trim() || username.trim() === user.username}
            className="w-full sm:w-auto">
            {t("u_save_username")}
          </Button>
        </div>

        {/* ---- password ---- */}
        <div className="mt-4 pt-4 border-t border-ink-600/60 space-y-2">
          <Field label={t("u_new_password")} hint={t("u_pw_hint")}>
            <Input type="password" value={password} autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button variant="ghost" onClick={savePassword}
            disabled={busy || password.length < 6} className="w-full sm:w-auto">
            {t("u_save_password")}
          </Button>
        </div>

        {/* ---- destructive reset ---- */}
        <div className="mt-4 pt-4 border-t border-down/30">
          <p className="text-xs font-semibold text-down">{t("u_reset_data")}</p>
          <p className="mt-1 text-[11px] leading-relaxed text-mist-500">{t("u_reset_hint")}</p>
          <div className="mt-2 space-y-2">
            <Field label={t("u_reset_confirm")}>
              <Input value={confirmName} autoComplete="off" placeholder={user.username}
                onChange={(e) => setConfirmName(e.target.value)} />
            </Field>
            <button onClick={resetData}
              disabled={busy || confirmName.trim() !== user.username}
              className="w-full sm:w-auto px-4 py-2 rounded-lg bg-down/15 border border-down/40 text-down text-xs font-semibold disabled:opacity-40">
              {busy ? "\u2026" : t("u_reset_btn")}
            </button>
          </div>
        </div>

        {err && <p className="mt-3 text-down text-xs break-words">{err}</p>}
        {msg && <p className="mt-3 text-up text-xs">{msg}</p>}

        <div className="flex justify-end mt-4">
          <button onClick={onClose} className="px-3 py-1.5 rounded-md bg-ink-600 text-mist-300 text-xs">
            {t("u_close")}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * "Allow new user registration" switch.
 *
 * The flag lives server-side (accounts.SystemSetting) and the register endpoint
 * enforces it, so this panel is a control surface, not the security boundary.
 * Staff can see the current state; only a super admin can change it, which the
 * backend also enforces \u2014 the disabled control here just avoids offering an
 * action that would be refused.
 */
function RegistrationPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    adminApi.settings().then(setSettings).catch((e) => setErr(e.message));
  }, []);

  async function toggle() {
    if (!settings) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const next = await adminApi.updateSettings({
        registration_enabled: !settings.registration_enabled,
      });
      setSettings(next);
      setMsg(t("saved"));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const on = settings?.registration_enabled !== false;
  const canEdit = settings?.can_edit;

  return (
    <Panel title={t("reg_title")} className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <span className={on ? "text-up" : "text-down"}>\u25cf</span>
            <span className="text-mist-200">
              {settings === null ? "\u2026" : on ? t("reg_on") : t("reg_off")}
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-mist-500">{t("reg_hint")}</p>
          {!canEdit && settings !== null && (
            <p className="mt-1 text-xs text-mist-500">{t("reg_superadmin_only")}</p>
          )}
        </div>
        <Button onClick={toggle} disabled={busy || settings === null || !canEdit}
          className="w-full sm:w-auto">
          {busy ? "\u2026" : on ? t("reg_disable") : t("reg_enable")}
        </Button>
      </div>
      {err && <p className="mt-2 text-xs text-down break-words">{err}</p>}
      {msg && <p className="mt-2 text-xs text-up">{msg}</p>}
    </Panel>
  );
}

function CTraderPanel() {
  const { t } = useI18n();
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { ctraderApi.status().then(setSt).catch(() => {}); }, []);

  async function connect() {
    setBusy(true);
    try {
      const { authorize_url } = await ctraderApi.connect();
      if (authorize_url) window.open(authorize_url, "_blank");
    } catch (e) { /* ignore */ }
    finally { setBusy(false); }
  }

  const connected = st?.connected;
  return (
    <Panel title={t("ctrader")} className="min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 text-sm min-w-0">
          <span className={connected ? "text-up" : "text-mist-500"}>\u25cf</span>
          <span className="text-mist-200">{connected ? t("ctrader_connected") : t("ctrader_disconnected")}</span>
          {st?.account_id && <span className="text-xs text-mist-500 truncate">\u00b7 {t("ctrader_account")} {st.account_id}</span>}
        </div>
        <Button onClick={connect} disabled={busy} className="w-full sm:w-auto">
          {busy ? "\u2026" : t("ctrader_connect_btn")}
        </Button>
      </div>
      <p className="text-xs text-mist-500 mt-3">{t("ctrader_hint")}</p>
    </Panel>
  );
}


function RiskLimitEditor({ userId, value, onClose, onSaved }) {
  const { t } = useI18n();
  const [f, setF] = useState({
    max_leverage: value.max_leverage ?? 20,
    max_position_usdt: value.max_position_usdt ?? 500,
    max_open_positions: value.max_open_positions ?? 3,
    daily_loss_limit_usdt: value.daily_loss_limit_usdt ?? 100,
    real_trading_enabled: value.real_trading_enabled !== false,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const num = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function save() {
    setBusy(true); setErr(null);
    try {
      const next = await prefsApi.setUserLimits(userId, {
        max_leverage: Number(f.max_leverage),
        max_position_usdt: Number(f.max_position_usdt),
        max_open_positions: Number(f.max_open_positions),
        daily_loss_limit_usdt: Number(f.daily_loss_limit_usdt),
        real_trading_enabled: f.real_trading_enabled,
      });
      onSaved(next);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  const inp = "w-full min-w-0 bg-ink-800 border border-ink-500 rounded-md px-2.5 py-2 text-sm text-mist-100 tnum";
  const lbl = "text-[11px] text-mist-500 mb-1 block";
  return (
    <div className="fixed inset-0 z-40 bg-black/60 flex items-start sm:items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}>
      {/* Single column below sm: two number inputs side by side on a phone left
          each one too narrow to read its own value. */}
      <div className="bg-ink-700 border border-ink-500 rounded-xl p-5 w-full max-w-md my-auto max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-mist-100 mb-4">{t("rl_title")}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="min-w-0"><label className={lbl}>{t("rl_max_lev")}</label>
            <input className={inp} type="number" min="1" max="125" value={f.max_leverage} onChange={num("max_leverage")} /></div>
          <div className="min-w-0"><label className={lbl}>{t("rl_max_pos")}</label>
            <input className={inp} type="number" value={f.max_position_usdt} onChange={num("max_position_usdt")} /></div>
          <div className="min-w-0"><label className={lbl}>{t("rl_max_open")}</label>
            <input className={inp} type="number" value={f.max_open_positions} onChange={num("max_open_positions")} /></div>
          <div className="min-w-0"><label className={lbl}>{t("rl_daily_loss")}</label>
            <input className={inp} type="number" value={f.daily_loss_limit_usdt} onChange={num("daily_loss_limit_usdt")} /></div>
        </div>
        {/* The daily loss limit above is what now silences trade alerts once it
            is breached (apps/alerts/gating.py). */}
        <p className="mt-2 text-[11px] leading-relaxed text-mist-500">{t("rl_loss_mutes_hint")}</p>
        <label className="flex items-center gap-2 text-sm text-mist-300 mt-3">
          <input type="checkbox" checked={f.real_trading_enabled}
            onChange={(e) => setF({ ...f, real_trading_enabled: e.target.checked })} />
          {t("rl_real_enabled")}
        </label>
        {err && <p className="text-down text-xs mt-2 break-words">{err}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-1.5 rounded-md bg-ink-600 text-mist-300 text-xs">{t("bx_confirm_no")}</button>
          <button onClick={save} disabled={busy}
            className="px-4 py-1.5 rounded-md bg-gold text-ink-900 text-xs font-bold">{busy ? "\u2026" : t("create")}</button>
        </div>
      </div>
    </div>
  );
}
