"""Strategy interfaces and concrete implementations for backtesting."""

from theme_picker.strategy.a_share_box_strategy import AShareBoxStrategy
from theme_picker.strategy.a_share_migrated_crypto import AShareMigratedCryptoStrategy
from theme_picker.strategy.base import Strategy, StrategySignal
from theme_picker.strategy.params import StrategyParams

STRATEGY_REGISTRY = {
    AShareBoxStrategy.name: AShareBoxStrategy,
    AShareMigratedCryptoStrategy.name: AShareMigratedCryptoStrategy,
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
    "Strategy",
    "StrategyParams",
    "StrategySignal",
    "STRATEGY_REGISTRY",
    "create_strategy",
]
