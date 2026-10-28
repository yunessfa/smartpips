# SmartPips — backtest/evaluation report

## Result status: no market-performance certification
The uploaded Excel contains journal outcomes, not historical market candles. No adequate immutable OHLCV/news/funding corpus was supplied for re-running the proposed engines. Unit fixtures and UI previews are NOT real market backtests.

|Partition|Protocol|Market result|
|---|---|---|
|Train|First 70%, fixed parameters; no fitting implemented|NOT RUN — qualifying OHLCV absent|
|Validation|Next 15%; pre-boundary bars are context only|NOT RUN|
|Holdout|Last 15%; opt-in, not accessed by default|NOT RUN / not consumed|
|Walk-forward|Three non-overlapping tests after expanding context, before holdout|NOT RUN|
|V1 vs V2 vs V3|Requires comparable frozen definitions and execution assumptions|NOT RUN; V2/V3 production engines not implemented|
|Feature ablation|Baseline vs feature added/removed|NOT RUN; no improvement claim|

The protocol code is tested for exact split indices, prefix lengths and default holdout exclusion. At least 286 bars are a structural minimum for the utility; this is not enough to establish statistical validity, especially for HTF features or rare setups. API's 500 recent bars are a smoke window, not a robust research dataset.

## Commands — offline/staging only
```bash
python manage.py evaluate_engine --input /research/BTCUSDT-5m.json --symbol BTCUSDT:PERP --timeframe 5m --engine native --output /research/native-preholdout.json
# Optional library is installed only in the research image/environment:
python manage.py evaluate_engine --input /research/BTCUSDT-5m.json --symbol BTCUSDT:PERP --timeframe 5m --engine backtesting --output /research/library-preholdout.json
# Only after pre-registering the fixed configuration and accepting holdout consumption:
python manage.py evaluate_engine --input /research/BTCUSDT-5m.json --symbol BTCUSDT:PERP --timeframe 5m --engine native --include-holdout --output /research/final-once.json
```
`evaluate_engine` rejects malformed/gapped/partially selected input. It hashes bars into its output. No optimizer or DB write is performed. Holdout single-use is an operational requirement, not technically enforced. `research_backtest` remains backward-compatible 70/30; use the NEW command for 70/15/15, do not confuse the two.

## Execution capabilities — do not infer parity
|Capability|Native|backtesting.py research|Live|
|---|---|---|---|
|Historical prefix decisions/HTF context|Yes|Yes adapter|Current completed feed|
|Next candle execution|Next open|Next open, broker semantics|Venue fill varies|
|Same-bar SL/TP|Conservative SL first|Library behavior; not certified identical|Tick/venue sequence|
|Fees|0.0006 each side by default|Commission configured|Unknown unless reconciled|
|Slippage|2bps each side default|Not modeled|Actual unknown|
|Spread/funding|Not replayed|Not replayed|Venue dependent|
|News|Historical unavailable|Historical unavailable|Current USD feed, unavailable status surfaced|
|Partial/trailing|Not simulated|Not simulated|Existing demo/paper pathways differ|
|Portfolio/daily limits/liquidation|Not simulated|Not simulated|Incomplete adapter-specific enforcement|
|Gap / timeout|Documented native assumptions|Known differences|Observed execution required|

Native PF is calculated from trade R values, while journal PF uses currency/reported PnL. They must not be compared as interchangeable monetary performance. Native pnl is per simulated unit, not a changing account balance return. No zero-trade run is a server error or proof of safety/profitability; inspect evaluated bars, base WAIT reasons and strategy vetoes.

## Required before promotion
Frozen data + version/config/engine hash; venue costs; historical news availability; sufficient HTF warmup; no leakage under partial/trailing execution; source-separated account simulation; train-only selection; validation-based model choice; one governed holdout; walk-forward and ablation; parameter sensitivity and multiple-comparison controls. Gate frequency and no-trade rate must accompany PF. Current utility reports no-trade rate over evaluated decision bars, not all bars while a position was open.
