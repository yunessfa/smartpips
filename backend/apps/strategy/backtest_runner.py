from rest_framework.exceptions import APIException, ValidationError
from .backtest import backtest


class ResearchUnavailable(APIException):
    status_code = 503


def run_selected(symbol, candles, *, source=None, timeframe="5m", version=None, **kwargs):
    source = source or {}
    selected = source.get("engine", "native")
    if selected == "native":
        return {**backtest(symbol, candles, timeframe=timeframe, version=version, **kwargs),
                "engine": "native", "engine_version": "smartpips-fixed-stop-v2",
                "experimental": False}
    kwargs.pop("mode", None)
    kwargs.pop("htf_series", None)
    if selected != "backtesting":
        raise ValidationError({"code": "unknown_backtest_engine", "error": "Choose native or backtesting."})
    try:
        from .research_backtesting import run
        return run(symbol, candles, timeframe=timeframe, version=version, **kwargs)
    except ImportError as exc:
        raise ResearchUnavailable({"code": "research_engine_not_installed",
            "error": "Build the optional research image; the default image intentionally excludes backtesting.py."}) from exc