# SmartPips — design-system foundation, not a completed redesign

## Product hierarchy
Private intelligence terminal first; public editorial/cinematic surface second. WAIT is an intentional decision, never a failure or hidden empty card. Critical risk and data quality precede decorative animation. No unverified historical win rate or simulated live example may appear as real execution evidence.

## Implemented tokens
`frontend/src/design-system.css` defines background #050607 / #080A0C / #0D1013; text #F3F4F5, cool secondary #A8B0BA, muted #6F7883; restrained warm gold #CFA65B, green #56A581, red #C87575. Audit surfaces adopt scoped `.sp-audit`. Existing terminal/TradingView layout is not globally restyled. This avoids another chart-height regression.

Persian: Vazirmatn then system sans; technical: JetBrains Mono / IBM Plex Mono / monospace. Use tabular numerals, readable Persian leading, no negative Persian tracking. Font names are fallbacks, not a claim licensed font binaries are bundled/offline guaranteed.

Motion tokens: page600ms, section500ms, hover200ms, signal2s, chart2s. New audit surfaces use no ornamental perpetual animation and respect prefers-reduced-motion. Migrating every legacy motion primitive/timer/offscreen animation is NOT completed. Prefer transforms/opacity; blur is not a guaranteed GPU-free effect.

## Actual UI changes
- Trades: source-separated audit metrics with loading/error/unknown states; verified net and initial R are null when unsupported. Existing aggregate statistics remain legacy pooled journal observations, not a production exchange balance.
- Trade journal: 50-row pagination replacing silently showing only the first100. Export still uses the complete filtered population. Filtering remains in memory; this is not server cursor pagination/virtualization.
- Protected feature routes are lazy-loaded. Main initial chunk still slightly exceeds the build warning limit; code splitting is improved, not fully optimized.
- Scalp: read-only backend DecisionAudit displays real explanation fields, missing families and research-only evidence status. It does not manufacture green ticks or confirmation levels.
- Public EngineCore explicitly labeled illustrative, not live. It remains a marketing diagram; a complete real-data animated replacement is pending.
- Admin: explicit authenticated cTrader account selection and status refresh. Existing public GET links no longer mutate trading accounts.

## Layout invariants
Preserve existing shared chart parent `height:80%`, top/lower chart dimensions, TradingView integration and position-chart behavior. Changes do not remove chart heights. Mobile new content wraps; technical hashes/long identifiers must break, figures and order actions stay legible. No redesign of chart aspect ratios.

## Target surfaces (not fabricated as completed)
- Mobile order: Signal → Entry/SL/TP → Why → Risk → Chart → Analysis.
- Dashboard: actual decision-centered Signal Strength + model validation status, initial risk/levels and 4–6 genuinely recorded factors.
- WAIT: precise blocking family, available evidence, next confirmation only when calculated; unknown confirmation stays unavailable.
- Trade detail: immutable entry snapshot + actual event timeline. Do not draw historical TP1/MSS events if not journaled.
- Strategy cards: version/source/sample/WR/PF/expectancy/DD plus unknown coverage and uncertainty. Do not rank eight discretionary trades against 500 clean engine observations as equivalent.
- Research/product/editorial pages: common hero/problem/engine/data/explanation/CTA. No private journal or account sample is published automatically. Cinema/articles are deferred until engine parity and validation are real.
- Analytics visualization targets: equity/drawdown/R/PnL source/symbol/session/strategy, leverage/holding relationships, tooltip/date/symbol/strategy filters. Only the source-count audit artifact is delivered here; the complete interactive chart suite is NOT implemented.

## QA standard
Desktop1440, mobile390, reduced motion, unknown/empty/loading/error, 5000-row synthetic pagination workload and preserved charts. Local mocked UI tests are not server/exchange performance verification. Device/WebView/browser matrix, real production response times, complete motion CPU profiling and accessibility audit remain staging work.
