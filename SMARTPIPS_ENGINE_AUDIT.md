# SmartPips — pre-change audit / staged implementation

## Scope and evidence
Baseline file inventory: `QA/full-audit/REPOSITORY_BASELINE.json` (389 files, SHA-256 per file). Static scan: `QA/full-audit/STATIC_SCAN.json` (327 text files). Generated before implementation. Static coverage is not a claim of full behavioral verification of every adapter. Critical engine, decision, risk, trades, journal, native/research backtests, account-selection paths and frontend orchestration were inspected. Live exchange execution, production PostgreSQL and Docker are not accessible here.

## Maps (before changes)
- Backend: Django config → accounts/prefs → market adapters → strategy → trades; Bitunix demo/real, cTrader/MT5 and LBank have separate order endpoints.
- Model: User → Trade; optional Strategy FK + frozen name/version; mutable SL/TP, partial flags/remaining/realized PnL; costs and execution provenance added in 0008. No complete entry snapshot/event ledger. Strategy → immutable configuration versions. Global broker token/account context is not per-user capital.
- Strategy: candle fetch → completed/stale-bar checks → TF/HTF indicators → weighted base gates → selected strategy *filter* → current news veto → suggested risk/sizing. Alerts/chat/scalp use central decision, but exchange endpoints and backtests do not share the entire pipeline.
- Trade: manual/demo/exchange request → optional mirror → partial/close → accounting. Demo daemon observes public prices; paper auto-close is page-polled. Real mirror is not proof of actual fill. Current-stop-based grading is not initial-risk attribution.
- Backtest: validated historical OHLCV → completed contiguous window → prefix decisions → selected-rule filter → next-open execution → stop-first SL/TP → timeout. Optional backtesting.py is a separate research adapter; fixed stop/single target, not parity with live portfolio/exits.
- Frontend: eager App routes → public SiteLayout or protected Layout; Scalp orchestrates quotes, decision/AI, charts and order modal. Trades renders full filtered collection. Public EngineCore/AIBrain/ScalpReplay are illustrative, not backend traces.

## Priorities, root causes and remediation
|ID|Priority|Problem / root cause|Remediation / expected impact|Validation|
|---|---|---|---|---|
|SEC-01|P0|Unauthenticated GET changes global cTrader trading account; OAuth lacks state binding; raw provider errors echoed|Admin-only POST selection, signed one-time browser-bound OAuth state, generic errors. Prevent unauthorized account mutation; no PnL claim|Permission, state, replay, missing-token tests; real OAuth needs staging|
|RISK-01|P0|Bitunix risk-check exceptions allow orders; unknown balance and failed leverage adjustment do not block|Fail closed before place_order; zero balance must remain zero|Mock failures; no live orders|
|DATA-01|P0|Entry metadata mutable/incomplete; history cannot be attributed retrospectively|Add entry snapshot/hash and lifecycle events, leave historical unknowns unchanged; never backfill from current strategy|Creation, immutability, close idempotency, migration-state checks|
|PROB-01|P1|Journal 'calibration' adds arbitrary grade nudges to pooled win rate|Disable false calibration, keep raw strength and explicit probability unavailable|No invented probability tests|
|RISK-02|P0|Sizing rounds up; minimum lot can exceed budget; unknown contracts default to gold|Floor quantities; reject sub-minimum/unknown contract sizing; finite inputs|Boundary, NaN and budget tests|
|RISK-03|P0|Daily loss based on opening date and mixed sources|Use UTC close date and explicit source scope|Overnight and demo/real isolation tests|
|ENG-01|P1|Score weights sum to 110 despite 100 comment; correlated features double count|Preserve V1 pending validation, add family-bounded *shadow* evidence and honest strength; no auto activation|Bounds/determinism tests; ablation/OOS required|
|LIQ-01|P1|Near-level wick classified as sweep; fixed percent tolerance|Strict ATR-relative candidate/confirmation detector, initially research-only|No breach/no rejection/no follow-through cases|
|FLOW-01|P1|OHLCV inferred pressure and cTrader tick-direction counts called real; inconsistent scales|Explicit estimated provenance; real volume is not aggressor flow|Provenance/scale tests; cross-venue basis remains a limitation|
|REG-01|P1|Only trend/range/quiet/high-vol; coarse thresholds; no transition|Canonical regime policy as research module, do not claim predictive improvement|Policy tests + later walk-forward|
|NEWS-01|P1|Current-news exceptions swallowed, fixed USD window, no historical replay|Surface unavailable status; configurable replay remains blocked without news data|Failure/status tests; no synthetic news|
|BT-01|P1|Live/account/exit pipeline diverges from native and optional research engine|Explicit execution capability matrix; chronological 70/15/15 and expanding walk-forward tooling; no optimization/holdout-fit|Split/prefix isolation tests; real OHLCV needed|
|MIG-01|P0 staging blocker|Historical migration branches re-add fields already in initial migration|Do not edit/fake old history. Inspect installed state + targeted additive plan; fresh-install repair remains separate work|PostgreSQL staging and restored backup mandatory|
|EXIT-01|P1|Exit advice uses mutable stop/hardcoded TF; no persistent full lifecycle state|Immutable initial risk and event ledger foundation; partial/trailing unified simulator deferred|Event atomicity; no claim of complete state machine|
|UI-01|P3|All routes eager; all trade rows render; decorative visuals may look live|Bound table render/page routes in later UI work; label illustration; preserve chart dimensions|5000-row browser performance not yet certified|

## Non-goals of this release
No threshold tuning on the journal; no invented historical attribution, costs, equity, candles, probabilities or validation results. No real orders, exchange reconciliation writes or server migration was performed. A full 42-phase certification is not delivered by a foundation release. See changelog status matrix.
