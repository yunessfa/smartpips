import { useEffect, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Badge, Button, Field, Input, Select, Spinner } from "../components/ui.jsx";
import { aiApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

const PROVIDERS = [
  ["deepseek", "DeepSeek", "https://api.deepseek.com", "deepseek-chat"],
  ["openai", "OpenAI", "https://api.openai.com", "gpt-4o-mini"],
  ["openrouter", "OpenRouter", "https://openrouter.ai/api", "deepseek/deepseek-chat"],
  ["groq", "Groq (free tier)", "https://api.groq.com/openai", "llama-3.3-70b-versatile"],
  ["ollama", "Ollama (local, no key)", "http://localhost:11434", "llama3.1"],
  ["custom", "Custom (OpenAI-compatible)", "", ""],
];
const EMPTY = { label: "", provider_type: "deepseek", base_url: "", model: "", api_key: "", temperature: 0.4 };

export default function AISettings() {
  const { t } = useI18n();
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [testResult, setTestResult] = useState({});

  async function load() {
    setLoading(true);
    try { setProviders(await aiApi.list()); setError(null); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  function pickType(type) {
    const [, , baseUrl, model] = PROVIDERS.find((p) => p[0] === type) || [];
    setForm((f) => ({ ...f, provider_type: type,
      base_url: editingId ? f.base_url : baseUrl || "",
      model: editingId ? f.model : model || "" }));
  }
  async function save() {
    try {
      const payload = { ...form };
      if (editingId && payload.api_key === "") delete payload.api_key;
      if (editingId) await aiApi.update(editingId, payload); else await aiApi.create(payload);
      setForm(EMPTY); setEditingId(null); await load();
    } catch (e) { setError(e.message); }
  }
  function edit(p) {
    setEditingId(p.id);
    setForm({ label: p.label, provider_type: p.provider_type, base_url: p.base_url, model: p.model, api_key: "", temperature: p.temperature });
  }
  async function activate(id) { await aiApi.activate(id); load(); }
  async function remove(id) { if (!confirm(t("delete") + "?")) return; await aiApi.remove(id); load(); }
  async function test(id) {
    setTestResult((r) => ({ ...r, [id]: { loading: true } }));
    try { const res = await aiApi.test(id); setTestResult((r) => ({ ...r, [id]: { ok: res.ok, msg: res.reply } })); }
    catch (e) { setTestResult((r) => ({ ...r, [id]: { ok: false, msg: e.message } })); }
  }

  return (
    <>
      <PageHeader title={t("ai_title")} subtitle={t("ai_subtitle")} />
      <div className="flex-1 overflow-y-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Panel title={t("configured_models")} className="lg:col-span-2">
          {loading ? <Spinner label="…" /> : providers.length === 0 ? (
            <p className="text-mist-500 text-sm">{t("no_models")}</p>
          ) : (
            <ul className="space-y-2">
              {providers.map((p) => {
                const tr = testResult[p.id];
                return (
                  <li key={p.id} className="px-3 py-3 rounded-lg bg-ink-800 border border-ink-500">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-mist-100">{p.label}</span>
                          <Badge tone="info">{p.provider_type}</Badge>
                          {p.is_active && <Badge tone="up">{t("active")}</Badge>}
                        </div>
                        <p className="tnum text-xs text-mist-500 mt-1">{p.model} · {p.api_key_masked || t("not_set")}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 flex-wrap">
                        {!p.is_active && <Button variant="ghost" onClick={() => activate(p.id)}>{t("set_active")}</Button>}
                        <Button variant="ghost" onClick={() => test(p.id)}>{t("test")}</Button>
                        <Button variant="ghost" onClick={() => edit(p)}>{t("edit")}</Button>
                        <Button variant="danger" onClick={() => remove(p.id)}>{t("delete")}</Button>
                      </div>
                    </div>
                    {tr && (
                      <p className={`text-xs mt-2 ${tr.loading ? "text-mist-500" : tr.ok ? "text-up" : "text-down"}`}>
                        {tr.loading ? t("testing") : tr.ok ? `✓ ${t("connected")}: ${tr.msg}` : `✗ ${tr.msg}`}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        <Panel title={editingId ? t("edit_model") : t("add_model")}>
          <div className="space-y-3">
            <Field label={t("provider")}>
              <Select value={form.provider_type} onChange={(e) => pickType(e.target.value)}>
                {PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label={t("label")}><Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="My DeepSeek" /></Field>
            <Field label={t("base_url")}><Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.deepseek.com" /></Field>
            <Field label={t("model")}><Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="deepseek-chat" /></Field>
            <Field label={t("api_key")} hint={editingId ? t("api_key_hint_edit") : t("api_key_hint_new")}>
              <Input type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder="sk-…" />
            </Field>
            <Field label={t("temperature")} hint={t("temp_hint")}>
              <Input type="number" step="0.1" min="0" max="1" value={form.temperature} onChange={(e) => setForm({ ...form, temperature: Number(e.target.value) })} />
            </Field>
            {error && <p className="text-down text-sm">{error}</p>}
            <div className="flex gap-2 pt-1">
              <Button onClick={save}>{editingId ? t("save_changes") : t("add_model")}</Button>
              {editingId && <Button variant="ghost" onClick={() => { setEditingId(null); setForm(EMPTY); }}>{t("cancel")}</Button>}
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
