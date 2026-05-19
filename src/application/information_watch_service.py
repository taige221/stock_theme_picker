# -*- coding: utf-8 -*-
"""
===================================
Information Watch Pool Service
===================================
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from theme_picker.application.information_l1_direct_service import InformationL1DirectService
from theme_picker.config import get_config
from theme_picker.infrastructure.persistence import (
    delete_information_watch_item,
    get_theme_picker_db,
    get_latest_information_event_by_duplicate_key,
    list_information_events,
    list_information_watch_items,
    save_information_event,
    upsert_information_watch_item,
)
from theme_picker.search_service import SearchResponse, SearchService, get_search_service

logger = logging.getLogger(__name__)


DEFAULT_INFORMATION_WATCH_ITEMS: List[Dict[str, Any]] = [
    {
        "item_id": "watch_cxmt_procurement",
        "name": "长鑫采购",
        "enabled": True,
        "priority": 10,
        "event_type": "order",
        "seed_terms": ["长鑫存储", "采购", "订单", "57亿"],
        "aliases": ["长鑫", "CXMT"],
        "themes": ["存储", "芯片"],
        "chain_tags": ["dram", "封测", "材料", "设备"],
        "source_tiers": ["L1", "L2"],
        "freshness_days": 3,
        "notes": "存储链核心订单观察项",
    },
    {
        "item_id": "watch_storage_price_hike",
        "name": "存储涨价",
        "enabled": True,
        "priority": 20,
        "event_type": "price_signal",
        "seed_terms": ["存储", "涨价", "提价", "dram", "nand"],
        "aliases": ["DRAM涨价", "NAND涨价"],
        "themes": ["存储", "芯片"],
        "chain_tags": ["dram", "nand", "模组", "控制器"],
        "source_tiers": ["L2", "L3"],
        "freshness_days": 2,
        "notes": "存储价格驱动",
    },
    {
        "item_id": "watch_packaging_expand",
        "name": "封测扩产",
        "enabled": True,
        "priority": 30,
        "event_type": "capacity_expand",
        "seed_terms": ["封测", "扩产", "投产", "产能"],
        "aliases": ["先进封装扩产"],
        "themes": ["芯片", "先进封装"],
        "chain_tags": ["封测", "先进封装", "设备", "材料"],
        "source_tiers": ["L1", "L2"],
        "freshness_days": 3,
    },
    {
        "item_id": "watch_h200_release",
        "name": "H200放行",
        "enabled": True,
        "priority": 40,
        "event_type": "policy_catalyst",
        "seed_terms": ["H200", "放行", "审批", "出口", "限制"],
        "aliases": ["英伟达H200", "H200出口"],
        "themes": ["算力", "CPO", "液冷", "央企算力"],
        "chain_tags": ["gpu", "液冷", "cpo", "服务器"],
        "source_tiers": ["L2", "L3"],
        "freshness_days": 2,
    },
    {
        "item_id": "watch_optimus_mass_production",
        "name": "Optimus量产",
        "enabled": True,
        "priority": 50,
        "event_type": "mass_production",
        "seed_terms": ["Optimus", "量产", "机器人", "特斯拉机器人"],
        "aliases": ["人形机器人量产"],
        "themes": ["机器人"],
        "chain_tags": ["丝杠", "减速器", "传感器", "执行器"],
        "source_tiers": ["L2", "L3"],
        "freshness_days": 3,
    },
]
SYSTEM_INFORMATION_WATCH_ITEM_IDS = {str(item.get("item_id") or "").strip() for item in DEFAULT_INFORMATION_WATCH_ITEMS}

_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)
_CHINESE_OR_WORD_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
_NOISY_HOST_MARKERS = (
    "instagram.com",
    "threads.net",
    "x.com",
    "twitter.com",
    "facebook.com",
    "tiktok.com",
    "douyin.com",
    "youtube.com",
)
_SOCIAL_HOST_MARKERS = _NOISY_HOST_MARKERS + (
    "reddit.com",
    "weibo.com",
    "xiaohongshu.com",
    "medium.com",
    "substack.com",
)
_OFFICIAL_HOST_MARKERS = (
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "gov.cn",
    "miit.gov.cn",
    "ndrc.gov.cn",
    "mof.gov.cn",
)
_MAINSTREAM_MEDIA_HOST_MARKERS = (
    "cls.cn",
    "stcn.com",
    "eastmoney.com",
    "10jqka.com.cn",
    "jrj.com.cn",
    "caixin.com",
    "yicai.com",
    "cnstock.com",
    "wallstreetcn.com",
    "sina.com.cn",
    "163.com",
    "ifeng.com",
)
_DATE_FRAGMENT_PATTERNS = (
    re.compile(r"\d{4}\s*[年/\-.]\s*\d{1,2}\s*[月/\-.]\s*\d{1,2}\s*日?"),
    re.compile(r"\d+\s*(?:分钟|小时|天|周|个月|月|年)\s*前"),
    re.compile(
        r"\d+\s*(?:minute|minutes|min|mins|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:today|yesterday|just now|now)\b", re.IGNORECASE),
    re.compile(r"(?:今天|今日|昨天|前天|刚刚)"),
)
_CLUSTER_STOPWORDS = {
    "事件", "新闻", "产业链", "公司", "上市公司", "观察", "主题", "订单", "采购", "扩产",
    "投产", "产能", "量产", "放行", "政策", "涨价", "价格", "风险", "公告",
}


class InformationWatchService:
    def __init__(
        self,
        *,
        search_service: Optional[SearchService] = None,
        direct_service: Optional[InformationL1DirectService] = None,
    ) -> None:
        self.db = get_theme_picker_db()
        self.search_service = search_service or get_search_service()
        self.direct_service = direct_service or InformationL1DirectService()
        self.config = get_config()

    def bootstrap_defaults(self) -> List[Any]:
        created = []
        existing_ids = {record.item_id for record in list_information_watch_items(self.db)}
        for item in DEFAULT_INFORMATION_WATCH_ITEMS:
            if item["item_id"] in existing_ids:
                continue
            created.append(upsert_information_watch_item(self.db, **item))
        return created

    def list_items(self, *, enabled_only: bool = False) -> List[Any]:
        self.bootstrap_defaults()
        return list_information_watch_items(self.db, enabled_only=enabled_only)

    def upsert_item(self, payload: Dict[str, Any]) -> Any:
        normalized = dict(payload)
        normalized["item_id"] = str(normalized.get("item_id") or uuid.uuid4().hex)
        normalized["seed_terms"] = self._normalize_list(normalized.get("seed_terms"))
        normalized["aliases"] = self._normalize_list(normalized.get("aliases"))
        normalized["themes"] = self._normalize_list(normalized.get("themes"))
        normalized["chain_tags"] = self._normalize_list(normalized.get("chain_tags"))
        normalized["source_tiers"] = self._normalize_list(normalized.get("source_tiers")) or ["L1", "L2"]
        return upsert_information_watch_item(self.db, **normalized)

    def delete_item(self, item_id: str) -> bool:
        normalized = str(item_id or "").strip()
        if not normalized:
            return False
        if self.is_system_item(normalized):
            raise ValueError("系统内置观察项不支持删除")
        return bool(delete_information_watch_item(self.db, normalized))

    @staticmethod
    def is_system_item(item_id: str) -> bool:
        return str(item_id or "").strip() in SYSTEM_INFORMATION_WATCH_ITEM_IDS

    def run_once(
        self,
        *,
        limit: int = 20,
        item_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        items = self.list_items(enabled_only=True)
        selected_ids = {str(item_id).strip() for item_id in (item_ids or []) if str(item_id).strip()}
        if selected_ids:
            items = [item for item in items if item.item_id in selected_ids]
        items = items[: max(1, int(limit))]

        created_event_map: Dict[str, Any] = {}
        promoted_event_ids = set()

        for item in items:
            for event_payload in self._scan_item(item):
                newly_promoted = bool(event_payload.pop("_newly_promoted", False))
                record = save_information_event(self.db, **event_payload)
                event_id = str(getattr(record, "event_id", "") or "")
                if event_id:
                    created_event_map[event_id] = record
                    if newly_promoted:
                        promoted_event_ids.add(event_id)

        latest_items = list_information_events(self.db, limit=max(1, min(len(created_event_map) or limit, 50)))
        return {
            "scanned_items": len(items),
            "created_events": len(created_event_map),
            "promoted_events": len(promoted_event_ids),
            "promoted_event_ids": list(promoted_event_ids),
            "items": latest_items,
        }

    def _scan_item(self, item: Any) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for query_plan in self._build_query_plan(item):
            response = self._search_query(
                query=str(query_plan.get("query") or "").strip(),
                days=int(query_plan.get("days") or getattr(item, "freshness_days", 3) or 3),
                strict_freshness=bool(query_plan.get("strict_freshness", True)),
                query_group=str(query_plan.get("name") or ""),
            )
            if not response.success or not response.results:
                continue
            for result in response.results:
                source_tier = self._infer_source_tier(result, query_plan)
                if not self._source_tier_allowed(item, source_tier):
                    continue
                if not self._is_result_relevant(item, query_plan, result):
                    continue
                event_payload = self._build_event_payload(
                    item=item,
                    query_plan=query_plan,
                    response=response,
                    result=result,
                )
                if event_payload is not None:
                    events.append(event_payload)
        return events

    def _search_query(self, *, query: str, days: int, strict_freshness: bool, query_group: str = "") -> SearchResponse:
        direct_enabled = bool(
            query
            and query_group == "hard_source_check"
            and bool(getattr(self.config, "information_l1_direct_enabled", True))
        )
        if direct_enabled:
            direct_response = self.direct_service.search(query=query, days=days, max_results=3)
            if direct_response.success and direct_response.results:
                return direct_response

        if not query or not self.search_service.is_available:
            return SearchResponse(query=query, results=[], provider="None", success=False, error_message="search unavailable")

        providers = [
            provider
            for provider in getattr(self.search_service, "_providers", []) or []
            if getattr(provider, "is_available", False)
        ]
        for provider in providers:
            response = provider.search(query, max_results=3, days=days)
            normalized = response
            if strict_freshness:
                filtered = self.search_service._filter_news_response(
                    response,
                    search_days=days,
                    max_results=3,
                    log_scope=f"information_watch:{query}",
                )
                if filtered.success and filtered.results:
                    return filtered
                if response.success and response.results:
                    normalized = self.search_service._normalize_and_limit_response(
                        response,
                        max_results=3,
                    )
            elif response.success:
                normalized = self.search_service._limit_search_response(response, max_results=3)

            if normalized.success and normalized.results:
                return normalized
        return SearchResponse(query=query, results=[], provider="None", success=False, error_message="all providers failed")

    def _build_query_plan(self, item: Any) -> List[Dict[str, Any]]:
        seed_terms = self._deserialize_json_list(getattr(item, "seed_terms_json", None))
        aliases = self._deserialize_json_list(getattr(item, "aliases_json", None))
        themes = self._deserialize_json_list(getattr(item, "themes_json", None))
        chain_tags = self._deserialize_json_list(getattr(item, "chain_tags_json", None))
        event_type = str(getattr(item, "event_type", "") or "")
        core = " ".join(seed_terms[:2]).strip() or str(item.name)
        alias = aliases[0] if aliases else ""
        theme_hint = " ".join(themes[:2]).strip()
        chain_hint = " ".join(chain_tags[:2]).strip()
        freshness_days = max(1, int(getattr(item, "freshness_days", 3) or 3))
        query_base = f"{core} {alias}".strip()
        event_suffix = {
            "order": "订单 采购 中标 供货",
            "capacity_expand": "扩产 投产 产能 开工",
            "mass_production": "量产 交付 验证 导入",
            "price_signal": "涨价 提价 报价",
            "policy_catalyst": "政策 放行 审批 许可",
            "technology_progress": "验证 送样 技术突破 导入",
            "capital_expenditure": "定增 募投 建设 投资",
            "risk_signal": "减持 解禁 问询 处罚 风险",
            "opinion_only": "研报 点评 解读",
        }.get(event_type, "新闻 事件")
        reaction_suffix = {
            "order": "受益股 供应商 产业链 龙头",
            "capacity_expand": "受益股 设备 材料 封测 产业链",
            "mass_production": "受益股 产业链 核心部件 龙头",
            "price_signal": "受益股 价格弹性 龙头",
            "policy_catalyst": "受益股 龙头 产业链",
            "technology_progress": "受益股 产业链 龙头",
            "capital_expenditure": "受益股 龙头 产业链",
            "risk_signal": "影响 利空 风险",
            "opinion_only": "受益方向 产业链",
        }.get(event_type, "受益股 龙头 产业链")
        return [
            {
                "name": "event_news",
                "query": " ".join(part for part in (query_base, theme_hint, event_suffix) if part).strip(),
                "strict_freshness": True,
                "days": freshness_days,
            },
            {
                "name": "market_reaction",
                "query": " ".join(part for part in (query_base, chain_hint, reaction_suffix) if part).strip(),
                "strict_freshness": False,
                "days": max(freshness_days, 3),
            },
            {
                "name": "risk_check",
                "query": f"{query_base} 澄清 延期 取消 风险 利空".strip(),
                "strict_freshness": True,
                "days": freshness_days,
            },
            {
                "name": "hard_source_check",
                "query": f"{query_base} cninfo 公告 上交所 深交所".strip(),
                "strict_freshness": True,
                "days": min(freshness_days, 3),
            },
        ]

    def _build_event_payload(
        self,
        *,
        item: Any,
        query_plan: Dict[str, Any],
        response: SearchResponse,
        result: Any,
    ) -> Optional[Dict[str, Any]]:
        title = str(getattr(result, "title", "") or "").strip()
        snippet = str(getattr(result, "snippet", "") or "").strip()
        if not title:
            return None

        source_tier = self._infer_source_tier(result, query_plan)
        published_at = self._parse_published_at(result)
        freshness_score = self._score_freshness(
            published_at,
            freshness_days=max(1, int(getattr(item, "freshness_days", 3) or 3)),
        )
        credibility_score = self._score_credibility(
            source_tier,
            provider=response.provider,
            result=result,
            published_at=published_at,
        )
        signal_strength = self._score_signal_strength(
            freshness_score=freshness_score,
            credibility_score=credibility_score,
            event_type=str(getattr(item, "event_type", "") or ""),
            query_group=str(query_plan.get("name") or ""),
        )
        status = self._derive_status(
            event_type=str(getattr(item, "event_type", "") or ""),
            freshness_score=freshness_score,
            credibility_score=credibility_score,
        )
        duplicate_key = self._build_duplicate_key(item_name=str(getattr(item, "name", "") or ""), title=title, published_at=published_at)
        previous = get_latest_information_event_by_duplicate_key(self.db, duplicate_key)
        is_new_event = previous is None

        themes = self._deserialize_json_list(getattr(item, "themes_json", None))
        chain_tags = self._deserialize_json_list(getattr(item, "chain_tags_json", None))
        entities = self._extract_entities(title, snippet)
        cluster_key = self._derive_cluster_key(
            event_type=str(getattr(item, "event_type", "") or ""),
            themes=themes,
            chain_tags=chain_tags,
            title=title,
        )
        cluster_label = self._derive_cluster_label(
            event_type=str(getattr(item, "event_type", "") or ""),
            themes=themes,
            chain_tags=chain_tags,
            title=title,
        )
        if previous is not None:
            first_seen_at = previous.first_seen_at or datetime.now()
            status = "repeated" if status != "promoted" else status
        else:
            first_seen_at = datetime.now()
        newly_promoted = status == "promoted" and str(getattr(previous, "status", "") or "") != "promoted"

        return {
            "_newly_promoted": newly_promoted,
            "event_id": str(previous.event_id) if previous is not None else uuid.uuid4().hex,
            "watch_item_id": getattr(item, "item_id", None),
            "title": title,
            "summary": snippet[:280] if snippet else None,
            "event_type": str(getattr(item, "event_type", "") or ""),
            "impact_direction": self._impact_direction(str(getattr(item, "event_type", "") or "")),
            "source_mode": "watch",
            "source_tier": source_tier,
            "provider": response.provider,
            "url": getattr(result, "url", None),
            "published_at": published_at,
            "first_seen_at": first_seen_at,
            "last_seen_at": datetime.now(),
            "is_new_event": is_new_event,
            "duplicate_key": duplicate_key,
            "themes": themes,
            "chain_tags": chain_tags,
            "entities": entities,
            "metadata": {
                "query_group": query_plan.get("name"),
                "query": query_plan.get("query"),
                "source_mode": "watch",
                "watch_name": getattr(item, "name", None),
                "source": getattr(result, "source", None),
                "source_host": self._extract_host(getattr(result, "url", None)),
                "raw_published_date": getattr(result, "published_date", None),
                "cluster_key": cluster_key,
                "cluster_label": cluster_label,
                "hard_source_confirmed": bool(source_tier == "L1" or str(query_plan.get("name") or "") == "hard_source_check"),
            },
            "freshness_score": freshness_score,
            "credibility_score": credibility_score,
            "signal_strength": signal_strength,
            "status": status,
        }

    @staticmethod
    def _normalize_list(values: Optional[Iterable[Any]]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for value in values or []:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    def _deserialize_json_list(self, value: Any) -> List[str]:
        if not value:
            return []
        parsed = self.db._safe_json_loads(value) if isinstance(value, str) else value
        return self._normalize_list(parsed if isinstance(parsed, list) else [])

    def _source_tier_allowed(self, item: Any, source_tier: str) -> bool:
        allowed = self._deserialize_json_list(getattr(item, "source_tiers_json", None))
        if not allowed:
            return True
        return source_tier in allowed

    def _is_result_relevant(self, item: Any, query_plan: Dict[str, Any], result: Any) -> bool:
        url = str(getattr(result, "url", "") or "").lower()
        source = str(getattr(result, "source", "") or "").lower()
        if any(marker in url for marker in _NOISY_HOST_MARKERS) or any(marker in source for marker in _NOISY_HOST_MARKERS):
            return False

        text = f"{getattr(result, 'title', '')} {getattr(result, 'snippet', '')}".lower()
        if not text.strip():
            return False

        seed_terms = self._deserialize_json_list(getattr(item, "seed_terms_json", None))
        aliases = self._deserialize_json_list(getattr(item, "aliases_json", None))
        themes = self._deserialize_json_list(getattr(item, "themes_json", None))
        chain_tags = self._deserialize_json_list(getattr(item, "chain_tags_json", None))

        term_hits = sum(1 for term in seed_terms[:4] if len(term.strip()) >= 2 and term.lower() in text)
        alias_hits = sum(1 for term in aliases[:3] if len(term.strip()) >= 2 and term.lower() in text)
        theme_hits = sum(1 for term in themes[:3] if len(term.strip()) >= 2 and term.lower() in text)
        chain_hits = sum(1 for term in chain_tags[:4] if len(term.strip()) >= 2 and term.lower() in text)

        query_group = str(query_plan.get("name") or "")
        if query_group == "market_reaction":
            return (term_hits + alias_hits) >= 1 and (theme_hits + chain_hits) >= 1
        if query_group == "risk_check":
            risk_hits = sum(1 for term in ("风险", "利空", "延期", "取消", "问询", "处罚", "减持") if term in text)
            return (term_hits + alias_hits) >= 1 and risk_hits >= 1
        return (term_hits + alias_hits) >= 1

    def _parse_published_at(self, result: Any) -> Optional[datetime]:
        candidates: List[str] = []
        raw_value = getattr(result, "published_date", None)
        if raw_value:
            candidates.append(str(raw_value).strip())

        for text in (
            getattr(result, "title", None),
            getattr(result, "snippet", None),
            getattr(result, "source", None),
        ):
            candidates.extend(self._extract_publish_date_candidates(text))

        seen = set()
        for candidate in candidates:
            value = str(candidate or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            parsed_dt = self._parse_datetime_candidate(value)
            if parsed_dt is not None:
                return parsed_dt
            parsed_date = self.search_service._normalize_news_publish_date(value)
            if parsed_date is not None:
                return datetime.combine(parsed_date, datetime.min.time())
        return None

    @staticmethod
    def _parse_datetime_candidate(value: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is not None:
                return parsed.astimezone().replace(tzinfo=None)
            return parsed
        except Exception:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    return parsed.astimezone().replace(tzinfo=None)
                return parsed
            except Exception:
                return None

    @classmethod
    def _extract_publish_date_candidates(cls, value: Any) -> List[str]:
        text = str(value or "").strip()
        if not text:
            return []
        candidates: List[str] = []
        for pattern in _DATE_FRAGMENT_PATTERNS:
            for match in pattern.findall(text):
                candidate = "".join(match) if isinstance(match, tuple) else str(match)
                if candidate:
                    candidates.append(candidate)
        return candidates

    @staticmethod
    def _build_duplicate_key(*, item_name: str, title: str, published_at: Optional[datetime]) -> str:
        normalized_title = _NON_WORD_RE.sub("", title.lower())[:48]
        date_part = published_at.date().isoformat() if published_at else "unknown"
        return f"{item_name.lower()}::{date_part}::{normalized_title}"

    @staticmethod
    def _extract_entities(title: str, snippet: str) -> Dict[str, Any]:
        text = f"{title} {snippet}".strip()
        tokens = []
        seen = set()
        for match in _CHINESE_OR_WORD_RE.findall(text):
            token = match.strip()
            if len(token) <= 1 or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= 12:
                break
        return {"tokens": tokens}

    @staticmethod
    def _infer_source_tier(result: Any, query_plan: Dict[str, Any]) -> str:
        url = str(getattr(result, "url", "") or "").lower()
        source = str(getattr(result, "source", "") or "").lower()
        text = f"{getattr(result, 'title', '')} {getattr(result, 'snippet', '')}".lower()
        if any(marker in url for marker in _OFFICIAL_HOST_MARKERS):
            return "L1"
        if any(marker in text for marker in ("公告", "问询", "回购", "定增")) and query_plan.get("name") != "market_reaction":
            return "L1"
        if any(marker in url for marker in _SOCIAL_HOST_MARKERS) or any(marker in source for marker in _SOCIAL_HOST_MARKERS):
            return "L3"
        if any(marker in text for marker in ("研报", "点评", "观点", "解读", "ins", "instagram")):
            return "L3"
        if query_plan.get("name") == "market_reaction":
            return "L3"
        if any(marker in url for marker in _MAINSTREAM_MEDIA_HOST_MARKERS) or any(marker in source for marker in ("eastmoney", "cls", "stcn", "10jqka", "jrj", "caixin", "yicai", "cnstock", "wallstreetcn")):
            return "L2"
        return "L3"

    @staticmethod
    def _score_freshness(published_at: Optional[datetime], *, freshness_days: int) -> float:
        if published_at is None:
            return 35.0
        age = max(0.0, (datetime.now() - published_at).total_seconds() / 86400.0)
        if age <= 1:
            return 100.0
        if age <= 2:
            return 85.0
        if age <= freshness_days:
            return 72.0
        if age <= freshness_days + 2:
            return 55.0
        return 30.0

    @staticmethod
    def _extract_host(url: Any) -> str:
        text = str(url or "").strip().lower()
        if not text:
            return ""
        match = re.search(r"^(?:https?://)?(?:www\.)?([^/]+)", text)
        return match.group(1) if match else text

    @classmethod
    def _score_credibility(
        cls,
        source_tier: str,
        *,
        provider: str,
        result: Any,
        published_at: Optional[datetime],
    ) -> float:
        base = {"L1": 92.0, "L2": 68.0, "L3": 42.0}.get(source_tier, 42.0)
        provider_bonus = {"CNInfoDirect": 4.0, "Tavily": 2.0, "SerpAPI": 1.0}.get(str(provider or ""), 0.0)
        source = str(getattr(result, "source", "") or "").lower()
        url = str(getattr(result, "url", "") or "").lower()
        text = f"{source} {url}".lower()
        domain_bonus = 0.0
        if any(marker in text for marker in _OFFICIAL_HOST_MARKERS):
            domain_bonus += 6.0
        elif any(marker in text for marker in _MAINSTREAM_MEDIA_HOST_MARKERS):
            domain_bonus += 3.0
        elif any(marker in text for marker in _SOCIAL_HOST_MARKERS):
            domain_bonus -= 18.0
        if published_at is None:
            domain_bonus -= 8.0
        return max(0.0, min(100.0, base + provider_bonus + domain_bonus))

    @staticmethod
    def _score_signal_strength(
        *,
        freshness_score: float,
        credibility_score: float,
        event_type: str,
        query_group: str,
    ) -> float:
        event_bonus = {
            "order": 8.0,
            "capacity_expand": 8.0,
            "mass_production": 7.0,
            "price_signal": 6.0,
            "policy_catalyst": 7.0,
            "technology_progress": 6.0,
            "capital_expenditure": 5.0,
            "risk_signal": -8.0,
            "opinion_only": -12.0,
        }.get(event_type, 0.0)
        query_bonus = {"event_news": 3.0, "market_reaction": -2.0, "risk_check": 0.0, "hard_source_check": 4.0}.get(query_group, 0.0)
        return max(0.0, min(100.0, freshness_score * 0.45 + credibility_score * 0.45 + event_bonus + query_bonus))

    def _derive_status(self, *, event_type: str, freshness_score: float, credibility_score: float) -> str:
        if event_type in {"risk_signal", "opinion_only"}:
            return "new"
        if (
            freshness_score >= float(getattr(self.config, "information_event_min_freshness_score", 70.0) or 70.0)
            and credibility_score >= float(getattr(self.config, "information_event_min_credibility_score", 65.0) or 65.0)
        ):
            return "promoted"
        return "new"

    @staticmethod
    def _impact_direction(event_type: str) -> str:
        mapping = {
            "order": "demand_pull",
            "capacity_expand": "capacity_expand",
            "mass_production": "technology_progress",
            "price_signal": "price_signal",
            "policy_catalyst": "policy_catalyst",
            "technology_progress": "technology_progress",
            "capital_expenditure": "capacity_expand",
            "risk_signal": "risk_signal",
            "opinion_only": "technology_progress",
        }
        return mapping.get(event_type, "demand_pull")

    @classmethod
    def _derive_cluster_key(cls, *, event_type: str, themes: List[str], chain_tags: List[str], title: str) -> str:
        theme_part = "-".join(sorted(cls._normalize_list(themes))[:2]) or "unthemed"
        chain_part = "-".join(sorted(cls._normalize_list(chain_tags))[:2]) or "nochains"
        token_part = "-".join(cls._extract_cluster_tokens(title)[:3]) or "generic"
        return f"{str(event_type or 'event').lower()}::{theme_part.lower()}::{chain_part.lower()}::{token_part.lower()}"

    @classmethod
    def _derive_cluster_label(cls, *, event_type: str, themes: List[str], chain_tags: List[str], title: str) -> str:
        if themes:
            base = "/".join(cls._normalize_list(themes)[:2])
            if chain_tags:
                return f"{base} · {'/'.join(cls._normalize_list(chain_tags)[:2])}"[:40]
            return f"{base} · {event_type}"[:40]
        compact_title = " ".join(str(title or "").split()).strip()
        return compact_title[:40] if compact_title else str(event_type or "事件")

    @classmethod
    def _extract_cluster_tokens(cls, title: str) -> List[str]:
        tokens: List[str] = []
        seen = set()
        for token in _CHINESE_OR_WORD_RE.findall(str(title or "")):
            normalized = str(token or "").strip()
            if len(normalized) <= 1 or normalized.lower() in _CLUSTER_STOPWORDS or normalized in seen:
                continue
            seen.add(normalized)
            tokens.append(normalized)
        return tokens
