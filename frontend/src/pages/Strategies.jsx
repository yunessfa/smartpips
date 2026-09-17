import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "../components/Layout.jsx";
import { Panel, Badge, Button, Field, Input, Select, Spinner } from "../components/ui.jsx";
import { strategyApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

/**
 * Strategy library, builder, backtest and analytics.
 *
 * Everything here is a thin surface over the backend:
 *   - the condition vocabulary is fetched from /strategy/vocabulary/ rather
 *     than hard-coded, so the builder can never offer a rule the validator
 *     would reject;
 *   - backtests call the existing engine through /strategies/:id/backtest/;
 *   - analytics are computed server-side from the user's real closed trades.
 *
 * No numbers on this page are invented client-side.
 */

const MARKETS = ["crypto", "forex", "metals"];
const DIRECTIONS = ["both", "long", "short"];

function emptyDraft() {
  return {
    name: "",
    description: "",
    market: "crypto",
    symbols: "",
    timeframes: "5m, 15m",
    direction: "both",
    min_confidence: 70,
    rules: [],
    weights: {},
    risk: {
      risk_per_trade_pct: 1,
      max_leverage: 10,
      max_open_positions: 3,
      min_rr: 2,
      trailing_stop: false,
      partial_tp: false,
    },
  };
}

export default function Strategies() {
  const { t, isRTL } = useI18n();
  const [items, setItems] = useState([]);
  const [vocab, setVocab] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [editing, setEditing] = useState(null); // draft object or null
  const [busyId, setBusyId] = useState(null);
  const [backtest, setBacktest] = useState(null); // { strategy, result }

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [list, analytic] = await Promise.all([
        strategyApi.strategies(),
        strategyApi.strategyAnalytics().catch(() => null),
      ]);
      setItems(Array.isArray(list) ? list : list?.results || []);
      setAnalytics(analytic);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    strategyApi.vocabulary().then(setVocab).catch(() => setVocab(null));
  }, [load]);

  const presets = useMemo(() => items.filter((s) => s.is_preset), [items]);
  const mine = useMemo(() => items.filter((s) => !s.is_preset), [items]);
  const active = useMemo(() => mine.find((s) => s.is_active) || null, [mine]);

  async function run(id, fn) {
    setBusyId(id);
    setErr(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function runBacktest(strategy) {
    setBusyId(strategy.id);
    setErr(null);
    try {
      const result = await strategyApi.runStrategyBacktest(strategy.id, {});
      setBacktest({ strategy, result });
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusyId(null);
    }
  }

  function startEdit(strategy) {
    const current = strategy?.current || {};
    setEditing({
      id: strategy.id,
      name: strategy.name,
      description: strategy.description || "",
      market: strategy.market,
      symbols: (strategy.symbols || []).join(", "),
      timeframes: (strategy.timeframes || []).join(", "),
      direction: strategy.direction,
      min_confidence: current.min_confidence ?? 70,
      rules: current.rules || [],
      weights: current.weights || {},
      risk: current.risk || {},
    });
  }

  return (
    <>
      <PageHeader title={t("st_title")} subtitle={t("st_sub")} />

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 md:p-6">
        {err && (
          <p className="rounded-lg border border-down/30 bg-down/10 px-3 py-2 text-xs text-down">
            {err}
          </p>
        )}

        {/* Active strategy summary. One strategy is live at a time, matching
            how the engine is consumed. */}
        <Panel title={t("st_active")}>
          {active ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-mist-100">
                  {active.name}{" "}
                  <span className="text-mist-500">v{active.current?.version ?? 1}</span>
                </p>
                <p className="mt-1 text-xs text-mist-500">
                  {t(`st_market_${active.market}`)} · {t(`st_dir_${active.direction}`)} ·{" "}
                  {t("st_min_conf")} {active.current?.min_confidence ?? "—"}%
                </p>
              </div>
              <Button
                variant="ghost"
                onClick={() => run(active.id, () => strategyApi.deactivateStrategy(active.id))}
                disabled={busyId === active.id}
              >
                {t("st_deactivate")}
              </Button>
            </div>
          ) : (
            <p className="text-xs text-mist-500">{t("st_none_active")}</p>
          )}
        </Panel>

        {/* ------------------------------------------------ my strategies */}
        <Panel
          title={t("st_mine")}
          action={<Button onClick={() => setEditing(emptyDraft())}>{t("st_new")}</Button>}
        >
          {loading ? (
            <Spinner label="…" />
          ) : mine.length === 0 ? (
            <p className="text-xs text-mist-500">{t("st_mine_empty")}</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {mine.map((s) => (
                <StrategyCard
                  key={s.id}
                  strategy={s}
                  busy={busyId === s.id}
                  onEdit={() => startEdit(s)}
                  onBacktest={() => runBacktest(s)}
                  onActivate={() => run(s.id, () => strategyApi.activateStrategy(s.id))}
                  onDeactivate={() => run(s.id, () => strategyApi.deactivateStrategy(s.id))}
                  onArchive={() =>
                    window.confirm(`${t("st_archive")} — ${s.name}?`) &&
                    run(s.id, () => strategyApi.removeStrategy(s.id))
                  }
                />
              ))}
            </div>
          )}
        </Panel>

        {/* ----------------------------------------------------- presets */}
        <Panel title={t("st_presets")}>
          <p className="mb-3 text-xs text-mist-500">{t("st_presets_hint")}</p>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {presets.map((s) => (
              <div key={s.id} className="rounded-xl border border-ink-500 bg-ink-800/60 p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 truncate text-sm font-semibold text-mist-100">{s.name}</p>
                  <Badge>{t(`st_market_${s.market}`)}</Badge>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-mist-500">{s.description}</p>
                <div className="mt-2.5 flex flex-wrap gap-1.5 text-[11px] text-mist-500">
                  <span className="rounded border border-ink-500 px-1.5 py-0.5">
                    {t("st_min_conf")} {s.current?.min_confidence}%
                  </span>
                  <span className="rounded border border-ink-500 px-1.5 py-0.5">
                    {(s.current?.rules || []).length} {t("st_rules")}
                  </span>
                  <span className="rounded border border-ink-500 px-1.5 py-0.5">
                    {(s.timeframes || []).join(" · ")}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    onClick={() => run(s.id, () => strategyApi.activateStrategy(s.id))}
                    disabled={busyId === s.id}
                  >
                    {t("st_use")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => run(s.id, () => strategyApi.cloneStrategy(s.id))}
                    disabled={busyId === s.id}
                  >
                    {t("st_clone")}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        {/* --------------------------------------------------- analytics */}
        <Panel title={t("st_analytics")}>
          <p className="mb-3 text-xs text-mist-500">{t("st_analytics_hint")}</p>
          {!analytics || !analytics.results?.length ? (
            <p className="text-xs text-mist-500">{t("st_analytics_empty")}</p>
          ) : (
            // Internal horizontal scroll only - the page itself never widens.
            <div className="-mx-1 overflow-x-auto px-1">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b border-ink-500 text-xs text-mist-500">
                  <tr>
                    <th className="px-2 py-2 text-start">{t("st_col_strategy")}</th>
                    <th className="px-2 py-2 text-end">{t("st_col_trades")}</th>
                    <th className="px-2 py-2 text-end">{t("st_col_winrate")}</th>
                    <th className="px-2 py-2 text-end">{t("st_col_pnl")}</th>
                    <th className="px-2 py-2 text-end">{t("st_col_pf")}</th>
                    <th className="px-2 py-2 text-end">{t("st_col_dd")}</th>
                    <th className="px-2 py-2 text-end">{t("st_col_hold")}</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.results.map((row) => (
                    <tr key={String(row.strategy_id || row.strategy)} className="border-b border-ink-600/50">
                      <td className="px-2 py-2.5 text-mist-100">
                        {row.strategy}
                        {row.version ? <span className="text-mist-500"> v{row.version}</span> : null}
                      </td>
                      <td className="tnum px-2 py-2.5 text-end text-mist-300">{row.trades}</td>
                      <td className="tnum px-2 py-2.5 text-end text-mist-300">{row.win_rate}%</td>
                      <td
                        className={`tnum px-2 py-2.5 text-end ${
                          row.pnl > 0 ? "text-up" : row.pnl < 0 ? "text-down" : "text-mist-300"
                        }`}
                      >
                        {row.pnl}
                      </td>
                      <td className="tnum px-2 py-2.5 text-end text-mist-300">
                        {row.profit_factor ?? "—"}
                      </td>
                      <td className="tnum px-2 py-2.5 text-end text-mist-300">{row.max_drawdown}</td>
                      <td className="tnum px-2 py-2.5 text-end text-mist-300">
                        {row.avg_hold_minutes != null ? `${row.avg_hold_minutes}m` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      {editing && (
        <BuilderModal
          draft={editing}
          vocab={vocab}
          isRTL={isRTL}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      )}

      {backtest && <BacktestModal data={backtest} onClose={() => setBacktest(null)} />}
    </>
  );
}

/* ------------------------------------------------------------------ card */

function StrategyCard({ strategy, busy, onEdit, onBacktest, onActivate, onDeactivate, onArchive }) {
  const { t } = useI18n();
  const current = strategy.current || {};
  const tested = Boolean(current.backtest_at);

  return (
    <div className="rounded-xl border border-ink-500 bg-ink-800/60 p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-mist-100">
            {strategy.name} <span className="text-mist-500">v{current.version ?? 1}</span>
          </p>
          <p className="mt-1 text-xs text-mist-500">
            {t(`st_market_${strategy.market}`)} · {t(`st_dir_${strategy.direction}`)} ·{" "}
            {(current.rules || []).length} {t("st_rules")}
          </p>
        </div>
        {strategy.is_active ? <Badge tone="up">{t("st_live")}</Badge> : null}
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5 text-[11px]">
        <span className="rounded border border-ink-500 px-1.5 py-0.5 text-mist-500">
          {t("st_min_conf")} {current.min_confidence ?? "—"}%
        </span>
        <span
          className={`rounded border px-1.5 py-0.5 ${
            tested ? "border-up/30 text-up" : "border-ink-500 text-mist-500"
          }`}
        >
          {tested ? t("st_backtested") : t("st_not_backtested")}
        </span>
      </div>

      {tested && current.backtest ? (
        <div className="tnum mt-2.5 grid grid-cols-3 gap-2 text-[11px] text-mist-300">
          <span>
            {t("bt_trades")}: {current.backtest.trades ?? "—"}
          </span>
          <span>
            {t("bt_winrate")}: {current.backtest.win_rate ?? "—"}
          </span>
          <span>
            {t("bt_pf")}: {current.backtest.profit_factor ?? "—"}
          </span>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="ghost" onClick={onEdit} disabled={busy}>
          {t("st_edit")}
        </Button>
        <Button variant="ghost" onClick={onBacktest} disabled={busy}>
          {t("st_backtest")}
        </Button>
        {strategy.is_active ? (
          <Button variant="ghost" onClick={onDeactivate} disabled={busy}>
            {t("st_deactivate")}
          </Button>
        ) : (
          <Button onClick={onActivate} disabled={busy || !strategy.can_activate}>
            {t("st_activate")}
          </Button>
        )}
        <Button variant="danger" onClick={onArchive} disabled={busy}>
          {t("st_archive")}
        </Button>
      </div>

      {!strategy.can_activate && !strategy.is_active && (
        <p className="mt-2 text-[11px] text-mist-500">{t("st_needs_backtest")}</p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- builder */

function BuilderModal({ draft, vocab, isRTL, onClose, onSaved }) {
  const { t } = useI18n();
  const [form, setForm] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // `t` echoes the key back when a translation is missing, which would print
  // "st_state_bullish" in the UI. The vocabulary comes from the backend and may
  // grow, so fall back to the raw server value instead of a broken key.
  const lab = (key, fallback) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const blocks = vocab?.blocks || [];
  const blockByKey = useMemo(() => Object.fromEntries(blocks.map((b) => [b.key, b])), [blocks]);

  const weightTotal = Object.values(form.weights || {}).reduce(
    (sum, v) => sum + (Number(v) || 0),
    0,
  );

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function defaultValue(block) {
    if (block.kind === "state") return block.states[0];
    if (block.kind === "number") return 0;
    return null;
  }

  function addRule() {
    const first = blocks[0];
    if (!first) return;
    set("rules", [
      ...form.rules,
      {
        block: first.key,
        operator: first.operators[0],
        value: defaultValue(first),
        applies_to: "both",
        required: false,
      },
    ]);
  }

  function updateRule(index, patch) {
    set("rules", form.rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  }

  function removeRule(index) {
    set("rules", form.rules.filter((_, i) => i !== index));
  }

  async function save() {
    setBusy(true);
    setErr(null);
    const payload = {
      name: form.name,
      description: form.description,
      market: form.market,
      direction: form.direction,
      symbols: form.symbols.split(",").map((s) => s.trim()).filter(Boolean),
      timeframes: form.timeframes.split(",").map((s) => s.trim()).filter(Boolean),
      min_confidence: Number(form.min_confidence),
      rules: form.rules,
      // An empty weight map is valid and means "weight every group equally", so
      // a partially filled builder still saves.
      weights: form.weights,
      risk: form.risk,
    };
    try {
      if (form.id) await strategyApi.updateStrategy(form.id, payload);
      else await strategyApi.createStrategy(payload);
      await onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      dir={isRTL ? "rtl" : "ltr"}
    >
      {/* w-full + max-w keeps the sheet inside a 390px viewport; on desktop it
          becomes a centred dialog rather than a full-bleed sheet. */}
      <div
        className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl border border-ink-500 bg-ink-800 p-4 sm:rounded-2xl sm:p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-mist-100">
            {form.id ? t("st_edit_title") : t("st_new_title")}
          </h3>
          <button onClick={onClose} className="px-2 py-1 text-sm text-mist-500">
            {t("cancel")}
          </button>
        </div>

        {form.id && (
          <p className="mb-3 rounded-lg border border-ink-500 bg-ink-700/60 px-3 py-2 text-[11px] leading-relaxed text-mist-500">
            {t("st_version_note")}
          </p>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("st_name")}>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label={t("st_market")}>
            <Select value={form.market} onChange={(e) => set("market", e.target.value)}>
              {MARKETS.map((m) => (
                <option key={m} value={m}>
                  {t(`st_market_${m}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("st_symbols")}>
            <Input
              value={form.symbols}
              onChange={(e) => set("symbols", e.target.value)}
              placeholder="BTCUSDT, ETHUSDT"
              dir="ltr"
            />
          </Field>
          <Field label={t("st_timeframes")}>
            <Input
              value={form.timeframes}
              onChange={(e) => set("timeframes", e.target.value)}
              placeholder="5m, 15m, 1h"
              dir="ltr"
            />
          </Field>
          <Field label={t("st_direction")}>
            <Select value={form.direction} onChange={(e) => set("direction", e.target.value)}>
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>
                  {t(`st_dir_${d}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={`${t("st_min_conf")} (%)`}>
            <Input
              type="number"
              min="0"
              max="100"
              value={form.min_confidence}
              onChange={(e) => set("min_confidence", e.target.value)}
            />
          </Field>
        </div>

        {/* ------------------------------------------------------ rules */}
        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-mist-500">
              {t("st_conditions")}
            </h4>
            <Button variant="ghost" onClick={addRule} disabled={!blocks.length}>
              + {t("st_add_rule")}
            </Button>
          </div>

          {!vocab && <p className="text-xs text-mist-500">…</p>}

          <div className="space-y-2">
            {form.rules.map((rule, index) => {
              const meta = blockByKey[rule.block];
              const between = rule.operator === "between";
              const pair = Array.isArray(rule.value) ? rule.value : [0, 0];
              return (
                <div key={index} className="rounded-lg border border-ink-500 bg-ink-700/40 p-2.5">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1.4fr_1fr_1fr]">
                    <Select
                      value={rule.block}
                      onChange={(e) => {
                        const next = blockByKey[e.target.value];
                        updateRule(index, {
                          block: next.key,
                          operator: next.operators[0],
                          value: defaultValue(next),
                        });
                      }}
                    >
                      {blocks.map((b) => (
                        <option key={b.key} value={b.key}>
                          {b.label}
                        </option>
                      ))}
                    </Select>

                    <Select
                      value={rule.operator}
                      onChange={(e) =>
                        updateRule(index, {
                          operator: e.target.value,
                          value:
                            e.target.value === "between"
                              ? [0, 0]
                              : between
                              ? 0
                              : rule.value,
                        })
                      }
                    >
                      {(meta?.operators || []).map((op) => (
                        <option key={op} value={op}>
                          {lab(`st_op_${op}`, op)}
                        </option>
                      ))}
                    </Select>

                    {meta?.kind === "state" && (
                      <Select
                        value={rule.value ?? ""}
                        onChange={(e) => updateRule(index, { value: e.target.value })}
                      >
                        {meta.states.map((s) => (
                          <option key={s} value={s}>
                            {lab(`st_state_${s}`, s)}
                          </option>
                        ))}
                      </Select>
                    )}

                    {meta?.kind === "number" && !between && (
                      <Input
                        type="number"
                        value={rule.value ?? 0}
                        onChange={(e) => updateRule(index, { value: Number(e.target.value) })}
                      />
                    )}

                    {meta?.kind === "number" && between && (
                      <div className="flex gap-2">
                        <Input
                          type="number"
                          value={pair[0]}
                          onChange={(e) =>
                            updateRule(index, { value: [Number(e.target.value), pair[1]] })
                          }
                        />
                        <Input
                          type="number"
                          value={pair[1]}
                          onChange={(e) =>
                            updateRule(index, { value: [pair[0], Number(e.target.value)] })
                          }
                        />
                      </div>
                    )}
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-mist-500">
                    <label className="flex items-center gap-1.5">
                      {t("st_applies")}
                      <select
                        value={rule.applies_to}
                        onChange={(e) => updateRule(index, { applies_to: e.target.value })}
                        className="rounded border border-ink-500 bg-ink-800 px-1.5 py-1 text-mist-200"
                      >
                        {DIRECTIONS.map((d) => (
                          <option key={d} value={d}>
                            {t(`st_dir_${d}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={!!rule.required}
                        onChange={(e) => updateRule(index, { required: e.target.checked })}
                      />
                      {t("st_required")}
                    </label>
                    <button
                      onClick={() => removeRule(index)}
                      className="ms-auto text-down hover:underline"
                    >
                      {t("st_remove")}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ---------------------------------------------------- weights */}
        {vocab && (
          <div className="mt-5">
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mist-500">
              {t("st_weights")}{" "}
              <span
                className={
                  weightTotal && (weightTotal < 95 || weightTotal > 105)
                    ? "text-down"
                    : "text-mist-500"
                }
              >
                ({weightTotal || 0}%)
              </span>
            </h4>
            <p className="mb-2 text-[11px] text-mist-500">{t("st_weights_hint")}</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {(vocab.weight_groups || []).map((group) => (
                <label key={group} className="flex items-center gap-2 text-[11px] text-mist-500">
                  <span className="min-w-0 flex-1 truncate">{lab(`st_group_${group}`, group)}</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={form.weights?.[group] ?? ""}
                    onChange={(e) => {
                      const next = { ...(form.weights || {}) };
                      if (e.target.value === "") delete next[group];
                      else next[group] = Number(e.target.value);
                      set("weights", next);
                    }}
                    className="tnum w-16 rounded border border-ink-500 bg-ink-800 px-2 py-1 text-mist-100"
                  />
                </label>
              ))}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------- risk */}
        <div className="mt-5">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mist-500">
            {t("st_risk")}
          </h4>
          <p className="mb-2 text-[11px] leading-relaxed text-mist-500">{t("st_risk_hint")}</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["risk_per_trade_pct", t("st_risk_per_trade")],
              ["max_leverage", t("st_max_lev")],
              ["max_open_positions", t("st_max_open")],
              ["min_rr", t("st_min_rr")],
            ].map(([key, label]) => (
              <Field key={key} label={label}>
                <Input
                  type="number"
                  value={form.risk?.[key] ?? ""}
                  onChange={(e) => {
                    const next = { ...(form.risk || {}) };
                    if (e.target.value === "") delete next[key];
                    else next[key] = Number(e.target.value);
                    set("risk", next);
                  }}
                />
              </Field>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-mist-500">
            {[
              ["trailing_stop", t("st_trailing")],
              ["partial_tp", t("st_partial_tp")],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={!!form.risk?.[key]}
                  onChange={(e) => set("risk", { ...(form.risk || {}), [key]: e.target.checked })}
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        {err && <p className="mt-3 text-xs text-down">{err}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button onClick={save} disabled={busy || !form.name.trim()}>
            {busy ? "…" : t("save")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- backtest */

function BacktestModal({ data, onClose }) {
  const { t } = useI18n();
  const { strategy, result } = data;
  const curve = result.equity_curve || [];

  const rows = [
    [t("bt_trades"), result.trades],
    [t("bt_winrate"), result.win_rate],
    [t("bt_pf"), result.profit_factor],
    [t("bt_avg_r"), result.avg_r],
    [t("bt_expectancy"), result.expectancy_r],
    [t("bt_dd"), result.max_drawdown_r],
    [t("bt_total_r"), result.total_r],
    [t("bt_wins"), result.wins],
    [t("bt_losses"), result.losses],
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-ink-500 bg-ink-800 p-4 sm:rounded-2xl sm:p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-mist-100">
          {t("bt_title")} — {strategy.name}
        </h3>
        <p className="mt-1 text-[11px] text-mist-500">
          {result.symbol} · {result.timeframe} · {result.candles_used} {t("bt_candles")}
        </p>

        <div className="mt-3 grid grid-cols-3 gap-2">
          {rows.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-ink-500 bg-ink-700/40 p-2">
              <p className="text-[10px] uppercase tracking-wide text-mist-500">{label}</p>
              <p className="tnum mt-0.5 text-sm text-mist-100">{value ?? "—"}</p>
            </div>
          ))}
        </div>

        {curve.length > 1 && <EquityCurve points={curve} />}

        <p className="mt-4 rounded-lg border border-gold/25 bg-gold/[0.06] px-3 py-2 text-[11px] leading-relaxed text-mist-300">
          {t("bt_disclaimer")}
        </p>

        <div className="mt-4 flex justify-end">
          <Button onClick={onClose}>{t("close")}</Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Equity curve drawn as an inline SVG.
 *
 * A charting library would be overkill for a single sparkline, and an SVG with
 * a viewBox scales to its container instead of forcing a pixel width — which is
 * what keeps this from widening the page on a phone.
 */
function EquityCurve({ points }) {
  const { t } = useI18n();
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const span = max - min || 1;
  const path = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 100;
      const y = 100 - ((value - min) / span) * 100;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const positive = points[points.length - 1] >= 0;

  return (
    <div className="mt-3">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-mist-500">{t("bt_equity")}</p>
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="h-24 w-full rounded-lg border border-ink-500 bg-ink-900"
      >
        <path
          d={path}
          fill="none"
          stroke={positive ? "#0ECB81" : "#F6465A"}
          strokeWidth="1.2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}
