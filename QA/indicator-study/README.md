# Indicator study (2026-10)

Question: do the engine's indicators carry directional information, on crypto futures, after costs?

Method: the PRODUCT engine (`apps.strategy.engine.run_strategy`, safe mode, 300-bar window, real closed
HTF candles) evaluated on Bitstamp BTC/USD 2019-01 .. 2026-10 (resampled; spot proxy for the perp):
1h every bar (68k), 15m every 2nd bar (137k), 5m every 6th bar (137k) — 342k evaluations, 0 errors.
For every reading: sign-adjusted forward return (bps) over 3-48 bars, hit rate, overlap-adjusted t,
split 2019-2022 (TR) vs 2023-2026 (HO); continuous readings: Spearman IC + top-minus-bottom quintile.
Round-trip cost reference: ~10 bps (maker entry, taker exit, slippage).

Findings (`report.json`):
* 5m/15m: no reading exceeds ~±2.5 bps; signs flip between TR and HO. Momentum readings (RSI, MACD,
  EMA gap, estimated order flow, premium/discount) have small NEGATIVE IC (-0.02..-0.05): short-term
  reversal, far below costs.
* Engine final signal on 5m/15m: ≈0 or negative. Higher "conviction" does not raise the edge.
* Only the higher-timeframe trend / trend family is consistently positive at long horizons
  (1h, 48 bars: +40 bps TR, +22 bps HO) — the basis of the trend-pullback playbook.
* Redundancy: VWAP vs EMA200 ρ=0.85; MACD/RSI/SMC/flow/premium-discount form one cluster. The
  12-component score is ~2-3 independent pieces of information counted several times.
* The engine says WAIT ~95% of the time, mostly "low score"/"weak conviction" — the repeated answer users saw.

Not testable offline: funding rate, open interest, liquidations, real taker buy/sell volume, order book.
