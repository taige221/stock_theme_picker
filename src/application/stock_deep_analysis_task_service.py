# -*- coding: utf-8 -*-
"""
===================================
单股深度分析异步任务服务
===================================
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from theme_picker.application.stock_deep_analysis_service import StockDeepAnalysisService
from theme_picker.infrastructure.persistence import (
    get_stock_deep_analysis_record,
    get_stock_query_record,
    get_theme_picker_db,
    list_stock_deep_analysis_records,
    save_stock_deep_analysis_record,
)

logger = logging.getLogger(__name__)


class StockDeepAnalysisTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StockDeepAnalysisTaskInfo:
    analysis_id: str
    query_id: str
    stock_code: str
    stock_name: str
    force_refresh: bool = False
    status: StockDeepAnalysisTaskStatus = StockDeepAnalysisTaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StockDeepAnalysisTaskService:
    _instance: Optional["StockDeepAnalysisTaskService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 2, max_history: int = 100):
        if getattr(self, "_initialized", False):
            return

        self._max_workers = max_workers
        self._max_history = max_history
        self._executor: Optional[ThreadPoolExecutor] = None
        self._tasks: Dict[str, StockDeepAnalysisTaskInfo] = {}
        self._lock = threading.RLock()
        self._db = get_theme_picker_db()
        self._initialized = True
        self._recover_unfinished_tasks()

    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="stock_deep_analysis_task_",
            )
        return self._executor

    def submit(self, query_id: str, *, force_refresh: bool = False):
        normalized_query_id = str(query_id or "").strip()
        if not normalized_query_id:
            raise ValueError("query_id 不能为空")

        if not force_refresh:
            existing = self._find_existing(query_id=normalized_query_id)
            if existing is not None:
                return existing

        stock_code, stock_name = self._resolve_query_target(normalized_query_id)
        analysis_id = uuid.uuid4().hex
        task = StockDeepAnalysisTaskInfo(
            analysis_id=analysis_id,
            query_id=normalized_query_id,
            stock_code=stock_code,
            stock_name=stock_name,
            force_refresh=force_refresh,
            status=StockDeepAnalysisTaskStatus.PENDING,
            progress=0,
            message="深度分析任务已加入队列",
        )
        pending_record = self._persist_task(task)
        with self._lock:
            self._tasks[analysis_id] = task
        self.executor.submit(self._execute_task, analysis_id)
        self._trim_memory_tasks()
        return pending_record

    def _find_existing(self, *, query_id: str):
        latest_completed = None
        for record in list_stock_deep_analysis_records(self._db, limit=self._max_history):
            if record.source_query_id != query_id:
                continue
            if record.status in {"pending", "processing"}:
                return record
            if record.status == "completed" and latest_completed is None:
                latest_completed = record
        return latest_completed

    def _resolve_query_target(self, query_id: str) -> tuple[str, str]:
        query_record = get_stock_query_record(self._db, query_id)
        if query_record is None:
            raise LookupError(f"未找到单股查询历史: {query_id}")
        result_payload = self._db._safe_json_loads(query_record.result_payload)
        if not isinstance(result_payload, dict):
            raise ValueError(f"单股查询历史缺少可用于深度分析的结果: {query_id}")

        stock_code = str(
            result_payload.get("stock_code")
            or getattr(query_record, "stock_code", "")
            or ""
        ).strip().upper()
        stock_name = str(
            result_payload.get("stock_name")
            or getattr(query_record, "stock_name", "")
            or stock_code
        ).strip() or stock_code
        if not stock_code:
            raise ValueError(f"单股查询历史缺少 stock_code: {query_id}")
        return stock_code, stock_name

    def _persist_task(self, task: StockDeepAnalysisTaskInfo):
        context_snapshot = {
            "source": "stock_query_history",
            "query_id": task.query_id,
            "task": {
                "force_refresh": bool(task.force_refresh),
                "progress": int(task.progress),
                "message": task.message,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            },
        }
        return save_stock_deep_analysis_record(
            self._db,
            analysis_id=task.analysis_id,
            stock_code=task.stock_code,
            stock_name=task.stock_name,
            source_query_id=task.query_id,
            status=task.status.value,
            context_snapshot=context_snapshot,
            error=task.error,
        )

    def _recover_unfinished_tasks(self) -> None:
        recovered = 0
        for record in list_stock_deep_analysis_records(self._db, limit=self._max_history):
            if record.status not in {"pending", "processing"}:
                continue
            if not record.source_query_id:
                continue
            context_snapshot = self._db._safe_json_loads(record.context_snapshot_json) or {}
            task_meta = context_snapshot.get("task") if isinstance(context_snapshot, dict) else {}
            task = StockDeepAnalysisTaskInfo(
                analysis_id=record.analysis_id,
                query_id=record.source_query_id,
                stock_code=record.stock_code,
                stock_name=record.stock_name,
                force_refresh=bool(task_meta.get("force_refresh")) if isinstance(task_meta, dict) else False,
                status=StockDeepAnalysisTaskStatus.PENDING,
                progress=min(int(task_meta.get("progress") or 0), 10) if isinstance(task_meta, dict) else 0,
                message="检测到服务重启，深度分析任务已重新入队",
                error=None,
                created_at=record.created_at or datetime.now(),
                started_at=None,
                completed_at=None,
            )
            with self._lock:
                self._tasks[task.analysis_id] = task
            self._persist_task(task)
            self.executor.submit(self._execute_task, task.analysis_id)
            recovered += 1
        if recovered > 0:
            logger.info("[StockDeepAnalysisTask] 服务重启后已恢复 %s 个未完成任务", recovered)

    def _execute_task(self, analysis_id: str) -> None:
        with self._lock:
            task = self._tasks.get(analysis_id)
            if task is None:
                return
            task.status = StockDeepAnalysisTaskStatus.PROCESSING
            task.progress = 20
            task.message = "正在生成结构化交易计划与风险判断"
            task.started_at = datetime.now()
            self._persist_task(task)

        try:
            service = StockDeepAnalysisService(db=self._db)
            service.create_from_query(
                task.query_id,
                force_refresh=True,
                analysis_id=analysis_id,
            )
            with self._lock:
                task = self._tasks.get(analysis_id)
                if task is None:
                    return
                task.status = StockDeepAnalysisTaskStatus.COMPLETED
                task.progress = 100
                task.message = "深度分析已完成"
                task.error = None
                task.completed_at = datetime.now()
        except Exception as exc:
            logger.error("[StockDeepAnalysisTask] 任务失败: %s", exc, exc_info=True)
            with self._lock:
                task = self._tasks.get(analysis_id)
                if task is None:
                    return
                task.status = StockDeepAnalysisTaskStatus.FAILED
                task.progress = 100
                task.message = "深度分析失败"
                task.error = str(exc)
                task.completed_at = datetime.now()
                self._persist_task(task)
        else:
            record = get_stock_deep_analysis_record(self._db, analysis_id)
            if record is not None and task is not None:
                save_stock_deep_analysis_record(
                    self._db,
                    analysis_id=record.analysis_id,
                    stock_code=record.stock_code,
                    stock_name=record.stock_name,
                    source_query_id=record.source_query_id,
                    status=StockDeepAnalysisTaskStatus.COMPLETED.value,
                    action=record.action,
                    summary=record.summary,
                    trade_plan=self._db._safe_json_loads(record.trade_plan_json) or {},
                    technical=self._db._safe_json_loads(record.technical_json) or {},
                    fundamental=self._db._safe_json_loads(record.fundamental_json) or {},
                    risk=self._db._safe_json_loads(record.risk_json) or {},
                    context_snapshot=self._db._safe_json_loads(record.context_snapshot_json) or {},
                    error=None,
                )
        finally:
            self._trim_memory_tasks()

    def _trim_memory_tasks(self) -> None:
        with self._lock:
            if len(self._tasks) <= self._max_history:
                return
            finished = sorted(
                (
                    task
                    for task in self._tasks.values()
                    if task.status in {StockDeepAnalysisTaskStatus.COMPLETED, StockDeepAnalysisTaskStatus.FAILED}
                ),
                key=self._task_activity_at,
            )
            overflow = len(self._tasks) - self._max_history
            for task in finished[:overflow]:
                self._tasks.pop(task.analysis_id, None)

    @staticmethod
    def _task_activity_at(task: StockDeepAnalysisTaskInfo) -> datetime:
        return task.completed_at or task.started_at or task.created_at


def get_stock_deep_analysis_task_service() -> StockDeepAnalysisTaskService:
    return StockDeepAnalysisTaskService()
