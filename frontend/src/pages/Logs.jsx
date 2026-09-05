import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Button, Select, Spinner } from "../components/ui.jsx";
import { systemApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

/**
 * Error log viewer (review item T-2).
 *
 * Until now a swallowed exception left no trace anywhere: no log file, no
 * health endpoint, and 46 bare `except Exception` blocks. The backend writes a
 * rotating JSON log now; this page is the window onto it, so a failure can be
 * read without SSH access to the server.
 *
 * Notes:
 *  - Super-admin only. The server enforces it; a non-superuser gets a 403 and
 *    the message below rather than a blank screen.
 *  - Secrets (API keys, tokens, passwords, VAPID keys) are redacted
 *    server-side before the text ever leaves the machine, so pasting a log
 *    line into a chat cannot leak credentials.
 *  - Only the tail of the file is read, so a multi-gigabyte log cannot
 *    exhaust server memory.
 */

const LEVELS = ["", "ERROR", "WARNING", "INFO"];
const LINE_CHOICES = [100, 200, 500, 1000, 2000];

function levelTone(line) {
  if (/"lvl"\s*:\s*"(ERROR|CRITICAL)"|\bERROR\b|\bCRITICAL\b/.test(line)) return "text-down";
  if (/"lvl"\s*:\s*"WARNING"|\bWARNING\b/.test(line)) return "text-gold-soft";
  if (/"lvl"\s*:\s*"DEBUG"/.test(line)) return "text-mist-500";
  return "text-mist-300";
}

/**
 * The log is JSON-per-line, which is great for machines and unreadable for
 * people. Pull out the useful fields when the line parses and fall back to the
 * raw text when it does not \u2014 tracebacks are multi-line and will not parse.
 */
function prettyLine(line) {
  try {
    const o = JSON.parse(line);
    if (o && (o.msg || o.lvl)) {
      const t = (o.t || "").replace("T", " ").slice(0, 19);
      return { time: t, level: o.lvl || "", logger: o.logger || "", msg: o.msg || "" };
    }
  } catch { /* not JSON \u2014 almost certainly a traceback continuation line */ }
  return null;
}

export default function Logs() {
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [health, setHealth] = useState(null);
  const [lines, setLines] = useState(200);
  const [level, setLevel] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [auto, setAuto] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setErr(null);
    try {
      setData(await systemApi.logs({ lines, level, q }));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [lines, level, q]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    systemApi.healthDeep().then(setHealth).catch(() => {
      // Non-fatal: the deep check needs staff. The log panel still works.
    });
  }, []);

  // Opt-in polling. Deliberately not on by default: an auto-refreshing log
  // that keeps jumping is impossible to read while you are investigating.
  useEffect(() => {
    if (!auto) return;
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [auto, load]);

  async function sendTest() {
    setBusy(true);
    try { await systemApi.logsTest(); await load(); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  function copyAll() {
    const text = (data?.lines || []).join("\n");
    navigator.clipboard?.writeText(text).catch(() => {});
  }

  const rows = data?.lines || [];

  return (
    <>
      <PageHeader title={t("logs_title")} subtitle={t("logs_sub")} />

      <div className="flex-1 overflow-y-auto min-h-0 p-4 md:p-6 space-y-4">
        {/* ---------------- health summary ---------------- */}
        {health && (
          <Panel title={t("logs_health")}>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {Object.entries(health.checks || {}).map(([key, val]) => {
                const ok = val?.ok !== false;
                return (
                  <div key={key}
                    className={`rounded-lg border px-3 py-2 min-w-0 ${
                      ok ? "border-up/30 bg-up/5" : "border-down/30 bg-down/5"}`}>
                    <div className="flex items-center gap-1.5">
                      <span className={ok ? "text-up" : "text-down"}>{ok ? "\u25cf" : "\u25cb"}</span>
                      <span className="text-xs font-medium text-mist-200 truncate">{key}</span>
                    </div>
                    <p className="mt-1 text-[11px] text-mist-500 break-words">
                      {val?.detail || (ok ? t("logs_ok") : t("logs_fail"))}
                    </p>
                  </div>
                );
              })}
            </div>
          </Panel>
        )}

        {/* ---------------- controls ---------------- */}
        <Panel title={t("logs_filters")}>
          {/* Wraps instead of a fixed row: on a phone these controls used to
              squash into unusable slivers, the same bug as the users page. */}
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 min-w-0">
              <span className="text-xs text-mist-400">{t("logs_level")}</span>
              <Select value={level} onChange={(e) => setLevel(e.target.value)}
                className="w-full sm:w-40">
                {LEVELS.map((l) => (
                  <option key={l || "all"} value={l}>{l || t("logs_all_levels")}</option>
                ))}
              </Select>
            </label>

            <label className="flex flex-col gap-1 min-w-0">
              <span className="text-xs text-mist-400">{t("logs_lines")}</span>
              <Select value={lines} onChange={(e) => setLines(Number(e.target.value))}
                className="w-full sm:w-32">
                {LINE_CHOICES.map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
            </label>

            <label className="flex flex-col gap-1 flex-1 min-w-[12rem]">
              <span className="text-xs text-mist-400">{t("logs_search")}</span>
              <input value={q} onChange={(e) => setQ(e.target.value)}
                placeholder={t("logs_search_ph")}
                className="w-full bg-ink-800 border border-ink-500 rounded-lg px-3 py-2 text-sm text-mist-100 placeholder-mist-500 focus:outline-none focus:border-gold/50" />
            </label>

            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={load}>{t("logs_refresh")}</Button>
              <Button variant="ghost" onClick={sendTest} disabled={busy}>
                {busy ? "\u2026" : t("logs_test")}
              </Button>
              <Button variant="ghost" onClick={copyAll} disabled={!rows.length}>
                {t("logs_copy")}
              </Button>
              <label className="flex items-center gap-1.5 text-xs text-mist-400">
                <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
                {t("logs_auto")}
              </label>
            </div>
          </div>

          {data?.path && (
            <p className="mt-3 text-[11px] text-mist-500 break-all">
              {t("logs_file")}: <span className="tnum">{data.path}</span>
              {data.size != null && ` \u00b7 ${(data.size / 1024).toFixed(1)} KB`}
            </p>
          )}
        </Panel>

        {/* ---------------- the log itself ---------------- */}
        <Panel title={`${t("logs_output")}${rows.length ? ` \u00b7 ${rows.length}` : ""}`}>
          {err && (
            <div className="text-down text-sm bg-down/10 border border-down/30 rounded-lg px-3 py-2 break-words">
              {err}
              <p className="mt-1 text-xs text-mist-500">{t("logs_forbidden_hint")}</p>
            </div>
          )}

          {!err && loading && <Spinner label="\u2026" />}

          {!err && !loading && !rows.length && (
            <p className="text-xs text-mist-500">{t("logs_empty")}</p>
          )}

          {!err && !!rows.length && (
            <div className="max-h-[60vh] overflow-auto rounded-lg bg-ink-900 border border-ink-600">
              <ul className="divide-y divide-ink-700/60">
                {rows.map((line, i) => {
                  const p = prettyLine(line);
                  return (
                    <li key={i} className="px-3 py-1.5 font-mono text-[11px] leading-relaxed">
                      {p ? (
                        <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                          <span className="text-mist-500 tnum shrink-0">{p.time}</span>
                          <span className={`shrink-0 font-semibold ${levelTone(line)}`}>{p.level}</span>
                          <span className="text-mist-500 shrink-0">{p.logger}</span>
                          <span className="text-mist-200 break-all min-w-0">{p.msg}</span>
                        </div>
                      ) : (
                        <span className={`whitespace-pre-wrap break-all ${levelTone(line)}`}>{line}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
