# -*- coding: utf-8 -*-
"""
===================================
单股查询接口
===================================
"""

from fastapi import APIRouter, HTTPException

from theme_picker.api.schemas import (
    StockQueryAnalyzeRequest,
    StockQueryAnalyzeResponse,
    StockQueryHistoryItemSchema,
    StockQueryHistoryListResponse,
)
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
