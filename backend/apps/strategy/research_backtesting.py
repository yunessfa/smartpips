"""Optional, lazy-loaded research adapter. Not used for live decisions/orders.

Next-open library gap fills and next-open timeout exits are intentionally not
represented as equivalent to native cancellation / close-of-bar timeouts.
"""
import contextlib
import io
import math
from .backtest import _decide_at


def run(symbol, candles, *, timeframe="5m", version=None, cash=10000,
        risk_pct=.5, fee_rate=.0006, max_hold=40, warmup=60):
    import pandas as pd
    import backtesting
    from backtesting import Strategy
    from backtesting.lib import FractionalBacktest
    if (not math.isfinite(cash) or cash <= 0 or not math.isfinite(risk_pct)
            or not 0 < risk_pct <= 2):
        raise ValueError("Research cash must be positive; risk_pct in (0,2].")
    diagnostics = {"bars_evaluated": 0, "base_engine_wait": 0, "strategy_veto": 0,
                   "invalid_plan": 0, "unfillable_entry": 0,
                   "base_wait_reasons": {}, "strategy_veto_reasons": {}}
    if len(candles) < warmup+2:
        raise ValueError("Insufficient completed candles")
    frame = pd.DataFrame(candles).rename(columns={
        k: k.title() for k in ("open", "high", "low", "close", "volume")})
    frame.index = pd.to_datetime(frame.pop("time"), unit="s", utc=True)
    unit = 1e-8
    plans = {}

    class Adapter(Strategy):
        def init(self):
            self.submitted = None

        def next(self):
            index = len(self.data)-1
            if self.trades:
                if index >= self.submitted+max_hold:
                    self.position.close()
                return
            if self.orders or index < warmup or index >= len(candles)-1:
                return
            if self.closed_trades and index <= self.closed_trades[-1].exit_bar:
                return
            diagnostics["bars_evaluated"] += 1
            plan = _decide_at(symbol, candles[:index+1], timeframe=timeframe,
                              version=version, diagnostics=diagnostics)
            if not plan:
                return
            close, stop, target = candles[index]["close"], plan["stop"], plan["target"]
            long = plan["direction"] == "buy"
            if not (stop < close < target if long else target < close < stop):
                diagnostics["invalid_plan"] += 1
                return
            per_coin = abs(close-stop)+(close+stop)*fee_rate
            qty = min(self.equity*risk_pct/100/per_coin,
                      self.equity*.95/(close*(1+fee_rate)))
            units = math.floor(qty/unit)
            if units < 1:
                diagnostics["invalid_plan"] += 1
                return
            plans[index+1] = plan
            kw = dict(size=units, sl=stop*unit, tp=target*unit)
            (self.buy if long else self.sell)(**kw)
            self.submitted = index

    with contextlib.redirect_stderr(io.StringIO()):
        stats = FractionalBacktest(
            frame, Adapter, cash=cash, commission=fee_rate, spread=0,
            margin=1, trade_on_close=False, exclusive_orders=True,
            finalize_trades=True, fractional_unit=unit).run()
    trade_list = []
    for _, t in stats["_trades"].iterrows():
        entry_index, exit_index = int(t.EntryBar), int(t.ExitBar)
        stop = plans[entry_index]["stop"]
        risk = abs(float(t.EntryPrice)-stop)*abs(float(t.Size))
        r = float(t.PnL)/risk if risk > 0 else None
        trade_list.append({"entry_index": entry_index, "exit_index": exit_index,
                           "entry_price": float(t.EntryPrice), "exit_price": float(t.ExitPrice),
                           "quantity": float(t.Size), "pnl": float(t.PnL), "r": r,
                           "exit_reason": "library_broker_exit"})
    rs = [t["r"] for t in trade_list if t["r"] is not None]
    pos, neg = sum(max(0,r) for r in rs), -sum(min(0,r) for r in rs)
    running = peak = dd = 0
    curve = []
    for r in rs:
        running += r
        peak = max(peak, running)
        dd = min(dd, running-peak)
        curve.append(round(running, 4))
    def finite(value):
        return float(value) if math.isfinite(float(value)) else None
    return {
        "engine": "backtesting", "engine_version": backtesting.__version__,
        "experimental": True, "activation_eligible": False, "trades": len(trade_list),
        "trade_list": trade_list, "diagnostics": diagnostics, "equity_curve": curve,
        "total_r": round(sum(rs),4), "avg_r": sum(rs)/len(rs) if rs else None,
        "expectancy_r": sum(rs)/len(rs) if rs else None,
        "max_drawdown_r": dd if rs else None,
        "win_rate": sum(r>0 for r in rs)/len(rs)*100 if rs else None,
        "profit_factor": pos/neg if neg else None,
        "wins": sum(r>0 for r in rs), "losses": sum(r<0 for r in rs),
        "account": {"starting_cash": cash, "ending_equity": finite(stats["Equity Final [$]"]),
                    "return_pct": finite(stats["Return [%]"]),
                    "max_drawdown_pct": finite(stats["Max. Drawdown [%]"]),
                    "risk_pct_requested": risk_pct, "leverage": 1},
        "assumptions": {"fee_rate_per_side": fee_rate, "slippage_bps": 0, "spread": 0,
                        "size": "stop-based fractional coin; 1x capital cap",
                        "entry": "next open; gap may invalidate planned risk",
                        "timeout": "market close request filled next open",
                        "history_end": "finalize remaining trade on last bar"},
        "note": "Experimental execution assumptions differ from native; not activation evidence.",
        "limitations": ["No funding, liquidation, tick path or historical news replay",
                        "Not equivalent to native gap-cancellation and close-of-bar timeout",
                        "No partial exits or trailing; no profitability claim"],
    }