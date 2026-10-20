"""Chronological holdout; parameters never fit using the holdout."""
import json
from pathlib import Path
from unittest.mock import patch
from django.core.management.base import BaseCommand, CommandError
from apps.strategy.backtest_data import historical_window
from apps.strategy.backtest_runner import run_selected
from apps.strategy.config_models import StrategyVersion


class Command(BaseCommand):
    help = "Read-only offline OHLCV backtest with chronological holdout. No orders/DB writes."

    def add_arguments(self, p):
        p.add_argument("--input", required=True, help="JSON array of completed OHLCV bars")
        p.add_argument("--symbol", default="BTCUSDT:PERP")
        p.add_argument("--timeframe", choices=["1m","5m","15m","1h","4h"], default="5m")
        p.add_argument("--engine", choices=["native","backtesting"], default="native")
        p.add_argument("--version-id", type=int)
        p.add_argument("--holdout", type=float, default=.3)

    def handle(self, *args, **o):
        try:
            if not .2 <= o["holdout"] <= .5:
                raise ValueError("Holdout fraction must be in [.2,.5].")
            raw = json.loads(Path(o["input"]).read_text())
            if not isinstance(raw, list):
                raise ValueError("Input must be a JSON array.")
            with patch("apps.market.candles.fetch_candles", return_value=raw):
                candles, info = historical_window(o["symbol"], o["timeframe"], with_diagnostics=True)
            cut = int(len(candles)*(1-o["holdout"]))
            if cut < 62 or len(candles)-cut < 2:
                raise ValueError("Need at least 62 training and 2 holdout bars after validation.")
            version = StrategyVersion.objects.get(pk=o["version_id"]) if o["version_id"] else None
            if version:
                from apps.strategy.backtest_data import backtest_inputs
                backtest_inputs({"symbol":o["symbol"],"timeframe":o["timeframe"]}, version.strategy)
            train = run_selected(o["symbol"], candles[:cut], timeframe=o["timeframe"],
                                 version=version, source={"engine":o["engine"]})
            # Holdout receives historical warmup context but makes NO pre-cut decisions.
            hold = run_selected(o["symbol"], candles, timeframe=o["timeframe"],
                                version=version, source={"engine":o["engine"]}, warmup=cut)
            self.stdout.write(json.dumps({"read_only":True, "data":info, "split_index":cut,
                "training":train, "holdout":hold, "parameter_fitting":False,
                "warning":"Fixed parameters; holdout trades only. Short histories do not establish profitability."}))
        except Exception as exc:
            raise CommandError(str(exc)) from exc