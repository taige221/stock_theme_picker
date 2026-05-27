# -*- coding: utf-8 -*-
"""
===================================
Single Stock Alert Service
===================================
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from theme_picker.application.stock_text_supplement_service import StockTextSupplementService
from theme_picker.config import get_config
from theme_picker.data_provider import DataFetcherManager
from theme_picker.infrastructure.persistence import (
    create_stock_alert_event,
    get_theme_picker_db,
    list_stock_alert_rules,
    list_stock_watchlist_items,
    update_stock_alert_rule,
)

logger = logging.getLogger(__name__)


@dataclass
class StockAlertTriggerRecord:
    stock_code: str
    stock_name: str
    rule_id: int
    rule_type: str
    event_type: str
    title: str
    message: str
    dedupe_key: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StockAlertScanSummary:
    scanned_rules: int = 0
    due_rules: int = 0
    triggered_events: int = 0
    skipped_rules: int = 0
    trigger_records: List[StockAlertTriggerRecord] = field(default_factory=list)


class StockAlertService:
    """Evaluate persisted stock alert rules with lightweight quote/news snapshots."""

    SUPPORT_RETEST_TOLERANCE = 0.01
    BREAKOUT_RESET_TOLERANCE = 0.005

    def __init__(
        self,
        *,
        db=None,
        fetcher_manager: Optional[DataFetcherManager] = None,
        text_supplement_service: Optional[StockTextSupplementService] = None,
    ) -> None:
        self.db = db or get_theme_picker_db()
        self.fetcher_manager = fetcher_manager or DataFetcherManager()
        self.text_supplement_service = text_supplement_service or StockTextSupplementService()

    def run_once(self, *, stock_code: Optional[str] = None, now: Optional[datetime] = None) -> StockAlertScanSummary:
        current_time = now or datetime.now()
        rules = list_stock_alert_rules(self.db, stock_code=stock_code.strip().upper() if stock_code else None)
        watchlist_items = {
            str(item.stock_code).strip().upper(): item
            for item in list_stock_watchlist_items(self.db)
            if bool(getattr(item, "alert_enabled", 0))
        }

        summary = StockAlertScanSummary(scanned_rules=len(rules))
        rules_by_stock: Dict[str, List[Any]] = {}

        for rule in rules:
            normalized_code = str(getattr(rule, "stock_code", "") or "").strip().upper()
            if not normalized_code or not bool(getattr(rule, "enabled", 0)):
                summary.skipped_rules += 1
                continue
            if normalized_code not in watchlist_items:
                summary.skipped_rules += 1
                continue
            if not self._is_rule_due(rule, current_time):
                summary.skipped_rules += 1
                continue
            summary.due_rules += 1
            rules_by_stock.setdefault(normalized_code, []).append(rule)

        for normalized_code, grouped_rules in rules_by_stock.items():
            stock_name = str(getattr(grouped_rules[0], "stock_name", "") or normalized_code)
            due_price_rules = [rule for rule in grouped_rules if str(getattr(rule, "rule_type", "")) in {"support_retest", "breakout_confirm"}]
            due_risk_rules = [rule for rule in grouped_rules if str(getattr(rule, "rule_type", "")) == "risk_event"]

            quote = None
            current_price = None
            quote_snapshot: Dict[str, Any] = {}
            if due_price_rules:
                quote_snapshot = self._fetch_realtime_quote_snapshot(normalized_code)
                quote = quote_snapshot.get("quote")
                current_price = self._safe_float(getattr(quote, "price", None)) if quote else None

            news_summary: Optional[Dict[str, Any]] = None
            if due_risk_rules and self.text_supplement_service.is_available:
                news_summary = self.text_supplement_service.get_stock_news_summary(normalized_code, stock_name) or {}

            for rule in grouped_rules:
                triggered = self._evaluate_rule(
                    rule=rule,
                    stock_name=stock_name,
                    current_time=current_time,
                    current_price=current_price,
                    quote_snapshot=quote_snapshot,
                    news_summary=news_summary,
                )
                if triggered is None:
                    continue
                event_record = create_stock_alert_event(
                    self.db,
                    stock_code=triggered.stock_code,
                    stock_name=triggered.stock_name,
                    rule_id=triggered.rule_id,
                    rule_type=triggered.rule_type,
                    event_type=triggered.event_type,
                    title=triggered.title,
                    message=triggered.message,
                    dedupe_key=triggered.dedupe_key,
                    payload=triggered.payload,
                )
                update_stock_alert_rule(
                    self.db,
                    rule_id=rule.id,
                    last_evaluated_at=current_time,
                    last_triggered_at=current_time,
                    last_trigger_key=triggered.dedupe_key or f"event:{event_record.id}",
                    last_scan_status="triggered",
                    last_scan_reason=triggered.message,
                    last_quote_source=triggered.payload.get("quote_source"),
                    last_quote_price=triggered.payload.get("current_price"),
                    last_scan_payload=triggered.payload,
                )
                summary.triggered_events += 1
                summary.trigger_records.append(triggered)

            for rule in grouped_rules:
                if not any(record.rule_id == rule.id for record in summary.trigger_records):
                    self._update_rule_post_scan(
                        rule=rule,
                        current_time=current_time,
                        current_price=current_price,
                        quote_snapshot=quote_snapshot,
                        news_summary=news_summary,
                    )

        return summary

    def _is_rule_due(self, rule: Any, current_time: datetime) -> bool:
        interval_minutes = max(5, int(getattr(rule, "scan_interval_minutes", 5) or 5))
        last_evaluated_at = getattr(rule, "last_evaluated_at", None)
        if not isinstance(last_evaluated_at, datetime):
            return True
        return current_time - last_evaluated_at >= timedelta(minutes=interval_minutes)

    def _evaluate_rule(
        self,
        *,
        rule: Any,
        stock_name: str,
        current_time: datetime,
        current_price: Optional[float],
        quote_snapshot: Dict[str, Any],
        news_summary: Optional[Dict[str, Any]],
    ) -> Optional[StockAlertTriggerRecord]:
        rule_type = str(getattr(rule, "rule_type", "") or "").strip()
        stock_code = str(getattr(rule, "stock_code", "") or "").strip().upper()
        threshold = self._safe_float(getattr(rule, "threshold_value", None))
        last_trigger_key = str(getattr(rule, "last_trigger_key", "") or "").strip() or None

        if rule_type == "support_retest":
            if current_price is None or threshold is None or threshold <= 0:
                return None
            distance_ratio = abs(current_price - threshold) / threshold
            if distance_ratio > self.SUPPORT_RETEST_TOLERANCE:
                return None
            dedupe_key = f"support_retest:{stock_code}:{threshold:.3f}"
            if dedupe_key == last_trigger_key:
                return None
            return StockAlertTriggerRecord(
                stock_code=stock_code,
                stock_name=stock_name,
                rule_id=int(rule.id),
                rule_type=rule_type,
                event_type=rule_type,
                title=f"{stock_name} 接近支撑位",
                message=f"{stock_name} 当前价格 {current_price:.2f} 已接近支撑位 {threshold:.2f}，可重新关注低吸机会。",
                dedupe_key=dedupe_key,
                payload={
                    "current_price": current_price,
                    "threshold_value": threshold,
                    "distance_ratio": round(distance_ratio, 6),
                    "scanned_at": current_time.isoformat(),
                    **self._quote_payload_fields(quote_snapshot),
                },
            )

        if rule_type == "breakout_confirm":
            if current_price is None or threshold is None or threshold <= 0:
                return None
            if current_price < threshold:
                return None
            dedupe_key = f"breakout_confirm:{stock_code}:{threshold:.3f}"
            if dedupe_key == last_trigger_key:
                return None
            return StockAlertTriggerRecord(
                stock_code=stock_code,
                stock_name=stock_name,
                rule_id=int(rule.id),
                rule_type=rule_type,
                event_type=rule_type,
                title=f"{stock_name} 突破确认位",
                message=f"{stock_name} 当前价格 {current_price:.2f} 已站上突破确认位 {threshold:.2f}，需要关注量价是否继续配合。",
                dedupe_key=dedupe_key,
                payload={
                    "current_price": current_price,
                    "threshold_value": threshold,
                    "scanned_at": current_time.isoformat(),
                    **self._quote_payload_fields(quote_snapshot),
                },
            )

        if rule_type == "risk_event":
            risk_events = list((news_summary or {}).get("risk_events") or [])
            headlines = list((news_summary or {}).get("headlines") or [])
            if not risk_events:
                return None
            dedupe_key = f"risk_event:{stock_code}:{'|'.join(risk_events[:3])}"
            if dedupe_key == last_trigger_key:
                return None
            return StockAlertTriggerRecord(
                stock_code=stock_code,
                stock_name=stock_name,
                rule_id=int(rule.id),
                rule_type=rule_type,
                event_type=rule_type,
                title=f"{stock_name} 出现风险事件",
                message=f"{stock_name} 最近新闻里识别到明确风险项：{'、'.join(risk_events[:3])}。",
                dedupe_key=dedupe_key,
                payload={
                    "risk_events": risk_events[:3],
                    "headlines": headlines[:3],
                    "summary": (news_summary or {}).get("summary"),
                    "scanned_at": current_time.isoformat(),
                },
            )

        return None

    def _update_rule_post_scan(
        self,
        *,
        rule: Any,
        current_time: datetime,
        current_price: Optional[float],
        quote_snapshot: Dict[str, Any],
        news_summary: Optional[Dict[str, Any]],
    ) -> None:
        rule_type = str(getattr(rule, "rule_type", "") or "").strip()
        threshold = self._safe_float(getattr(rule, "threshold_value", None))
        outcome = self._build_scan_outcome(
            rule=rule,
            current_time=current_time,
            current_price=current_price,
            quote_snapshot=quote_snapshot,
            news_summary=news_summary,
        )
        should_clear_trigger_key = False

        if rule_type == "support_retest" and current_price is not None and threshold and threshold > 0:
            should_clear_trigger_key = abs(current_price - threshold) / threshold > self.SUPPORT_RETEST_TOLERANCE
        elif rule_type == "breakout_confirm" and current_price is not None and threshold and threshold > 0:
            should_clear_trigger_key = current_price < threshold * (1 - self.BREAKOUT_RESET_TOLERANCE)
        elif rule_type == "risk_event":
            should_clear_trigger_key = news_summary is not None and not bool((news_summary or {}).get("risk_events"))

        update_kwargs: Dict[str, Any] = {
            "rule_id": int(rule.id),
            "last_evaluated_at": current_time,
            "last_scan_status": outcome["status"],
            "last_scan_reason": outcome["reason"],
            "last_quote_source": outcome["payload"].get("quote_source"),
            "last_quote_price": outcome["payload"].get("current_price"),
            "last_scan_payload": outcome["payload"],
        }
        if should_clear_trigger_key:
            update_kwargs["last_trigger_key"] = None
        update_stock_alert_rule(self.db, **update_kwargs)

    def _fetch_realtime_quote_snapshot(self, stock_code: str) -> Dict[str, Any]:
        config = get_config()
        timeout_seconds = float(getattr(config, "watchlist_realtime_quote_timeout_seconds", 8.0) or 0.0)
        source_priority = str(getattr(config, "realtime_source_priority", "") or "")
        try:
            quote = self._run_with_timeout(
                lambda: self.fetcher_manager.get_realtime_quote(stock_code, log_final_failure=False),
                timeout_seconds=timeout_seconds,
                task_name=f"watchlist realtime quote {stock_code}",
            )
            return {
                "quote": quote,
                "quote_source": self._resolve_quote_source(quote),
                "realtime_source_priority": source_priority,
                "quote_error": None if quote else "all realtime quote sources returned empty",
                "quote_timeout_seconds": timeout_seconds,
            }
        except Exception as exc:
            logger.warning("观察池实时行情失败: code=%s error=%s", stock_code, exc)
            return {
                "quote": None,
                "quote_source": None,
                "realtime_source_priority": source_priority,
                "quote_error": str(exc),
                "quote_timeout_seconds": timeout_seconds,
            }

    def _build_scan_outcome(
        self,
        *,
        rule: Any,
        current_time: datetime,
        current_price: Optional[float],
        quote_snapshot: Dict[str, Any],
        news_summary: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rule_type = str(getattr(rule, "rule_type", "") or "").strip()
        stock_code = str(getattr(rule, "stock_code", "") or "").strip().upper()
        threshold = self._safe_float(getattr(rule, "threshold_value", None))
        payload: Dict[str, Any] = {
            "stock_code": stock_code,
            "rule_type": rule_type,
            "threshold_value": threshold,
            "scanned_at": current_time.isoformat(),
        }

        if rule_type in {"support_retest", "breakout_confirm"}:
            payload.update(self._quote_payload_fields(quote_snapshot))
            payload["current_price"] = current_price
            if threshold is None or threshold <= 0:
                return {"status": "invalid_rule", "reason": "规则缺少有效价格阈值。", "payload": payload}
            if current_price is None:
                reason = payload.get("quote_error") or "实时行情未返回有效价格。"
                return {"status": "quote_unavailable", "reason": str(reason), "payload": payload}
            if rule_type == "support_retest":
                distance_ratio = abs(current_price - threshold) / threshold
                payload["distance_ratio"] = round(distance_ratio, 6)
                if distance_ratio <= self.SUPPORT_RETEST_TOLERANCE:
                    return {
                        "status": "deduped",
                        "reason": "价格仍在支撑观察带内，但本规则已提醒过，等待价格离开观察带后再重新提醒。",
                        "payload": payload,
                    }
                return {
                    "status": "not_triggered",
                    "reason": f"当前价 {current_price:.2f} 距支撑位 {threshold:.2f} 偏离 {distance_ratio * 100:.2f}%，未进入 {self.SUPPORT_RETEST_TOLERANCE * 100:.2f}% 观察带。",
                    "payload": payload,
                }
            payload["breakout_gap_ratio"] = round((current_price - threshold) / threshold, 6)
            if current_price >= threshold:
                return {
                    "status": "deduped",
                    "reason": "价格仍在突破确认位上方，但本规则已提醒过，等待跌回重置区间后再重新提醒。",
                    "payload": payload,
                }
            return {
                "status": "not_triggered",
                "reason": f"当前价 {current_price:.2f} 尚未站上突破确认位 {threshold:.2f}。",
                "payload": payload,
            }

        if rule_type == "risk_event":
            risk_events = list((news_summary or {}).get("risk_events") or [])
            headlines = list((news_summary or {}).get("headlines") or [])
            payload.update(
                {
                    "risk_events": risk_events[:3],
                    "headlines": headlines[:3],
                    "summary": (news_summary or {}).get("summary"),
                    "text_supplement_available": bool(self.text_supplement_service.is_available),
                }
            )
            if not self.text_supplement_service.is_available:
                return {"status": "news_unavailable", "reason": "文本情报补充未配置，无法扫描风险事件。", "payload": payload}
            if news_summary is None:
                return {"status": "news_unavailable", "reason": "新闻摘要未返回结果。", "payload": payload}
            return {"status": "not_triggered", "reason": "最近新闻未识别到明确风险项。", "payload": payload}

        return {"status": "unknown_rule_type", "reason": f"未知观察规则类型：{rule_type}", "payload": payload}

    @staticmethod
    def _quote_payload_fields(quote_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "quote_source": quote_snapshot.get("quote_source"),
            "realtime_source_priority": quote_snapshot.get("realtime_source_priority"),
            "quote_error": quote_snapshot.get("quote_error"),
            "quote_timeout_seconds": quote_snapshot.get("quote_timeout_seconds"),
        }

    @staticmethod
    def _resolve_quote_source(quote: Any) -> Optional[str]:
        source = getattr(quote, "source", None)
        value = getattr(source, "value", None)
        if value:
            return str(value)
        if source:
            return str(source)
        return None

    @staticmethod
    def _run_with_timeout(task, *, timeout_seconds: float, task_name: str):
        if timeout_seconds <= 0:
            return task()

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(task)
            return future.result(timeout=max(0.0, float(timeout_seconds)))
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"{task_name} timeout after {timeout_seconds:.1f}s") from exc
        finally:
            executor.shutdown(wait=False)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            converted = float(value)
        except (TypeError, ValueError):
            return None
        if converted != converted:
            return None
        return converted
