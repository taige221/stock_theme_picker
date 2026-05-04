# -*- coding: utf-8 -*-
"""
===================================
Theme Event Scanner
===================================
"""

from __future__ import annotations

import logging
from typing import List, Optional

from theme_picker.domain.theme_event import (
    ThemeDefinitionSchema,
    ThemeEventSchema,
    ThemeNewsItemSchema,
)
from theme_picker.search_service import SearchResult, SearchService

logger = logging.getLogger(__name__)


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
    ):
        """Run a generic keyword search through SearchService providers."""
        last_response = None
        providers = getattr(self.search_service, "_providers", []) or []
        for provider in providers:
            if not provider.is_available:
                continue
            response = provider.search(query, max_results=max_results, days=days)
            last_response = response
            if response.success and response.results:
                return response
        return last_response or self.search_service.search_stock_price_fallback(
            stock_code=query,
            stock_name=query,
            max_attempts=1,
            max_results=max_results,
        )

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
