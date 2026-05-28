"""Strategy interfaces and concrete implementations for backtesting."""

from theme_picker.strategy.a_share_box_strategy import AShareBoxStrategy
from theme_picker.strategy.a_share_migrated_crypto import AShareMigratedCryptoStrategy
from theme_picker.strategy.base import Strategy, StrategySignal
from theme_picker.strategy.params import StrategyParamValidationError, StrategyParams
from theme_picker.strategy.stock_signal_strategy import (
    StockSignalBacktestStrategy,
    StockSignalBreakoutStrategy,
    StockSignalHoldingStrategy,
    StockSignalPullbackStrategy,
    StockSignalTrendFollowStrategy,
)

STRATEGY_REGISTRY = {
    AShareBoxStrategy.name: AShareBoxStrategy,
    AShareMigratedCryptoStrategy.name: AShareMigratedCryptoStrategy,
    StockSignalBacktestStrategy.name: StockSignalBacktestStrategy,
    StockSignalPullbackStrategy.name: StockSignalPullbackStrategy,
    StockSignalBreakoutStrategy.name: StockSignalBreakoutStrategy,
    StockSignalTrendFollowStrategy.name: StockSignalTrendFollowStrategy,
    StockSignalHoldingStrategy.name: StockSignalHoldingStrategy,
}

STRATEGY_METADATA = {
    "a_share_box": {
        "name": "A股箱体策略",
        "description": "箱体突破/回踩确认，使用本地已同步 A 股日线缓存回测。",
        "category": "box",
        "is_default": True,
    },
    "a_share_migrated_crypto": {
        "name": "A股趋势突破基础策略",
        "description": "从趋势突破逻辑迁移而来，入场看近期新高、涨幅和量能，出场看止损/止盈/超时/MA10。",
        "category": "trend_breakout",
        "is_default": False,
    },
    "stock_signal_auto": {
        "name": "单股信号自动策略",
        "description": "复用单股查询的自动决策视角，在低吸、突破、趋势跟随、持有候选中选择可回测信号。",
        "category": "single_stock_signal",
        "is_default": False,
    },
    "stock_signal_pullback": {
        "name": "单股低吸回踩策略",
        "description": "复用单股查询的低吸回踩视角，偏向 MA10/MA20 支撑带附近的承接确认。",
        "category": "single_stock_signal",
        "is_default": False,
    },
    "stock_signal_breakout": {
        "name": "单股突破确认策略",
        "description": "复用单股查询的突破确认视角，偏向涨幅、量比和趋势分足够的短线异动。",
        "category": "single_stock_signal",
        "is_default": False,
    },
    "stock_signal_trend_follow": {
        "name": "单股趋势跟随策略",
        "description": "复用单股查询的趋势跟随视角，偏向多头排列中乖离不过高的顺势机会。",
        "category": "single_stock_signal",
        "is_default": False,
    },
    "stock_signal_holding": {
        "name": "单股趋势持有策略",
        "description": "复用单股查询的趋势持有视角，把趋势底座完整的持有候选作为回测入场条件。",
        "category": "single_stock_signal",
        "is_default": False,
    },
}


def create_strategy(name: str) -> Strategy:
    strategy_name = str(name or "").strip()
    strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
    if strategy_cls is None:
        raise ValueError(f"Unsupported strategy: {strategy_name}")
    return strategy_cls()


__all__ = [
    "AShareBoxStrategy",
    "AShareMigratedCryptoStrategy",
    "StockSignalBacktestStrategy",
    "StockSignalBreakoutStrategy",
    "StockSignalHoldingStrategy",
    "StockSignalPullbackStrategy",
    "StockSignalTrendFollowStrategy",
    "Strategy",
    "StrategyParamValidationError",
    "StrategyParams",
    "StrategySignal",
    "STRATEGY_METADATA",
    "STRATEGY_REGISTRY",
    "create_strategy",
]
