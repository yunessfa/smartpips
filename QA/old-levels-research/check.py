import numpy as np, pandas as pd, sys
sys.argv = ["explore.py", "15m"]
import explore as X
E = X.ev_table(); f = X.run_events(E, "fade", 2.0); f = X.seg(f, "TR")
pd.set_option("display.width", 250)
s = f.sample(4, random_state=3)[["time", "open", "high", "low", "close", "atr", "side", "Lin", "Lout", "src", "age", "nlev", "dir", "sd", "R"]]
s = s.round(2); s["time"] = pd.to_datetime(s.time, unit="s"); print(s.to_string())
df = X.df
# random baseline with the same stop sizes and the same costs (market in / market out)
rng = np.random.default_rng(11)
tr = X.seg(df, "TR"); idx = rng.choice(tr.index.values[:-100], 20000, replace=False)
for tgt in (2.0, 3.0):
    sd = rng.choice(f.sd.values / f.close.values, len(idx)) * df.close.values[idx]
    R = X.outcomes(X.o, X.h, X.l, X.c, idx.astype(np.int64), rng.choice(np.array([-1, 1]), len(idx)).astype(np.int64), sd,
                   np.zeros(len(idx)), tgt, 72, 12, 900.0, X.TAKER, X.MAKER, X.SLIP, X.FUND)
    print(X.line(f"RANDOM same stops tgt={tgt}", R))
print("fade median stop %:", round(float((f.sd / f.close * 100).median()), 2), " avg cost in R:", round(float((0.0016 / (f.sd / f.close)).mean()), 3))
