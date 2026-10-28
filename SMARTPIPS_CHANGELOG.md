# SmartPips — audited foundation release

## Scope honesty
This delivery is a P0/P1/P2 foundation and small P3 usability changes, NOT completion of all 42 phases. No engine profitability/accuracy uplift is asserted. The repository was inventoried and critical paths audited before implementation; private data was analyzed before choosing changes.

## Implemented
- Reject unauthenticated/GET cTrader account mutation; admin POST selection; expiring signed browser-bound OAuth with shared database single-use nonce. No provider token/error payload echoed. Existing selected account is cleared only after successful NEW authorization; existing connections are untouched by migration. Callback now asks for explicit Admin selection.
- Bitunix real orders fail closed on risk-check failure, unknown balance, insufficient funds and failed requested leverage change. Explicit numeric zero is not replaced by another balance field.
- LBank real confirmation requires boolean true; finite positive order amount/limit price/type validation. MT5 numeric volume/SL/TP validation hardened. This is NOT complete account/portfolio risk parity for these adapters.
- Floor sizing rather than round up; reject sub-minimum lot when over budget and unknown contract assumptions. Daily guard uses close day UTC and source isolation. Scalp source included in non-real margin scope. Invalid balance/risk and failed exposure checks veto the decision. A lower user risk request is never raised to a minimum.
- Strict completed OHLCV gate for live TF/HTF; invalid/duplicate/nonmonotonic/gapped crypto data not used as valid evidence.
- Disabled arbitrary pooled-WR grade-nudge 'calibration'. Separate bounded strength, unavailable historical probability, honest flow provenance/units and final explanation gate.
- Shadow family evidence, strict ATR sweep research helper and six-state regime policy. V1 execution weights/setup logic preserved pending OOS validation.
- Additive trades0009 entry snapshot/hash + event table; cTrader0002 OAuth attempt table. Server-signed context integrated into scalp quick journal/modal/Bitunix mirror when present. Historical rows not reconstructed or PnL rewritten.
- Deterministic user-scoped trade analytics and audit timeline API, actual Excel crosschecks, source-separated UI metrics. Unknown R/net/attribution remain unknown.
- Fixed-parameter 70/15/15 evaluation utility and pre-holdout expanding walk-forward; optional backtesting.py stays separate.
- 50-row pagination, lazy feature routes, real-data explanation audit component, scoped design tokens and illustrative public diagram label.
- Six reports, pre-change file inventory, tests, QA artifacts and fail-closed additive deployment helper.

## Phase status matrix
|Phases|Status in this delivery|
|---|---|
|0 repository audit|Inventory/static scan + deep audit of critical paths; not a behavioral proof of every source file|
|1 journal analytics|Implemented core engine and many segments; missing evidence explicitly unavailable|
|2 immutable attribution|New-entry foundation + signed context; old unknowns retained; not DB-admin-proof WORM|
|3 layered engine|Architecture mapped; live data boundary and shadow trace added; full independent-layer rewrite pending|
|4 family evidence|Bounded research model, sparse truthful mapping; production reweighting pending|
|5 confidence/probability|False calibration removed; probability unavailable; no prospective calibration yet|
|6 liquidity/structure|Strict sweep research helper tested; production liquidity replacement/OB/FVG accuracy work pending|
|7 flow honesty|Provenance/mode/units exposed; actual aggressor feed not implemented|
|8 regime|Six-state research policy only; validated detector not implemented|
|9 news|Unavailable surfaced; configurable historical replay/affected-symbol policy pending|
|10 adaptive entry|Not implemented; V1 setup retained|
|11–13 unified risk/leverage/portfolio|Specific sizing/daily/fail-open fixes; authoritative portfolio/correlation/liquidation engine pending|
|14 exit lifecycle|Snapshot/event foundation; complete stateful executor and backtest parity pending|
|15 manual exit counterfactual|Note proxies audited; engine state and post-exit bars absent; comparison not run|
|16 attribution cards|Analytics segments/API foundation; full trustworthy performance-card UI pending|
|17–20 backtest/OOS/ablation/A-B|Temporal utility + existing conservative simulator tests; real-data evaluation and advanced execution not run/implemented|
|21 explanation|Backend trace + actual final veto/unknowns; complete positive/negative/invalidation/next-event tree not fabricated|
|22–28 terminal/hero/engine/signal/WAIT redesign|Scoped tokens and read-only evidence UI; full cinematic/dashboard redesign pending|
|29–31 Trades/detail/Strategies|Source audit UI + pagination + snapshot/events API; complete charts/timeline/cards pending|
|32–34 Research/product/motion|Documented target; public privacy preserved; no complete new article/motion system|
|35–37 mobile/performance/visuals|Local synthetic pagination/mobile QA; chart artifact; not full interactive analytics suite|
|38 security/integrity|Specific critical fixes and app-level immutable context; full security audit/DB constraints pending|
|39 tests|Regression/new tests + local QA; no PostgreSQL/venue/Docker certification|
|40 preserve production|Auth/CSRF/refresh/alerts regression checks; chart layout preserved; no actual production operation|
|41 migrations|Installed-state additive smoke + explicit plan command; legacy fresh-install conflict remains staging blocker|
|42 deliverables|All six requested report filenames supplied, including clear not-run/pending sections|

## Deployment safety
Read `deploy/ENTRY-AUDIT-DEPLOY-FA.md`. New helper only accepts an installed consistent baseline with trades0008 and cTrader0001. It refuses historical prerequisites, backwards migration and schema/history mismatch. PostgreSQL restored staging verification is required before production. Do NOT run a blanket migrate/fake/reset to bypass the legacy fresh-install conflict. Code is not a guarantee all trading risk is protected; keep real automation paused during review.
