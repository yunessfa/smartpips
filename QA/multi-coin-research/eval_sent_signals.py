import json, re, sys, bisect, collections
S = sys.argv[1]
TFM = {"1m":1,"5m":5,"15m":15,"1h":60}
BASE_EXP = {"1m":10,"5m":6,"15m":4,"1h":3}
COST = 0.0002+0.0006+0.0002*2  # maker in + taker out + slippage (approx, as fraction of price)
K = {}
def load(sym):
    if sym not in K:
        try: K[sym] = json.load(open(f"{S}/k1m/{sym}.json"))
        except FileNotFoundError: K[sym] = None
    return K[sym]
sigs = []
for line in open(f"{S}/signals.tsv"):
    ts, sym, tf, side, e, sl, tp, strat, uid, body = line.rstrip("\n").split("\t")
    if sym.startswith("XAU") or tf not in TFM: continue
    sigs.append(dict(ts=int(ts)*1000, sym=sym.split(":")[0], tf=tf, side=side, e=float(e), sl=float(sl), tp=float(tp),
                     strat="TrendPullback" if "Trend" in strat else "BaseEngine", limit="LIMIT" in body,
                     valid=(int(m.group(1)) if (m:=re.search(r"valid ~(\d+) min", body)) else None)))
sigs.sort(key=lambda s: s["ts"])
busy = {}  # key -> time until which a previous trade on the key is pending/open
res = collections.defaultdict(list)
for s in sigs:
    k = load(s["sym"])
    if not k: continue
    key = (s["strat"], s["sym"], s["tf"], s["side"])
    if busy.get(key, 0) > s["ts"]: continue
    times = [r[0] for r in k] if "times" not in s else None
    i = bisect.bisect_left(KT[s["sym"]], s["ts"]) if s["sym"] in (KT:=globals().setdefault("KT", {})) else None
    if i is None:
        KT[s["sym"]] = [r[0] for r in k]; i = bisect.bisect_left(KT[s["sym"]], s["ts"])
    if i >= len(k) - 1: continue
    m = TFM[s["tf"]]
    valid = s["valid"] or BASE_EXP[s["tf"]] * m
    long = s["side"] == "buy"
    risk = abs(s["e"] - s["sl"])
    if risk <= 0: continue
    # fill
    fill = None
    if s["limit"]:
        for j in range(i, min(i + valid, len(k))):
            lo, hi = k[j][3], k[j][2]
            if (long and lo <= s["e"]) or (not long and hi >= s["e"]): fill = j; break
            # target hit before fill = missed
    else:
        fill = i
    if fill is None:
        busy[key] = s["ts"] + valid * 60000; res[(s["strat"], s["tf"])].append(("nofill", 0, s)); continue
    out = None
    for j in range(fill, min(fill + 72 * m, len(k))):
        o, hi, lo, c = k[j][1], k[j][2], k[j][3], k[j][4]
        hit_sl = lo <= s["sl"] if long else hi >= s["sl"]
        hit_tp = hi >= s["tp"] if long else lo <= s["tp"]
        if j == fill and s["limit"]: hit_tp = False
        if hit_sl: out = ("loss", -1.0, j); break
        if hit_tp: out = ("win", abs(s["tp"] - s["e"]) / risk, j); break
    if out is None:
        j = min(fill + 72 * m, len(k)) - 1
        if j >= len(k) - 2 and fill + 72*m > len(k): busy[key] = 1e18; continue  # still open
        r = ((k[j][4] - s["e"]) if long else (s["e"] - k[j][4])) / risk
        out = ("time", r, j)
    cost_r = COST * s["e"] / risk
    busy[key] = k[out[2]][0]
    res[(s["strat"], s["tf"])].append((out[0], out[1] - cost_r, s))
print(f"{'strategy':14}{'tf':>4}{'signals':>8}{'filled':>7}{'win%':>6}{'avgR':>7}{'sumR':>8}{'costR':>6}")
for key in sorted(res):
    rows = res[key]; f = [r for r in rows if r[0] != "nofill"]
    if not f: continue
    w = sum(1 for r in f if r[1] > 0)
    print(f"{key[0]:14}{key[1]:>4}{len(rows):>8}{len(f):>7}{100*w/len(f):>6.1f}{sum(r[1] for r in f)/len(f):>7.3f}{sum(r[1] for r in f):>8.1f}")
# by symbol for trend pullback
print("\nTrendPullback by symbol (all tf):")
agg = collections.defaultdict(list)
for key, rows in res.items():
    if key[0] != "TrendPullback": continue
    for r in rows:
        if r[0] != "nofill": agg[r[2]["sym"]].append(r[1])
for sym, v in sorted(agg.items(), key=lambda x: -sum(x[1])):
    print(f"  {sym:10}{len(v):>5} win%={100*sum(1 for x in v if x>0)/len(v):5.1f} avgR={sum(v)/len(v):+.3f} sumR={sum(v):+.1f}")
