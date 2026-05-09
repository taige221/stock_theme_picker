# -*- coding: utf-8 -*-
"""
===================================
Theme Event Scanner
===================================
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from theme_picker.domain.theme_event import (
    ThemeDefinitionSchema,
    ThemeEventSchema,
    ThemeNewsItemSchema,
)
from theme_picker.infrastructure.search_fallback_logging import emit_search_fallback_log
from theme_picker.search_service import SearchResult, SearchService

logger = logging.getLogger(__name__)
_SEARCH_FALLBACK_TAG = "SEARCH_FALLBACK"


def _emit_theme_news_fallback_log(payload: dict, *, level: str = "info") -> None:
    enriched_payload = {"tag": _SEARCH_FALLBACK_TAG, **payload}
    emit_search_fallback_log(
        enriched_payload,
        level=level,
        mirror_logger=logger,
    )


class ThemeEventScanner:
    """Scan theme-related news using dynamic theme keywords."""

    def __init__(self, search_service: Optional[SearchService] = None):
        self.search_service = search_service

    def scan_theme(
        self,
        theme: ThemeDefinitionSchema,
        *,
        max_results_per_keyword: int = 5,
        days: int = 7,
        log_context: Optional[Dict[str, Any]] = None,
    ) -> ThemeEventSchema:
        if self.search_service is None or not self.search_service.is_available:
            return ThemeEventSchema(
                theme_id=theme.id,
                theme_name=theme.name,
                trigger_reason="搜索服务不可用",
                triggered=False,
            )

        dedup: dict[str, ThemeNewsItemSchema] = {}

        for keyword in theme.keywords:
            query = str(keyword or "").strip()
            if not query:
                continue
            try:
                response = self._search_query(
                    query=query,
                    max_results=max_results_per_keyword,
                    days=days,
                    log_context=log_context,
                )
            except Exception as exc:
                logger.warning("主题扫描失败: theme=%s keyword=%s err=%s", theme.id, query, exc)
                continue

            if not response.success:
                continue

            for item in response.results:
                self._merge_result(
                    dedup=dedup,
                    item=item,
                    provider=response.provider,
                    keyword=query,
                    max_news_items=theme.event_rules.max_news_items,
                )

        news_items = list(dedup.values())[: theme.event_rules.max_news_items]
        matched_keywords = sorted(
            {
                keyword
                for item in news_items
                for keyword in item.matched_keywords
            }
        )
        matched_news_count = len(news_items)
        keyword_hit_count = len(matched_keywords)
        triggered = (
            matched_news_count >= theme.event_rules.min_news_count
            and keyword_hit_count >= theme.event_rules.min_keyword_hits
        )
        event_score = min(
            100,
            keyword_hit_count * 20 + matched_news_count * 10,
        )

        if triggered:
            trigger_reason = (
                f"命中关键词 {keyword_hit_count} 个，相关新闻 {matched_news_count} 条"
            )
        else:
            trigger_reason = (
                f"未达到触发阈值：关键词 {keyword_hit_count}/{theme.event_rules.min_keyword_hits}，"
                f"新闻 {matched_news_count}/{theme.event_rules.min_news_count}"
            )

        return ThemeEventSchema(
            theme_id=theme.id,
            theme_name=theme.name,
            event_score=event_score,
            triggered=triggered,
            trigger_reason=trigger_reason,
            matched_keywords=matched_keywords,
            matched_news_count=matched_news_count,
            news_items=news_items,
        )

    def _search_query(
        self,
        *,
        query: str,
        max_results: int,
        days: int,
        log_context: Optional[Dict[str, Any]] = None,
    ):
        """Run a generic keyword search through SearchService providers."""
        last_response = None
        providers = getattr(self.search_service, "_providers", []) or []
        attempts = []
        context = dict(log_context or {})
        for provider in providers:
            if not provider.is_available:
                continue
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            try:
                response = provider.search(query, max_results=max_results, days=days)
            except Exception as exc:
                attempts.append(
                    {
                        "provider": provider_name,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                continue
            last_response = response
            attempts.append(
                {
                    "provider": provider_name,
                    "status": "success" if response.success and response.results else ("empty" if response.success else "failed"),
                    "result_count": len(response.results or []),
                    "response_provider": response.provider,
                    "error": response.error_message,
                }
            )
            if response.success and response.results:
                if len(attempts) > 1:
                    _emit_theme_news_fallback_log(
                        {
                            "event": "theme_news_provider_fallback",
                            "stage": "theme_news",
                            "query": query,
                            "days": days,
                            "max_results": max_results,
                            "fallback_used": True,
                            "selected_provider": response.provider,
                            "attempts": attempts,
                            **context,
                        }
                    )
                return response
        fallback_response = self.search_service.search_stock_price_fallback(
            stock_code=query,
            stock_name=query,
            max_attempts=1,
            max_results=max_results,
        )
        _emit_theme_news_fallback_log(
            {
                "event": "theme_news_provider_fallback",
                "stage": "theme_news",
                "query": query,
                "days": days,
                "max_results": max_results,
                "fallback_used": True,
                "selected_provider": getattr(fallback_response, "provider", None) if fallback_response else None,
                "attempts": attempts,
                "fallback_response_success": bool(fallback_response and fallback_response.success),
                "fallback_result_count": len(getattr(fallback_response, "results", []) or []) if fallback_response else 0,
                **context,
            },
            level="warning",
        )
        return last_response or fallback_response

    @staticmethod
    def _merge_result(
        *,
        dedup: dict[str, ThemeNewsItemSchema],
        item: SearchResult,
        provider: str,
        keyword: str,
        max_news_items: int,
    ) -> None:
        if len(dedup) >= max_news_items:
            return

        key = (item.url or item.title or "").strip()
        if not key:
            return

        existing = dedup.get(key)
        if existing is None:
            dedup[key] = ThemeNewsItemSchema(
                title=item.title,
                snippet=item.snippet,
                url=item.url,
                source=item.source,
                published_date=item.published_date,
                provider=provider,
                matched_keywords=[keyword],
            )
            return

        if keyword not in existing.matched_keywords:
            existing.matched_keywords.append(keyword)
