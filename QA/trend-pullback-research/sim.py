"""Fast event simulator for strategy research. Conservative conventions:
- signal evaluated on bar i close; market entry at open[i+1] + slippage (taker)
- limit entry: rests from bar i+1 for `wait` bars, fills on touch (maker), gap-through fills at open (taker)
- stop & target on the same bar => stop first; on a limit-fill bar the target is ignored
- trailing stop (chandelier, k*ATR from best close) updated on bar close, effective next bar
- exit-on-signal at next open (taker); max_hold bars timeout at close (taker)
- funding: FUND per 8h held, charged regardless of side (conservative)
"""
import numpy as np
from numba import njit

TAKER, MAKER, SLIP, FUND8H = 0.0006, 0.0002, 0.0002, 0.0001


@njit(cache=True)
def simulate(o, h, l, c, atr, sig, lim_px, stop_dist, tgt_r, trail_k, be_r, max_hold, wait, exit_long, exit_short,
             bar_sec, taker, maker, slip, fund8h, pen, tp_taker):
    n = len(c)
    out = np.zeros((n // 2 + 1, 8))  # entry_i, exit_i, dir, entry, exit, R_net, pct_net, reason
    k = 0
    i = 0
    while i < n - 2:
        s = sig[i]
        if s == 0 or stop_dist[i] <= 0 or np.isnan(stop_dist[i]):
            i += 1
            continue
        d = s
        # ---- entry
        fi = -1
        fee_in = taker
        if lim_px[i] > 0:
            lp = lim_px[i]
            for j in range(i + 1, min(i + 1 + wait, n)):
                if (d > 0 and l[j] <= lp * (1 - pen)) or (d < 0 and h[j] >= lp * (1 + pen)):
                    fi = j
                    if (d > 0 and o[j] <= lp) or (d < 0 and o[j] >= lp):
                        e = o[j]
                    else:
                        e = lp
                        fee_in = maker
                    break
            if fi < 0:
                i += 1
                continue
            is_lim = True
        else:
            fi = i + 1
            e = o[fi] * (1 + slip * d)
            is_lim = False
        sd = stop_dist[i]
        stop = e - d * sd
        tgt = e + d * sd * tgt_r if tgt_r > 0 else np.nan
        best = e
        ex = np.nan
        reason = 0  # 0 timeout 1 stop 2 target 3 signal 4 trail
        xi = fi
        moved_be = False
        j = fi
        while j < n:
            # stop
            if (d > 0 and l[j] <= stop) or (d < 0 and h[j] >= stop):
                if d > 0:
                    ex = min(stop, o[j]) if j > fi else stop
                else:
                    ex = max(stop, o[j]) if j > fi else stop
                ex = ex * (1 - slip * d)
                reason = 1
                xi = j
                break
            if tgt_r > 0 and not (is_lim and j == fi):
                if (d > 0 and h[j] >= tgt) or (d < 0 and l[j] <= tgt):
                    ex = tgt * (1 - slip * d) if tp_taker else tgt
                    reason = 2
                    xi = j
                    break
            if j - fi >= max_hold:
                ex = c[j] * (1 - slip * d)
                reason = 0
                xi = j
                break
            if (d > 0 and exit_long[j]) or (d < 0 and exit_short[j]):
                if j + 1 < n:
                    ex = o[j + 1] * (1 - slip * d)
                    xi = j + 1
                else:
                    ex = c[j]
                    xi = j
                reason = 3
                break
            # update trailing / breakeven at close of j
            if d > 0:
                best = max(best, c[j])
            else:
                best = min(best, c[j])
            if be_r > 0 and not moved_be and (best - e) * d >= be_r * sd:
                stop = e + d * 0.1 * sd if d > 0 else e + d * 0.1 * sd
                moved_be = True
            if trail_k > 0 and not np.isnan(atr[j]):
                ts = best - d * trail_k * atr[j]
                if (ts - stop) * d > 0:
                    stop = ts
            j += 1
        if j >= n:
            ex = c[n - 1]
            xi = n - 1
        fee_out = maker if (reason == 2 and not tp_taker) else taker
        held_h = (xi - fi + 1) * bar_sec / 3600.0
        fund = fund8h * held_h / 8.0
        gross = (ex - e) * d / e
        pct = gross - fee_in - fee_out - fund
        out[k, 0] = fi
        out[k, 1] = xi
        out[k, 2] = d
        out[k, 3] = e
        out[k, 4] = ex
        out[k, 5] = pct * e / sd
        out[k, 6] = pct
        out[k, 7] = reason
        k += 1
        i = xi + 1
    return out[:k]


def run(df, sig, stop_dist, *, lim_px=None, tgt_r=0.0, trail_k=0.0, be_r=0.0, max_hold=10**9, wait=0,
        exit_long=None, exit_short=None, bar_sec=3600, taker=TAKER, maker=MAKER, slip=SLIP, fund=FUND8H, pen=0.0, tp_taker=False):
    n = len(df)
    z = np.zeros(n, dtype=np.bool_)
    res = simulate(df.open.values, df.high.values, df.low.values, df.close.values,
                   df.atr.values if "atr" in df else np.full(n, np.nan),
                   np.nan_to_num(np.asarray(sig, dtype=np.float64)).astype(np.int64),
                   np.zeros(n) if lim_px is None else np.nan_to_num(np.asarray(lim_px, dtype=np.float64)),
                   np.asarray(stop_dist, dtype=np.float64), float(tgt_r), float(trail_k), float(be_r), int(max_hold),
                   int(wait), z if exit_long is None else np.asarray(exit_long, dtype=np.bool_),
                   z if exit_short is None else np.asarray(exit_short, dtype=np.bool_),
                   float(bar_sec), taker, maker, slip, fund, float(pen), bool(tp_taker))
    import pandas as pd
    t = pd.DataFrame(res, columns=["fi", "xi", "dir", "entry", "exit", "R", "pct", "reason"])
    t["time"] = df.time.values[t.fi.astype(int)] if len(t) else []
    return t


def stats(t, label="", risk_pct=1.0):
    import pandas as pd
    if len(t) == 0:
        return dict(label=label, n=0)
    yr = pd.to_datetime(t.time, unit="s").dt.year
    eq = t.R.cumsum()
    dd = (eq - eq.cummax()).min()
    pos, neg = t.R[t.R > 0].sum(), -t.R[t.R <= 0].sum()
    by = t.groupby(yr).R.sum()
    return dict(label=label, n=len(t), win=round((t.R > 0).mean() * 100, 1), expR=round(t.R.mean(), 3),
                totR=round(t.R.sum(), 1), PF=round(pos / neg, 2) if neg else None, maxDD_R=round(dd, 1),
                years_pos=f"{(by > 0).sum()}/{len(by)}", by_year={int(k): round(v, 1) for k, v in by.items()},
                tpy=round(len(t) / max(1e-9, (t.time.iloc[-1] - t.time.iloc[0]) / 31557600), 1))
