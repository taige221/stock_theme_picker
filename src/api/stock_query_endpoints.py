# -*- coding: utf-8 -*-
"""
===================================
单股查询接口
===================================
"""

from datetime import datetime
import uuid
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from theme_picker.api.schemas import (
    EtfQueryHistoryItemSchema,
    EtfQueryHistoryListResponse,
    EtfMarketSnapshotResponse,
    StockAlertRuleItemSchema,
    StockAlertRuleListResponse,
    StockDeepAnalysisAlertRulesRequest,
    StockDeepAnalysisChatRequest,
    StockDeepAnalysisChatResponse,
    StockDeepAnalysisCreateRequest,
    StockDeepAnalysisItemSchema,
    StockDeepAnalysisListResponse,
    StockDeepAnalysisMessageSchema,
    StockQueryAnalyzeRequest,
    StockQueryAnalyzeResponse,
    StockQueryHistoryItemSchema,
    StockQueryHistoryListResponse,
    StockQueryTaskAcceptedSchema,
    StockQueryTaskStatusSchema,
)
from theme_picker.application.etf_market_service import get_etf_market_service
from theme_picker.application.stock_deep_analysis_service import StockDeepAnalysisService
from theme_picker.application.stock_deep_analysis_task_service import get_stock_deep_analysis_task_service
from theme_picker.application.stock_query_task_service import get_stock_query_task_service
from theme_picker.infrastructure.etf_query_logging import emit_etf_query_log
from theme_picker.infrastructure.persistence import (
    get_etf_query_record,
    get_theme_picker_db,
    list_etf_query_records,
    save_etf_query_record,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/analyze",
    status_code=202,
    response_model=StockQueryTaskAcceptedSchema,
    responses={
        202: {"description": "单股查询任务已接受", "model": StockQueryTaskAcceptedSchema},
        400: {"description": "请求参数错误"},
        500: {"description": "服务器错误"},
    },
    summary="执行单股查询",
    description="根据股票代码或名称，异步执行单股查询任务。",
)
def analyze_single_stock(request: StockQueryAnalyzeRequest) -> JSONResponse:
    try:
        task_service = get_stock_query_task_service()
        task = task_service.submit_query(request)
        accepted = StockQueryTaskAcceptedSchema(
            task_id=task.task_id,
            status=task.status.value,
            message=task.message or "单股查询任务已接受",
        )
        return JSONResponse(status_code=202, content=accepted.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"单股查询失败: {exc}"},
        ) from exc


@router.get(
    "/status/{task_id}",
    response_model=StockQueryTaskStatusSchema,
    responses={
        200: {"description": "单股查询任务状态", "model": StockQueryTaskStatusSchema},
        404: {"description": "任务不存在"},
    },
    summary="查询单股查询任务状态",
    description="根据 task_id 查询单股查询任务状态；完成时返回 result。",
)
def get_single_stock_status(task_id: str) -> StockQueryTaskStatusSchema:
    task_service = get_stock_query_task_service()
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到单股查询任务: {task_id}"},
        )

    result = StockQueryAnalyzeResponse(**task.result) if isinstance(task.result, dict) else None
    return StockQueryTaskStatusSchema(
        task_id=task.task_id,
        status=task.status.value,
        progress=task.progress,
        message=task.message,
        result=result,
        error=task.error,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.get(
    "/etf-market/{stock_code}",
    response_model=EtfMarketSnapshotResponse,
    responses={
        200: {"description": "ETF 市场快照", "model": EtfMarketSnapshotResponse},
        400: {"description": "请求参数错误"},
        500: {"description": "服务器错误"},
    },
    summary="获取 ETF 市场快照",
    description="通过 mootdx 和腾讯财经获取 ETF 的实时行情、盘口和最近日线，绕开东财链路。",
)
def get_etf_market_snapshot(stock_code: str, bars: int = 20) -> EtfMarketSnapshotResponse:
    db = get_theme_picker_db()
    query_id = uuid.uuid4().hex
    request_payload = {"stock_code": stock_code, "bars": bars}
    created_at = datetime.now()
    try:
        service = get_etf_market_service()
        payload = service.get_snapshot(stock_code, bars=bars)
        payload["query_id"] = query_id
        _save_etf_query_history_fail_open(
            db,
            query_id=query_id,
            status="completed",
            query_text=str(stock_code or "").strip() or None,
            stock_code=payload.get("stock_code"),
            stock_name=payload.get("stock_name"),
            request_payload=request_payload,
            result_payload=payload,
            error=None,
            created_at=created_at,
            completed_at=datetime.now(),
        )
        latest_bar = (payload.get("daily_bars") or [])[-1] if (payload.get("daily_bars") or []) else None
        emit_etf_query_log(
            {
                "tag": "ETF_QUERY",
                "event": "etf_query_completed",
                "query_id": query_id,
                "query_text": str(stock_code or "").strip() or None,
                "stock_code": payload.get("stock_code"),
                "stock_name": payload.get("stock_name"),
                "instrument_type": payload.get("instrument_type"),
                "bars": bars,
                "status": "completed",
                "price": ((payload.get("quote") or {}).get("price")),
                "change_pct": ((payload.get("quote") or {}).get("change_pct")),
                "daily_bar_count": len(payload.get("daily_bars") or []),
                "latest_bar_date": (latest_bar or {}).get("datetime"),
                "top_holdings_count": len(payload.get("top_holdings") or []),
                "tracking_target": ((payload.get("profile") or {}).get("tracking_target")),
                "data_sources": payload.get("data_sources") or {},
                "error_count": len(payload.get("errors") or []),
                "errors": (payload.get("errors") or [])[:5],
            },
            mirror_logger=logger,
        )
        return EtfMarketSnapshotResponse(**payload)
    except ValueError as exc:
        _save_etf_query_history_fail_open(
            db,
            query_id=query_id,
            status="failed",
            query_text=str(stock_code or "").strip() or None,
            stock_code=str(stock_code or "").strip() or None,
            stock_name=None,
            request_payload=request_payload,
            result_payload=None,
            error=str(exc),
            created_at=created_at,
            completed_at=datetime.now(),
        )
        emit_etf_query_log(
            {
                "tag": "ETF_QUERY",
                "event": "etf_query_failed",
                "query_id": query_id,
                "query_text": str(stock_code or "").strip() or None,
                "stock_code": str(stock_code or "").strip() or None,
                "bars": bars,
                "status": "failed",
                "error": str(exc),
            },
            level="warning",
            mirror_logger=logger,
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        _save_etf_query_history_fail_open(
            db,
            query_id=query_id,
            status="failed",
            query_text=str(stock_code or "").strip() or None,
            stock_code=str(stock_code or "").strip() or None,
            stock_name=None,
            request_payload=request_payload,
            result_payload=None,
            error=str(exc),
            created_at=created_at,
            completed_at=datetime.now(),
        )
        emit_etf_query_log(
            {
                "tag": "ETF_QUERY",
                "event": "etf_query_failed",
                "query_id": query_id,
                "query_text": str(stock_code or "").strip() or None,
                "stock_code": str(stock_code or "").strip() or None,
                "bars": bars,
                "status": "failed",
                "error": str(exc),
            },
            level="warning",
            mirror_logger=logger,
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"ETF 市场快照失败: {exc}"},
        ) from exc


@router.post(
    "/{query_id}/deep-analysis",
    status_code=202,
    response_model=StockDeepAnalysisItemSchema,
    responses={
        202: {"description": "单股深度分析任务已接受", "model": StockDeepAnalysisItemSchema},
        400: {"description": "请求参数错误"},
        404: {"description": "单股查询历史不存在"},
        500: {"description": "服务器错误"},
    },
    summary="基于单股查询生成深度分析",
    description="读取某次单股查询历史结果，生成结构化交易计划和深度分析记录。",
)
def create_stock_deep_analysis(
    query_id: str,
    request: StockDeepAnalysisCreateRequest | None = None,
) -> JSONResponse:
    try:
        task_service = get_stock_deep_analysis_task_service()
        service = StockDeepAnalysisService()
        record = task_service.submit(query_id, force_refresh=bool(request and request.force_refresh))
        payload = _build_stock_deep_analysis_item(service, record, include_context=True)
        return JSONResponse(status_code=202, content=payload.model_dump())
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"深度分析失败: {exc}"},
        ) from exc


@router.get(
    "/deep-analysis/{analysis_id}",
    response_model=StockDeepAnalysisItemSchema,
    responses={
        200: {"description": "单股深度分析详情", "model": StockDeepAnalysisItemSchema},
        404: {"description": "深度分析不存在"},
    },
    summary="获取单股深度分析详情",
)
def get_stock_deep_analysis(analysis_id: str) -> StockDeepAnalysisItemSchema:
    service = StockDeepAnalysisService()
    try:
        record = service.get_analysis(analysis_id)
        return _build_stock_deep_analysis_item(service, record, include_context=True)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/deep-analysis-history",
    response_model=StockDeepAnalysisListResponse,
    summary="获取深度分析历史列表",
)
def list_all_stock_deep_analysis_history(limit: int = 20, stock_code: str | None = None) -> StockDeepAnalysisListResponse:
    service = StockDeepAnalysisService()
    records = service.list_history(stock_code=stock_code, limit=limit)
    return StockDeepAnalysisListResponse(
        items=[_build_stock_deep_analysis_item(service, record, include_context=False) for record in records]
    )


@router.get(
    "/{stock_code}/deep-analysis-history",
    response_model=StockDeepAnalysisListResponse,
    summary="获取某只股票的深度分析历史",
)
def list_stock_deep_analysis_history(stock_code: str, limit: int = 20) -> StockDeepAnalysisListResponse:
    service = StockDeepAnalysisService()
    records = service.list_history(stock_code=stock_code, limit=limit)
    return StockDeepAnalysisListResponse(
        items=[_build_stock_deep_analysis_item(service, record, include_context=False) for record in records]
    )


@router.post(
    "/deep-analysis/{analysis_id}/chat",
    response_model=StockDeepAnalysisChatResponse,
    responses={
        200: {"description": "深度分析追问结果", "model": StockDeepAnalysisChatResponse},
        400: {"description": "请求参数错误"},
        404: {"description": "深度分析不存在"},
    },
    summary="围绕深度分析继续追问",
    description="追问只基于本次深度分析上下文，不触发新的行情或新闻搜索。",
)
def chat_stock_deep_analysis(
    analysis_id: str,
    request: StockDeepAnalysisChatRequest,
) -> StockDeepAnalysisChatResponse:
    service = StockDeepAnalysisService()
    try:
        user_message, assistant_message = service.chat(analysis_id, request.message)
        return StockDeepAnalysisChatResponse(
            analysis_id=analysis_id,
            user_message=_build_stock_deep_analysis_message(user_message),
            assistant_message=_build_stock_deep_analysis_message(assistant_message),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc


@router.post(
    "/deep-analysis/{analysis_id}/alert-rules",
    response_model=StockAlertRuleListResponse,
    responses={
        200: {"description": "由深度分析生成的告警规则", "model": StockAlertRuleListResponse},
        404: {"description": "深度分析不存在"},
    },
    summary="由深度分析生成告警规则",
)
def create_stock_deep_analysis_alert_rules(
    analysis_id: str,
    request: StockDeepAnalysisAlertRulesRequest | None = None,
) -> StockAlertRuleListResponse:
    service = StockDeepAnalysisService()
    try:
        records = service.create_alert_rules(
            analysis_id,
            scan_interval_minutes=(request.scan_interval_minutes if request else 5),
        )
        return StockAlertRuleListResponse(items=[_build_stock_alert_rule_item(record) for record in records])
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/etf-history",
    response_model=EtfQueryHistoryListResponse,
    responses={
        200: {"description": "ETF 查询历史列表", "model": EtfQueryHistoryListResponse},
    },
    summary="获取 ETF 查询历史",
    description="返回最近的 ETF 查询历史，供前端恢复查看历史快照。",
)
def list_etf_history(limit: int = 20, stock_code: str | None = None) -> EtfQueryHistoryListResponse:
    db = get_theme_picker_db()
    records = list_etf_query_records(db, limit=limit, stock_code=stock_code)
    return EtfQueryHistoryListResponse(items=[_build_etf_query_history_item(db, record) for record in records])


@router.get(
    "/etf-history/{query_id}",
    response_model=EtfQueryHistoryItemSchema,
    responses={
        200: {"description": "ETF 查询历史详情", "model": EtfQueryHistoryItemSchema},
        404: {"description": "历史记录不存在"},
    },
    summary="获取 ETF 查询历史详情",
    description="根据 query_id 返回某次 ETF 查询的完整历史结果。",
)
def get_etf_history(query_id: str) -> EtfQueryHistoryItemSchema:
    db = get_theme_picker_db()
    record = get_etf_query_record(db, query_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到 ETF 查询历史: {query_id}"},
        )
    return _build_etf_query_history_item(db, record)


@router.get(
    "/history",
    response_model=StockQueryHistoryListResponse,
    responses={
        200: {"description": "单股查询历史列表", "model": StockQueryHistoryListResponse},
    },
    summary="获取单股查询历史",
    description="返回最近的单股查询历史，供前端历史入口恢复查看过去结果。",
)
def list_single_stock_history(limit: int = 20, stock_code: str | None = None) -> StockQueryHistoryListResponse:
    task_service = get_stock_query_task_service()
    items = [_build_stock_query_history_item(task) for task in task_service.list_tasks(limit=limit, stock_code=stock_code)]
    return StockQueryHistoryListResponse(items=items)


@router.get(
    "/history/{query_id}",
    response_model=StockQueryHistoryItemSchema,
    responses={
        200: {"description": "单股查询历史详情", "model": StockQueryHistoryItemSchema},
        404: {"description": "历史记录不存在"},
    },
    summary="获取单股查询历史详情",
    description="根据 query_id 返回某次单股查询的完整历史结果。",
)
def get_single_stock_history(query_id: str) -> StockQueryHistoryItemSchema:
    task_service = get_stock_query_task_service()
    task = task_service.get_task(query_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到单股查询历史: {query_id}"},
        )
    return _build_stock_query_history_item(task)


def _build_stock_query_history_item(task) -> StockQueryHistoryItemSchema:
    result = StockQueryAnalyzeResponse(**task.result) if isinstance(task.result, dict) else None
    request_payload = task.request_payload if isinstance(task.request_payload, dict) else {}
    return StockQueryHistoryItemSchema(
        query_id=task.task_id,
        status=task.status.value if hasattr(task.status, "value") else str(task.status),
        query_text=str(request_payload.get("query") or request_payload.get("stock_code") or request_payload.get("stock_name") or "") or None,
        stock_code=(result.stock_code if result else None) or request_payload.get("stock_code"),
        stock_name=(result.stock_name if result else None) or request_payload.get("stock_name"),
        instrument_type=result.instrument_type if result else None,
        instrument_label=result.instrument_label if result else None,
        signal=result.signal if result else None,
        error=task.error,
        created_at=task.created_at.isoformat() if task.created_at else "",
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        result=result,
    )


def _build_etf_query_history_item(db, record) -> EtfQueryHistoryItemSchema:
    result_payload = db._safe_json_loads(record.result_payload) if record.result_payload else None
    request_payload = db._safe_json_loads(record.request_payload) or {}
    result = EtfMarketSnapshotResponse(**result_payload) if isinstance(result_payload, dict) else None
    return EtfQueryHistoryItemSchema(
        query_id=record.query_id,
        status=record.status,
        query_text=record.query_text,
        stock_code=(result.stock_code if result else None) or request_payload.get("stock_code") or record.stock_code,
        stock_name=(result.stock_name if result else None) or record.stock_name,
        error=record.error,
        created_at=record.created_at.isoformat() if record.created_at else "",
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        result=result,
    )


def _save_etf_query_history_fail_open(db, **kwargs) -> None:
    try:
        save_etf_query_record(db, **kwargs)
    except Exception as exc:
        logger.warning(
            "ETF 查询历史落库失败，不影响主查询返回: query_id=%s error=%s",
            kwargs.get("query_id"),
            exc,
            exc_info=True,
        )


def _build_stock_deep_analysis_item(
    service: StockDeepAnalysisService,
    record,
    *,
    include_context: bool,
) -> StockDeepAnalysisItemSchema:
    db = service.db
    messages = service.list_messages(record.analysis_id, limit=50) if include_context else []
    return StockDeepAnalysisItemSchema(
        analysis_id=record.analysis_id,
        stock_code=record.stock_code,
        stock_name=record.stock_name,
        source_query_id=record.source_query_id,
        status=record.status,
        action=record.action,
        summary=record.summary,
        trade_plan=db._safe_json_loads(record.trade_plan_json) or {},
        technical=db._safe_json_loads(record.technical_json) or {},
        fundamental=db._safe_json_loads(record.fundamental_json) or {},
        risk=db._safe_json_loads(record.risk_json) or {},
        context_snapshot=(db._safe_json_loads(record.context_snapshot_json) or None) if include_context else None,
        error=record.error,
        created_at=record.created_at.isoformat() if record.created_at else "",
        updated_at=record.updated_at.isoformat() if record.updated_at else "",
        messages=[_build_stock_deep_analysis_message(message) for message in messages],
    )


def _build_stock_deep_analysis_message(record) -> StockDeepAnalysisMessageSchema:
    return StockDeepAnalysisMessageSchema(
        id=record.id,
        analysis_id=record.analysis_id,
        role=record.role,
        content=record.content,
        created_at=record.created_at.isoformat() if record.created_at else "",
    )


def _build_stock_alert_rule_item(record) -> StockAlertRuleItemSchema:
    return StockAlertRuleItemSchema(
        id=record.id,
        stock_code=record.stock_code,
        stock_name=record.stock_name,
        rule_type=record.rule_type,
        threshold_value=record.threshold_value,
        scan_interval_minutes=max(5, int(getattr(record, "scan_interval_minutes", 5) or 5)),
        enabled=bool(record.enabled),
        note=record.note,
        source_query_id=record.source_query_id,
        created_at=record.created_at.isoformat() if record.created_at else "",
        updated_at=record.updated_at.isoformat() if record.updated_at else "",
    )
