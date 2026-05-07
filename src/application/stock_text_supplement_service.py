# -*- coding: utf-8 -*-
"""
===================================
Single Stock Text Supplement Service
===================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from theme_picker.search_service import SearchResponse, SearchService


class StockTextSupplementService:
    """Fetch lightweight text supplements for stock earnings and institution context."""

    def __init__(self) -> None:
        self._search_service = SearchService()

    @property
    def is_available(self) -> bool:
        return self._search_service.is_available

    def get_earnings_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        queries = [
            f"{stock_name} {stock_code} 业绩预告 财报 快报 营收 净利润",
            f"{stock_name} 业绩预告 快报 公告",
        ]
        return self._search_queries(queries)

    def get_institution_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        queries = [
            f"{stock_name} 研报 评级 目标价 机构 调研",
            f"{stock_name} 券商 评级 机构观点 调研纪要",
        ]
        return self._search_queries(queries)

    def get_stock_news_summary(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        queries = [
            f"{stock_name} {stock_code} 公告 异动 订单 调研 合同 回购 监管",
            f"{stock_name} 财报 快报 业绩预告 机构调研",
        ]
        response = self._search_queries(queries, max_items=5)
        if not response:
            return {}

        headlines = response.get("text_headlines") or []
        summary = str(response.get("text_summary") or "").strip()
        catalysts = self._extract_catalysts(headlines)
        risk_events = self._extract_risk_events(headlines)
        sentiment = self._derive_sentiment(" ".join([summary, *headlines]), risk_events=risk_events)

        return {
            "summary": summary,
            "provider": response.get("text_provider") or "search",
            "headlines": headlines[:3],
            "catalysts": catalysts[:3],
            "risk_events": risk_events[:3],
            "sentiment": sentiment,
        }

    def _search_queries(self, queries: List[str], *, max_items: int = 3) -> Dict[str, Any]:
        if not self.is_available:
            return {}

        aggregated: List[Dict[str, str]] = []
        seen_urls = set()
        provider: Optional[str] = None

        for query in queries:
            response = self._search_service.search(query, max_results=3, days=45)
            if not response.success or not response.results:
                continue
            if provider is None:
                provider = response.provider
            for item in response.results[:max(2, min(max_items, 3))]:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                aggregated.append(
                    {
                        "title": item.title,
                        "snippet": item.snippet,
                        "source": item.source,
                        "published_date": item.published_date or "",
                    }
                )
            if len(aggregated) >= max_items:
                break

        if not aggregated:
            return {}

        return {
            "text_summary": self._build_summary(aggregated),
            "text_provider": provider or "search",
            "text_headlines": [item["title"] for item in aggregated[:max_items] if item.get("title")],
        }

    @staticmethod
    def _build_summary(results: List[Dict[str, str]]) -> str:
        lines: List[str] = []
        for item in results[:2]:
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if snippet and snippet not in title:
                lines.append(f"{title}：{snippet[:80]}")
            elif title:
                lines.append(title)
        return "；".join(line for line in lines if line).strip()

    @staticmethod
    def _extract_catalysts(headlines: List[str]) -> List[str]:
        keywords = [
            "业绩预告",
            "快报",
            "公告",
            "订单",
            "中标",
            "调研",
            "回购",
            "增持",
            "减持",
            "监管",
            "异动",
            "合作",
            "合同",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _extract_risk_events(headlines: List[str]) -> List[str]:
        keywords = [
            "减持",
            "监管",
            "问询",
            "处罚",
            "风险",
            "亏损",
            "下滑",
            "冻结",
            "诉讼",
            "违规",
            "立案",
            "终止",
            "跌停",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _derive_sentiment(text: str, *, risk_events: Optional[List[str]] = None) -> str:
        normalized = str(text or "")
        if not normalized:
            return "neutral"

        risk_keywords = ("减持", "监管", "问询", "处罚", "风险", "下滑", "亏损")
        positive_keywords = ("订单", "中标", "回购", "增持", "预增", "扭亏", "合作", "突破")

        if risk_events:
            return "risk"
        if any(keyword in normalized for keyword in risk_keywords):
            return "risk"
        if any(keyword in normalized for keyword in positive_keywords):
            return "positive"
        return "mixed"
