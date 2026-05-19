# -*- coding: utf-8 -*-
"""
===================================
Information L1 Direct Service
===================================
"""

from __future__ import annotations

import html
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from theme_picker.config import get_config
from theme_picker.data.stock_index_loader import get_stock_name_index_map
from theme_picker.data.stock_mapping import STOCK_NAME_MAP
from theme_picker.data_provider.base import _disable_proxy_env_for_attempt, _restore_proxy_env_after_attempt
from theme_picker.search_service import SearchResponse, SearchResult

logger = logging.getLogger(__name__)

_CNINFO_STOCK_INDEX_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
_CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_CNINFO_DETAIL_URL = "http://www.cninfo.com.cn/new/disclosure/detail"
_CNINFO_PDF_BASE_URL = "http://static.cninfo.com.cn/"
_CNINFO_MARKET = "沪深京"
_CNINFO_COLUMN = "szse"
_QUERY_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,}")
_CODE_RE = re.compile(r"\b(\d{6})\b")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DIRECT_QUERY_STOPWORDS = {
    "cninfo",
    "CNINFO",
    "公告",
    "上交所",
    "深交所",
    "北交所",
    "沪深京",
    "A股",
    "a股",
    "上市公司",
    "全局",
    "发现",
    "观察",
    "主题",
    "产业链",
    "受益股",
    "龙头",
    "公司",
    "新闻",
    "事件",
    "搜索",
    "模板",
}
_NAME_BLACKLIST = {
    "上市公司",
    "受益股",
    "龙头",
    "产业链",
    "观察池",
    "主题待发现",
    "公告",
}


@dataclass(frozen=True)
class _ResolvedStock:
    code: str
    name: str
    org_id: Optional[str] = None


class InformationL1DirectService:
    def __init__(self) -> None:
        self.config = get_config()
        self._session = requests.Session()
        self._org_map_lock = threading.RLock()
        self._name_map_lock = threading.RLock()
        self._stock_org_map: Optional[Dict[str, str]] = None
        self._stock_name_map: Optional[Dict[str, str]] = None

    def search(self, *, query: str, days: int, max_results: int = 3) -> SearchResponse:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return SearchResponse(
                query=normalized_query,
                results=[],
                provider="CNInfoDirect",
                success=False,
                error_message="empty query",
            )

        keyword = self._build_keyword(normalized_query)
        if not keyword:
            return SearchResponse(
                query=normalized_query,
                results=[],
                provider="CNInfoDirect",
                success=False,
                error_message="no effective keyword",
            )

        resolved_stock = self._resolve_stock(normalized_query)
        started_at = datetime.now()
        try:
            announcements = self._query_announcements(
                resolved_stock=resolved_stock,
                keyword=keyword,
                days=max(1, int(days)),
                page_size=max(3, int(max_results) * 2),
            )
        except Exception as exc:
            logger.warning("CNInfoDirect 查询失败: query=%s error=%s", normalized_query, exc)
            return SearchResponse(
                query=normalized_query,
                results=[],
                provider="CNInfoDirect",
                success=False,
                error_message=str(exc) or type(exc).__name__,
                search_time=max(0.0, (datetime.now() - started_at).total_seconds()),
            )

        results = self._normalize_results(announcements, max_results=max_results)
        return SearchResponse(
            query=normalized_query,
            results=results,
            provider="CNInfoDirect",
            success=bool(results),
            error_message=None if results else "no direct announcement matched",
            search_time=max(0.0, (datetime.now() - started_at).total_seconds()),
        )

    def _query_announcements(
        self,
        *,
        resolved_stock: Optional[_ResolvedStock],
        keyword: str,
        days: int,
        page_size: int,
    ) -> List[Dict[str, Any]]:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=max(1, int(days)))
        payload = {
            "pageNum": "1",
            "pageSize": str(max(3, min(page_size, 30))),
            "column": _CNINFO_COLUMN,
            "tabName": "fulltext",
            "plate": "",
            "stock": self._build_stock_param(resolved_stock),
            "searchkey": keyword,
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start_date.isoformat()}~{end_date.isoformat()}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }

        snapshot = _disable_proxy_env_for_attempt()
        try:
            response = self._session.post(
                _CNINFO_QUERY_URL,
                data=payload,
                timeout=float(getattr(self.config, "information_l1_direct_timeout_seconds", 10.0) or 10.0),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
                },
            )
            response.raise_for_status()
            payload_json = response.json()
        finally:
            _restore_proxy_env_after_attempt(snapshot)

        announcements = payload_json.get("announcements") or []
        if not isinstance(announcements, list):
            return []
        return announcements

    def _build_stock_param(self, resolved_stock: Optional[_ResolvedStock]) -> str:
        if resolved_stock is None:
            return ""
        org_id = resolved_stock.org_id or self._get_stock_org_map().get(resolved_stock.code)
        if not org_id:
            return ""
        return f"{resolved_stock.code},{org_id}"

    def _normalize_results(self, announcements: List[Dict[str, Any]], *, max_results: int) -> List[SearchResult]:
        items: List[SearchResult] = []
        for raw in announcements[: max(1, int(max_results))]:
            title = self._clean_text(raw.get("announcementTitle") or raw.get("shortTitle") or "")
            if not title:
                continue
            sec_code = str(raw.get("secCode") or "").strip()
            sec_name = self._clean_text(raw.get("secName") or raw.get("tileSecName") or "")
            announcement_type = self._clean_text(raw.get("announcementTypeName") or "")
            published_at = self._normalize_published_at(raw.get("announcementTime"))
            detail_url = self._build_result_url(raw, sec_code=sec_code, published_at=published_at)
            snippet_parts = [part for part in (sec_name, announcement_type, "巨潮资讯公告") if part]
            items.append(
                SearchResult(
                    title=title,
                    snippet=" | ".join(snippet_parts),
                    url=detail_url,
                    source="巨潮资讯",
                    published_date=published_at,
                )
            )
        return items

    def _build_result_url(self, raw: Dict[str, Any], *, sec_code: str, published_at: Optional[str]) -> str:
        adjunct_url = str(raw.get("adjunctUrl") or "").strip()
        if adjunct_url:
            return f"{_CNINFO_PDF_BASE_URL}{adjunct_url.lstrip('/')}"
        announcement_id = str(raw.get("announcementId") or "").strip()
        org_id = str(raw.get("orgId") or "").strip()
        if announcement_id and org_id and sec_code:
            published_value = published_at or ""
            return (
                f"{_CNINFO_DETAIL_URL}?stockCode={sec_code}"
                f"&announcementId={announcement_id}&orgId={org_id}&announcementTime={published_value}"
            )
        return _CNINFO_DETAIL_URL

    @staticmethod
    def _normalize_published_at(raw_value: Any) -> Optional[str]:
        if raw_value in (None, ""):
            return None
        try:
            timestamp = float(raw_value) / 1000.0
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            text = str(raw_value).strip()
            return text or None

    def _resolve_stock(self, query: str) -> Optional[_ResolvedStock]:
        code_match = _CODE_RE.search(str(query or ""))
        if code_match:
            code = code_match.group(1)
            return _ResolvedStock(
                code=code,
                name=self._get_stock_name_map().get(code, code),
                org_id=self._get_stock_org_map().get(code),
            )

        query_text = str(query or "")
        for name, code in self._get_name_to_code_items():
            if name in _NAME_BLACKLIST:
                continue
            if name and name in query_text:
                return _ResolvedStock(
                    code=code,
                    name=name,
                    org_id=self._get_stock_org_map().get(code),
                )
        return None

    def _build_keyword(self, query: str) -> str:
        tokens: List[str] = []
        seen = set()
        for token in _QUERY_TOKEN_RE.findall(str(query or "")):
            cleaned = str(token or "").strip()
            if not cleaned or cleaned in seen or cleaned in _DIRECT_QUERY_STOPWORDS:
                continue
            if cleaned.isdigit() and len(cleaned) == 6:
                continue
            seen.add(cleaned)
            tokens.append(cleaned)
        return " ".join(tokens[:4]).strip()

    def _get_stock_org_map(self) -> Dict[str, str]:
        if self._stock_org_map is not None:
            return self._stock_org_map

        with self._org_map_lock:
            if self._stock_org_map is not None:
                return self._stock_org_map
            snapshot = _disable_proxy_env_for_attempt()
            try:
                response = self._session.get(
                    _CNINFO_STOCK_INDEX_URL,
                    timeout=float(getattr(self.config, "information_l1_direct_timeout_seconds", 10.0) or 10.0),
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        ),
                        "Referer": "http://www.cninfo.com.cn/",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                stock_list = payload.get("stockList") or []
                mapping: Dict[str, str] = {}
                for item in stock_list:
                    code = str(item.get("code") or "").strip()
                    org_id = str(item.get("orgId") or "").strip()
                    if code and org_id:
                        mapping[code] = org_id
                self._stock_org_map = mapping
            finally:
                _restore_proxy_env_after_attempt(snapshot)
            return self._stock_org_map or {}

    def _get_stock_name_map(self) -> Dict[str, str]:
        if self._stock_name_map is not None:
            return self._stock_name_map
        with self._name_map_lock:
            if self._stock_name_map is not None:
                return self._stock_name_map
            merged = dict(get_stock_name_index_map())
            merged.update({str(code): str(name) for code, name in STOCK_NAME_MAP.items() if str(code).isdigit() and len(str(code)) == 6})
            self._stock_name_map = merged
            return self._stock_name_map

    def _get_name_to_code_items(self) -> List[Tuple[str, str]]:
        pairs = [(name, code) for code, name in self._get_stock_name_map().items() if name and str(code).isdigit() and len(str(code)) == 6]
        pairs.sort(key=lambda item: len(item[0]), reverse=True)
        return pairs

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = _HTML_TAG_RE.sub("", text)
        return " ".join(text.split()).strip()
