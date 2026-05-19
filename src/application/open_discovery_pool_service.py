# -*- coding: utf-8 -*-
"""
===================================
Open Discovery Pool Service
===================================
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from theme_picker.application.information_watch_service import InformationWatchService
from theme_picker.config import get_config
from theme_picker.infrastructure.persistence import (
    get_information_event,
    get_information_watch_item,
    get_latest_information_event_by_duplicate_key,
    get_theme_picker_db,
    list_information_events,
    list_open_discovery_profiles,
    save_information_event,
    upsert_open_discovery_profile,
)
from theme_picker.search_service import SearchResponse, SearchService, get_search_service


DEFAULT_OPEN_DISCOVERY_PROFILES: List[Dict[str, Any]] = [
    {
        "profile_id": "discovery_large_order",
        "name": "大额订单/采购发现",
        "enabled": True,
        "priority": 10,
        "event_type": "order",
        "query_templates": [
            "A股 大额订单 中标 采购 供货 上市公司",
            "产业链 订单 采购 中标 受益股 龙头",
        ],
        "themes": ["主题待发现"],
        "chain_tags": ["订单", "采购", "供应商", "产业链"],
        "source_tiers": ["L1", "L2"],
        "freshness_days": 2,
        "notes": "扫描全局大额订单、采购、中标类事件，反推新的产业链受益方向。",
    },
    {
        "profile_id": "discovery_capacity_expand",
        "name": "扩产/投产发现",
        "enabled": True,
        "priority": 20,
        "event_type": "capacity_expand",
        "query_templates": [
            "A股 扩产 投产 产能 开工 上市公司",
            "产业链 扩产 投产 设备 材料 封测 受益股",
        ],
        "themes": ["主题待发现"],
        "chain_tags": ["扩产", "投产", "产能", "设备", "材料"],
        "source_tiers": ["L1", "L2"],
        "freshness_days": 3,
        "notes": "捕捉新的资本开支、扩产和投产信息。",
    },
    {
        "profile_id": "discovery_price_signal",
        "name": "涨价/供需变化发现",
        "enabled": True,
        "priority": 30,
        "event_type": "price_signal",
        "query_templates": [
            "A股 涨价 提价 报价 上调 行业",
            "供需 紧张 涨价 受益股 产业链 龙头",
        ],
        "themes": ["主题待发现"],
        "chain_tags": ["涨价", "供需", "报价", "景气"],
        "source_tiers": ["L2", "L3"],
        "freshness_days": 2,
        "notes": "从涨价和供需变化里发现新的景气方向。",
    },
    {
        "profile_id": "discovery_policy_release",
        "name": "政策/放行发现",
        "enabled": True,
        "priority": 40,
        "event_type": "policy_catalyst",
        "query_templates": [
            "A股 政策 放行 审批 许可 补贴 试点",
            "政策 放行 受益股 产业链 龙头 上市公司",
        ],
        "themes": ["主题待发现"],
        "chain_tags": ["政策", "放行", "审批", "补贴"],
        "source_tiers": ["L1", "L2"],
        "freshness_days": 2,
        "notes": "追踪新的政策催化和准入放行事件。",
    },
    {
        "profile_id": "discovery_mass_production",
        "name": "量产/验证发现",
        "enabled": True,
        "priority": 50,
        "event_type": "mass_production",
        "query_templates": [
            "A股 量产 交付 验证 送样 导入 上市公司",
            "量产 验证 受益股 产业链 核心部件 龙头",
        ],
        "themes": ["主题待发现"],
        "chain_tags": ["量产", "验证", "导入", "交付"],
        "source_tiers": ["L2", "L3"],
        "freshness_days": 3,
        "notes": "发掘刚开始兑现的新技术、新产品方向。",
    },
]

THEME_KEYWORD_MAP: Dict[str, List[str]] = {
    "存储": ["dram", "nand", "hbm", "存储", "长鑫", "cxmt"],
    "芯片": ["半导体", "芯片", "晶圆", "封测", "先进封装"],
    "先进封装": ["先进封装", "封测", "2.5d", "3d封装", "cowo", "coos"],
    "算力": ["gpu", "算力", "服务器", "英伟达", "nvidia", "h200", "h20", "h100"],
    "CPO": ["cpo", "光模块", "coherent", "800g", "1.6t", "硅光"],
    "液冷": ["液冷", "散热", "冷板", "浸没"],
    "机器人": ["机器人", "optimus", "人形", "执行器", "减速器", "丝杠"],
    "电力": ["电网", "特高压", "配电", "变压器", "电力设备"],
    "央企算力": ["央企算力", "东数西算", "智算中心", "国资云"],
}

CHAIN_KEYWORD_MAP: Dict[str, List[str]] = {
    "gpu": ["gpu", "h200", "h20", "英伟达", "nvidia"],
    "液冷": ["液冷", "冷板", "散热", "浸没"],
    "cpo": ["cpo", "光模块", "硅光", "800g", "1.6t"],
    "dram": ["dram", "hbm", "长鑫", "cxmt"],
    "nand": ["nand", "ssd", "闪存"],
    "封测": ["封测", "先进封装", "2.5d", "3d封装"],
    "设备": ["设备", "机台", "产线"],
    "材料": ["材料", "化学品", "抛光", "靶材"],
    "丝杠": ["丝杠", "滚珠丝杠"],
    "减速器": ["减速器", "谐波", "rv"],
}
_CLUSTER_STOPWORDS = {
    "a股", "上市公司", "事件", "新闻", "产业链", "受益股", "龙头", "公司", "全局", "发现", "模板",
    "订单", "采购", "中标", "扩产", "投产", "产能", "量产", "验证", "政策", "放行", "涨价",
}
_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,}")


class OpenDiscoveryPoolService:
    def __init__(
        self,
        *,
        search_service: Optional[SearchService] = None,
        watch_service: Optional[InformationWatchService] = None,
    ) -> None:
        self.db = get_theme_picker_db()
        self.search_service = search_service or get_search_service()
        self.watch_service = watch_service or InformationWatchService(search_service=self.search_service)
        self.config = get_config()

    def bootstrap_defaults(self) -> List[Any]:
        created = []
        existing_ids = {record.profile_id for record in list_open_discovery_profiles(self.db)}
        for profile in DEFAULT_OPEN_DISCOVERY_PROFILES:
            if profile["profile_id"] in existing_ids:
                continue
            created.append(upsert_open_discovery_profile(self.db, **profile))
        return created

    def list_profiles(self, *, enabled_only: bool = False) -> List[Any]:
        self.bootstrap_defaults()
        return list_open_discovery_profiles(self.db, enabled_only=enabled_only)

    def run_once(
        self,
        *,
        limit: int = 12,
        profile_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        profiles = self.list_profiles(enabled_only=True)
        selected_ids = {str(profile_id).strip() for profile_id in (profile_ids or []) if str(profile_id).strip()}
        if selected_ids:
            profiles = [profile for profile in profiles if profile.profile_id in selected_ids]
        profiles = profiles[: max(1, int(limit))]

        created_events: List[Any] = []
        promoted_events = 0

        for profile in profiles:
            for event_payload in self._dedupe_batch_event_payloads(self._scan_profile(profile)):
                record = save_information_event(self.db, **event_payload)
                created_events.append(record)
                if str(record.status or "") == "promoted":
                    promoted_events += 1

        latest_items = self.db.list_information_events(
            limit=max(1, min(len(created_events) or limit, 50)),
            source_mode="discovery",
        )
        return {
            "scanned_profiles": len(profiles),
            "created_events": len(created_events),
            "promoted_events": promoted_events,
            "items": latest_items,
        }

    def list_events(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
        promoted_only: bool = False,
    ) -> List[Any]:
        return list_information_events(
            self.db,
            limit=limit,
            status=status,
            promoted_only=promoted_only,
            source_mode="discovery",
        )

    def list_candidates(
        self,
        *,
        limit: int = 20,
        promoted_only: bool = True,
    ) -> List[Dict[str, Any]]:
        events = self.list_events(limit=max(80, limit * 8), promoted_only=promoted_only)
        clusters: Dict[str, Dict[str, Any]] = {}
        for event in events:
            metadata = self.db._safe_json_loads(getattr(event, "metadata_json", None)) or {}
            cluster_key = str(metadata.get("cluster_key") or "").strip() or self._derive_cluster_key(
                event_type=str(getattr(event, "event_type", "") or ""),
                themes=self.db._safe_json_loads(getattr(event, "themes_json", None)) or [],
                chain_tags=self.db._safe_json_loads(getattr(event, "chain_tags_json", None)) or [],
                title=str(getattr(event, "title", "") or ""),
            )
            if not cluster_key:
                continue
            cluster = clusters.setdefault(
                cluster_key,
                {
                    "cluster_key": cluster_key,
                    "label": str(metadata.get("cluster_label") or "").strip() or self._derive_cluster_label(
                        event_type=str(getattr(event, "event_type", "") or ""),
                        themes=self.db._safe_json_loads(getattr(event, "themes_json", None)) or [],
                        chain_tags=self.db._safe_json_loads(getattr(event, "chain_tags_json", None)) or [],
                        title=str(getattr(event, "title", "") or ""),
                    ),
                    "event_type": str(getattr(event, "event_type", "") or ""),
                    "themes": [],
                    "chain_tags": [],
                    "source_hosts": [],
                    "source_tiers": [],
                    "event_count": 0,
                    "promoted_count": 0,
                    "hard_source_confirmed": False,
                    "candidate_score": 0.0,
                    "representative_event_id": None,
                    "representative_title": None,
                    "latest_published_at": None,
                    "watch_item_id": None,
                    "watch_item_name": None,
                    "status": "candidate",
                    "_signal_sum": 0.0,
                    "_credibility_sum": 0.0,
                },
            )
            cluster["event_count"] += 1
            cluster["_signal_sum"] += float(getattr(event, "signal_strength", 0.0) or 0.0)
            cluster["_credibility_sum"] += float(getattr(event, "credibility_score", 0.0) or 0.0)
            if str(getattr(event, "status", "") or "") == "promoted":
                cluster["promoted_count"] += 1
            if str(getattr(event, "source_tier", "") or "") == "L1":
                cluster["hard_source_confirmed"] = True
            for value in self.db._safe_json_loads(getattr(event, "themes_json", None)) or []:
                if value not in cluster["themes"]:
                    cluster["themes"].append(value)
            for value in self.db._safe_json_loads(getattr(event, "chain_tags_json", None)) or []:
                if value not in cluster["chain_tags"]:
                    cluster["chain_tags"].append(value)
            source_host = str(metadata.get("source_host") or "").strip()
            if source_host and source_host not in cluster["source_hosts"]:
                cluster["source_hosts"].append(source_host)
            source_tier = str(getattr(event, "source_tier", "") or "").strip()
            if source_tier and source_tier not in cluster["source_tiers"]:
                cluster["source_tiers"].append(source_tier)
            if cluster["representative_event_id"] is None or float(getattr(event, "signal_strength", 0.0) or 0.0) > float(
                cluster.get("candidate_score") or 0.0
            ):
                cluster["representative_event_id"] = getattr(event, "event_id", None)
                cluster["representative_title"] = getattr(event, "title", None)
            published_at = getattr(event, "published_at", None) or getattr(event, "last_seen_at", None)
            if published_at is not None:
                previous = cluster.get("latest_published_at")
                if previous is None or published_at > previous:
                    cluster["latest_published_at"] = published_at
            if getattr(event, "watch_item_id", None) and cluster["watch_item_id"] is None:
                cluster["watch_item_id"] = getattr(event, "watch_item_id", None)
                linked = get_information_watch_item(self.db, cluster["watch_item_id"])
                if linked is not None:
                    cluster["watch_item_name"] = linked.name
                    cluster["status"] = "linked"

        items: List[Dict[str, Any]] = []
        for cluster in clusters.values():
            event_count = max(1, int(cluster["event_count"]))
            avg_signal = float(cluster.pop("_signal_sum", 0.0) or 0.0) / event_count
            avg_credibility = float(cluster.pop("_credibility_sum", 0.0) or 0.0) / event_count
            repetition_bonus = min(16.0, max(0.0, (event_count - 1) * 4.0))
            promoted_bonus = min(12.0, float(cluster["promoted_count"]) * 3.0)
            hard_source_bonus = 8.0 if cluster["hard_source_confirmed"] else 0.0
            cluster["candidate_score"] = max(
                0.0,
                min(100.0, avg_signal * 0.55 + avg_credibility * 0.2 + repetition_bonus + promoted_bonus + hard_source_bonus),
            )
            items.append(cluster)

        items.sort(
            key=lambda item: (
                float(item.get("candidate_score") or 0.0),
                int(item.get("event_count") or 0),
                int(item.get("promoted_count") or 0),
            ),
            reverse=True,
        )
        return items[: max(1, int(limit))]

    def create_watch_item_from_event(self, event_id: str) -> Any:
        normalized = str(event_id or "").strip()
        if not normalized:
            raise ValueError("event_id 不能为空")

        event = get_information_event(self.db, normalized)
        if event is None:
            raise ValueError(f"未找到开放发现事件: {normalized}")
        if str(getattr(event, "source_mode", "") or "") != "discovery":
            raise ValueError("只有开放发现池事件才支持加入观察池")

        existing_item_id = str(getattr(event, "watch_item_id", "") or "").strip()
        if existing_item_id:
            existing = get_information_watch_item(self.db, existing_item_id)
            if existing is not None:
                return existing

        payload = self._build_watch_item_payload_from_event(event)
        record = self.watch_service.upsert_item(payload)
        self._link_event_to_watch_item(event, record.item_id)
        return record

    def create_watch_item_from_candidate(self, cluster_key: str) -> Any:
        normalized = str(cluster_key or "").strip()
        if not normalized:
            raise ValueError("cluster_key 不能为空")
        candidates = self.list_candidates(limit=80, promoted_only=False)
        candidate = next((item for item in candidates if str(item.get("cluster_key") or "") == normalized), None)
        if candidate is None:
            raise ValueError(f"未找到开放发现候选主题: {normalized}")
        existing_item_id = str(candidate.get("watch_item_id") or "").strip()
        if existing_item_id:
            existing = get_information_watch_item(self.db, existing_item_id)
            if existing is not None:
                return existing
        payload = {
            "item_id": uuid.uuid4().hex,
            "name": str(candidate.get("label") or "新发现主题").strip()[:32],
            "enabled": True,
            "priority": 85,
            "event_type": str(candidate.get("event_type") or "order"),
            "seed_terms": self._normalize_watch_terms(
                list(candidate.get("themes") or []) + list(candidate.get("chain_tags") or []) + [str(candidate.get("representative_title") or "")]
            )[:8],
            "aliases": self._normalize_watch_terms(list(candidate.get("source_hosts") or []))[:4],
            "themes": self._normalize_watch_terms(list(candidate.get("themes") or []))[:4],
            "chain_tags": self._normalize_watch_terms(list(candidate.get("chain_tags") or []))[:6],
            "source_tiers": self._derive_watch_source_tiers_from_cluster(list(candidate.get("source_tiers") or [])),
            "freshness_days": self._derive_watch_freshness_days(str(candidate.get("event_type") or "")),
            "notes": f"由开放发现候选聚类沉淀：{candidate.get('label') or normalized}；事件数 {candidate.get('event_count') or 0}；候选分 {float(candidate.get('candidate_score') or 0.0):.1f}",
        }
        record = self.watch_service.upsert_item(payload)
        for event in self.list_events(limit=240, promoted_only=False):
            metadata = self.db._safe_json_loads(getattr(event, "metadata_json", None)) or {}
            if str(metadata.get("cluster_key") or "") != normalized:
                continue
            self._link_event_to_watch_item(event, record.item_id)
        return record

    def _scan_profile(self, profile: Any) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for query_plan in self._build_query_plan(profile):
            response = self.watch_service._search_query(
                query=str(query_plan.get("query") or "").strip(),
                days=int(query_plan.get("days") or getattr(profile, "freshness_days", 2) or 2),
                strict_freshness=bool(query_plan.get("strict_freshness", True)),
                query_group=str(query_plan.get("name") or ""),
            )
            if not response.success or not response.results:
                continue
            for result in response.results:
                source_tier = self.watch_service._infer_source_tier(result, query_plan)
                if not self._source_tier_allowed(profile, source_tier):
                    continue
                if not self._is_result_relevant(profile, query_plan, result):
                    continue
                event_payload = self._build_event_payload(profile=profile, query_plan=query_plan, response=response, result=result)
                if event_payload is not None:
                    events.append(event_payload)
        return events

    def _dedupe_batch_event_payloads(self, payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for payload in sorted(payloads, key=lambda item: float(item.get("signal_strength") or 0.0), reverse=True):
            matched = False
            for existing in merged:
                if str(existing.get("event_type") or "") != str(payload.get("event_type") or ""):
                    continue
                existing_meta = dict(existing.get("metadata") or {})
                payload_meta = dict(payload.get("metadata") or {})
                if str(existing_meta.get("cluster_key") or "") != str(payload_meta.get("cluster_key") or ""):
                    continue
                similarity = self._title_similarity(
                    str(existing.get("title") or ""),
                    str(payload.get("title") or ""),
                )
                if similarity < 0.62:
                    continue
                matched = True
                existing["signal_strength"] = max(float(existing.get("signal_strength") or 0.0), float(payload.get("signal_strength") or 0.0))
                existing["freshness_score"] = max(float(existing.get("freshness_score") or 0.0), float(payload.get("freshness_score") or 0.0))
                existing["credibility_score"] = max(float(existing.get("credibility_score") or 0.0), float(payload.get("credibility_score") or 0.0))
                if payload.get("source_tier") == "L1" and existing.get("source_tier") != "L1":
                    existing["source_tier"] = "L1"
                merged_sources = list(existing_meta.get("merged_sources") or [])
                payload_source = str(payload_meta.get("source_host") or payload_meta.get("source") or "").strip()
                if payload_source and payload_source not in merged_sources:
                    merged_sources.append(payload_source)
                existing_meta["merged_sources"] = merged_sources[:8]
                existing_meta["near_duplicate_count"] = int(existing_meta.get("near_duplicate_count") or 1) + 1
                existing_meta["dedupe_similarity_max"] = max(
                    float(existing_meta.get("dedupe_similarity_max") or 0.0),
                    similarity,
                )
                existing["metadata"] = existing_meta
                break
            if not matched:
                metadata = dict(payload.get("metadata") or {})
                initial_source = str(metadata.get("source_host") or metadata.get("source") or "").strip()
                metadata["merged_sources"] = [initial_source] if initial_source else []
                metadata["near_duplicate_count"] = 1
                metadata["dedupe_similarity_max"] = 1.0
                payload["metadata"] = metadata
                merged.append(payload)
        return merged

    def _build_query_plan(self, profile: Any) -> List[Dict[str, Any]]:
        query_templates = self._deserialize_json_list(getattr(profile, "query_templates_json", None))
        freshness_days = max(1, int(getattr(profile, "freshness_days", 2) or 2))
        query_plans: List[Dict[str, Any]] = []
        for index, query in enumerate(query_templates[:4]):
            query_plans.append(
                {
                    "name": "event_news" if index == 0 else ("chain_mapping" if index == 1 else "market_reaction"),
                    "query": query,
                    "strict_freshness": index != 1,
                    "days": freshness_days if index != 1 else max(freshness_days, 3),
                }
            )
        if str(getattr(profile, "event_type", "") or "") not in {"opinion_only"}:
            query_plans.append(
                {
                    "name": "hard_source_check",
                    "query": f"{query_templates[0]} cninfo 公告 上交所 深交所".strip() if query_templates else "cninfo 公告 上交所 深交所",
                    "strict_freshness": True,
                    "days": min(freshness_days, 3),
                }
            )
        return query_plans

    def _build_watch_item_payload_from_event(self, event: Any) -> Dict[str, Any]:
        metadata = self.db._safe_json_loads(getattr(event, "metadata_json", None)) or {}
        themes = self._normalize_watch_terms(self.db._safe_json_loads(getattr(event, "themes_json", None)) or [])
        chain_tags = self._normalize_watch_terms(self.db._safe_json_loads(getattr(event, "chain_tags_json", None)) or [])
        entities = self.db._safe_json_loads(getattr(event, "entities_json", None)) or {}
        entity_tokens = self._normalize_watch_terms((entities or {}).get("tokens") or [])

        title = str(getattr(event, "title", "") or "").strip()
        summary = str(getattr(event, "summary", "") or "").strip()
        source_host = str((metadata or {}).get("source_host") or "").strip()
        profile_name = str((metadata or {}).get("discovery_profile_name") or "").strip()
        published_at = getattr(event, "published_at", None)

        seed_terms = self._normalize_watch_terms(themes + chain_tags + entity_tokens)
        aliases = self._normalize_watch_terms(entity_tokens[len(seed_terms[:4]) :])
        if not seed_terms:
            seed_terms = self._normalize_watch_terms([title])

        notes_parts = [f"由开放发现池事件沉淀：{title}"]
        if summary:
            notes_parts.append(summary[:140])
        if profile_name:
            notes_parts.append(f"发现模板：{profile_name}")
        if source_host:
            notes_parts.append(f"来源：{source_host}")
        if getattr(event, "url", None):
            notes_parts.append(f"原文：{getattr(event, 'url')}")
        if published_at is not None:
            try:
                notes_parts.append(f"发布时间：{published_at.strftime('%Y-%m-%d %H:%M')}")
            except Exception:
                pass

        return {
            "item_id": uuid.uuid4().hex,
            "name": self._derive_watch_item_name(title=title, themes=themes, event_type=str(getattr(event, "event_type", "") or "")),
            "enabled": True,
            "priority": 80,
            "event_type": str(getattr(event, "event_type", "") or "order"),
            "seed_terms": seed_terms[:8],
            "aliases": aliases[:6],
            "themes": themes[:4],
            "chain_tags": chain_tags[:6],
            "source_tiers": self._derive_watch_source_tiers(str(getattr(event, "source_tier", "") or "")),
            "freshness_days": self._derive_watch_freshness_days(str(getattr(event, "event_type", "") or "")),
            "notes": "；".join(part for part in notes_parts if part),
        }

    def _link_event_to_watch_item(self, event: Any, watch_item_id: str) -> None:
        self.db.save_information_event(
            event_id=event.event_id,
            watch_item_id=watch_item_id,
            title=event.title,
            summary=event.summary,
            event_type=event.event_type,
            impact_direction=event.impact_direction,
            source_tier=event.source_tier,
            provider=event.provider,
            url=event.url,
            published_at=event.published_at,
            first_seen_at=event.first_seen_at,
            last_seen_at=event.last_seen_at,
            source_mode=getattr(event, "source_mode", "discovery") or "discovery",
            is_new_event=bool(event.is_new_event),
            duplicate_key=event.duplicate_key,
            themes=self.db._safe_json_loads(getattr(event, "themes_json", None)) or [],
            chain_tags=self.db._safe_json_loads(getattr(event, "chain_tags_json", None)) or [],
            entities=self.db._safe_json_loads(getattr(event, "entities_json", None)) or {},
            metadata=self.db._safe_json_loads(getattr(event, "metadata_json", None)) or {},
            freshness_score=float(event.freshness_score or 0.0),
            credibility_score=float(event.credibility_score or 0.0),
            signal_strength=float(event.signal_strength or 0.0),
            status=event.status,
        )

    @staticmethod
    def _normalize_watch_terms(values: Iterable[Any]) -> List[str]:
        generic_terms = {
            "主题待发现",
            "订单",
            "采购",
            "供应商",
            "产业链",
            "受益股",
            "龙头",
            "上市公司",
            "全局探索",
            "开放发现",
            "事件",
            "新闻",
            "中国",
            "A股",
        }
        normalized: List[str] = []
        seen = set()
        for value in values or []:
            text = str(value or "").strip()
            if not text or text in generic_terms or text.lower() in {item.lower() for item in generic_terms}:
                continue
            if text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @staticmethod
    def _derive_watch_item_name(*, title: str, themes: List[str], event_type: str) -> str:
        compact_title = " ".join(str(title or "").split()).strip()
        if compact_title:
            return compact_title[:32]
        suffix = {
            "order": "订单观察",
            "capacity_expand": "扩产观察",
            "mass_production": "量产观察",
            "price_signal": "价格观察",
            "policy_catalyst": "政策观察",
            "technology_progress": "技术观察",
            "capital_expenditure": "资本开支观察",
            "risk_signal": "风险观察",
            "opinion_only": "观点观察",
        }.get(event_type, "事件观察")
        if themes:
            return f"{themes[0]} {suffix}"[:32]
        return suffix

    @staticmethod
    def _derive_watch_source_tiers(source_tier: str) -> List[str]:
        normalized = str(source_tier or "").strip().upper()
        if normalized == "L1":
            return ["L1", "L2"]
        if normalized == "L2":
            return ["L1", "L2"]
        return ["L2", "L3"]

    @staticmethod
    def _derive_watch_freshness_days(event_type: str) -> int:
        return {
            "price_signal": 2,
            "policy_catalyst": 2,
            "order": 3,
            "capacity_expand": 3,
            "mass_production": 3,
            "technology_progress": 4,
            "capital_expenditure": 4,
            "risk_signal": 3,
            "opinion_only": 5,
        }.get(str(event_type or ""), 3)

    def _source_tier_allowed(self, profile: Any, source_tier: str) -> bool:
        allowed = self._deserialize_json_list(getattr(profile, "source_tiers_json", None))
        return not allowed or source_tier in allowed

    def _is_result_relevant(self, profile: Any, query_plan: Dict[str, Any], result: Any) -> bool:
        text = f"{getattr(result, 'title', '')} {getattr(result, 'snippet', '')}".lower()
        if not text.strip():
            return False
        if any(marker in text for marker in ("instagram", "threads", "reddit", "x.com", "twitter")):
            return False

        event_type = str(getattr(profile, "event_type", "") or "")
        event_keywords = {
            "order": ("订单", "采购", "中标", "供货", "签约", "框架协议"),
            "capacity_expand": ("扩产", "投产", "开工", "产能", "募投"),
            "mass_production": ("量产", "交付", "导入", "送样", "验证"),
            "price_signal": ("涨价", "提价", "报价", "价格上涨", "供需"),
            "policy_catalyst": ("放行", "审批", "政策", "许可", "补贴", "试点"),
        }.get(event_type, ())
        if event_keywords and not any(keyword.lower() in text for keyword in event_keywords):
            return False

        matched_themes = self._extract_keywords(text, THEME_KEYWORD_MAP)
        matched_chain_tags = self._extract_keywords(text, CHAIN_KEYWORD_MAP)
        query_group = str(query_plan.get("name") or "")
        if query_group == "chain_mapping":
            return bool(matched_themes or matched_chain_tags)
        return bool(event_keywords) and bool(matched_themes or matched_chain_tags or any(word in text for word in ("产业链", "受益股", "供应商", "龙头")))

    def _build_event_payload(
        self,
        *,
        profile: Any,
        query_plan: Dict[str, Any],
        response: SearchResponse,
        result: Any,
    ) -> Optional[Dict[str, Any]]:
        title = str(getattr(result, "title", "") or "").strip()
        snippet = str(getattr(result, "snippet", "") or "").strip()
        if not title:
            return None

        text = f"{title} {snippet}".lower()
        source_tier = self.watch_service._infer_source_tier(result, query_plan)
        published_at = self.watch_service._parse_published_at(result)
        freshness_days = max(1, int(getattr(profile, "freshness_days", 2) or 2))
        freshness_score = self.watch_service._score_freshness(published_at, freshness_days=freshness_days)
        credibility_score = self.watch_service._score_credibility(
            source_tier,
            provider=response.provider,
            result=result,
            published_at=published_at,
        )
        query_group = str(query_plan.get("name") or "")
        event_type = str(getattr(profile, "event_type", "") or "")
        signal_strength = self.watch_service._score_signal_strength(
            freshness_score=freshness_score,
            credibility_score=credibility_score,
            event_type=event_type,
            query_group=("market_reaction" if query_group == "chain_mapping" else query_group),
        )

        matched_themes = self._extract_keywords(text, THEME_KEYWORD_MAP)
        matched_chain_tags = self._extract_keywords(text, CHAIN_KEYWORD_MAP)
        themes = matched_themes or self._deserialize_json_list(getattr(profile, "themes_json", None))
        chain_tags = list(dict.fromkeys(matched_chain_tags + self._deserialize_json_list(getattr(profile, "chain_tags_json", None))))
        entities = self.watch_service._extract_entities(title, snippet)
        cluster_key = self._derive_cluster_key(
            event_type=event_type,
            themes=themes,
            chain_tags=chain_tags,
            title=title,
        )
        cluster_label = self._derive_cluster_label(
            event_type=event_type,
            themes=themes,
            chain_tags=chain_tags,
            title=title,
        )

        duplicate_key = self.watch_service._build_duplicate_key(
            item_name=str(getattr(profile, "name", "") or ""),
            title=title,
            published_at=published_at,
        )
        previous = get_latest_information_event_by_duplicate_key(self.db, duplicate_key)
        status = self._derive_status(
            freshness_score=freshness_score,
            credibility_score=credibility_score,
            theme_count=len(themes),
        )
        if previous is not None and status != "promoted":
            status = "repeated"

        return {
            "event_id": str(previous.event_id) if previous is not None else uuid.uuid4().hex,
            "watch_item_id": None,
            "title": title,
            "summary": snippet[:280] if snippet else None,
            "event_type": event_type,
            "impact_direction": self.watch_service._impact_direction(event_type),
            "source_mode": "discovery",
            "source_tier": source_tier,
            "provider": response.provider,
            "url": getattr(result, "url", None),
            "published_at": published_at,
            "first_seen_at": previous.first_seen_at if previous is not None else datetime.now(),
            "last_seen_at": datetime.now(),
            "is_new_event": previous is None,
            "duplicate_key": duplicate_key,
            "themes": themes,
            "chain_tags": chain_tags,
            "entities": entities,
            "metadata": {
                "source_mode": "discovery",
                "discovery_profile_id": getattr(profile, "profile_id", None),
                "discovery_profile_name": getattr(profile, "name", None),
                "query_group": query_group,
                "query": query_plan.get("query"),
                "source": getattr(result, "source", None),
                "source_host": self.watch_service._extract_host(getattr(result, "url", None)),
                "raw_published_date": getattr(result, "published_date", None),
                "cluster_key": cluster_key,
                "cluster_label": cluster_label,
                "hard_source_confirmed": bool(source_tier == "L1" or query_group == "hard_source_check"),
            },
            "freshness_score": freshness_score,
            "credibility_score": credibility_score,
            "signal_strength": signal_strength,
            "status": status,
        }

    def _derive_status(self, *, freshness_score: float, credibility_score: float, theme_count: int) -> str:
        min_freshness = float(getattr(self.config, "information_event_min_freshness_score", 70.0) or 70.0)
        min_credibility = float(getattr(self.config, "information_event_min_credibility_score", 65.0) or 65.0)
        if freshness_score >= min_freshness and credibility_score >= min_credibility and theme_count >= 1:
            return "promoted"
        return "new"

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

    @staticmethod
    def _extract_keywords(text: str, keyword_map: Dict[str, List[str]]) -> List[str]:
        matched: List[str] = []
        for label, keywords in keyword_map.items():
            if any(str(keyword).lower() in text for keyword in keywords):
                matched.append(label)
        return matched

    def _derive_cluster_key(self, *, event_type: str, themes: List[str], chain_tags: List[str], title: str) -> str:
        theme_part = "-".join(sorted(self._normalize_watch_terms(themes))[:2]) or "unthemed"
        chain_part = "-".join(sorted(self._normalize_watch_terms(chain_tags))[:2]) or "nochains"
        token_part = "-".join(self._extract_cluster_tokens(title)[:3]) or "generic"
        return f"{str(event_type or 'event').lower()}::{theme_part.lower()}::{chain_part.lower()}::{token_part.lower()}"

    def _derive_cluster_label(self, *, event_type: str, themes: List[str], chain_tags: List[str], title: str) -> str:
        if themes:
            base = "/".join(self._normalize_watch_terms(themes)[:2])
            if chain_tags:
                return f"{base} · {'/'.join(self._normalize_watch_terms(chain_tags)[:2])}"[:40]
            return f"{base} · {self._event_type_label(event_type)}"[:40]
        compact_title = " ".join(str(title or "").split()).strip()
        if compact_title:
            return compact_title[:40]
        return self._event_type_label(event_type)

    @staticmethod
    def _event_type_label(event_type: str) -> str:
        return {
            "order": "订单/采购",
            "capacity_expand": "扩产/投产",
            "mass_production": "量产/验证",
            "price_signal": "涨价/供需",
            "policy_catalyst": "政策/放行",
            "technology_progress": "技术进展",
            "capital_expenditure": "资本开支",
            "risk_signal": "风险事件",
            "opinion_only": "观点解读",
        }.get(str(event_type or ""), str(event_type or "事件"))

    @classmethod
    def _extract_cluster_tokens(cls, title: str) -> List[str]:
        tokens: List[str] = []
        seen = set()
        for match in _TOKEN_RE.findall(str(title or "")):
            token = str(match or "").strip()
            lowered = token.lower()
            if not token or lowered in _CLUSTER_STOPWORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
        return tokens

    @classmethod
    def _title_similarity(cls, left: str, right: str) -> float:
        left_tokens = set(cls._extract_cluster_tokens(left))
        right_tokens = set(cls._extract_cluster_tokens(right))
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return float(intersection) / float(union or 1)

    @staticmethod
    def _derive_watch_source_tiers_from_cluster(source_tiers: List[str]) -> List[str]:
        normalized = {str(item or "").strip().upper() for item in source_tiers if str(item or "").strip()}
        if "L1" in normalized:
            return ["L1", "L2"]
        if "L2" in normalized:
            return ["L1", "L2", "L3"]
        return ["L2", "L3"]
