# -*- coding: utf-8 -*-
"""
===================================
主题选股接口
===================================
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from theme_picker.api.schemas import (
    InformationEventListResponse,
    InformationEventSchema,
    InformationReviewSummarySchema,
    OpenDiscoveryProfileListResponse,
    OpenDiscoveryCandidateListResponse,
    OpenDiscoveryCandidateSchema,
    OpenDiscoveryProfileSchema,
    OpenDiscoveryRunOnceRequest,
    OpenDiscoveryRunOnceResponse,
    InformationWatchItemListResponse,
    InformationWatchItemSchema,
    InformationWatchItemUpsertRequest,
    InformationWatchRunOnceRequest,
    InformationWatchRunOnceResponse,
    ThemeFactorScanItemSchema,
    ThemeFactorScanListResponse,
    ThemeFactorScanRunOnceRequest,
    ThemeFactorScanRunOnceResponse,
    ThemePickerTaskHistoryItemSchema,
    ThemePickerTaskHistoryListResponse,
    ThemePickerScanRequest,
    ThemePickerScanResponse,
    ThemePickerTaskAcceptedSchema,
    ThemePickerTaskStatusSchema,
    ThemePickerThemeListResponse,
)
from theme_picker.application.information_review_service import InformationReviewService
from theme_picker.application.information_watch_service import InformationWatchService
from theme_picker.application.open_discovery_pool_service import OpenDiscoveryPoolService
from theme_picker.application.picker_service import ThemePickerService
from theme_picker.application.theme_factor_scan_service import ThemeFactorScanService
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


@router.get(
    "/information-watch/items",
    response_model=InformationWatchItemListResponse,
    summary="获取信息观察池",
    description="返回当前信息观察池中的观察项，首次调用会自动补齐默认观察项。",
)
def list_information_watch_pool_items() -> InformationWatchItemListResponse:
    service = InformationWatchService()
    records = service.list_items(enabled_only=False)
    return InformationWatchItemListResponse(items=[_build_information_watch_item(record) for record in records])


@router.post(
    "/information-watch/items",
    response_model=InformationWatchItemSchema,
    summary="新增或更新信息观察项",
    description="写入一条信息观察项，供后续定时扫描和 run-once 扫描使用。",
)
def upsert_information_watch_pool_item(request: InformationWatchItemUpsertRequest) -> InformationWatchItemSchema:
    service = InformationWatchService()
    record = service.upsert_item(request.model_dump())
    return _build_information_watch_item(record)


@router.delete(
    "/information-watch/items/{item_id}",
    summary="删除信息观察项",
    description="删除一条信息观察池观察项；后续扫描不再继续使用该主题。",
)
def delete_information_watch_pool_item(item_id: str) -> dict[str, bool]:
    service = InformationWatchService()
    try:
        deleted = service.delete_item(item_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到信息观察项: {item_id}"},
        )
    return {"deleted": True}


@router.post(
    "/information-watch/run-once",
    response_model=InformationWatchRunOnceResponse,
    summary="手动执行一次信息观察池扫描",
    description="立即扫描信息观察池并生成结构化信息事件。",
)
def run_information_watch_once(request: InformationWatchRunOnceRequest) -> InformationWatchRunOnceResponse:
    service = InformationWatchService()
    result = service.run_once(limit=request.limit, item_ids=request.item_ids)
    return InformationWatchRunOnceResponse(
        scanned_items=int(result.get("scanned_items") or 0),
        created_events=int(result.get("created_events") or 0),
        promoted_events=int(result.get("promoted_events") or 0),
        items=[_build_information_event(record) for record in (result.get("items") or [])],
    )


@router.get(
    "/information-discovery/profiles",
    response_model=OpenDiscoveryProfileListResponse,
    summary="获取开放发现池模板",
    description="返回开放发现池默认启用的发现模板，用于全局高价值事件探索。",
)
def list_open_discovery_profiles() -> OpenDiscoveryProfileListResponse:
    service = OpenDiscoveryPoolService()
    records = service.list_profiles(enabled_only=False)
    return OpenDiscoveryProfileListResponse(items=[_build_open_discovery_profile(record) for record in records])


@router.post(
    "/information-discovery/run-once",
    response_model=OpenDiscoveryRunOnceResponse,
    summary="手动执行一次开放发现池扫描",
    description="用全局高价值事件模板扫描新增产业信息，并将结果并入信息事件主表。",
)
def run_open_discovery_once(request: OpenDiscoveryRunOnceRequest) -> OpenDiscoveryRunOnceResponse:
    service = OpenDiscoveryPoolService()
    result = service.run_once(limit=request.limit, profile_ids=request.profile_ids)
    return OpenDiscoveryRunOnceResponse(
        scanned_profiles=int(result.get("scanned_profiles") or 0),
        created_events=int(result.get("created_events") or 0),
        promoted_events=int(result.get("promoted_events") or 0),
        items=[_build_information_event(record) for record in (result.get("items") or [])],
    )


@router.get(
    "/information-discovery/events",
    response_model=InformationEventListResponse,
    summary="获取开放发现事件列表",
    description="返回最近的开放发现池事件，只包含 source_mode=discovery 的事件。",
)
def list_open_discovery_events(
    limit: int = 50,
    status: str | None = None,
    promoted_only: bool = False,
) -> InformationEventListResponse:
    service = OpenDiscoveryPoolService()
    records = service.list_events(limit=limit, status=status, promoted_only=promoted_only)
    return InformationEventListResponse(items=[_build_information_event(record) for record in records])


@router.get(
    "/information-discovery/candidates",
    response_model=OpenDiscoveryCandidateListResponse,
    summary="获取开放发现候选主题",
    description="按 discovery 事件聚类后的观察主题候选，可用于自动沉淀成长期观察项。",
)
def list_open_discovery_candidates(limit: int = 20, promoted_only: bool = True) -> OpenDiscoveryCandidateListResponse:
    service = OpenDiscoveryPoolService()
    items = service.list_candidates(limit=limit, promoted_only=promoted_only)
    return OpenDiscoveryCandidateListResponse(items=[_build_open_discovery_candidate(item) for item in items])


@router.post(
    "/information-discovery/events/{event_id}/watch-item",
    response_model=InformationWatchItemSchema,
    summary="将开放发现事件加入观察池",
    description="把一条 discovery 事件转换成信息观察项，供后续持续扫描与跟踪。",
)
def promote_open_discovery_event_to_watch_item(event_id: str) -> InformationWatchItemSchema:
    service = OpenDiscoveryPoolService()
    try:
        record = service.create_watch_item_from_event(event_id)
    except ValueError as exc:
        message = str(exc)
        if "未找到开放发现事件" in message:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": message},
            ) from exc
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": message},
        ) from exc
    return _build_information_watch_item(record)


@router.post(
    "/information-discovery/candidates/{cluster_key}/watch-item",
    response_model=InformationWatchItemSchema,
    summary="将开放发现候选主题加入观察池",
    description="把一组高频 discovery 聚类候选直接沉淀成观察项，并回链关联事件。",
)
def promote_open_discovery_candidate_to_watch_item(cluster_key: str) -> InformationWatchItemSchema:
    service = OpenDiscoveryPoolService()
    try:
        record = service.create_watch_item_from_candidate(cluster_key)
    except ValueError as exc:
        message = str(exc)
        if "未找到开放发现候选主题" in message:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": message},
            ) from exc
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": message},
        ) from exc
    return _build_information_watch_item(record)


@router.get(
    "/information-watch/events",
    response_model=InformationEventListResponse,
    summary="获取信息事件列表",
    description="返回最近的信息观察池事件，可按状态或 promoted 条件查看。",
)
def list_information_watch_events(
    limit: int = 50,
    status: str | None = None,
    promoted_only: bool = False,
) -> InformationEventListResponse:
    service = InformationWatchService()
    records = service.db.list_information_events(limit=limit, status=status, promoted_only=promoted_only)
    return InformationEventListResponse(items=[_build_information_event(record) for record in records])


@router.post(
    "/theme-factor-scans/run-once",
    response_model=ThemeFactorScanRunOnceResponse,
    summary="手动执行一次主题因子扫描",
    description="根据高质量信息事件，执行一轮主题因子扫描并输出主题/ETF/候选股结果。",
)
def run_theme_factor_scans_once(request: ThemeFactorScanRunOnceRequest) -> ThemeFactorScanRunOnceResponse:
    service = ThemeFactorScanService()
    result = service.run_once(
        limit=request.limit,
        event_ids=request.event_ids,
        min_signal_strength=request.min_signal_strength,
    )
    return ThemeFactorScanRunOnceResponse(
        scanned_events=int(result.get("scanned_events") or 0),
        generated_scans=int(result.get("generated_scans") or 0),
        items=[_build_theme_factor_scan_item(record) for record in (result.get("items") or [])],
    )


@router.get(
    "/theme-factor-scans",
    response_model=ThemeFactorScanListResponse,
    summary="获取主题因子扫描历史",
    description="返回最近的信息事件驱动主题因子扫描结果。",
)
def list_theme_factor_scans(limit: int = 20, event_id: str | None = None) -> ThemeFactorScanListResponse:
    service = ThemeFactorScanService()
    records = service.list_history(limit=limit, event_id=event_id)
    return ThemeFactorScanListResponse(items=[_build_theme_factor_scan_item(record) for record in records])


@router.get(
    "/information-review/summary",
    response_model=InformationReviewSummarySchema,
    summary="获取信息观察与主题因子复盘统计",
    description="返回最近一段时间的信息事件、主题因子扫描与 ETF 确认转化统计。",
)
def get_information_review_summary(days: int = 7) -> InformationReviewSummarySchema:
    service = InformationReviewService()
    return InformationReviewSummarySchema(**service.build_summary(days=days))


def _build_information_watch_item(record) -> InformationWatchItemSchema:
    db = InformationWatchService().db
    return InformationWatchItemSchema(
        item_id=record.item_id,
        name=record.name,
        enabled=bool(record.enabled),
        is_system=InformationWatchService.is_system_item(record.item_id),
        priority=int(record.priority or 100),
        event_type=record.event_type,
        seed_terms=db._safe_json_loads(record.seed_terms_json) or [],
        aliases=db._safe_json_loads(record.aliases_json) or [],
        themes=db._safe_json_loads(record.themes_json) or [],
        chain_tags=db._safe_json_loads(record.chain_tags_json) or [],
        source_tiers=db._safe_json_loads(record.source_tiers_json) or [],
        freshness_days=int(record.freshness_days or 3),
        notes=record.notes,
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


def _build_open_discovery_profile(record) -> OpenDiscoveryProfileSchema:
    db = OpenDiscoveryPoolService().db
    return OpenDiscoveryProfileSchema(
        profile_id=record.profile_id,
        name=record.name,
        enabled=bool(record.enabled),
        priority=int(record.priority or 100),
        event_type=record.event_type,
        query_templates=db._safe_json_loads(record.query_templates_json) or [],
        themes=db._safe_json_loads(record.themes_json) or [],
        chain_tags=db._safe_json_loads(record.chain_tags_json) or [],
        source_tiers=db._safe_json_loads(record.source_tiers_json) or [],
        freshness_days=int(record.freshness_days or 2),
        notes=record.notes,
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


def _build_information_event(record) -> InformationEventSchema:
    service = InformationWatchService()
    db = service.db
    watch_item_name = None
    if getattr(record, "watch_item_id", None):
        watch_item = db.get_information_watch_item(record.watch_item_id)
        if watch_item is not None:
            watch_item_name = watch_item.name
    metadata = db._safe_json_loads(record.metadata_json) or {}
    return InformationEventSchema(
        event_id=record.event_id,
        watch_item_id=record.watch_item_id,
        watch_item_name=watch_item_name,
        title=record.title,
        summary=record.summary,
        event_type=record.event_type,
        impact_direction=record.impact_direction,
        source_mode=getattr(record, "source_mode", "watch") or "watch",
        source_tier=record.source_tier,
        provider=record.provider,
        source_host=str(metadata.get("source_host") or "") or None,
        cluster_key=str(metadata.get("cluster_key") or "") or None,
        cluster_label=str(metadata.get("cluster_label") or "") or None,
        url=record.url,
        published_at=record.published_at.isoformat() if record.published_at else None,
        first_seen_at=record.first_seen_at.isoformat() if record.first_seen_at else None,
        last_seen_at=record.last_seen_at.isoformat() if record.last_seen_at else None,
        is_new_event=bool(record.is_new_event),
        duplicate_key=record.duplicate_key,
        themes=db._safe_json_loads(record.themes_json) or [],
        chain_tags=db._safe_json_loads(record.chain_tags_json) or [],
        entities=db._safe_json_loads(record.entities_json) or {},
        metadata=metadata,
        freshness_score=float(record.freshness_score or 0.0),
        credibility_score=float(record.credibility_score or 0.0),
        signal_strength=float(record.signal_strength or 0.0),
        status=record.status,
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


def _build_open_discovery_candidate(item: dict) -> OpenDiscoveryCandidateSchema:
    latest_published_at = item.get("latest_published_at")
    return OpenDiscoveryCandidateSchema(
        cluster_key=str(item.get("cluster_key") or ""),
        label=str(item.get("label") or ""),
        event_type=str(item.get("event_type") or ""),
        themes=list(item.get("themes") or []),
        chain_tags=list(item.get("chain_tags") or []),
        event_count=int(item.get("event_count") or 0),
        promoted_count=int(item.get("promoted_count") or 0),
        source_hosts=list(item.get("source_hosts") or []),
        source_tiers=list(item.get("source_tiers") or []),
        hard_source_confirmed=bool(item.get("hard_source_confirmed")),
        candidate_score=float(item.get("candidate_score") or 0.0),
        representative_event_id=item.get("representative_event_id"),
        representative_title=item.get("representative_title"),
        latest_published_at=latest_published_at.isoformat() if hasattr(latest_published_at, "isoformat") else latest_published_at,
        watch_item_id=item.get("watch_item_id"),
        watch_item_name=item.get("watch_item_name"),
        status=str(item.get("status") or "candidate"),
    )


def _build_theme_factor_scan_item(record) -> ThemeFactorScanItemSchema:
    db = ThemeFactorScanService().db
    return ThemeFactorScanItemSchema(
        scan_id=record.scan_id,
        event_id=record.event_id,
        theme_id=record.theme_id,
        theme_name=record.theme_name,
        status=record.status,
        event_score=record.event_score,
        etf_confirmation_score=record.etf_confirmation_score,
        leader_confirmation_score=record.leader_confirmation_score,
        theme_factor_score=record.theme_factor_score,
        result=db._safe_json_loads(record.result_payload) or {},
        error=record.error,
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )
