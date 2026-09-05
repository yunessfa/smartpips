"""
Builds a per-user "trader profile" from their trade journal: win rate, profit
factor, leverage habits, directional bias, best/worst symbols, risk/reward and a
few behavioural tendencies. Used both for a UI panel and to personalise the AI's
suggestions (sizing, leverage caps, avoiding the user's recurring mistakes).

No ML dependencies — just aggregate statistics over the user's own trades.
"""
from statistics import mean, median


def _safe_mean(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def compute_trader_profile(user) -> dict:
    from .models import Trade

    trades = list(Trade.objects.filter(user=user).order_by("opened_at"))
    total = len(trades)
    closed = [t for t in trades if t.status == "closed" and t.pnl is not None]
    open_count = total - len(closed)

    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else None

    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0.0

    longs = [t for t in trades if t.direction == "long"]
    shorts = [t for t in trades if t.direction == "short"]
    if longs and shorts:
        bias = "long" if len(longs) > len(shorts) * 1.3 else (
            "short" if len(shorts) > len(longs) * 1.3 else "balanced")
    elif longs:
        bias = "long"
    elif shorts:
        bias = "short"
    else:
        bias = "n/a"

    # Per-symbol performance.
    by_symbol = {}
    for t in trades:
        s = by_symbol.setdefault(t.symbol, {"trades": 0, "pnl": 0.0, "wins": 0, "closed": 0})
        s["trades"] += 1
        if t.status == "closed" and t.pnl is not None:
            s["closed"] += 1
            s["pnl"] += t.pnl
            if t.pnl > 0:
                s["wins"] += 1
    best_symbol = max(by_symbol.items(), key=lambda kv: kv[1]["pnl"], default=(None, None))
    worst_symbol = min(by_symbol.items(), key=lambda kv: kv[1]["pnl"], default=(None, None))

    # Risk / reward where both TP and SL were set.
    rr_values = []
    for t in trades:
        if t.take_profit and t.stop_loss and t.entry_price:
            reward = abs(t.take_profit - t.entry_price)
            risk = abs(t.entry_price - t.stop_loss)
            if risk > 0:
                rr_values.append(reward / risk)

    leverages = [t.leverage for t in trades if t.leverage]
    avg_leverage = _safe_mean(leverages)
    max_leverage = max(leverages) if leverages else None
    med_leverage = median(leverages) if leverages else None

    # --- Behavioural tendencies (cheap heuristics) ---
    tendencies = []

    no_sl = [t for t in trades if not t.stop_loss]
    if total and len(no_sl) / total > 0.3:
        tendencies.append(
            f"often trades WITHOUT a stop-loss ({len(no_sl)}/{total}) — risky")

    if wins and losses:
        lev_win = _safe_mean([t.leverage for t in wins])
        lev_loss = _safe_mean([t.leverage for t in losses])
        if lev_win and lev_loss and lev_loss > lev_win * 1.25:
            tendencies.append(
                f"uses higher leverage on losing trades ({lev_loss}x) than winners "
                f"({lev_win}x) — over-leverages under pressure")

    # Revenge trading: a trade with above-median leverage right after a closed loss.
    revenge = 0
    for i in range(1, len(trades)):
        prev = trades[i - 1]
        cur = trades[i]
        if (prev.status == "closed" and prev.pnl is not None and prev.pnl < 0
                and med_leverage and cur.leverage and cur.leverage > med_leverage):
            revenge += 1
    if revenge >= 2:
        tendencies.append(
            f"signs of revenge trading: {revenge}x raised leverage right after a loss")

    if win_rate and win_rate < 40 and len(closed) >= 5:
        tendencies.append(f"low win rate ({win_rate}%) — entries may need tighter filters")
    if profit_factor is not None and profit_factor < 1 and len(closed) >= 5:
        tendencies.append(
            f"profit factor below 1 ({profit_factor}) — losers outweigh winners overall")

    return {
        "total_trades": total,
        "open_trades": open_count,
        "closed_trades": len(closed),
        "win_rate": win_rate,
        "wins": len(wins),
        "losses": len(losses),
        "profit_factor": profit_factor,
        "avg_win_pct": _safe_mean([t.pnl_percent for t in wins]),
        "avg_loss_pct": _safe_mean([t.pnl_percent for t in losses]),
        "total_pnl": round(sum(t.pnl for t in closed), 2) if closed else 0.0,
        "direction_bias": bias,
        "long_count": len(longs),
        "short_count": len(shorts),
        "avg_leverage": avg_leverage,
        "max_leverage": max_leverage,
        "avg_rr": _safe_mean(rr_values),
        "best_symbol": best_symbol[0],
        "worst_symbol": worst_symbol[0],
        "tendencies": tendencies,
    }


def profile_for_prompt(user) -> str:
    """A compact, AI-readable version of the profile for the system prompt."""
    if user is None or not getattr(user, "is_authenticated", False):
        return "- (no trade history)"
    p = compute_trader_profile(user)
    if p["total_trades"] == 0:
        return "- (user hasn't logged any trades yet — use conservative defaults)"

    lines = [
        f"- Trades: {p['total_trades']} ({p['closed_trades']} closed), "
        f"win rate {p['win_rate']}%, profit factor {p['profit_factor']}",
        f"- Direction bias: {p['direction_bias']} "
        f"(long {p['long_count']} / short {p['short_count']})",
        f"- Leverage: avg {p['avg_leverage']}x, max {p['max_leverage']}x; "
        f"avg R:R {p['avg_rr']}",
        f"- Best symbol: {p['best_symbol']} · Worst: {p['worst_symbol']}",
    ]
    if p["tendencies"]:
        lines.append("- Tendencies to account for: " + "; ".join(p["tendencies"]))
    return "\n".join(lines)
