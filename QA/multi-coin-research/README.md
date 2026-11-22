# Multi-coin playbook and spike research (2026-11)

Data: Binance USD-M 5m klines, 12 coins, 2021-01 .. 2026-10 (`fetch.sh`, `build.py`). SUI starts 2023-05.
Costs and fills: same simulator and assumptions as `../trend-pullback-research`.
Periods: 2021-2023 (TR), 2024 (VA), 2025-2026 (HO).

| script | question | result |
|---|---|---|
| `eval_sent_signals.py` | Did signals really sent 2026-10-22 .. 11-22 hit TP or SL? | Base engine lost (1m -0.36R, 5m -0.26R). Playbook sample is 5 days, too short to judge. |
| `tp_alts.py` | Does the unchanged playbook work beyond BTC? | Positive in TR, VA and HO on all coins combined, on 5m, 15m and 1h. |
| `spike.py`, `extras.py fade` | Do volume/range spikes give an entry? | No robust variant after costs (fade, wick rejection, momentum, retest). |
| `extras.py exits`, `be_check.py` | Can win rate rise without losing expectancy? | 1h breakeven at +1R: win rate 35% to 49%, same expectancy, max drawdown -65R to -49R. About half of those wins are under 0.3R. |
| `extras.py filters` | Do Fear & Greed or DVOL improve the playbook? | No consistent improvement across periods. |

Limits: the coins are survivors; trades on different coins are correlated, so trade counts overstate certainty;
the exit and filter comparisons were read on all three periods, so HO is not a clean holdout for those choices.
