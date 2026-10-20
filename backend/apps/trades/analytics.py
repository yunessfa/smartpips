"""Deterministic journal analytics, not exchange accounting or model validation.

No pandas/DB dependency; the same function serves offline evidence and user API.
Unknowns are not zeros. Segments always retain an unknown bucket.
"""
import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median, pstdev


def number(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def stamp(v):
    try:
        d = v if isinstance(v, datetime) else datetime.fromisoformat(v.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (AttributeError, ValueError, TypeError):
        return None


def wilson(wins, n):
    if not n:
        return None
    z = 1.95996398454; p = wins/n; den = 1+z*z/n
    mid = (p+z*z/(2*n))/den
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [100*(mid-half), 100*(mid+half)]


def distribution(values):
    xs = [x for x in values if x is not None]
    return {"sample": len(xs), "min": min(xs) if xs else None, "max": max(xs) if xs else None,
            "mean": mean(xs) if xs else None, "median": median(xs) if xs else None}


def summarize(rows):
    rows = sorted(rows, key=lambda r: (stamp(r.get("closed_at")) or datetime.min.replace(tzinfo=timezone.utc), str(r.get("id", ""))))
    pnl = [number(r.get("pnl")) for r in rows]
    p = [x for x in pnl if x is not None]; n = len(p)
    w = [v for v in p if v>0]; l = [v for v in p if v<0]
    curve=peak=drawdown=0.; sw=sl=mw=ml=0; equity=[]
    for row, v in zip(rows, pnl):
        if v is None: continue
        curve += v; peak=max(peak,curve); dd=peak-curve; drawdown=max(drawdown,dd)
        sw=sw+1 if v>0 else 0; sl=sl+1 if v<0 else 0; mw=max(mw,sw); ml=max(ml,sl)
        equity.append({"id":row.get("id"),"closed_at":str(row.get("closed_at") or ""), "cumulative_reported_pnl":curve,"drawdown_reported_pnl":dd})
    durations=[]; rs=[]; planned=[]; stops=[]; tps=[]; risks=[]; exits=[]
    for r in rows:
        a,b=stamp(r.get("opened_at")),stamp(r.get("closed_at"))
        if a and b and b>=a: durations.append((b-a).total_seconds()/60)
        snap=r.get("entry_snapshot") or {}; c=snap.get("context") or {}
        risk=number(snap.get("initial_risk_quote")); v=number(r.get("pnl"))
        if risk and risk>0 and v is not None: rs.append(v/risk)
        e,s,t=number(c.get("entry")),number(c.get("stop_loss")),number(c.get("take_profit"))
        if e and s and e!=s:
            stops.append(abs(e-s)/e*100)
            if t: planned.append(abs(t-e)/abs(e-s)); tps.append(abs(t-e)/e*100)
        rp=number(c.get("risk_per_trade_pct"))
        if rp is not None: risks.append(rp)
        reason=r.get("exit_reason") or ""
        # A note proxy remains separately identified, never promoted to verified labels.
        exits.append(reason)
    avgw=mean(w) if w else None; avgl=mean(l) if l else None
    downside=[min(v,0)**2 for v in rs]
    vol=pstdev(rs) if len(rs)>1 else 0
    ds=math.sqrt(mean(downside)) if downside else 0
    verified_net = [number(r.get("net_pnl")) for r in rows if r.get("costs_verified") and r.get("execution_verified")]
    full_net = bool(rows) and len(verified_net)==len(rows) and all(v is not None for v in verified_net)
    return {"trades":len(rows), "pnl_sample":n,"wins":len(w),"losses":len(l),"zeros":sum(v==0 for v in p),
        "win_rate":len(w)/n*100 if n else None,"loss_rate":len(l)/n*100 if n else None,
        "win_rate_wilson_95":wilson(len(w),n), "statistical_note":"Descriptive interval; IID assumption, not conditional/OOS probability",
        "total_reported_pnl":math.fsum(p),"verified_net_pnl":math.fsum(verified_net) if full_net else None,
        "profit_factor":math.fsum(w)/-math.fsum(l) if l else None,
        "profit_factor_status":"finite" if l else "no_losses" if w else "no_outcomes",
        "expectancy_pnl":mean(p) if p else None,"average_winner":avgw,"average_loser":avgl,
        "payoff_ratio":avgw/-avgl if avgw is not None and avgl is not None else None,
        "max_drawdown_reported_pnl":drawdown if p else None,"max_drawdown_equity_pct":None,
        "max_consecutive_wins":mw,"max_consecutive_losses":ml,
        "recovery_factor":math.fsum(p)/drawdown if drawdown else None,
        "realized_R":distribution(rs),"total_R":math.fsum(rs) if rs else None,
        "R_basis":"gross journal PnL / immutable planned initial stop risk, costs excluded",
        "planned_R":distribution(planned),"average_R":mean(rs) if rs else None,"median_R":median(rs) if rs else None,
        "sharpe_like_trade_R":mean(rs)/vol if len(rs)>=30 and vol else None,
        "sortino_like_trade_R":mean(rs)/ds if len(rs)>=30 and ds else None,
        "risk_adjusted_note":"Non-annualized trade-R descriptive ratios; not account return Sharpe/Sortino",
        "holding_minutes":distribution(durations),"leverage":distribution([number(r.get("leverage")) for r in rows]),
        "risk_per_trade_pct":distribution(risks),"initial_stop_distance_pct":distribution(stops),"initial_tp_distance_pct":distribution(tps),
        "exit_reason_sample":sum(bool(e) for e in exits),
        "manual_exit_rate":sum(e=="manual" for e in exits)/len(rows)*100 if rows and all(exits) else None,
        "stop_loss_rate":sum(e=="sl" for e in exits)/len(rows)*100 if rows and all(exits) else None,
        "liquidation_rate":sum(e in ("liq","liquidation") for e in exits)/len(rows)*100 if rows and all(exits) else None,
        "manual_note_proxy_count":sum(r.get("notes")=="closed manually" for r in rows),
        "liquidation_note_proxy_count":sum(r.get("notes")=="closed by liq" for r in rows),
        "actual_slippage":None,"fees":distribution([number(r.get("fees_paid")) for r in rows]),
        "funding":distribution([number(r.get("funding_paid")) for r in rows]),
        "equity_curve_basis":"closed reported journal PnL, zero starting cumulative PnL; not balance/equity NAV",
        "equity_curve":equity}


def analyze(rows):
    rows=[dict(r) for r in rows if r.get("status")=="closed"]
    dims=("symbol","direction","timeframe","strategy_name","strategy_version","setup_class","confidence_bucket",
          "leverage_bucket","market_regime","session","exit_reason","source","mode","day_utc","hour_utc","week_utc","month_utc")
    groups={k:defaultdict(list) for k in dims}
    for r in rows:
        c=(r.get("entry_snapshot") or {}).get("context") or {}
        close=stamp(r.get("closed_at")); lev=number(r.get("leverage")); score=number(c.get("score"))
        values={k:r.get(k) for k in dims}
        regime=c.get("market_regime"); sess=c.get("session")
        values.update(market_regime=regime.get("regime") if isinstance(regime,dict) else regime,
            session=sess.get("name") if isinstance(sess,dict) else sess,
            confidence_bucket=("0–49" if score<50 else "50–69" if score<70 else "70–84" if score<85 else "85–100") if score is not None else None,
            leverage_bucket=("1–10" if lev<=10 else "11–25" if lev<=25 else "26–50" if lev<=50 else "51–75" if lev<=75 else ">75") if lev is not None else None,
            mode={"bitunix_demo":"demo","bitunix_real":"real"}.get(r.get("source"),"journal_unverified"),
            day_utc=close.strftime("%A") if close else None,hour_utc=close.strftime("%H") if close else None,
            week_utc=close.strftime("%G-W%V") if close else None,month_utc=close.strftime("%Y-%m") if close else None)
        for key in dims:groups[key][str(values[key]) if values.get(key) not in (None,"") else "unknown"].append(r)
    segments={}
    for dim,buckets in groups.items():
        segments[dim]=[]
        for key,group in sorted(buckets.items()):
            item=summarize(group);item.pop("equity_curve",None)
            segments[dim].append({"key":key,**item})
    return {"schema_version":1,"closed_only":True,"timezone":"UTC","overall":summarize(rows),"segments":segments,
        "coverage":{key:sum(r.get(key) not in (None,"") for r in rows) for key in ("strategy_name","strategy_version","timeframe","confidence","exit_reason")},
        "warning":"Journal observations are not causal strategy validation. Unknown attribution/costs are not imputed."}
