"""Infrastructure package exports with lazy imports.

Avoid importing provider-heavy modules during package initialization; several
data providers also import infrastructure modules and would otherwise form a
cycle during Config/DataFetcherManager startup.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ThemeBoardResolverService",
    "ThemeEventScanner",
    "ThemeExpansionService",
    "get_theme_picker_db",
    "get_theme_picker_config",
    "ThemeSignalService",
    "ThemeStockPoolService",
]


def __getattr__(name: str) -> Any:
    if name == "ThemeBoardResolverService":
        from theme_picker.infrastructure.board_resolver_service import ThemeBoardResolverService

        return ThemeBoardResolverService
    if name == "ThemeEventScanner":
        from theme_picker.infrastructure.event_scanner import ThemeEventScanner

        return ThemeEventScanner
    if name == "ThemeExpansionService":
        from theme_picker.infrastructure.expansion_service import ThemeExpansionService

        return ThemeExpansionService
    if name == "get_theme_picker_db":
        from theme_picker.infrastructure.persistence import get_theme_picker_db

        return get_theme_picker_db
    if name == "get_theme_picker_config":
        from theme_picker.infrastructure.runtime import get_theme_picker_config

        return get_theme_picker_config
    if name == "ThemeSignalService":
        from theme_picker.infrastructure.signal_service import ThemeSignalService

        return ThemeSignalService
    if name == "ThemeStockPoolService":
        from theme_picker.infrastructure.stock_pool_service import ThemeStockPoolService

        return ThemeStockPoolService
    raise AttributeError(name)
