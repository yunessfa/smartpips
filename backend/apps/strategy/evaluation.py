"""Read-only chronological protocol for FIXED parameters, not an optimizer.

Holdout is opt-in and must be governed externally; this module does not claim to
prevent a researcher from rerunning a holdout or changing parameters afterwards.
"""
import hashlib
import json
from .backtest_runner import run_selected


def split_plan(n, minimum_train=200):
    train_end=int(n*.70); validation_end=int(n*.85)
    if train_end < minimum_train or n-validation_end < 40 or validation_end-train_end < 40:
        raise ValueError("Need at least 286 completed contiguous bars; substantially more is required for HTF/OOS evidence.")
    return {"train": [0,train_end],"validation":[train_end,validation_end],"holdout":[validation_end,n]}


def evaluate(symbol, candles, timeframe="5m", engine="native", version=None, include_holdout=False):
    plan=split_plan(len(candles)); raw_hash=hashlib.sha256(json.dumps(candles,sort_keys=True,allow_nan=False).encode()).hexdigest()
    source={"engine":engine}
    def run_interval(a,b):
        # No candle beyond b is supplied. Prior data is warmup only; no pre-a positions.
        result=run_selected(symbol,candles[:b],timeframe=timeframe,source=source,version=version,
                            warmup=max(a,200) if a == 0 else a)
        d=result.get("diagnostics") or {}; evaluated=d.get("bars_evaluated",0)
        waits=d.get("base_engine_wait",0)+d.get("strategy_veto",0)
        return {"interval":[a,b],"warmup_history_end_exclusive":a,"result":result,
                "no_trade_rate_pct":100*waits/evaluated if evaluated else None,
                "no_trade_rate_basis":"evaluated decision bars, excluding bars already in a position",
                "trade_frequency_per_1000_window_bars":1000*result.get("trades",0)/(b-a)}
    out={"protocol":"fixed-parameters-chronological-70-15-15-v1", "data_sha256":raw_hash,
         "split_indices":plan,"parameter_fitting":False,"optimization":False,"historical_news":"Historical news unavailable",
         "holdout_policy":"Opt-in; no single-use enforcement. Pre-register manifest externally before final evaluation.",
         "limitations":["No portfolio/partial/trailing/funding/news parity with live engine", "Window-boundary positions are closed by the selected simulator; no cross-fold carry"],
         "train":run_interval(*plan["train"]), "validation":run_interval(*plan["validation"]),
         "holdout":run_interval(*plan["holdout"]) if include_holdout else {"status":"not_accessed"}}
    # Expanding training context, three disjoint fixed-parameter tests before holdout.
    first=int(len(candles)*.4); last=plan["holdout"][0]; width=(last-first)//3
    out["walk_forward"]=[]
    for k in range(3):
        a=first+k*width; b=first+(k+1)*width if k<2 else last
        out["walk_forward"].append({"training_context":[0,a],"test":run_interval(a,b),"fitting":False})
    return out
