"""
Smart trade journal — find the PATTERNS in a user's closed trades so they learn
what actually works for them, not just see a list. Works on existing trade data
(no schema changes): session is derived from the open time, direction and symbol
from the trade itself.

This is the high-value layer the review asked for: "biggest loss = counter-trend",
"best session = London", etc.
"""
from statistics import mean

from apps.market.sessions import current_session


def _bucket_stats(trades):
    wins = [t for t in trades if (t.pnl or 0) > 0]
    n = len(trades)
    return {
        "trades": n,
        "wins": len(wins),
        "win_rate": round(len(wins) / n * 100, 1) if n else 0.0,
        "total_pnl": round(sum(t.pnl or 0 for t in trades), 2),
    }


def analyze_journal(user, min_trades=5):
    """Return pattern breakdowns over the user's CLOSED trades."""
    closed = list(user.trades.filter(status="closed").exclude(pnl=None))
    if len(closed) < min_trades:
        return {"enough": False, "trades": len(closed), "min_trades": min_trades}

    # by session (derived from open time, UTC)
    by_session = {}
    for t in closed:
        sess = current_session(t.opened_at)["name"]
        by_session.setdefault(sess, []).append(t)
    sessions = {k: _bucket_stats(v) for k, v in by_session.items()}

    # by direction
    by_dir = {"long": [], "short": []}
    for t in closed:
        by_dir.setdefault(t.direction, []).append(t)
    directions = {k: _bucket_stats(v) for k, v in by_dir.items() if v}

    # by symbol
    by_sym = {}
    for t in closed:
        by_sym.setdefault(t.symbol, []).append(t)
    symbols = {k: _bucket_stats(v) for k, v in by_sym.items()}

    # by source (assistant vs manual)
    by_src = {}
    for t in closed:
        by_src.setdefault(t.source or "manual", []).append(t)
    sources = {k: _bucket_stats(v) for k, v in by_src.items()}

    # headline best/worst session by win rate (needs a few trades each)
    rated = {k: v for k, v in sessions.items() if v["trades"] >= 3}
    best_session = max(rated, key=lambda k: rated[k]["win_rate"], default=None)
    worst_session = min(rated, key=lambda k: rated[k]["win_rate"], default=None)

    overall = _bucket_stats(closed)
    wins = [t.pnl for t in closed if (t.pnl or 0) > 0]
    losses = [t.pnl for t in closed if (t.pnl or 0) <= 0]
    overall["profit_factor"] = (round(sum(wins) / abs(sum(losses)), 2)
                                if losses and sum(losses) else None)
    overall["avg_win"] = round(mean(wins), 2) if wins else 0
    overall["avg_loss"] = round(mean(losses), 2) if losses else 0

    return {
        "enough": True,
        "overall": overall,
        "by_session": sessions,
        "by_direction": directions,
        "by_symbol": symbols,
        "by_source": sources,
        "best_session": best_session,
        "worst_session": worst_session,
    }


def grade_trade(trade):
    """A simple 1-10 grade + reason for one closed trade, from its R multiple."""
    if trade.status != "closed" or trade.pnl is None:
        return None
    risk = None
    if trade.stop_loss and trade.entry_price:
        risk = abs(trade.entry_price - trade.stop_loss)
    r_mult = None
    if risk and risk > 0 and trade.exit_price is not None:
        move = ((trade.exit_price - trade.entry_price) if trade.direction == "long"
                else (trade.entry_price - trade.exit_price))
        r_mult = round(move / risk, 2)

    won = (trade.pnl or 0) > 0
    sess = current_session(trade.opened_at)["name"]
    reasons = []
    if r_mult is not None:
        reasons.append(f"result {r_mult}R")
    reasons.append(f"{sess} session")
    if won:
        grade = 8 if (r_mult or 0) >= 1.5 else 6
    else:
        grade = 3 if (r_mult or 0) <= -1 else 4
    return {"grade": grade, "won": won, "r_multiple": r_mult, "reasons": reasons}


def calibrated_confidence(user, grade, raw_confidence, min_trades=10):
    """Blend the engine's grade with the user's REAL historical win-rate.

    A confidence number only means something if it reflects what actually happened.
    If the user has enough closed trades, we anchor the displayed confidence to
    their realised win-rate (optionally nudged by the setup grade). With too few
    trades we fall back to the engine's own number, clearly flagged as un-calibrated.
    """
    closed = list(user.trades.filter(status="closed"))
    n = len(closed)
    if n < min_trades:
        return {"value": raw_confidence, "calibrated": False, "sample": n}

    wins = sum(1 for t in closed if (t.pnl or 0) > 0)
    base_wr = wins / n * 100.0

    # nudge by grade: A+/A setups historically do a bit better than the average,
    # C a bit worse. Keep the nudge modest so it never overrides real data.
    nudge = {"A+": 8, "A": 4, "B": 0, "C": -6, "D": -12}.get(grade, 0)
    value = max(5.0, min(95.0, base_wr + nudge))
    return {"value": round(value, 1), "calibrated": True, "sample": n,
            "base_win_rate": round(base_wr, 1)}


def setup_statistics(user, min_trades=1):
    """SETUP STATISTICS ENGINE — win-rate & profit-factor per setup class.

    Once enough trades accumulate, this tells you (and the engine) which setups
    actually work for this user/instrument, so weak ones can be de-emphasised.
    Honest note: needs HUNDREDS of trades to be statistically meaningful; with a
    handful it's only indicative.
    """
    closed = list(user.trades.filter(status="closed").exclude(setup_class=""))
    buckets = {}
    for t in closed:
        b = buckets.setdefault(t.setup_class, {"trades": 0, "wins": 0,
                                               "gross_win": 0.0, "gross_loss": 0.0})
        b["trades"] += 1
        pnl = t.pnl or 0
        if pnl > 0:
            b["wins"] += 1
            b["gross_win"] += pnl
        else:
            b["gross_loss"] += abs(pnl)

    out = []
    for name, b in buckets.items():
        if b["trades"] < min_trades:
            continue
        wr = b["wins"] / b["trades"] * 100 if b["trades"] else 0
        pf = (b["gross_win"] / b["gross_loss"]) if b["gross_loss"] > 0 else None
        out.append({
            "setup_class": name,
            "trades": b["trades"],
            "win_rate": round(wr, 1),
            "profit_factor": round(pf, 2) if pf is not None else None,
            "reliable": b["trades"] >= 30,   # flag if sample is big enough to trust
        })
    out.sort(key=lambda x: x["win_rate"], reverse=True)
    return out
