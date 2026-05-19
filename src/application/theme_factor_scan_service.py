# -*- coding: utf-8 -*-
"""
===================================
Theme Factor Scan Service
===================================
"""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

from theme_picker.application.picker_service import ThemePickerService
from theme_picker.application.registry_service import ThemeRegistryService
from theme_picker.config import get_config
from theme_picker.infrastructure.etf_http_provider import get_etf_http_provider
from theme_picker.infrastructure.persistence import (
    get_information_event,
    get_theme_picker_db,
    list_information_events,
    list_theme_factor_scan_records,
    save_theme_factor_scan_record,
)

logger = logging.getLogger(__name__)

DEFAULT_THEME_ETF_MAP: Dict[str, List[str]] = {
    "芯片": ["159995.SZ", "588200.SH"],
    "存储": ["159995.SZ", "588000.SH"],
    "机器人": ["562500.SH"],
    "cpo": ["515880.SH"],
    "电力": ["159611.SZ"],
    "央企算力": ["560170.SH"],
    "算力": ["560170.SH"],
}


class ThemeFactorScanService:
    def __init__(self) -> None:
        self.db = get_theme_picker_db()
        self.config = get_config()
        self.registry_service = ThemeRegistryService()
        self.theme_picker_service = ThemePickerService(registry_service=self.registry_service)
        self.etf_http_provider = get_etf_http_provider()

    def run_once(
        self,
        *,
        limit: int = 10,
        event_ids: Optional[Iterable[str]] = None,
        min_signal_strength: float = 70.0,
    ) -> Dict[str, Any]:
        events = self._load_target_events(limit=limit, event_ids=event_ids, min_signal_strength=min_signal_strength)
        records: List[Any] = []
        for event in events:
            for theme_name in self._resolve_theme_candidates(event):
                records.append(self._scan_one_theme(event=event, theme_name=theme_name))
        return {
            "scanned_events": len(events),
            "generated_scans": len(records),
            "items": records,
        }

    def list_history(self, *, limit: int = 20, event_id: Optional[str] = None) -> List[Any]:
        return list_theme_factor_scan_records(self.db, limit=limit, event_id=event_id)

    def _load_target_events(
        self,
        *,
        limit: int,
        event_ids: Optional[Iterable[str]],
        min_signal_strength: float,
    ) -> List[Any]:
        selected_ids: List[str] = []
        seen_ids = set()
        for item_id in event_ids or []:
            normalized = str(item_id).strip()
            if not normalized or normalized in seen_ids:
                continue
            seen_ids.add(normalized)
            selected_ids.append(normalized)
        if selected_ids:
            events = []
            for event_id in selected_ids:
                event = get_information_event(self.db, event_id)
                if event is not None:
                    events.append(event)
            return events[: max(1, int(limit))]

        events = list_information_events(self.db, limit=max(1, int(limit) * 3), promoted_only=True)
        filtered = [event for event in events if float(getattr(event, "signal_strength", 0.0) or 0.0) >= float(min_signal_strength)]
        return filtered[: max(1, int(limit))]

    def _resolve_theme_candidates(self, event: Any) -> List[str]:
        parsed = self.db._safe_json_loads(getattr(event, "themes_json", None)) or []
        themes: List[str] = []
        seen = set()
        for value in parsed:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                themes.append(text)
        return themes or ["主题待归类"]

    def _scan_one_theme(self, *, event: Any, theme_name: str) -> Any:
        scan_id = uuid.uuid4().hex
        request_payload = {
            "event_id": event.event_id,
            "theme_name": theme_name,
            "source_event_title": event.title,
        }
        try:
            request = self._build_theme_request(theme_name)
            theme_result = self.theme_picker_service.scan(request, task_id=f"factor-{scan_id}")
            etf_confirmation = self._evaluate_etf_confirmation(theme_name)
            leader_snapshot = self._build_leader_snapshot(theme_result)
            role_breakdown = self._build_role_breakdown(theme_result)
            leader_confirmation_score = float(leader_snapshot.get("score") or 0.0)
            event_hard_source_confirmed = self._event_hard_source_confirmed(event)
            theme_factor_score = self._score_theme_factor(
                event_score=float(getattr(event, "signal_strength", 0.0) or 0.0),
                etf_confirmation_score=float(etf_confirmation.get("score") or 0.0),
                leader_confirmation_score=leader_confirmation_score,
                hard_source_confirmed=event_hard_source_confirmed,
                breadth_score=float(role_breakdown.get("breadth_score") or 0.0),
            )
            record = save_theme_factor_scan_record(
                self.db,
                scan_id=scan_id,
                event_id=event.event_id,
                theme_id=request.theme_id if getattr(request, "theme_id", None) else None,
                theme_name=theme_name,
                status="completed",
                event_score=float(getattr(event, "signal_strength", 0.0) or 0.0),
                etf_confirmation_score=float(etf_confirmation.get("score") or 0.0),
                leader_confirmation_score=leader_confirmation_score,
                theme_factor_score=theme_factor_score,
                request_payload=request_payload,
                result_payload={
                    "event": {
                        "event_id": event.event_id,
                        "title": event.title,
                        "event_type": event.event_type,
                        "source_tier": event.source_tier,
                        "hard_source_confirmed": event_hard_source_confirmed,
                    },
                    "etf_confirmation": etf_confirmation,
                    "leader_confirmation": leader_snapshot,
                    "role_breakdown": role_breakdown,
                    "theme_scan": theme_result,
                },
            )
            return record
        except Exception as exc:
            logger.exception("主题因子扫描失败: event=%s theme=%s", getattr(event, "event_id", None), theme_name)
            return save_theme_factor_scan_record(
                self.db,
                scan_id=scan_id,
                event_id=event.event_id,
                theme_id=None,
                theme_name=theme_name,
                status="failed",
                event_score=float(getattr(event, "signal_strength", 0.0) or 0.0),
                etf_confirmation_score=None,
                leader_confirmation_score=None,
                theme_factor_score=None,
                request_payload=request_payload,
                result_payload=None,
                error=str(exc),
            )

    def _build_theme_request(self, theme_name: str) -> Any:
        theme = next(
            (
                item for item in self.registry_service.list_themes(enabled_only=True)
                if str(item.id or "").strip() == theme_name or str(item.name or "").strip() == theme_name
            ),
            None,
        )
        return SimpleNamespace(
            theme_id=(theme.id if theme is not None else None),
            theme_name=(None if theme is not None else theme_name),
            board_code=None,
            board_name=None,
            strategy_mode="holding",
            max_candidates=8,
            include_untriggered=True,
        )

    def _evaluate_etf_confirmation(self, theme_name: str) -> Dict[str, Any]:
        etf_codes = self._resolve_theme_etfs(theme_name)
        evaluated: List[Dict[str, Any]] = []
        for etf_code in etf_codes:
            try:
                quote = self.etf_http_provider.get_tencent_quote(etf_code.split(".", 1)[0])
            except Exception as exc:
                logger.warning("ETF确认失败: theme=%s etf=%s error=%s", theme_name, etf_code, exc)
                continue
            pct_chg = self._safe_float(quote.get("change_pct")) or self._safe_float(quote.get("pct_chg")) or 0.0
            volume_ratio = self._safe_float(quote.get("volume_ratio")) or 0.0
            score = 45.0
            if pct_chg >= 3.0:
                score += 20.0
            elif pct_chg >= 1.5:
                score += 10.0
            if volume_ratio >= 2.0:
                score += 20.0
            elif volume_ratio >= 1.2:
                score += 10.0
            evaluated.append(
                {
                    "etf_code": etf_code,
                    "etf_name": quote.get("name") or etf_code,
                    "pct_chg": pct_chg,
                    "volume_ratio": volume_ratio,
                    "score": min(100.0, score),
                    "confirmed": bool(score >= 65.0),
                }
            )
        if evaluated:
            evaluated.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
            best = dict(evaluated[0])
            confirmed_count = sum(1 for item in evaluated if bool(item.get("confirmed")))
            breadth_bonus = min(10.0, max(0, confirmed_count - 1) * 5.0)
            best["score"] = min(100.0, float(best.get("score") or 0.0) + breadth_bonus)
            best["confirmed"] = bool(best.get("score", 0.0) >= 65.0)
            best["confirmed_count"] = confirmed_count
            best["items"] = evaluated
            return best
        return {"score": 0.0, "confirmed": False, "etf_code": None, "etf_name": None, "items": []}

    def _resolve_theme_etfs(self, theme_name: str) -> List[str]:
        theme_name_normalized = str(theme_name or "").strip().lower()
        for key, value in DEFAULT_THEME_ETF_MAP.items():
            if key.lower() == theme_name_normalized or key.lower() in theme_name_normalized or theme_name_normalized in key.lower():
                return value
        return []

    @staticmethod
    def _build_leader_snapshot(theme_result: Dict[str, Any]) -> Dict[str, Any]:
        stocks = list((theme_result.get("stocks") or []))
        if not stocks:
            return {"score": 0.0, "stock_code": None, "stock_name": None, "signal_level": None}
        top = stocks[0]
        signal_level = str(top.get("signal_level") or "")
        trend_score = float(top.get("trend_score") or 0.0)
        base = {
            "优先关注": 80.0,
            "持有候选": 72.0,
            "低吸观察": 68.0,
            "主题触发": 50.0,
            "不宜追高": 35.0,
        }.get(signal_level, 40.0)
        if trend_score >= 70:
            base += 8.0
        elif trend_score >= 55:
            base += 4.0
        return {
            "score": min(100.0, base),
            "stock_code": top.get("stock_code"),
            "stock_name": top.get("stock_name"),
            "signal_level": signal_level,
            "trend_score": trend_score,
            "selection_reason": top.get("selection_reason"),
        }

    @staticmethod
    def _build_role_breakdown(theme_result: Dict[str, Any]) -> Dict[str, Any]:
        stocks = list((theme_result.get("stocks") or []))
        leader = None
        first_order: List[Dict[str, Any]] = []
        second_order: List[Dict[str, Any]] = []
        observe: List[Dict[str, Any]] = []
        for index, stock in enumerate(stocks):
            trend_score = float(stock.get("trend_score") or 0.0)
            signal_level = str(stock.get("signal_level") or "")
            item = {
                "stock_code": stock.get("stock_code"),
                "stock_name": stock.get("stock_name"),
                "signal_level": signal_level,
                "trend_score": trend_score,
                "selection_reason": stock.get("selection_reason"),
            }
            if index == 0 or (signal_level == "优先关注" and trend_score >= 70):
                leader = item
                continue
            if signal_level in {"优先关注", "持有候选"} and trend_score >= 62:
                first_order.append(item)
            elif signal_level in {"低吸观察", "持有候选", "主题触发"} and trend_score >= 48:
                second_order.append(item)
            else:
                observe.append(item)
        breadth_score = min(100.0, len(first_order) * 18.0 + len(second_order) * 10.0 + (10.0 if leader else 0.0))
        return {
            "leader": leader,
            "first_order": first_order[:4],
            "second_order": second_order[:4],
            "observe": observe[:4],
            "breadth_score": breadth_score,
        }

    @staticmethod
    def _score_theme_factor(
        *,
        event_score: float,
        etf_confirmation_score: float,
        leader_confirmation_score: float,
        hard_source_confirmed: bool,
        breadth_score: float,
    ) -> float:
        hard_source_bonus = 6.0 if hard_source_confirmed else 0.0
        return max(
            0.0,
            min(
                100.0,
                event_score * 0.4
                + etf_confirmation_score * 0.2
                + leader_confirmation_score * 0.25
                + breadth_score * 0.1
                + hard_source_bonus,
            ),
        )

    def _event_hard_source_confirmed(self, event: Any) -> bool:
        metadata = self.db._safe_json_loads(getattr(event, "metadata_json", None)) or {}
        if bool(metadata.get("hard_source_confirmed")):
            return True
        return str(getattr(event, "source_tier", "") or "") == "L1"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
