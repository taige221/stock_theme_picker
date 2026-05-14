# -*- coding: utf-8 -*-
"""
===================================
单股查询异步任务服务
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
from types import SimpleNamespace
from typing import Any, Dict, Optional

from theme_picker.application.stock_query_service import StockQueryService
from theme_picker.infrastructure.persistence import (
    get_stock_query_record,
    get_theme_picker_db,
    list_stock_query_records,
    save_stock_query_record,
)
from theme_picker.infrastructure.stock_query_logging import emit_stock_query_log

logger = logging.getLogger(__name__)


class StockQueryTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StockQueryTaskInfo:
    task_id: str
    status: StockQueryTaskStatus = StockQueryTaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    request_payload: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StockQueryTaskService:
    _instance: Optional["StockQueryTaskService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 2, max_history: int = 50):
        if getattr(self, "_initialized", False):
            return

        self._max_workers = max_workers
        self._max_history = max_history
        self._executor: Optional[ThreadPoolExecutor] = None
        self._tasks: Dict[str, StockQueryTaskInfo] = {}
        self._lock = threading.RLock()
        self._db = get_theme_picker_db()
        self._initialized = True
        self._recover_unfinished_tasks()

    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="stock_query_task_",
            )
        return self._executor

    @staticmethod
    def _serialize_request_payload(request: Any) -> Dict[str, Any]:
        if hasattr(request, "model_dump"):
            payload = request.model_dump()
            return payload if isinstance(payload, dict) else {}
        if isinstance(request, dict):
            return dict(request)
        return {
            "query": getattr(request, "query", None),
            "stock_code": getattr(request, "stock_code", None),
            "stock_name": getattr(request, "stock_name", None),
        }

    @staticmethod
    def _copy_task(task: StockQueryTaskInfo) -> StockQueryTaskInfo:
        return StockQueryTaskInfo(
            **{
                **task.__dict__,
                "request_payload": dict(task.request_payload),
                "result": dict(task.result) if isinstance(task.result, dict) else task.result,
            }
        )

    def _persist_task(self, task: StockQueryTaskInfo) -> None:
        request_payload = dict(task.request_payload)
        query_text = str(
            request_payload.get("query")
            or request_payload.get("stock_code")
            or request_payload.get("stock_name")
            or ""
        ).strip() or None

        result_payload = task.result if isinstance(task.result, dict) else None
        stock_code = None
        stock_name = None
        signal = None
        if result_payload:
            stock_code = str(result_payload.get("stock_code") or "") or None
            stock_name = str(result_payload.get("stock_name") or "") or None
            signal = str(result_payload.get("signal") or "") or None

        try:
            save_stock_query_record(
                self._db,
                query_id=task.task_id,
                status=task.status.value,
                query_text=query_text,
                stock_code=stock_code,
                stock_name=stock_name,
                signal=signal,
                request_payload=request_payload,
                result_payload=result_payload,
                error=task.error,
                created_at=task.created_at,
                completed_at=task.completed_at,
            )
        except Exception as exc:
            logger.error("[StockQueryTask] 落库失败: %s", exc, exc_info=True)

    def _recover_unfinished_tasks(self) -> None:
        recovered = 0
        for record in list_stock_query_records(self._db, limit=self._max_history):
            if record.status not in {"pending", "processing"}:
                continue
            task = self._deserialize_record(record)
            task.status = StockQueryTaskStatus.PENDING
            task.progress = min(task.progress or 0, 10)
            task.message = "检测到服务重启，单股查询任务已重新入队"
            task.error = None
            task.started_at = None
            task.completed_at = None
            with self._lock:
                self._tasks[task.task_id] = task
            self._persist_task(self._copy_task(task))
            self.executor.submit(self._execute_query, task.task_id)
            recovered += 1
        if recovered > 0:
            logger.info("[StockQueryTask] 服务重启后已恢复 %s 个未完成任务", recovered)

    def _deserialize_record(self, record) -> StockQueryTaskInfo:
        payload = self._db._safe_json_loads(record.request_payload) or {}
        result = self._db._safe_json_loads(record.result_payload) if record.result_payload else None
        return StockQueryTaskInfo(
            task_id=record.query_id,
            status=StockQueryTaskStatus(record.status),
            progress=100 if record.status in {"completed", "failed"} else 0,
            message=None,
            result=result if isinstance(result, dict) else None,
            error=record.error,
            request_payload=payload if isinstance(payload, dict) else {},
            created_at=record.created_at or datetime.now(),
            started_at=None,
            completed_at=record.completed_at,
        )

    def _enqueue_task(self, task: StockQueryTaskInfo) -> StockQueryTaskInfo:
        with self._lock:
            self._tasks[task.task_id] = task
        self._persist_task(self._copy_task(task))
        self.executor.submit(self._execute_query, task.task_id)
        return task

    def submit_query(self, request: Any) -> StockQueryTaskInfo:
        request_payload = self._serialize_request_payload(request)
        task = StockQueryTaskInfo(
            task_id=uuid.uuid4().hex,
            status=StockQueryTaskStatus.PENDING,
            progress=0,
            message="单股查询任务已加入队列",
            request_payload=request_payload,
        )
        return self._enqueue_task(task)

    def get_task(self, task_id: str) -> Optional[StockQueryTaskInfo]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                return self._copy_task(task)
        record = get_stock_query_record(self._db, task_id)
        return self._deserialize_record(record) if record else None

    def list_tasks(self, limit: int = 20, stock_code: Optional[str] = None) -> list[StockQueryTaskInfo]:
        with self._lock:
            memory_tasks = sorted(
                self._tasks.values(),
                key=self._task_activity_at,
                reverse=True,
            )
        def _matches_stock(task: StockQueryTaskInfo) -> bool:
            if not stock_code:
                return True
            result_code = None
            if isinstance(task.result, dict):
                result_code = task.result.get("stock_code")
            request_code = task.request_payload.get("stock_code") if isinstance(task.request_payload, dict) else None
            return result_code == stock_code or request_code == stock_code

        merged: Dict[str, StockQueryTaskInfo] = {
            task.task_id: self._copy_task(task)
            for task in memory_tasks
            if _matches_stock(task)
        }
        for record in list_stock_query_records(self._db, limit=max(1, limit) * 3, stock_code=stock_code):
            merged.setdefault(record.query_id, self._deserialize_record(record))
        tasks = sorted(merged.values(), key=self._task_activity_at, reverse=True)[: max(1, limit)]
        return [self._copy_task(task) for task in tasks]

    def _execute_query(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = StockQueryTaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.progress = 15
            task.message = "正在获取日线、实时行情和基本面"
            request_payload = dict(task.request_payload)
            processing_snapshot = self._copy_task(task)
        self._persist_task(processing_snapshot)

        try:
            service = StockQueryService()
            result = service.analyze(SimpleNamespace(**request_payload), query_id=task_id)
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                task.status = StockQueryTaskStatus.COMPLETED
                task.progress = 100
                task.message = "单股查询已完成"
                task.result = result
                task.error = None
                task.completed_at = datetime.now()
                completed_snapshot = self._copy_task(task)
            self._persist_task(completed_snapshot)
        except Exception as exc:
            logger.error("[StockQueryTask] 任务失败: %s", exc, exc_info=True)
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                task.status = StockQueryTaskStatus.FAILED
                task.progress = 100
                task.message = "单股查询失败"
                task.error = str(exc)
                task.completed_at = datetime.now()
                failed_snapshot = self._copy_task(task)
            self._persist_task(failed_snapshot)
            emit_stock_query_log(
                {
                    "tag": "STOCK_QUERY",
                    "event": "stock_query_failed",
                    "query_id": task_id,
                    "query_text": request_payload.get("query") or request_payload.get("stock_code") or request_payload.get("stock_name"),
                    "stock_code": request_payload.get("stock_code"),
                    "stock_name": request_payload.get("stock_name"),
                    "status": "failed",
                    "error": str(exc),
                },
                level="warning",
                mirror_logger=logger,
            )
        finally:
            self._trim_memory_tasks()

    def _trim_memory_tasks(self) -> None:
        with self._lock:
            if len(self._tasks) <= self._max_history:
                return
            finished = sorted(
                (task for task in self._tasks.values() if task.status in {StockQueryTaskStatus.COMPLETED, StockQueryTaskStatus.FAILED}),
                key=self._task_activity_at,
            )
            overflow = len(self._tasks) - self._max_history
            for task in finished[:overflow]:
                self._tasks.pop(task.task_id, None)

    @staticmethod
    def _task_activity_at(task: StockQueryTaskInfo) -> datetime:
        return task.completed_at or task.started_at or task.created_at


def get_stock_query_task_service() -> StockQueryTaskService:
    return StockQueryTaskService()
