"""The eight built-in strategies.

These are real configurations, not labels: each one is a rule set + weight
split + minimum confidence + risk block that the same evaluator runs. Two
presets given the same candles will disagree, because they weight the engine's
findings differently and demand different confluence.

Presets are seeded as `Strategy` rows with `user=None` (shared, read-only). A
user who wants to change one clones it, which produces an owned strategy at v1.
"""

PRESETS = [
    {
        "key": "smartpips_core",
        "name": "SmartPips Core",
        "description": (
            "The house baseline. Wants structure, liquidity and order flow "
            "pointing the same way before it takes anything."
        ),
        "market": "crypto",
        "timeframes": ["5m", "15m", "1h"],
        "direction": "both",
        "min_confidence": 72,
        "weights": {"structure": 25, "liquidity": 20, "order_flow": 20,
                    "ema": 10, "rsi": 10, "risk": 15},
        "rules": [
            {"block": "market_structure", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "market_structure", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "liquidity", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "liquidity", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "order_flow", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "order_flow", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "ema_fast_vs_slow", "operator": "is", "value": "above", "applies_to": "long"},
            {"block": "ema_fast_vs_slow", "operator": "is", "value": "below", "applies_to": "short"},
            {"block": "risk_reward", "operator": "gte", "value": 2, "applies_to": "both", "required": True},
        ],
        "risk": {"risk_per_trade_pct": 1.0, "max_leverage": 10, "max_open_positions": 3,
                 "min_rr": 2.0, "max_chase_pct": 0.15, "tp_method": "structure",
                 "sl_method": "atr", "trailing_stop": True, "partial_tp": True},
    },
    {
        "key": "scalping",
        "name": "Scalping",
        "description": (
            "Fast intraday continuation. Needs order flow and volume, tolerates "
            "a lower reward multiple because holds are short."
        ),
        "market": "crypto",
        "timeframes": ["1m", "3m", "5m"],
        "direction": "both",
        "min_confidence": 65,
        "weights": {"order_flow": 30, "volume": 20, "ema": 15, "vwap": 15,
                    "structure": 10, "risk": 10},
        "rules": [
            {"block": "order_flow", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "order_flow", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "price_vs_vwap", "operator": "is", "value": "above", "applies_to": "long"},
            {"block": "price_vs_vwap", "operator": "is", "value": "below", "applies_to": "short"},
            {"block": "volume_ratio", "operator": "gte", "value": 1.2, "applies_to": "both"},
            {"block": "session_active", "operator": "is_true", "applies_to": "both"},
            {"block": "risk_reward", "operator": "gte", "value": 1.2, "applies_to": "both", "required": True},
        ],
        "risk": {"risk_per_trade_pct": 0.5, "max_leverage": 15, "max_open_positions": 2,
                 "min_rr": 1.2, "max_chase_pct": 0.08, "tp_method": "fixed_rr",
                 "sl_method": "atr", "trailing_stop": True, "partial_tp": True},
    },
    {
        "key": "trend_following",
        "name": "Trend Following",
        "description": (
            "Only trades with an established trend. Refuses ranging regimes and "
            "leans on moving-average alignment plus MACD."
        ),
        "market": "crypto",
        "timeframes": ["15m", "1h", "4h"],
        "direction": "both",
        "min_confidence": 70,
        "weights": {"ema": 25, "structure": 25, "macd": 20, "regime": 15, "risk": 15},
        "rules": [
            {"block": "market_regime", "operator": "is", "value": "trending",
             "applies_to": "both", "required": True},
            {"block": "ema_fast_vs_slow", "operator": "is", "value": "above", "applies_to": "long"},
            {"block": "ema_fast_vs_slow", "operator": "is", "value": "below", "applies_to": "short"},
            {"block": "market_structure", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "market_structure", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "macd_hist", "operator": "gt", "value": 0, "applies_to": "long"},
            {"block": "macd_hist", "operator": "lt", "value": 0, "applies_to": "short"},
            {"block": "risk_reward", "operator": "gte", "value": 2.5, "applies_to": "both"},
        ],
        "risk": {"risk_per_trade_pct": 1.0, "max_leverage": 8, "max_open_positions": 4,
                 "min_rr": 2.5, "max_chase_pct": 0.25, "tp_method": "atr",
                 "sl_method": "structure", "trailing_stop": True, "partial_tp": False},
    },
    {
        "key": "liquidity_sweep",
        "name": "Liquidity Sweep",
        "description": (
            "Waits for a stop raid against the prevailing structure, then joins "
            "the reversal once order flow confirms."
        ),
        "market": "crypto",
        "timeframes": ["5m", "15m"],
        "direction": "both",
        "min_confidence": 75,
        "weights": {"liquidity": 35, "structure": 20, "order_flow": 20,
                    "support_resistance": 10, "risk": 15},
        "rules": [
            {"block": "liquidity_sweep", "operator": "is_true",
             "applies_to": "both", "required": True},
            {"block": "liquidity", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "liquidity", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "order_flow", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "order_flow", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "fvg_present", "operator": "is_true", "applies_to": "both"},
            {"block": "risk_reward", "operator": "gte", "value": 2, "applies_to": "both", "required": True},
        ],
        "risk": {"risk_per_trade_pct": 0.8, "max_leverage": 10, "max_open_positions": 2,
                 "min_rr": 2.0, "max_chase_pct": 0.1, "tp_method": "levels",
                 "sl_method": "structure", "trailing_stop": False, "partial_tp": True},
    },
    {
        "key": "breakout",
        "name": "Breakout",
        "description": (
            "Trades expansion out of compression: price at the edge of a range "
            "with volume and volatility picking up."
        ),
        "market": "crypto",
        "timeframes": ["5m", "15m", "1h"],
        "direction": "both",
        "min_confidence": 70,
        "weights": {"support_resistance": 25, "volume": 25, "atr": 20,
                    "structure": 15, "risk": 15},
        "rules": [
            {"block": "distance_to_resistance_pct", "operator": "lte", "value": 0.3,
             "applies_to": "long"},
            {"block": "distance_to_support_pct", "operator": "lte", "value": 0.3,
             "applies_to": "short"},
            {"block": "volume_ratio", "operator": "gte", "value": 1.5,
             "applies_to": "both", "required": True},
            {"block": "atr_pct", "operator": "gte", "value": 0.3, "applies_to": "both"},
            {"block": "market_regime", "operator": "is_not", "value": "quiet", "applies_to": "both"},
            {"block": "risk_reward", "operator": "gte", "value": 2, "applies_to": "both"},
        ],
        "risk": {"risk_per_trade_pct": 1.0, "max_leverage": 10, "max_open_positions": 3,
                 "min_rr": 2.0, "max_chase_pct": 0.2, "tp_method": "atr",
                 "sl_method": "atr", "trailing_stop": True, "partial_tp": True},
    },
    {
        "key": "mean_reversion",
        "name": "Mean Reversion",
        "description": (
            "The mirror image of the trend preset: fades stretched moves inside "
            "a range, and stands aside when a trend is running."
        ),
        "market": "crypto",
        "timeframes": ["5m", "15m", "1h"],
        "direction": "both",
        "min_confidence": 68,
        "weights": {"rsi": 30, "vwap": 20, "support_resistance": 20,
                    "regime": 15, "risk": 15},
        "rules": [
            {"block": "market_regime", "operator": "is", "value": "ranging",
             "applies_to": "both", "required": True},
            {"block": "rsi", "operator": "lte", "value": 32, "applies_to": "long"},
            {"block": "rsi", "operator": "gte", "value": 68, "applies_to": "short"},
            {"block": "price_vs_vwap", "operator": "is", "value": "below", "applies_to": "long"},
            {"block": "price_vs_vwap", "operator": "is", "value": "above", "applies_to": "short"},
            {"block": "distance_to_support_pct", "operator": "lte", "value": 0.5, "applies_to": "long"},
            {"block": "distance_to_resistance_pct", "operator": "lte", "value": 0.5, "applies_to": "short"},
            {"block": "risk_reward", "operator": "gte", "value": 1.5, "applies_to": "both"},
        ],
        "risk": {"risk_per_trade_pct": 0.6, "max_leverage": 5, "max_open_positions": 3,
                 "min_rr": 1.5, "max_chase_pct": 0.1, "tp_method": "levels",
                 "sl_method": "fixed_pct", "trailing_stop": False, "partial_tp": False},
    },
    {
        "key": "conservative",
        "name": "Conservative",
        "description": (
            "High bar, few trades. Every major layer must agree, reward must be "
            "at least 3R, and leverage stays low."
        ),
        "market": "crypto",
        "timeframes": ["1h", "4h"],
        "direction": "both",
        "min_confidence": 85,
        "weights": {"structure": 25, "liquidity": 20, "order_flow": 15,
                    "regime": 15, "risk": 25},
        "rules": [
            {"block": "market_structure", "operator": "is", "value": "bullish",
             "applies_to": "long", "required": True},
            {"block": "market_structure", "operator": "is", "value": "bearish",
             "applies_to": "short", "required": True},
            {"block": "liquidity", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "liquidity", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "market_regime", "operator": "is_not", "value": "volatile",
             "applies_to": "both", "required": True},
            {"block": "engine_score", "operator": "gte", "value": 70, "applies_to": "both"},
            {"block": "risk_reward", "operator": "gte", "value": 3, "applies_to": "both", "required": True},
        ],
        "risk": {"risk_per_trade_pct": 0.5, "max_leverage": 3, "max_open_positions": 2,
                 "min_rr": 3.0, "max_chase_pct": 0.05, "tp_method": "structure",
                 "sl_method": "structure", "trailing_stop": True, "partial_tp": False},
    },
    {
        "key": "aggressive",
        "name": "Aggressive",
        "description": (
            "Low bar, more trades, wider risk appetite. Takes partial confluence "
            "and relies on the engine score rather than full agreement."
        ),
        "market": "crypto",
        "timeframes": ["1m", "5m", "15m"],
        "direction": "both",
        "min_confidence": 55,
        "weights": {"order_flow": 25, "structure": 20, "volume": 15,
                    "ema": 15, "atr": 15, "risk": 10},
        "rules": [
            {"block": "engine_score", "operator": "gte", "value": 45, "applies_to": "both"},
            {"block": "order_flow", "operator": "is", "value": "bullish", "applies_to": "long"},
            {"block": "order_flow", "operator": "is", "value": "bearish", "applies_to": "short"},
            {"block": "ema_fast_vs_slow", "operator": "is", "value": "above", "applies_to": "long"},
            {"block": "ema_fast_vs_slow", "operator": "is", "value": "below", "applies_to": "short"},
            {"block": "risk_reward", "operator": "gte", "value": 1.2, "applies_to": "both", "required": True},
        ],
        # Note the leverage request: the account-level RiskLimits ceiling still
        # clamps this down for real orders (see rule_schema.effective_risk).
        "risk": {"risk_per_trade_pct": 2.0, "max_leverage": 25, "max_open_positions": 5,
                 "min_rr": 1.2, "max_chase_pct": 0.35, "tp_method": "fixed_rr",
                 "sl_method": "atr", "trailing_stop": True, "partial_tp": True},
    },
]

PRESETS_BY_KEY = {preset["key"]: preset for preset in PRESETS}


def sync_presets():
    """Create or refresh the shared preset rows. Safe to call repeatedly.

    Called lazily by the strategy list endpoint so a fresh install has the
    library without needing a separate management command or data migration
    that would be awkward to re-run after a preset is tweaked.
    """
    from .config_models import Strategy, StrategyVersion

    for preset in PRESETS:
        strategy, _ = Strategy.objects.update_or_create(
            user=None, preset_key=preset["key"],
            defaults={
                "name": preset["name"],
                "description": preset["description"],
                "market": preset["market"],
                "timeframes": preset["timeframes"],
                "direction": preset["direction"],
                "symbols": preset.get("symbols", []),
            },
        )
        StrategyVersion.objects.update_or_create(
            strategy=strategy, version=1,
            defaults={
                "rules": preset["rules"],
                "weights": preset["weights"],
                "min_confidence": preset["min_confidence"],
                "risk": preset["risk"],
                "notes": "Built-in preset",
            },
        )
