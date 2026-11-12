"""Does REAL futures order flow add information? Runs on the output of `manage.py backfill_flow`.

    python study.py prepare  BTCUSDT /path/to/flow-data     # build bar files from the backfill (once)
    python study.py ic       BTCUSDT 15m [reveal]           # flow features vs forward returns
    python study.py sweeps   BTCUSDT 15m [reveal]           # old-level sweeps / breakouts split by taker delta
    python study.py playbook BTCUSDT 15m [reveal]           # trend-pullback trades split by flow and funding

Same rules as ../old-levels-research: decisions on closed bars only, same costs, and the
later periods (VA, HO) are printed only with `reveal`, after the TRAIN tables have been
read and a hypothesis written down. Nothing here optimises anything.

Not covered: open interest (the exchange only keeps one month), order book and liquidations
(no history at all). Those come from `record_flow` and need a few months of recording first.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CMD, SYMBOL = sys.argv[1], sys.argv[2].upper()
os.environ.setdefault("SP_LAB", os.path.join(HERE, "data"))
os.environ["SP_PREFIX"] = SYMBOL.lower()
sys.path.insert(0, os.path.join(HERE, "..", "old-levels-research"))
from common import CFG, DATA, PREFIX, htf_merge, load, run, signals  # noqa: E402
from lv import build_levels, detect, outcomes  # noqa: E402

TAKER, MAKER, SLIP, FUND = 0.0006, 0.0002, 0.0002, 0.0001
BAR = {"5m": 300, "15m": 900, "1h": 3600}
RULES = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def prepare(root):
    files = sorted(glob.glob(os.path.join(root, SYMBOL, "hist", "kline_*", "*.csv.gz")))
    if not files:
        sys.exit(f"no backfill under {root}/{SYMBOL}/hist - run: manage.py backfill_flow --symbols {SYMBOL}")
    df = pd.concat([pd.read_csv(f) for f in files]).drop_duplicates("time").sort_values("time")
    step = int(df.time.diff().median())
    gaps = int((df.time.diff() > step).sum())
    print(f"{SYMBOL}: {len(df)} bars of {step}s, {pd.to_datetime(df.time.iloc[0], unit='s')} .. "
          f"{pd.to_datetime(df.time.iloc[-1], unit='s')}, gaps: {gaps}")
    os.makedirs(DATA, exist_ok=True)
    d = df.set_index(pd.to_datetime(df.time, unit="s"))
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "taker_buy": "sum",
           "delta": "sum"}
    for tf, rule in RULES.items():
        if BAR.get(tf, 10**9) < step:
            continue
        r = d.resample(rule, label="left", closed="left").agg(agg).dropna()
        r["time"] = ((r.index - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
        r.reset_index(drop=True).to_parquet(f"{DATA}{PREFIX}_{tf}.parquet", index=False)
        print(f"  {tf}: {len(r)} bars")
    fpath = os.path.join(root, SYMBOL, "hist", "funding.csv.gz")
    if os.path.exists(fpath):
        pd.read_csv(fpath).to_parquet(f"{DATA}{PREFIX}_funding.parquet", index=False)
        print("  funding copied")


def splits(df):
    """Fixed calendar splits when the history is long enough, otherwise 50 / 25 / 25 by time."""
    t0, t1 = df.time.iloc[0], df.time.iloc[-1]
    ts = lambda s: pd.Timestamp(s).timestamp()
    if t0 <= ts("2021-01-01"):
        return {"TR": (t0, ts("2023-01-01")), "VA": (ts("2023-01-01"), ts("2025-01-01")), "HO": (ts("2025-01-01"), t1 + 1)}
    a, b = t0 + (t1 - t0) * 0.5, t0 + (t1 - t0) * 0.75
    return {"TR": (t0, a), "VA": (a, b), "HO": (b, t1 + 1)}


def flow_features(df):
    v = df.volume.replace(0, np.nan)
    df["d1"] = df.delta / v                                            # share of the bar's volume, -1 .. 1
    for n in (6, 24):
        df[f"d{n}"] = df.delta.rolling(n).sum() / df.volume.rolling(n).sum().replace(0, np.nan)
    df["agree24"] = np.sign(df.close.pct_change(24)) * df.d24          # < 0 = price and delta disagree
    df["vol_z"] = df.volume / df.volume.rolling(96).mean()
    return df


def line(lbl, R):
    R = np.asarray(R, dtype=float)
    R = R[~np.isnan(R)]
    if len(R) < 30:
        return f"{lbl:44s} n={len(R):5d}  (too few)"
    se = R.std(ddof=1) / np.sqrt(len(R))
    pos, neg = R[R > 0].sum(), -R[R <= 0].sum()
    return (f"{lbl:44s} n={len(R):5d} win={100 * (R > 0).mean():5.1f}% expR={R.mean():+.3f} "
            f"t={R.mean() / se:+.1f} PF={pos / neg if neg else float('nan'):.2f}")


def parts(df, reveal):
    sp = splits(df)
    return [(k, sp[k]) for k in (("TR", "VA", "HO") if reveal else ("TR",))]


def cmd_ic(tf, reveal):
    df = flow_features(load(tf))
    for k in (3, 12, 48):
        df[f"fwd{k}"] = df.close.shift(-k) / df.close - 1
    for name, (a, b) in parts(df, reveal):
        x = df[(df.time >= a) & (df.time < b)]
        print(f"\n=== {SYMBOL} {tf} [{name}] {len(x)} bars - Spearman IC and top-minus-bottom quintile (bps); "
              "round-trip cost ~10-16 bps")
        for f in ("d1", "d6", "d24", "agree24", "vol_z"):
            row = f"{f:8s}"
            for k in (3, 12, 48):
                y = x[[f, f"fwd{k}"]].dropna()
                ic = y[f].rank().corr(y[f"fwd{k}"].rank())
                q = pd.qcut(y[f], 5, labels=False, duplicates="drop")
                spread = (y[f"fwd{k}"][q == q.max()].mean() - y[f"fwd{k}"][q == 0].mean()) * 1e4
                row += f"  +{k:<2d}bars IC={ic:+.3f} Q5-Q1={spread:+6.1f}"
            print(row)


def events(tf):
    df = flow_features(load(tf))
    df = htf_merge(df, load("4h"), ["e50", "e200", "close"], "h4_")
    lv = build_levels()
    r = detect(df.time.values, df.high.values, df.low.values, df.close.values, lv.avail.values.astype(np.int64),
               lv.price.values, lv.is_high.values.astype(np.int64), lv.src.values.astype(np.int64))
    for k, v in zip("hn hmax hmin hsrc hage ln lmax lmin lsrc lage up_room dn_room".split(), r):
        df[k] = v
    e = df[((df.hn > 0) & (df.ln == 0)) | ((df.ln > 0) & (df.hn == 0))].copy()
    e["side"] = np.where(e.hn > 0, 1, -1)
    e["Lout"] = np.where(e.side > 0, e.hmax, e.lmin)
    e["Lin"] = np.where(e.side > 0, e.hmin, e.lmax)
    e["reclaim"] = np.where(e.side > 0, e.close < e.Lin, e.close > e.Lin)
    e["breakout"] = np.where(e.side > 0, e.close > e.Lout + 0.25 * e.atr, e.close < e.Lout - 0.25 * e.atr)
    e["ext"] = np.where(e.side > 0, e.high, e.low)
    e["push"] = e.d1 * e.side          # > 0: takers were aggressive IN the direction of the sweep
    return df, e


def cmd_sweeps(tf, reveal):
    df, e = events(tf)
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    for kind, tgt in (("fade", 2.0), ("follow", 2.5)):
        x = e[e.reclaim] if kind == "fade" else e[e.breakout]
        d = -x.side.values if kind == "fade" else x.side.values
        sd = (np.abs(x.ext.values - x.close.values) + 0.1 * x.atr.values) if kind == "fade" else 1.5 * x.atr.values
        ok = (sd / x.close.values * 100 >= 0.40) & (sd <= 3.0 * x.atr.values)
        x, d, sd = x[ok], d[ok], sd[ok]
        R = outcomes(o, h, l, c, x.index.values.astype(np.int64), d.astype(np.int64), sd, np.zeros(len(x)), tgt, 72,
                     12, float(BAR[tf]), TAKER, MAKER, SLIP, FUND)
        x = x.assign(R=R)
        for name, (a, b) in parts(df, reveal):
            y = x[(x.time >= a) & (x.time < b)]
            print(f"\n--- {SYMBOL} {tf} {kind} {tgt}R [{name}]   push = taker delta share in the sweep direction")
            print(line("ALL", y.R))
            print(line("push > +10% (takers drove the sweep)", y.R[y.push > 0.10]))
            print(line("push -10%..+10%", y.R[(y.push >= -0.10) & (y.push <= 0.10)]))
            print(line("push < -10% (takers faded the sweep)", y.R[y.push < -0.10]))
            print(line("high volume (vol_z > 2)", y.R[y.vol_z > 2]))
            print(line("high volume & push > +10%", y.R[(y.vol_z > 2) & (y.push > 0.10)]))
            print(line("high volume & push < -10%", y.R[(y.vol_z > 2) & (y.push < -0.10)]))


def cmd_playbook(tf, reveal):
    df, sig, sd = signals(tf)
    df = flow_features(df)
    t = run(df, sig, sd, lim_px=df.e21.values, wait=12, tgt_r=CFG[tf]["tp"], max_hold=72, bar_sec=BAR[tf], tp_taker=True)
    k = t.fi.values.astype(int) - 1                    # last bar fully known before the fill
    for f in ("d6", "d24", "vol_z"):
        t[f] = df[f].values[k]
    t["with24"] = t.d24 * t.dir
    t["with6"] = t.d6 * t.dir
    fpath = f"{DATA}{PREFIX}_funding.parquet"
    if os.path.exists(fpath):
        fund = pd.read_parquet(fpath).sort_values("time")
        m = pd.merge_asof(pd.DataFrame({"time": df.time.values[k]}), fund[["time", "rate"]], on="time")
        t["pay"] = m.rate.values * t.dir.values        # > 0: this side pays funding
    for name, (a, b) in parts(df, reveal):
        y = t[(t.time >= a) & (t.time < b)]
        print(f"\n=== {SYMBOL} {tf} trend-pullback [{name}] target={CFG[tf]['tp']}R")
        print(line("ALL", y.R))
        print(line("24-bar delta WITH the trade (> +3%)", y.R[y.with24 > 0.03]))
        print(line("24-bar delta neutral", y.R[(y.with24 >= -0.03) & (y.with24 <= 0.03)]))
        print(line("24-bar delta AGAINST the trade (< -3%)", y.R[y.with24 < -0.03]))
        print(line("pullback sold into: 6-bar delta against", y.R[y.with6 < -0.05]))
        print(line("pullback on light delta: |6-bar| <= 5%", y.R[y.with6.abs() <= 0.05]))
        if "pay" in y:
            print(line("this side PAYS funding", y.R[y.pay > 0]))
            print(line("this side RECEIVES funding", y.R[y.pay <= 0]))


if __name__ == "__main__":
    if CMD == "prepare":
        prepare(sys.argv[3])
    else:
        tf = sys.argv[3]
        reveal = len(sys.argv) > 4 and sys.argv[4] == "reveal"
        {"ic": cmd_ic, "sweeps": cmd_sweeps, "playbook": cmd_playbook}[CMD](tf, reveal)
