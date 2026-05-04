# -*- coding: utf-8 -*-
"""
===================================
主题选股异步任务服务
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

from theme_picker.application.picker_service import ThemePickerService
from theme_picker.infrastructure.persistence import (
    ThemePickerTaskHistory,
    cleanup_task_history,
    get_task_history,
    get_theme_picker_db,
    list_task_history,
    list_task_history_by_statuses,
    save_task_history,
)
from theme_picker.infrastructure.runtime import get_theme_picker_config

logger = logging.getLogger(__name__)


class ThemePickerTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ThemePickerTaskInfo:
    task_id: str
    status: ThemePickerTaskStatus = ThemePickerTaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    request_payload: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ThemePickerTaskService:
    _instance: Optional["ThemePickerTaskService"] = None
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
        self._tasks: Dict[str, ThemePickerTaskInfo] = {}
        self._lock = threading.RLock()
        self._db = get_theme_picker_db()
        self._config = get_theme_picker_config()
        self._initialized = True
        self._recover_unfinished_tasks()
        self._cleanup_persisted_history()

    @classmethod
    def reset_instance(cls) -> None:
        with cls._instance_lock:
            instance = cls._instance
            if instance is not None and instance._executor is not None:
                instance._executor.shutdown(wait=False, cancel_futures=True)
            cls._instance = None

    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="theme_picker_task_",
            )
        return self._executor

    @staticmethod
    def _copy_task(task: ThemePickerTaskInfo) -> ThemePickerTaskInfo:
        return ThemePickerTaskInfo(
            **{
                **task.__dict__,
                "request_payload": dict(task.request_payload),
                "result": dict(task.result) if isinstance(task.result, dict) else task.result,
            }
        )

    def _persist_task(self, task: ThemePickerTaskInfo) -> None:
        result_payload = task.result if isinstance(task.result, dict) else None
        normalized_result, changed = ThemePickerService.normalize_response_payload(result_payload, db=self._db)
        if changed:
            task.result = normalized_result
        try:
            save_task_history(
                self._db,
                task_id=task.task_id,
                status=task.status.value,
                progress=task.progress,
                message=task.message,
                error=task.error,
                request_payload=task.request_payload,
                result_payload=normalized_result if isinstance(normalized_result, dict) else None,
                created_at=task.created_at,
                started_at=task.started_at,
                completed_at=task.completed_at,
            )
        except Exception as exc:
            logger.error("[ThemePickerTask] 落库失败: %s", exc, exc_info=True)

    def _cleanup_persisted_history(self) -> None:
        try:
            removed = cleanup_task_history(
                self._db,
                retention_days=self._config.theme_picker_task_history_retention_days,
                batch_size=self._config.theme_picker_task_history_cleanup_batch_size,
            )
            if removed > 0:
                logger.info("[ThemePickerTask] 已清理 %s 条过期历史记录", removed)
        except Exception as exc:
            logger.error("[ThemePickerTask] 清理历史失败: %s", exc, exc_info=True)

    def _recover_unfinished_tasks(self) -> None:
        try:
            records = list_task_history_by_statuses(
                self._db,
                ['pending', 'processing'],
                limit=self._max_history,
            )
        except Exception as exc:
            logger.error("[ThemePickerTask] 加载未完成任务失败: %s", exc, exc_info=True)
            return

        if not records:
            return

        recovered_count = 0
        with self._lock:
            for record in records:
                task = self._deserialize_persisted_task(record)
                task.status = ThemePickerTaskStatus.PENDING
                task.progress = min(task.progress or 0, 10)
                task.message = "检测到服务重启，任务已重新入队"
                task.error = None
                task.started_at = None
                task.completed_at = None
                self._tasks[task.task_id] = task
                self._persist_task(self._copy_task(task))
                self.executor.submit(self._execute_scan, task.task_id)
                recovered_count += 1

        if recovered_count > 0:
            logger.info("[ThemePickerTask] 服务重启后已恢复 %s 个未完成任务", recovered_count)

    def _enqueue_task(self, task: ThemePickerTaskInfo) -> ThemePickerTaskInfo:
        with self._lock:
            self._tasks[task.task_id] = task
        self._persist_task(self._copy_task(task))
        self.executor.submit(self._execute_scan, task.task_id)
        return task

    def _deserialize_persisted_task(self, record: ThemePickerTaskHistory) -> ThemePickerTaskInfo:
        payload = self._db._safe_json_loads(record.request_payload) or {}
        result = self._db._safe_json_loads(record.result_payload) if record.result_payload else None
        normalized_result, changed = ThemePickerService.normalize_response_payload(
            result if isinstance(result, dict) else None,
            db=self._db,
        )
        if changed:
            try:
                save_task_history(
                    self._db,
                    task_id=record.task_id,
                    status=record.status,
                    progress=record.progress or 0,
                    message=record.message,
                    error=record.error,
                    request_payload=payload if isinstance(payload, dict) else {},
                    result_payload=normalized_result if isinstance(normalized_result, dict) else None,
                    created_at=record.created_at,
                    started_at=record.started_at,
                    completed_at=record.completed_at,
                )
            except Exception as exc:
                logger.error("[ThemePickerTask] 修复历史结果去重失败: %s", exc, exc_info=True)
        return ThemePickerTaskInfo(
            task_id=record.task_id,
            status=ThemePickerTaskStatus(record.status),
            progress=record.progress or 0,
            message=record.message,
            result=normalized_result if isinstance(normalized_result, dict) else normalized_result,
            error=record.error,
            request_payload=payload if isinstance(payload, dict) else {},
            created_at=record.created_at or datetime.now(),
            started_at=record.started_at,
            completed_at=record.completed_at,
        )

    def submit_scan(self, request: Any) -> ThemePickerTaskInfo:
        if hasattr(request, "model_dump"):
            request_payload = request.model_dump()
        elif isinstance(request, dict):
            request_payload = dict(request)
        else:
            raise TypeError("request must be a dict-like payload or Pydantic model")

        task_id = uuid.uuid4().hex
        task = ThemePickerTaskInfo(
            task_id=task_id,
            status=ThemePickerTaskStatus.PENDING,
            progress=0,
            message="主题选股任务已加入队列",
            request_payload=request_payload,
        )
        return self._enqueue_task(task)

    def retry_task(self, task_id: str) -> ThemePickerTaskInfo:
        persisted = get_task_history(self._db, task_id)
        if persisted is None:
            raise ValueError(f"未找到主题选股任务: {task_id}")
        if persisted.status not in {"completed", "failed"}:
            raise ValueError(f"任务 {task_id} 当前状态为 {persisted.status}，暂不允许重试")

        original = self._deserialize_persisted_task(persisted)
        if not original.request_payload:
            raise ValueError(f"任务 {task_id} 缺少原始请求参数，无法重试")

        retry_task = ThemePickerTaskInfo(
            task_id=uuid.uuid4().hex,
            status=ThemePickerTaskStatus.PENDING,
            progress=0,
            message=f"已基于历史任务 {task_id} 重新加入队列",
            request_payload=dict(original.request_payload),
        )
        return self._enqueue_task(retry_task)

    def get_task(self, task_id: str) -> Optional[ThemePickerTaskInfo]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                persisted = get_task_history(self._db, task_id)
                return self._deserialize_persisted_task(persisted) if persisted else None
            return self._copy_task(task)

    def list_tasks(self, limit: int = 20) -> list[ThemePickerTaskInfo]:
        with self._lock:
            memory_tasks = sorted(
                self._tasks.values(),
                key=self._task_activity_at,
                reverse=True,
            )

        merged: Dict[str, ThemePickerTaskInfo] = {
            task.task_id: self._copy_task(task)
            for task in memory_tasks
        }
        for persisted in list_task_history(self._db, limit=max(1, limit) * 3):
            merged.setdefault(persisted.task_id, self._deserialize_persisted_task(persisted))

        tasks = sorted(
            merged.values(),
            key=self._task_activity_at,
            reverse=True,
        )[: max(1, limit)]
        return [self._copy_task(task) for task in tasks]

    def _execute_scan(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = ThemePickerTaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.progress = 15
            task.message = "正在执行主题、板块与新闻筛选"
            request_payload = dict(task.request_payload)
            processing_snapshot = self._copy_task(task)
        self._persist_task(processing_snapshot)

        try:
            service = ThemePickerService()
            result = service.scan(SimpleNamespace(**request_payload))

            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                task.status = ThemePickerTaskStatus.COMPLETED
                task.progress = 100
                task.completed_at = datetime.now()
                task.result = result
                task.message = "主题选股完成"
                completed_snapshot = self._copy_task(task)
                self._cleanup_locked()
            self._persist_task(completed_snapshot)
            self._cleanup_persisted_history()
        except Exception as exc:
            logger.error("[ThemePickerTask] 任务失败: %s", exc, exc_info=True)
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                task.status = ThemePickerTaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(exc)
                task.message = f"主题选股失败: {str(exc)[:80]}"
                failed_snapshot = self._copy_task(task)
                self._cleanup_locked()
            self._persist_task(failed_snapshot)
            self._cleanup_persisted_history()

    def _cleanup_locked(self) -> None:
        if len(self._tasks) <= self._max_history:
            return

        removable = sorted(
            [
                task
                for task in self._tasks.values()
                if task.status in (ThemePickerTaskStatus.COMPLETED, ThemePickerTaskStatus.FAILED)
            ],
            key=self._task_activity_at,
        )
        overflow = len(self._tasks) - self._max_history
        for task in removable[:overflow]:
            self._tasks.pop(task.task_id, None)

    @staticmethod
    def _task_activity_at(task: ThemePickerTaskInfo) -> datetime:
        return task.completed_at or task.started_at or task.created_at


def get_theme_picker_task_service() -> ThemePickerTaskService:
    return ThemePickerTaskService()
