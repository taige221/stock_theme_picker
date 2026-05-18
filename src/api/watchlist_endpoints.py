# -*- coding: utf-8 -*-
"""
===================================
观察池接口
===================================
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from theme_picker.api.schemas import (
    StockAlertEventItemSchema,
    StockAlertEventListResponse,
    StockAlertEventMarkAllReadRequest,
    StockAlertLoopStatusSchema,
    StockAlertRuleDefaultsRequest,
    StockAlertRuleItemSchema,
    StockAlertRuleListResponse,
    StockAlertScanSummarySchema,
    StockAlertRuleUpdateRequest,
    StockAlertRuleUpsertRequest,
    StockWatchlistItemSchema,
    StockWatchlistListResponse,
    StockWatchlistUpsertRequest,
)
from theme_picker.application.stock_alert_service import StockAlertService
from theme_picker.config import get_config
from theme_picker.storage import UNSET
from theme_picker.infrastructure.persistence import (
    delete_stock_alert_rule,
    delete_stock_watchlist_item,
    get_stock_alert_rule,
    list_stock_deep_analysis_records,
    get_stock_watchlist_item,
    get_theme_picker_db,
    list_stock_alert_rules,
    list_stock_alert_events,
    mark_all_stock_alert_events_read,
    mark_stock_alert_event_read,
    list_stock_watchlist_items,
    update_stock_alert_rule,
    upsert_stock_alert_rule,
    upsert_stock_watchlist_item,
)

router = APIRouter()


@router.get(
    "/stocks",
    response_model=StockWatchlistListResponse,
    summary="获取股票观察池",
    description="返回当前已经加入观察池的股票列表。",
)
def list_watchlist_stocks() -> StockWatchlistListResponse:
    db = get_theme_picker_db()
    records = list_stock_watchlist_items(db)
    return StockWatchlistListResponse(items=[_build_watchlist_item(record) for record in records])


@router.post(
    "/stocks",
    response_model=StockWatchlistItemSchema,
    summary="加入或更新股票观察池",
    description="将股票加入观察池；如果已存在，则更新最近信号、题材和时间。",
)
def upsert_watchlist_stock(request: StockWatchlistUpsertRequest) -> StockWatchlistItemSchema:
    stock_code = str(request.stock_code or "").strip().upper()
    stock_name = str(request.stock_name or "").strip()
    if not stock_code or not stock_name:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": "stock_code 和 stock_name 不能为空"},
        )

    db = get_theme_picker_db()
    record = upsert_stock_watchlist_item(
        db,
        stock_code=stock_code,
        stock_name=stock_name,
        group_name=request.group_name,
        note=request.note,
        latest_signal=request.latest_signal,
        latest_theme=request.latest_theme,
        alert_enabled=request.alert_enabled,
        source_query_id=request.source_query_id,
    )
    return _build_watchlist_item(record)


@router.delete(
    "/stocks/{stock_code}",
    summary="移除股票观察项",
    description="按股票代码从观察池中删除一条股票记录。",
)
def delete_watchlist_stock(stock_code: str) -> dict[str, bool]:
    db = get_theme_picker_db()
    existing = get_stock_watchlist_item(db, stock_code.strip().upper())
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"观察池中不存在该股票: {stock_code}"},
        )

    deleted = delete_stock_watchlist_item(db, stock_code.strip().upper())
    return {"success": deleted}


@router.get(
    "/stock-alert-rules",
    response_model=StockAlertRuleListResponse,
    summary="获取单股告警规则",
    description="返回当前单股告警规则列表，可按股票代码过滤。",
)
def list_watchlist_stock_alert_rules(stock_code: str | None = None) -> StockAlertRuleListResponse:
    db = get_theme_picker_db()
    records = list_stock_alert_rules(db, stock_code=stock_code.strip().upper() if stock_code else None)
    return StockAlertRuleListResponse(items=[_build_stock_alert_rule_item(record) for record in records])


@router.post(
    "/stock-alert-rules",
    response_model=StockAlertRuleItemSchema,
    summary="创建或更新单股告警规则",
    description="基于股票和规则类型创建或更新一条单股告警规则。",
)
def upsert_watchlist_stock_alert_rule(request: StockAlertRuleUpsertRequest) -> StockAlertRuleItemSchema:
    db = get_theme_picker_db()
    record = upsert_stock_alert_rule(
        db,
        stock_code=request.stock_code.strip().upper(),
        stock_name=request.stock_name.strip(),
        rule_type=request.rule_type.strip(),
        threshold_value=request.threshold_value,
        scan_interval_minutes=request.scan_interval_minutes,
        enabled=request.enabled,
        note=request.note,
        source_query_id=request.source_query_id,
    )
    return _build_stock_alert_rule_item(record)


@router.post(
    "/stock-alert-rules/defaults",
    response_model=StockAlertRuleListResponse,
    summary="为单股创建默认告警规则",
    description="按单股当前分析结果，一次性创建默认三条规则：接近支撑、突破确认、明确风险事件。",
)
def create_default_stock_alert_rules(request: StockAlertRuleDefaultsRequest) -> StockAlertRuleListResponse:
    stock_code = request.stock_code.strip().upper()
    stock_name = request.stock_name.strip()
    db = get_theme_picker_db()
    upsert_stock_watchlist_item(
        db,
        stock_code=stock_code,
        stock_name=stock_name,
        alert_enabled=True,
        source_query_id=request.source_query_id,
    )
    created = []

    if request.support_price is not None:
        created.append(
            upsert_stock_alert_rule(
                db,
                stock_code=stock_code,
                stock_name=stock_name,
                rule_type="support_retest",
                threshold_value=request.support_price,
                scan_interval_minutes=request.scan_interval_minutes,
                enabled=True,
                note="当价格重新接近支撑位时提醒",
                source_query_id=request.source_query_id,
            )
        )

    if request.breakout_price is not None:
        created.append(
            upsert_stock_alert_rule(
                db,
                stock_code=stock_code,
                stock_name=stock_name,
                rule_type="breakout_confirm",
                threshold_value=request.breakout_price,
                scan_interval_minutes=request.scan_interval_minutes,
                enabled=True,
                note="当价格突破确认位时提醒",
                source_query_id=request.source_query_id,
            )
        )

    created.append(
        upsert_stock_alert_rule(
            db,
            stock_code=stock_code,
            stock_name=stock_name,
            rule_type="risk_event",
            threshold_value=None,
            scan_interval_minutes=request.scan_interval_minutes,
            enabled=True,
            note="当新闻中识别到明确风险事件时提醒",
            source_query_id=request.source_query_id,
        )
    )

    return StockAlertRuleListResponse(items=[_build_stock_alert_rule_item(record) for record in created])


@router.patch(
    "/stock-alert-rules/{rule_id}",
    response_model=StockAlertRuleItemSchema,
    summary="更新单股告警规则",
    description="按规则 ID 更新启停状态、阈值或备注。",
)
def update_watchlist_stock_alert_rule(rule_id: int, request: StockAlertRuleUpdateRequest) -> StockAlertRuleItemSchema:
    db = get_theme_picker_db()
    existing = get_stock_alert_rule(db, rule_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到告警规则: {rule_id}"},
        )
    record = update_stock_alert_rule(
        db,
        rule_id=rule_id,
        threshold_value=request.threshold_value if "threshold_value" in request.model_fields_set else UNSET,
        scan_interval_minutes=request.scan_interval_minutes,
        enabled=request.enabled,
        note=request.note,
    )
    return _build_stock_alert_rule_item(record)


@router.delete(
    "/stock-alert-rules/{rule_id}",
    summary="删除单股告警规则",
    description="按规则 ID 删除一条单股告警规则。",
)
def delete_watchlist_stock_alert_rule(rule_id: int) -> dict[str, bool]:
    db = get_theme_picker_db()
    deleted = delete_stock_alert_rule(db, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到告警规则: {rule_id}"},
        )
    return {"success": True}


@router.get(
    "/stock-alert-events",
    response_model=StockAlertEventListResponse,
    summary="获取单股告警事件",
    description="返回最近的单股告警事件，可按股票代码过滤，也可只看未读事件。",
)
def list_watchlist_stock_alert_events(
    limit: int = 30,
    stock_code: str | None = None,
    unread_only: bool = False,
) -> StockAlertEventListResponse:
    db = get_theme_picker_db()
    records = list_stock_alert_events(
        db,
        limit=max(1, min(int(limit), 200)),
        stock_code=stock_code.strip().upper() if stock_code else None,
        unread_only=bool(unread_only),
    )
    return StockAlertEventListResponse(items=[_build_stock_alert_event_item(db, record) for record in records])


@router.patch(
    "/stock-alert-events/{event_id}/read",
    response_model=StockAlertEventItemSchema,
    summary="标记单条告警事件为已读",
)
def mark_watchlist_stock_alert_event_read(event_id: int) -> StockAlertEventItemSchema:
    db = get_theme_picker_db()
    record = mark_stock_alert_event_read(db, event_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到告警事件: {event_id}"},
        )
    return _build_stock_alert_event_item(db, record)


@router.post(
    "/stock-alert-events/read-all",
    summary="批量标记告警事件为已读",
)
def mark_watchlist_stock_alert_events_read_all(request: StockAlertEventMarkAllReadRequest) -> dict[str, int]:
    db = get_theme_picker_db()
    count = mark_all_stock_alert_events_read(
        db,
        stock_code=request.stock_code.strip().upper() if request.stock_code else None,
    )
    return {"updated": count}


@router.get(
    "/stock-alert-loop/status",
    response_model=StockAlertLoopStatusSchema,
    summary="获取单股告警后台循环状态",
)
def get_stock_alert_loop_status(request: Request) -> StockAlertLoopStatusSchema:
    cfg = get_config()
    loop = getattr(request.app.state, "stock_alert_loop", None)
    raw_status = loop.status() if loop is not None else {}
    raw_summary = raw_status.get("last_summary") or None
    return StockAlertLoopStatusSchema(
        enabled=bool(getattr(cfg, "stock_alert_loop_enabled", False)),
        running=bool(raw_status.get("running", False)),
        base_tick_seconds=int(raw_status.get("base_tick_seconds") or getattr(cfg, "stock_alert_loop_base_tick_seconds", 60) or 60),
        last_started_at=raw_status.get("last_started_at"),
        last_finished_at=raw_status.get("last_finished_at"),
        last_error=raw_status.get("last_error"),
        last_summary=StockAlertScanSummarySchema(**raw_summary) if isinstance(raw_summary, dict) else None,
    )


@router.post(
    "/stock-alert-loop/run-once",
    response_model=StockAlertScanSummarySchema,
    summary="手动执行一轮单股告警扫描",
)
def run_stock_alert_loop_once(stock_code: str | None = None) -> StockAlertScanSummarySchema:
    summary = StockAlertService().run_once(stock_code=stock_code)
    payload = asdict(summary)
    return StockAlertScanSummarySchema(
        scanned_rules=payload.get("scanned_rules", 0),
        due_rules=payload.get("due_rules", 0),
        triggered_events=payload.get("triggered_events", 0),
        skipped_rules=payload.get("skipped_rules", 0),
    )


def _build_watchlist_item(record) -> StockWatchlistItemSchema:
    return StockWatchlistItemSchema(
        stock_code=record.stock_code,
        stock_name=record.stock_name,
        group_name=record.group_name,
        note=record.note,
        latest_signal=record.latest_signal,
        latest_theme=record.latest_theme,
        alert_enabled=bool(record.alert_enabled),
        source_query_id=record.source_query_id,
        created_at=record.created_at.isoformat() if record.created_at else "",
        updated_at=record.updated_at.isoformat() if record.updated_at else "",
    )


def _build_stock_alert_rule_item(record) -> StockAlertRuleItemSchema:
    return StockAlertRuleItemSchema(
        id=record.id,
        stock_code=record.stock_code,
        stock_name=record.stock_name,
        rule_type=record.rule_type,
        threshold_value=record.threshold_value,
        scan_interval_minutes=max(5, int(record.scan_interval_minutes or 5)),
        enabled=bool(record.enabled),
        note=record.note,
        source_query_id=record.source_query_id,
        created_at=record.created_at.isoformat() if record.created_at else "",
        updated_at=record.updated_at.isoformat() if record.updated_at else "",
    )


def _build_stock_alert_event_item(db, record) -> StockAlertEventItemSchema:
    rule = get_stock_alert_rule(db, record.rule_id)
    source_query_id = getattr(rule, "source_query_id", None)
    linked_analysis_id = None
    payload = db._safe_json_loads(getattr(record, "payload_json", None))
    if source_query_id:
        for analysis in list_stock_deep_analysis_records(db, stock_code=record.stock_code, limit=50):
            if analysis.status == "completed" and analysis.source_query_id == source_query_id:
                linked_analysis_id = analysis.analysis_id
                break

    return StockAlertEventItemSchema(
        id=record.id,
        stock_code=record.stock_code,
        stock_name=record.stock_name,
        rule_id=record.rule_id,
        rule_type=record.rule_type,
        event_type=record.event_type,
        title=record.title,
        message=record.message,
        dedupe_key=record.dedupe_key,
        payload=payload if isinstance(payload, dict) else None,
        source_query_id=source_query_id,
        linked_analysis_id=linked_analysis_id,
        created_at=record.created_at.isoformat() if record.created_at else "",
        read_at=record.read_at.isoformat() if record.read_at else None,
    )
