"""Infrastructure package exports with lazy imports to avoid circular dependencies."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ThemeBoardResolverService",
    "ThemeEventScanner",
    "ThemeExpansionService",
    "get_theme_picker_db",
    "get_theme_picker_config",
    "ThemeSignalService",
    "ThemeStockPoolService",
]


def __getattr__(name: str):
    if name == "ThemeBoardResolverService":
        return import_module("theme_picker.infrastructure.board_resolver_service").ThemeBoardResolverService
    if name == "ThemeEventScanner":
        return import_module("theme_picker.infrastructure.event_scanner").ThemeEventScanner
    if name == "ThemeExpansionService":
        return import_module("theme_picker.infrastructure.expansion_service").ThemeExpansionService
    if name == "get_theme_picker_db":
        return import_module("theme_picker.infrastructure.persistence").get_theme_picker_db
    if name == "get_theme_picker_config":
        return import_module("theme_picker.infrastructure.runtime").get_theme_picker_config
    if name == "ThemeSignalService":
        return import_module("theme_picker.infrastructure.signal_service").ThemeSignalService
    if name == "ThemeStockPoolService":
        return import_module("theme_picker.infrastructure.stock_pool_service").ThemeStockPoolService
    raise AttributeError(name)
