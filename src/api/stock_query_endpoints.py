# -*- coding: utf-8 -*-
"""
===================================
单股查询接口
===================================
"""

from fastapi import APIRouter, HTTPException

from theme_picker.api.schemas import (
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
)
from theme_picker.application.stock_deep_analysis_service import StockDeepAnalysisService
from theme_picker.application.stock_query_service import StockQueryService
from theme_picker.infrastructure.persistence import (
    get_stock_query_record,
    get_theme_picker_db,
    list_stock_query_records,
)

router = APIRouter()


@router.post(
    "/analyze",
    response_model=StockQueryAnalyzeResponse,
    responses={
        200: {"description": "单股查询结果", "model": StockQueryAnalyzeResponse},
        400: {"description": "请求参数错误"},
        500: {"description": "服务器错误"},
    },
    summary="执行单股查询",
    description="根据股票代码或名称，返回该股票的技术状态、关联主题以及入选/未入选原因。",
)
def analyze_single_stock(request: StockQueryAnalyzeRequest) -> StockQueryAnalyzeResponse:
    try:
        service = StockQueryService()
        payload = service.analyze(request)
        return StockQueryAnalyzeResponse(**payload)
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


@router.post(
    "/{query_id}/deep-analysis",
    response_model=StockDeepAnalysisItemSchema,
    responses={
        200: {"description": "单股深度分析结果", "model": StockDeepAnalysisItemSchema},
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
) -> StockDeepAnalysisItemSchema:
    try:
        service = StockDeepAnalysisService()
        record = service.create_from_query(query_id, force_refresh=bool(request and request.force_refresh))
        return _build_stock_deep_analysis_item(service, record, include_context=True)
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
    "/history",
    response_model=StockQueryHistoryListResponse,
    responses={
        200: {"description": "单股查询历史列表", "model": StockQueryHistoryListResponse},
    },
    summary="获取单股查询历史",
    description="返回最近的单股查询历史，供前端历史入口恢复查看过去结果。",
)
def list_single_stock_history(limit: int = 20, stock_code: str | None = None) -> StockQueryHistoryListResponse:
    db = get_theme_picker_db()
    records = list_stock_query_records(db, limit=limit, stock_code=stock_code)
    items = [_build_stock_query_history_item(db, record) for record in records]
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
    db = get_theme_picker_db()
    record = get_stock_query_record(db, query_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到单股查询历史: {query_id}"},
        )
    return _build_stock_query_history_item(db, record)


def _build_stock_query_history_item(db, record) -> StockQueryHistoryItemSchema:
    result_payload = db._safe_json_loads(record.result_payload) if record.result_payload else None
    result = StockQueryAnalyzeResponse(**result_payload) if isinstance(result_payload, dict) else None
    return StockQueryHistoryItemSchema(
        query_id=record.query_id,
        status=record.status,
        query_text=record.query_text,
        stock_code=record.stock_code,
        stock_name=record.stock_name,
        signal=record.signal,
        error=record.error,
        created_at=record.created_at.isoformat() if record.created_at else "",
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        result=result,
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
