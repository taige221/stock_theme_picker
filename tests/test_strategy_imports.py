# -*- coding: utf-8 -*-

from __future__ import annotations


def test_strategy_family_imports_match_registry_exports() -> None:
    from theme_picker.strategy import AShareBoxStrategy as RegistryBoxStrategy
    from theme_picker.strategy import StockSignalBacktestStrategy as RegistrySignalStrategy
    from theme_picker.strategy.a_share_box import AShareBoxStrategy as FamilyBoxStrategy
    from theme_picker.strategy.benchmarks import (
        AShareMigratedCryptoStrategy as FamilyBenchmarkStrategy,
    )
    from theme_picker.strategy.stock_signal import (
        StockSignalBacktestStrategy as FamilySignalStrategy,
    )

    assert RegistryBoxStrategy is FamilyBoxStrategy
    assert FamilyBenchmarkStrategy.name == "a_share_migrated_crypto"
    assert RegistrySignalStrategy is FamilySignalStrategy
