"""Do old levels add information to the VALIDATED trend-pullback trades? TRAIN only unless 'reveal'."""
import sys, numpy as np, pandas as pd
from common import signals, CFG, run
from lv import build_levels, detect, nearest_hist
REVEAL = len(sys.argv) > 2 and sys.argv[2] == "reveal"
tf = sys.argv[1]; BAR = {"5m": 300, "15m": 900, "1h": 3600}[tf]
SPL = {"TR": ("2019-01-01", "2023-01-01"), "VA": ("2023-01-01", "2025-01-01"), "HO": ("2025-01-01", "2027-01-01")}
df, sig, sd = signals(tf)
t = run(df, sig, sd, lim_px=df.e21.values, wait=12, tgt_r=CFG[tf]["tp"], max_hold=72, bar_sec=BAR, tp_taker=True)
lv = build_levels()
A = (lv.avail.values.astype(np.int64), lv.price.values, lv.is_high.values.astype(np.int64), lv.src.values.astype(np.int64))
r = detect(df.time.values, df.high.values, df.low.values, df.close.values, *A)
names = "hn hmax hmin hsrc hage ln lmax lmin lsrc lage up_room dn_room".split()
F = dict(zip(names, r))
# major-only (W/M + daily pivots) version of the room
maj = lv[(lv.src & (2 | 4 | 16)) > 0]
rm = detect(df.time.values, df.high.values, df.low.values, df.close.values, maj.avail.values.astype(np.int64),
            maj.price.values, maj.is_high.values.astype(np.int64), maj.src.values.astype(np.int64))
Fm = dict(zip(names, rm))
k = t.fi.values.astype(int) - 1                      # last bar fully known before the fill
d = t.dir.values; e = t.entry.values; s = sd.values[k]
t["room"] = np.where(d > 0, F["up_room"][k] - e, e - F["dn_room"][k]) / s       # R to the nearest untaken level AHEAD
t["room_maj"] = np.where(d > 0, Fm["up_room"][k] - e, e - Fm["dn_room"][k]) / s
t["conf"] = nearest_hist(df.time.values[k], e, A[0], A[1], 90.0) / df.atr.values[k]   # ATRs from entry to nearest known level
# was opposite-side liquidity swept in the last N bars? (long: an old LOW taken recently)
N = 48
ln_roll = pd.Series(F["ln"]).rolling(N).sum().values; hn_roll = pd.Series(F["hn"]).rolling(N).sum().values
t["swept_opp"] = np.where(d > 0, ln_roll[k], hn_roll[k]) > 0
t["swept_same"] = np.where(d > 0, hn_roll[k], ln_roll[k]) > 0

def line(lbl, R):
    if len(R) < 30: return f"{lbl:36s} n={len(R):5d} (too few)"
    se = R.std(ddof=1) / np.sqrt(len(R)); pos, neg = R[R > 0].sum(), -R[R <= 0].sum()
    return f"{lbl:36s} n={len(R):5d} win={100*(R>0).mean():5.1f}% expR={R.mean():+.3f} t={R.mean()/se:+.1f} PF={pos/neg:.2f}"

for part in (["TR", "VA", "HO"] if REVEAL else ["TR"]):
    a, b = (pd.Timestamp(x).timestamp() for x in SPL[part]); x = t[(t.time >= a) & (t.time < b)]
    tg = CFG[tf]["tp"]
    print(f"\n=== {tf} trend-pullback [{part}] target={tg}R")
    print(line("ALL", x.R.values))
    print(line("room: none ahead (new extreme)", x.R[x.room.isna()].values))
    print(line("room < 1R", x.R[x.room < 1].values))
    print(line(f"room 1R..{tg}R (level before TP)", x.R[(x.room >= 1) & (x.room < tg)].values))
    print(line(f"room >= {tg}R (clear path)", x.R[x.room >= tg].values))
    print(line("MAJOR room: none ahead", x.R[x.room_maj.isna()].values))
    print(line(f"MAJOR room < {tg}R", x.R[x.room_maj < tg].values))
    print(line(f"MAJOR room >= {tg}R", x.R[x.room_maj >= tg].values))
    print(line("entry within 0.3 ATR of a level", x.R[x.conf <= 0.3].values))
    print(line("entry 0.3-1 ATR from a level", x.R[(x.conf > 0.3) & (x.conf <= 1)].values))
    print(line("entry > 1 ATR from any level", x.R[x.conf > 1].values))
    print(line("opposite liquidity swept (48 bars)", x.R[x.swept_opp].values))
    print(line("no opposite sweep", x.R[~x.swept_opp].values))
    print(line("same-side level broken (48 bars)", x.R[x.swept_same].values))
    print(line("no same-side break", x.R[~x.swept_same].values))
