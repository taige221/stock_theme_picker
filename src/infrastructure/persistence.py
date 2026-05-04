# -*- coding: utf-8 -*-
"""Theme picker persistence adapters."""

from __future__ import annotations

from typing import Any

from theme_picker.storage import DatabaseManager, ThemePickerTaskHistory, get_db


def get_theme_picker_db() -> DatabaseManager:
    return get_db()


def save_task_history(db: DatabaseManager, **kwargs: Any) -> None:
    db.save_theme_picker_task_history(**kwargs)


def get_task_history(db: DatabaseManager, task_id: str):
    return db.get_theme_picker_task_history(task_id)


def list_task_history(db: DatabaseManager, limit: int):
    return db.list_theme_picker_task_history(limit=limit)


def list_task_history_by_statuses(db: DatabaseManager, statuses: list[str], limit: int):
    return db.list_theme_picker_task_history_by_statuses(statuses, limit=limit)


def cleanup_task_history(db: DatabaseManager, *, retention_days: int, batch_size: int) -> int:
    return db.cleanup_theme_picker_task_history(
        retention_days=retention_days,
        batch_size=batch_size,
    )


__all__ = [
    "ThemePickerTaskHistory",
    "get_theme_picker_db",
    "save_task_history",
    "get_task_history",
    "list_task_history",
    "list_task_history_by_statuses",
    "cleanup_task_history",
]
