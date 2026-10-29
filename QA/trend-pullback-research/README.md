# Trend-pullback research (2026-10)

Reproduces the evidence embedded in `backend/apps/strategy/trend_pullback.py` (`RESEARCH`).

Data: Bitstamp BTC/USD 1-minute archive (github.com/ff137/bitstamp-btcusd-minute-data),
2019-01-01 .. 2026-10-27, resampled with `build_data.py` (closed bars only; HTF values
are attached only after the HTF bar has closed — no look-ahead).

Costs: limit entry maker 0.02%; stop and target exit as market (taker 0.06% + 0.02% slippage);
funding 0.01% per 8 h held; stop assumed first when stop and target share a bar; a limit
fill bar never also books the target.

Protocol: parameters fixed on 2019-2022 (TR), checked untouched on 2023-2024 (VA) and
2025-2026 (HO). `exp_b.py 1h grid` = 108-point neighbourhood (107 positive in TR, VA and HO).

| file | what |
|---|---|
| `sim.py` | numba event simulator |
| `exp_a.py` | random baseline, Donchian breakout, pullback, RSI-2 mean reversion |
| `exp_b.py` | pullback robustness: grid, stress, 15m/5m, min-stop filter, target grid |
| `final.py`, `final2.py` | final rule set on 5m/15m/1h, stress tests, Monte Carlo drawdown |
| `run_product_bt.py` | runs the PRODUCT backtester (`apps.strategy.backtest`) on the same data — parity check |
| `*.jsonl` | raw outputs |

Product parity (same data, `run_product_bt.py`): 1h VA +0.138R / HO +0.265R, 15m VA +0.118R / HO +0.148R,
5m VA +0.097R / HO +0.334R — identical to `final2.py` ("TP as market").
