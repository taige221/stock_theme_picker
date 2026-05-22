# -*- coding: utf-8 -*-
"""Data provider package exports with lazy imports."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "BaseFetcher",
    "DataFetcherManager",
    "is_us_index_code",
    "is_us_stock_code",
    "is_hk_stock_code",
    "get_us_index_yf_symbol",
    "US_INDEX_MAPPING",
]


def __getattr__(name: str):
    if name in {"BaseFetcher", "DataFetcherManager"}:
        module = import_module("theme_picker.data_provider.base")
        return getattr(module, name)
    if name in {"is_us_index_code", "is_us_stock_code", "get_us_index_yf_symbol", "US_INDEX_MAPPING"}:
        module = import_module("theme_picker.data_provider.us_index_mapping")
        return getattr(module, name)
    if name == "is_hk_stock_code":
        try:
            module = import_module("theme_picker.data_provider.akshare_fetcher")
            return getattr(module, name)
        except Exception:
            def fallback(stock_code: str) -> bool:
                code = (stock_code or "").strip().lower()
                if code.endswith(".hk"):
                    base = code[:-3]
                    return base.isdigit() and 1 <= len(base) <= 5
                if code.startswith("hk"):
                    base = code[2:]
                    return base.isdigit() and 1 <= len(base) <= 5
                return code.isdigit() and len(code) == 5

            return fallback
    raise AttributeError(name)
