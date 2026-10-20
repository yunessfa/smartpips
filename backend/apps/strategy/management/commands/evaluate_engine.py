import json
from pathlib import Path
from unittest.mock import patch
from django.core.management.base import BaseCommand, CommandError
from apps.strategy.backtest_data import historical_window
from apps.strategy.evaluation import evaluate

class Command(BaseCommand):
    help="Offline fixed-parameter 70/15/15 and expanding walk-forward. No orders, fitting or DB writes."
    def add_arguments(self,p):
        p.add_argument("--input",required=True)
        p.add_argument("--output",required=True)
        p.add_argument("--symbol",default="BTCUSDT:PERP")
        p.add_argument("--timeframe",choices=["1m","5m","15m","1h","4h"],default="5m")
        p.add_argument("--engine",choices=["native","backtesting"],default="native")
        p.add_argument("--include-holdout",action="store_true",help="Explicit final evaluation; not single-use protected")
    def handle(self,*args,**o):
        try:
            raw=json.loads(Path(o["input"]).read_text())
            if not isinstance(raw,list):raise ValueError("Expected OHLCV array")
            with patch("apps.market.candles.fetch_candles",return_value=raw):
                bars,quality=historical_window(o["symbol"],o["timeframe"],with_diagnostics=True)
            if quality["invalid_rows"] or quality["gaps_detected"] or quality["partial_history"]:
                raise ValueError("Evaluation requires a complete contiguous valid input; no silent row/window selection")
            result=evaluate(o["symbol"],bars,o["timeframe"],o["engine"],include_holdout=o["include_holdout"])
            result["data_quality"]=quality
            Path(o["output"]).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
            self.stdout.write("Research report written; this is not strategy profitability certification.")
        except Exception as exc:raise CommandError(str(exc)) from exc
