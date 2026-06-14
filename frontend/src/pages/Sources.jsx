import { useEffect, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Badge, Button, Field, Input, Select, Spinner } from "../components/ui.jsx";
import { sourcesApi, strategyApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

const TYPES = [
  ["exchange", "Exchange"], ["news", "News"], ["data", "Market Data"],
  ["social", "Social / Sentiment"], ["research", "Research"],
];
const IND_KINDS = [
  ["rsi", "RSI"], ["macd", "MACD"], ["ema", "EMA"], ["sma", "SMA"],
  ["bollinger", "Bollinger Bands"], ["fibonacci", "Fibonacci"],
  ["stoch", "Stochastic"], ["ichimoku", "Ichimoku"], ["volume", "Volume"],
  ["support_resistance", "Support / Resistance"], ["custom", "Custom"],
];
const EMPTY_SRC = { name: "", url: "", feed_url: "", source_type: "exchange", description: "", weight: 5, is_active: true };
const EMPTY_IND = { label: "", key: "rsi", settings: "", notes: "", is_active: true };
const EMPTY_CH = { username: "", title: "", is_active: true };

export default function Sources() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t("src_title")} subtitle={t("src_subtitle")} />
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        <SourcesSection />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <IndicatorsSection />
          <TelegramSection />
        </div>
      </div>
    </>
  );
}

/* ---------------- Sources ---------------- */
function SourcesSection() {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY_SRC);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true);
    try { setItems(await sourcesApi.list()); setError(null); }
    catch (e) { setError(e.message); } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    try {
      if (editingId) await sourcesApi.update(editingId, form);
      else await sourcesApi.create(form);
      setForm(EMPTY_SRC); setEditingId(null); await load();
    } catch (e) { setError(e.message); }
  }
  async function toggle(s) { await sourcesApi.update(s.id, { is_active: !s.is_active }); load(); }
  function edit(s) {
    setEditingId(s.id);
    setForm({ name: s.name, url: s.url, feed_url: s.feed_url, source_type: s.source_type, description: s.description, weight: s.weight, is_active: s.is_active });
  }
  async function remove(id) { if (!confirm(t("delete") + "?")) return; await sourcesApi.remove(id); load(); }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <Panel title={t("active_sources")} className="lg:col-span-2">
        {loading ? <Spinner label="…" /> : items.length === 0 ? (
          <p className="text-mist-500 text-sm">{t("no_sources")}</p>
        ) : (
          <ul className="space-y-2">
            {items.map((s) => (
              <li key={s.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-3 py-3 rounded-lg bg-ink-800 border border-ink-500">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-mist-100">{s.name}</span>
                    <Badge tone="info">{s.source_type}</Badge>
                    <Badge tone="gold">{t("trust")} <span className="tnum">{s.weight}/10</span></Badge>
                    {s.feed_url && <Badge tone="up">RSS</Badge>}
                    {!s.is_active && <Badge tone="down">{t("paused")}</Badge>}
                  </div>
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-xs text-info hover:underline break-all">{s.url}</a>
                </div>
                <div className="flex items-center gap-2 shrink-0 flex-wrap">
                  <Button variant="ghost" onClick={() => toggle(s)}>{s.is_active ? t("pause") : t("enable")}</Button>
                  <Button variant="ghost" onClick={() => edit(s)}>{t("edit")}</Button>
                  <Button variant="danger" onClick={() => remove(s.id)}>{t("delete")}</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel title={editingId ? t("edit_source") : t("add_source")}>
        <div className="space-y-3">
          <Field label={t("name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Binance" /></Field>
          <Field label={t("url")}><Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://www.binance.com" /></Field>
          <Field label={t("feed_url")} hint={t("feed_hint")}><Input value={form.feed_url} onChange={(e) => setForm({ ...form, feed_url: e.target.value })} placeholder="https://…/rss" /></Field>
          <Field label={t("type")}>
            <Select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
              {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label={t("trust_weight")} hint={t("trust_hint")}><Input type="number" min={1} max={10} value={form.weight} onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })} /></Field>
          {error && <p className="text-down text-sm">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button onClick={save}>{editingId ? t("save_changes") : t("add_source")}</Button>
            {editingId && <Button variant="ghost" onClick={() => { setEditingId(null); setForm(EMPTY_SRC); }}>{t("cancel")}</Button>}
          </div>
        </div>
      </Panel>
    </div>
  );
}

/* ---------------- Indicators ---------------- */
function IndicatorsSection() {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY_IND);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    try { setItems(await strategyApi.indicators()); } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    try {
      if (!form.label) form.label = IND_KINDS.find((k) => k[0] === form.key)?.[1] || form.key;
      if (editingId) await strategyApi.updateIndicator(editingId, form);
      else await strategyApi.createIndicator(form);
      setForm(EMPTY_IND); setEditingId(null); await load();
    } catch (e) { setError(e.message); }
  }
  async function toggle(i) { await strategyApi.updateIndicator(i.id, { is_active: !i.is_active }); load(); }
  function edit(i) { setEditingId(i.id); setForm({ label: i.label, key: i.key, settings: i.settings, notes: i.notes, is_active: i.is_active }); }
  async function remove(id) { if (!confirm(t("delete") + "?")) return; await strategyApi.removeIndicator(id); load(); }

  return (
    <Panel title={t("indicators")} action={<span className="text-xs text-mist-500">{t("indicators_sub")}</span>}>
      <div className="space-y-3">
        {items.length === 0 ? <p className="text-mist-500 text-sm">{t("no_indicators")}</p> : (
          <ul className="space-y-2">
            {items.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg bg-ink-800 border border-ink-500">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-mist-100">{i.label}</span>
                    <Badge tone="info">{i.key}</Badge>
                    {!i.is_active && <Badge tone="down">{t("paused")}</Badge>}
                  </div>
                  {i.settings && <p className="text-xs text-mist-500 tnum">{i.settings}</p>}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button variant="ghost" onClick={() => toggle(i)}>{i.is_active ? t("pause") : t("enable")}</Button>
                  <Button variant="ghost" onClick={() => edit(i)}>{t("edit")}</Button>
                  <Button variant="danger" onClick={() => remove(i.id)}>{t("delete")}</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t border-ink-500 pt-3 space-y-3">
          <p className="text-xs font-medium text-mist-300">{editingId ? t("edit_indicator") : t("add_indicator")}</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("indicator_kind")}>
              <Select value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })}>
                {IND_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label={t("indicator_label")}><Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="RSI 14" /></Field>
          </div>
          <Field label={t("indicator_settings")} hint={t("indicator_settings_hint")}><Input value={form.settings} onChange={(e) => setForm({ ...form, settings: e.target.value })} /></Field>
          {error && <p className="text-down text-sm">{error}</p>}
          <div className="flex gap-2">
            <Button onClick={save}>{editingId ? t("save_changes") : t("add_indicator")}</Button>
            {editingId && <Button variant="ghost" onClick={() => { setEditingId(null); setForm(EMPTY_IND); }}>{t("cancel")}</Button>}
          </div>
        </div>
      </div>
    </Panel>
  );
}

/* ---------------- Telegram ---------------- */
function TelegramSection() {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY_CH);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState({});

  async function load() {
    try { setItems(await strategyApi.channels()); } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    try { await strategyApi.createChannel(form); setForm(EMPTY_CH); await load(); }
    catch (e) { setError(e.message); }
  }
  async function toggle(c) { await strategyApi.updateChannel(c.id, { is_active: !c.is_active }); load(); }
  async function remove(id) { if (!confirm(t("delete") + "?")) return; await strategyApi.removeChannel(id); load(); }
  async function doPreview(id) {
    setPreview((p) => ({ ...p, [id]: { loading: true } }));
    try { const res = await strategyApi.previewChannel(id); setPreview((p) => ({ ...p, [id]: { ok: res.ok, messages: res.messages } })); }
    catch (e) { setPreview((p) => ({ ...p, [id]: { ok: false, error: e.message } })); }
  }

  return (
    <Panel title={t("telegram_channels")} action={<span className="text-xs text-mist-500">{t("telegram_sub")}</span>}>
      <div className="space-y-3">
        <p className="text-xs text-gold-soft bg-gold/10 border border-gold/30 rounded-lg px-3 py-2">{t("telegram_note")}</p>
        {items.length === 0 ? <p className="text-mist-500 text-sm">{t("no_channels")}</p> : (
          <ul className="space-y-2">
            {items.map((c) => {
              const pv = preview[c.id];
              return (
                <li key={c.id} className="px-3 py-2.5 rounded-lg bg-ink-800 border border-ink-500">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                      <span className="font-medium text-mist-100 tnum">@{c.username}</span>
                      {c.title && <span className="text-xs text-mist-500 truncate">{c.title}</span>}
                      {!c.is_active && <Badge tone="down">{t("paused")}</Badge>}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button variant="ghost" onClick={() => doPreview(c.id)}>{t("preview")}</Button>
                      <Button variant="ghost" onClick={() => toggle(c)}>{c.is_active ? t("pause") : t("enable")}</Button>
                      <Button variant="danger" onClick={() => remove(c.id)}>{t("delete")}</Button>
                    </div>
                  </div>
                  {pv && (
                    <div className="mt-2 text-xs">
                      {pv.loading ? <span className="text-mist-500">{t("previewing")}</span>
                        : pv.ok ? (
                          <div className="text-up">
                            ✓ {t("preview_ok")}
                            <ul className="mt-1 space-y-1 text-mist-300">
                              {pv.messages.slice(0, 3).map((m, idx) => <li key={idx} className="truncate">• {m.text}</li>)}
                            </ul>
                          </div>
                        ) : <span className="text-down">✗ {t("preview_fail")}</span>}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <div className="border-t border-ink-500 pt-3 space-y-3">
          <p className="text-xs font-medium text-mist-300">{t("add_channel")}</p>
          <Field label={t("channel_username")} hint={t("channel_username_hint")}><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="whalepool" /></Field>
          <Field label={t("channel_title")}><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          {error && <p className="text-down text-sm">{error}</p>}
          <Button onClick={save}>{t("add_channel")}</Button>
        </div>
      </div>
    </Panel>
  );
}
