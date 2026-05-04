# -*- coding: utf-8 -*-
"""
===================================
Theme Alert Pipeline
===================================
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from theme_picker.application.registry_service import ThemeRegistryService
from theme_picker.domain.theme_event import ThemeAlertResultSchema, ThemeDefinitionSchema
from theme_picker.infrastructure.event_scanner import ThemeEventScanner
from theme_picker.infrastructure.expansion_service import ThemeExpansionService
from theme_picker.infrastructure.signal_service import ThemeSignalService
from theme_picker.infrastructure.stock_pool_service import ThemeStockPoolService


class ThemeAlertPipeline:
    """Orchestrate dynamic theme event scanning and technical confirmation."""

    def __init__(
        self,
        registry_service: Optional[ThemeRegistryService] = None,
        event_scanner: Optional[ThemeEventScanner] = None,
        stock_pool_service: Optional[ThemeStockPoolService] = None,
        expansion_service: Optional[ThemeExpansionService] = None,
        signal_service: Optional[ThemeSignalService] = None,
    ):
        self.registry_service = registry_service or ThemeRegistryService()
        self.event_scanner = event_scanner or ThemeEventScanner()
        self.stock_pool_service = stock_pool_service or ThemeStockPoolService()
        self.expansion_service = expansion_service or ThemeExpansionService()
        self.signal_service = signal_service or ThemeSignalService()

    def run(
        self,
        *,
        theme_ids: Optional[Iterable[str]] = None,
        extra_themes: Optional[Iterable[ThemeDefinitionSchema]] = None,
        days: int = 7,
        max_results_per_keyword: int = 5,
        max_expanded_candidates: int = 30,
        triggered_only: bool = True,
    ) -> ThemeAlertResultSchema:
        themes = self._resolve_themes(theme_ids, extra_themes=extra_themes)
        result = ThemeAlertResultSchema(scanned_theme_ids=[theme.id for theme in themes])

        for theme in themes:
            event = self.event_scanner.scan_theme(
                theme,
                max_results_per_keyword=max_results_per_keyword,
                days=days,
            )
            result.events.append(event)

            if triggered_only and not event.triggered:
                continue

            stock_pool = self.stock_pool_service.get_stock_pool(theme)
            candidate_pool = self.expansion_service.expand_theme(
                theme,
                event,
                stock_pool,
                days=days,
                max_results_per_query=max_results_per_keyword,
                max_candidates=max_expanded_candidates,
            )
            signals = self.signal_service.evaluate_theme(theme, event, candidate_pool)
            result.signals.extend(signals)

        return result

    def _resolve_themes(
        self,
        theme_ids: Optional[Iterable[str]],
        *,
        extra_themes: Optional[Iterable[ThemeDefinitionSchema]] = None,
    ) -> List[ThemeDefinitionSchema]:
        resolved: List[ThemeDefinitionSchema] = []
        seen = set()

        if theme_ids is None:
            for theme in self.registry_service.list_themes(enabled_only=True):
                if theme.id in seen:
                    continue
                seen.add(theme.id)
                resolved.append(theme)
        else:
            for theme_id in theme_ids:
                theme = self.registry_service.get_theme(str(theme_id))
                if theme is not None and theme.enabled and theme.id not in seen:
                    seen.add(theme.id)
                    resolved.append(theme)

        for theme in extra_themes or []:
            if theme.id in seen:
                continue
            seen.add(theme.id)
            resolved.append(theme)
        return resolved
