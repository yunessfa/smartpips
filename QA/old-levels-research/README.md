# Old-level price-action research (2026-11)

Question: do **old levels** (previous day / week / month highs and lows, confirmed 4h and daily swing
pivots) give a tradeable entry on BTC, after costs — on their own, or as a filter on the validated
trend-pullback playbook?

Data: same Bitstamp BTC/USD 1-minute archive as `../trend-pullback-research` (spot proxy for the
perp), 2018-01 .. 2026-11-12; 2018 is warm-up only so that 2019 already has old levels.
Costs: taker 0.06%, maker 0.02%, slippage 0.02% per side, funding 0.01% / 8h; stop first when stop
and target share a bar; targets are paid as market exits.
Protocol: every choice was made on 2019-2022 (TR). 2023-2024 (VA) and 2025-2026 (HO) were opened
once, afterwards, to see whether the TR picture holds. Nothing was optimised.

No look-ahead: a level exists only after the day / week / month / pivot window that formed it has
closed, and a bar can only interact with levels that existed at its open (`lv.detect`). A level
stays active until some later bar trades through it. 12,482 levels; ~5,000 sweep bars per timeframe.

## Setups tested (`explore.py`)

* **fade** — bar trades through an old level and closes back inside (sweep & reclaim); market entry
  next open against the sweep, stop behind the wick + 0.1 ATR, fixed 2R / 3R target.
* **retest** — bar closes beyond the level by > 0.25 ATR; LIMIT back at the level (12 bars),
  stop 1.5 ATR, 2.5R.
* **follow** — same breakout, market entry next open, stop 1.5 ATR, 2.5R.

Stops under 0.4% of price are skipped (fees vs risk, same rule as the playbook); max hold 72 bars.

Expectancy in R per trade, net of costs (n in brackets):

| setup | TF | TR 2019-22 | VA 2023-24 | HO 2025-26 |
|---|---|---|---|---|
| fade 2R | 1h | -0.238 (867) | -0.132 (406) | -0.260 (303) |
| fade 2R | 15m | -0.371 (674) | -0.188 (265) | -0.345 (179) |
| fade 2R | 5m | -0.291 (469) | -0.170 (128) | -0.155 (91) |
| retest 2.5R | 1h | -0.163 (428) | -0.105 (181) | -0.199 (224) |
| retest 2.5R | 15m | -0.278 (466) | -0.473 (186) | -0.316 (176) |
| retest 2.5R | 5m | -0.165 (425) | +0.072 (91) | -0.363 (76) |
| follow 2.5R | 1h | -0.028 (583) | -0.146 (263) | -0.214 (299) |
| follow 2.5R | 15m | -0.115 (693) | -0.100 (279) | -0.297 (240) |
| follow 2.5R | 5m | -0.114 (637) | -0.042 (128) | -0.359 (104) |

Reference: **random** entries with the same stop sizes and costs lose -0.23R (15m, TR,
`results_baseline.txt`): with a median stop of 0.77% a market-in / market-out round trip costs
~0.22R. So fades are at or below random, breakouts are at or slightly above random, and none of them
covers costs. Splitting by level source (D / W / M / pivots), level age (<2d .. >90d), number of
levels swept, or 4h-trend alignment does not produce a bucket that is reliably positive in TR: a few
small ones are above zero, the best at t = +1.1 (`results_setups.txt`). TR win rates sit at 24-34%,
i.e. what a fixed 2-3R target gives by chance.

## Old levels as context for the trend-pullback playbook (`tp_levels.py`)

Baseline reproduced: 1h +0.352 / +0.138 / +0.266R, 15m +0.163 / +0.118 / +0.153R,
5m +0.178 / +0.097 / +0.281R (TR / VA / HO), win rate 35-44%.

| split of the playbook trades | result |
|---|---|
| untaken level between entry and target vs clear path | no stable effect — sign flips between TR, VA and HO on 1h and 15m |
| entry within 0.3 ATR of a known level vs far from any level | no stable effect — "far from levels" is best in TR, not in VA |
| opposite-side liquidity swept in the previous 48 bars | no benefit (worse on 1h TR) |

## Conclusion

1. On OHLC data, classic level setups (sweep & reclaim, break & retest, breakout) are **not an edge**
   on BTC 5m / 15m / 1h. Do not wire them into the engine as entry signals.
2. Old levels do not improve or damage the trend-pullback entries in a repeatable way. They are fine
   as chart context and as reference prices, not as a filter.
3. The trend-pullback playbook already runs at 35-44% wins with 2.5-3R targets. What separates it
   from the losing setups is the limit (maker) entry and the minimum-stop rule, not the indicator.
4. Not testable with this data: whether a sweep is absorbed or accepted (real taker buy / sell
   volume, open interest, liquidations, order book). That needs futures data that is only partly
   available historically (taker volume, OI, funding) and must otherwise be recorded going forward
   (order book, liquidations).

Limits: BTC only, spot proxy, t-statistics assume independent trades, limit fills on touch.

## Reproduce

```bash
git clone --depth 1 https://github.com/ff137/bitstamp-btcusd-minute-data /tmp/bs
pip install numba pandas pyarrow
python build_data.py /tmp/bs                 # writes ./data (override with SP_LAB)
python explore.py 15m            # TRAIN only
python explore.py 15m reveal     # + validation and holdout
python tp_levels.py 15m reveal
python check.py                  # sample events + random baseline
```
