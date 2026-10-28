# SmartPips — architecture, compatibility and implementation boundaries

## Principle
Context + evidence + risk + execution + lifecycle + historical learning. A plan is not an execution confirmation. Strength is not probability. Missing evidence is unknown, not a positive vote. Deterministic analysis is authoritative; optional LLM prose cannot change its decision.

## Existing path preserved
Market adapters → `decision.decide` → completed/stale bars → V1 TF/HTF features and gates → selected strategy filter → current news veto → suggested risk/sizing → scalp/chat/alerts. Native/research backtest uses prefix decisions, not the entire live account pipeline. Exchange adapters still have separate execution boundaries.

## New foundation
- `data_quality.inspect_bars`: finite positive timestamped OHLC, volume non-negative, coherent bounds, no hidden duplicate/reordering, completed bars only; crypto gaps veto live entries. Metals session gaps are disclosed. HTF invalid data is omitted, never interpolated. No full exchange-calendar completeness guarantee.
- `evidence.bounded_family_model`: nine independent budget slots: TREND/STRUCTURE/LIQUIDITY/ORDER_FLOW/MOMENTUM/LOCATION/VOLATILITY/SESSION/RISK. Within-family votes are averaged/clamped, not added. Missing families stay null. Initial integration only maps evidence with proven semantics (HTF bias and normalized OHLCV delta). This is intentionally incomplete shadow telemetry, NOT V2 production scoring.
- `strict_liquidity.confirmed_sweep`: known prior level → ATR-relative actual breach → rejection → close back → separate later structure-follow-through bar. Caller must supply a genuinely prior level. Not wired to V1 execution. ATR coefficients are documented hypotheses, not journal-tuned improvements.
- `regime_policy`: explicit allowed-setup policy for six canonical regimes; this is NOT a newly validated six-state detector. V1 regime detector remains active.
- `enrich_explanation`: final decision/gate reason survives scope/news/risk veto; no fake missing confirmation level; raw score retained, bounded display strength separate; historical probability unavailable. No false ENTRY CONFIRMED on model plans.
- Flow provenance: OHLCV allocation and quote tick direction both ESTIMATED_ORDER_FLOW. Units/source exposed. Genuine bid/ask aggressor feed remains unavailable; exchange volume does not prove aggressor flow. Legacy V1 numeric flow behavior is not silently normalized/reweighted.

## Entry context and lifecycle
`Trade.entry_snapshot` JSON + SHA-256 captures strategy/name/version, engine/timeframe, indicator/evidence fields, entry/SL/TP, initial planned gross risk and capture quality. Missing fields remain null. New ordinary journal entries capture only known entry fields. Scalp/exchange entries can carry a user/symbol-bound signed analysis context (180s expiry); edited client attribution must match that context. Signing is integrity, not encryption or execution authorization. No secret is included.

Actual entered prices/sizing are separated from the model context. A signed analysis can be WAIT while a human chooses a discretionary trade; it is not upgraded to engine-confirmed execution. Full capture does not mean independently verified exchange fill. Historical rows receive empty snapshot/default hash via additive migration, no invented backfill.

New Trade.save creates ENTRY event. Changes to stop/target/status/partial flags append state events in the same transaction. Existing close/partial row locks and idempotency remain. Snapshot/hash updates via normal model/queryset paths are rejected; events are append-only through application methods. This is NOT database-level WORM: privileged raw SQL, database admin actions, cascade deletion and future unguarded code require separate controls. No cryptographic chain/externally anchored ledger is claimed.

TradeEvent is a lifecycle foundation, not a complete ENTRY→TP1→BE→TP2→RUNNER→TRAIL→EXIT executor. Historical intermediate events cannot be reconstructed. Exit advice is still not a unified stateful portfolio exit engine.

## Analytics
Pure `trades.analytics.analyze(rows)` also serves authenticated user-scoped `/api/trades/analytics/`. Source/date/symbol/direction/timeframe/version filters precede aggregation. `/api/trades/{id}/audit_timeline/` is owner-scoped. Segments retain unknowns. PnL, verified net, initial planned gross-risk R, account equity and conditional probability are distinct quantities. A descriptive Wilson interval is not causal/OOS confidence. Rank best/worst regimes only after recorded attribution and an adequate pre-registered cohort exist.

## Research protocol
`evaluate_engine`: fixed parameters, prefix-only 70/15/15 and three expanding-context tests within pre-holdout data. Holdout not accessed by default. No optimization performed. Explicit opt-in final evaluation is NOT a single-use lock; manifest pre-registration and external holdout custody remain necessary. Optional backtesting.py remains isolated and cannot overwrite native results/unlock strategy activation.

## Target architecture still to implement
Data gate → regime → HTF → structure → strict liquidity → flow → momentum → location → setup state machine → validation → authoritative account/portfolio risk → sizing → decision → independently running stateful management/exit → verified journal → attribution.

Unfinished: unified authoritative account/venue identity; portfolio/correlation exposure and liquidation schedules; historical news replay; adaptive multi-stage entry; complete execution policy parity across Bitunix/LBank/MT5/cTrader; partial/trailing/portfolio simulator; prospective calibration; A/B V1/V2/V3 + feature ablation with real OHLCV. No UI polish or journal statistics can substitute for these.
