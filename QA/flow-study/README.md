# Flow study (2026-11) — ready to run, NOT yet run on real data

Question: does real futures order flow (taker buy / sell volume, funding) separate good trades from
bad ones — at old-level sweeps, and on the trend-pullback playbook?

The 2026-10 indicator study and the 2026-11 old-level study both ended at the same wall: OHLC data
cannot tell whether a sweep was absorbed or accepted. This folder is the next step. It needs data
from the server (the development sandbox cannot reach the exchange), so no result is claimed here.

## Run it (on the server)

```bash
# 1. history that exists: 5m bars with taker volume + funding (a few minutes per symbol)
docker compose -f docker-compose.flow.yml run --rm flow-recorder \
    python manage.py backfill_flow --symbols BTCUSDT --days 2500 --interval 5m
# 2. the study (needs: pip install numba pandas pyarrow)
python QA/flow-study/study.py prepare  BTCUSDT ./flow-data
python QA/flow-study/study.py ic       BTCUSDT 15m
python QA/flow-study/study.py sweeps   BTCUSDT 15m
python QA/flow-study/study.py playbook BTCUSDT 15m
```

Read the TRAIN tables first, write down which split you expect to hold, then add `reveal` once to
see validation and holdout. A bucket that is only good in TRAIN is not a finding.

## How big is noise?

The script was smoke-tested on real BTC prices with **random** taker volume, where every true effect
is zero. In that null run the information coefficients stayed within ±0.02, and playbook buckets of
100-300 trades still differed from each other by up to ±0.15R per trade (e.g. +0.24R vs 0.00R in
TRAIN, gone in the other periods). Treat anything of that size on real data as noise unless it
repeats in TRAIN, validation and holdout.

## What it tests

| command | question |
|---|---|
| `ic` | do delta share (1 / 6 / 24 bars), price-delta agreement and relative volume predict forward returns? |
| `sweeps` | sweep & reclaim and breakout entries at old levels, split by whether takers drove or faded the sweep bar |
| `playbook` | trend-pullback trades split by delta with / against the trade before the fill, and by who pays funding |

Costs, fills and the no-look-ahead rules are the ones in `../old-levels-research`.

## Not covered yet

Open interest (one month of history only), order book and liquidations (no history). `record_flow`
stores them from the day it starts; they need a few months before any split has enough trades.
