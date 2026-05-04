# -*- coding: utf-8 -*-
"""
===================================
主题选股接口
===================================
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from theme_picker.api.schemas import (
    ThemePickerTaskHistoryItemSchema,
    ThemePickerTaskHistoryListResponse,
    ThemePickerScanRequest,
    ThemePickerScanResponse,
    ThemePickerTaskAcceptedSchema,
    ThemePickerTaskStatusSchema,
    ThemePickerThemeListResponse,
)
from theme_picker.application.picker_service import ThemePickerService
from theme_picker.application.task_service import get_theme_picker_task_service

router = APIRouter()


@router.post(
    "/scan",
    status_code=202,
    response_model=ThemePickerTaskAcceptedSchema,
    responses={
        202: {"description": "主题选股任务已接受", "model": ThemePickerTaskAcceptedSchema},
        400: {"description": "请求参数错误"},
        500: {"description": "服务器错误"},
    },
    summary="执行主题选股",
    description="根据主题、板块或题材输入，异步执行主题选股任务。",
)
def scan_theme_picker(request: ThemePickerScanRequest) -> JSONResponse:
    try:
        task_service = get_theme_picker_task_service()
        task = task_service.submit_scan(request)
        accepted = ThemePickerTaskAcceptedSchema(
            task_id=task.task_id,
            status=task.status.value,
            message=task.message or "主题选股任务已接受",
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
            detail={"error": "internal_error", "message": f"主题选股失败: {exc}"},
        ) from exc


@router.get(
    "/status/{task_id}",
    response_model=ThemePickerTaskStatusSchema,
    responses={
        200: {"description": "主题选股任务状态", "model": ThemePickerTaskStatusSchema},
        404: {"description": "任务不存在"},
    },
    summary="查询主题选股任务状态",
    description="根据 task_id 查询主题选股任务状态；完成时返回 result。",
)
def get_theme_picker_status(task_id: str) -> ThemePickerTaskStatusSchema:
    task_service = get_theme_picker_task_service()
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到主题选股任务: {task_id}"},
        )

    result = ThemePickerScanResponse(**task.result) if isinstance(task.result, dict) else None
    return ThemePickerTaskStatusSchema(
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
    "/history",
    response_model=ThemePickerTaskHistoryListResponse,
    responses={
        200: {"description": "主题选股历史列表", "model": ThemePickerTaskHistoryListResponse},
    },
    summary="获取主题选股历史",
    description="返回最近的主题选股任务历史，供前端历史入口恢复查看过去结果。",
)
def list_theme_picker_history(limit: int = 20) -> ThemePickerTaskHistoryListResponse:
    task_service = get_theme_picker_task_service()
    tasks = task_service.list_tasks(limit=limit)

    items = []
    for task in tasks:
        result = ThemePickerScanResponse(**task.result) if isinstance(task.result, dict) else None
        stocks = result.stocks if result else []
        items.append(
            ThemePickerTaskHistoryItemSchema(
                task_id=task.task_id,
                status=task.status.value,
                progress=task.progress,
                message=task.message,
                created_at=task.created_at.isoformat(),
                started_at=task.started_at.isoformat() if task.started_at else None,
                completed_at=task.completed_at.isoformat() if task.completed_at else None,
                query=result.query if result else None,
                theme_name=result.theme_insight.theme_name if result else None,
                board_mapping_path=result.theme_insight.board_mapping_path if result else None,
                stock_count=len(stocks),
                top_stock_names=[stock.stock_name for stock in stocks[:3]],
                can_retry=bool(task.request_payload) and item_can_retry(task.status.value),
                result=result,
                error=task.error,
            )
        )

    return ThemePickerTaskHistoryListResponse(items=items)


@router.get(
    "/themes",
    response_model=ThemePickerThemeListResponse,
    responses={
        200: {"description": "可用主题列表", "model": ThemePickerThemeListResponse},
        500: {"description": "服务器错误"},
    },
    summary="获取可用主题",
    description="返回当前注册表中可用的主题列表，供前端主题 chips 和建议输入使用。",
)
def list_theme_picker_themes() -> ThemePickerThemeListResponse:
    try:
        service = ThemePickerService()
        return service.list_themes()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取主题列表失败: {exc}"},
        ) from exc


def item_can_retry(status: str) -> bool:
    return status in {"completed", "failed"}


@router.post(
    "/retry/{task_id}",
    status_code=202,
    response_model=ThemePickerTaskAcceptedSchema,
    responses={
        202: {"description": "主题选股重试任务已接受", "model": ThemePickerTaskAcceptedSchema},
        404: {"description": "任务不存在"},
        400: {"description": "任务不可重试"},
        500: {"description": "服务器错误"},
    },
    summary="重试主题选股任务",
    description="基于历史任务的原始请求参数重新提交一次主题选股任务。",
)
def retry_theme_picker_task(task_id: str) -> JSONResponse:
    try:
        task_service = get_theme_picker_task_service()
        task = task_service.retry_task(task_id)
        accepted = ThemePickerTaskAcceptedSchema(
            task_id=task.task_id,
            status=task.status.value,
            message=task.message or "主题选股重试任务已接受",
        )
        return JSONResponse(status_code=202, content=accepted.model_dump())
    except ValueError as exc:
        message = str(exc)
        if "未找到主题选股任务" in message:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": message},
            ) from exc
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": message},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"重试主题选股失败: {exc}"},
        ) from exc
