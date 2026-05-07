# -*- coding: utf-8 -*-
"""
===================================
Single Stock Theme Attribution Service
===================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from theme_picker.application.registry_service import ThemeRegistryService
from theme_picker.infrastructure.stock_pool_service import build_stock_code_variants, canonicalize_stock_code


class StockThemeAttributionService:
    """Build lightweight stock-to-theme attribution without board expansion."""

    def __init__(self, *, registry_service: Optional[ThemeRegistryService] = None):
        self.registry_service = registry_service or ThemeRegistryService()

    def attribute(self, stock_code: str) -> List[Dict[str, Any]]:
        variants = set(build_stock_code_variants(stock_code))
        items: List[Dict[str, Any]] = []

        themes = sorted(
            self.registry_service.list_themes(enabled_only=True),
            key=lambda item: (int(getattr(item, "priority", 100) or 100), str(item.name or "")),
        )
        for theme in themes:
            normalized_pool = {
                canonicalize_stock_code(code)
                for code in (theme.stock_pool or [])
                if str(code or "").strip()
            }
            if variants & normalized_pool:
                items.append(
                    {
                        "theme_id": theme.id,
                        "theme_name": theme.name,
                        "relation_type": "direct_stock_pool",
                        "confidence": "high",
                        "reason": "股票命中主题直连股票池",
                    }
                )

        return items
