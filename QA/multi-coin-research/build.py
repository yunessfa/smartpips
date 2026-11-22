import glob, sys, zipfile, io, numpy as np, pandas as pd
src, dst = sys.argv[1], sys.argv[2]
syms = sorted({p.split("/")[-1].split("-")[0] for p in glob.glob(f"{src}/*.zip")})
for s in syms:
    parts = []
    for p in sorted(glob.glob(f"{src}/{s}-5m-*.zip")):
        with zipfile.ZipFile(p) as z:
            raw = z.read(z.namelist()[0]).decode()
        lines = [l for l in raw.splitlines() if l and l[0].isdigit()]
        a = np.array([l.split(",")[:11] for l in lines], dtype=float)
        parts.append(a)
    a = np.concatenate(parts)
    df = pd.DataFrame({"time": (a[:, 0] // 1000).astype(np.int64), "open": a[:, 1], "high": a[:, 2], "low": a[:, 3],
                       "close": a[:, 4], "volume": a[:, 5], "tbv": a[:, 9]}).drop_duplicates("time").sort_values("time")
    df.to_pickle(f"{dst}/{s}_5m.pkl")
    print(s, len(df), pd.to_datetime(df.time.iloc[0], unit="s").date(), pd.to_datetime(df.time.iloc[-1], unit="s").date(), flush=True)
