# -*- coding: utf-8 -*-
"""
===================================
Single Stock Theme Attribution Service
===================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from theme_picker.application.registry_service import ThemeRegistryService
from theme_picker.infrastructure.stock_pool_service import build_stock_code_variants, canonicalize_stock_code


class StockThemeAttributionService:
    """Build lightweight stock-to-theme attribution without board expansion."""

    def __init__(self, *, registry_service: Optional[ThemeRegistryService] = None):
        self.registry_service = registry_service or ThemeRegistryService()

    def attribute(
        self,
        stock_code: str,
        *,
        board_items: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        variants = set(build_stock_code_variants(stock_code))
        items: List[Dict[str, Any]] = []
        seen_keys = set()

        normalized_board_codes = {
            str(item.get("code") or "").strip().upper()
            for item in (board_items or [])
            if isinstance(item, dict) and str(item.get("code") or "").strip()
        }
        normalized_board_names = {
            str(item.get("name") or "").strip()
            for item in (board_items or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }

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
                key = (theme.id, "direct_stock_pool")
                if key not in seen_keys:
                    seen_keys.add(key)
                    items.append(
                        {
                            "theme_id": theme.id,
                            "theme_name": theme.name,
                            "relation_type": "direct_stock_pool",
                            "confidence": "high",
                            "reason": "股票命中主题直连股票池",
                            "matched_boards": [],
                        }
                    )

            theme_board_codes = {
                str(code or "").strip().upper()
                for code in (getattr(theme, "concept_board_codes", []) or [])
                if str(code or "").strip()
            }
            theme_board_names = {
                str(name or "").strip()
                for name in (getattr(theme, "concept_board_names", []) or [])
                if str(name or "").strip()
            }
            matched_boards = sorted(
                list((theme_board_codes & normalized_board_codes) | (theme_board_names & normalized_board_names))
            )
            if matched_boards:
                key = (theme.id, "concept_board_match")
                if key not in seen_keys:
                    seen_keys.add(key)
                    items.append(
                        {
                            "theme_id": theme.id,
                            "theme_name": theme.name,
                            "relation_type": "concept_board_match",
                            "confidence": "medium" if not (variants & normalized_pool) else "high",
                            "reason": f"股票所属概念板块与主题映射命中：{'、'.join(matched_boards[:3])}",
                            "matched_boards": matched_boards[:5],
                        }
                    )

        return items
