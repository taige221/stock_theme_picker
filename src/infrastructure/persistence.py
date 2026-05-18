# -*- coding: utf-8 -*-
"""Theme picker persistence adapters."""

from __future__ import annotations

from typing import Any

from theme_picker.storage import (
    DatabaseManager,
    EtfDailyMetricsSnapshot,
    EtfQueryHistory,
    StockAlertEvent,
    StockAlertRule,
    StockDeepAnalysisHistory,
    StockDeepAnalysisMessage,
    StockQueryHistory,
    StockWatchlist,
    ThemePickerTaskHistory,
    get_db,
)


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


def save_stock_query_record(db: DatabaseManager, **kwargs: Any) -> None:
    db.save_stock_query_history(**kwargs)


def get_stock_query_record(db: DatabaseManager, query_id: str):
    return db.get_stock_query_history(query_id)


def list_stock_query_records(db: DatabaseManager, *, limit: int = 20, stock_code: str | None = None):
    return db.list_stock_query_history(limit=limit, stock_code=stock_code)


def save_etf_query_record(db: DatabaseManager, **kwargs: Any) -> None:
    db.save_etf_query_history(**kwargs)


def get_etf_query_record(db: DatabaseManager, query_id: str):
    return db.get_etf_query_history(query_id)


def list_etf_query_records(db: DatabaseManager, *, limit: int = 20, stock_code: str | None = None):
    return db.list_etf_query_history(limit=limit, stock_code=stock_code)


def save_etf_daily_metrics_snapshots(db: DatabaseManager, rows: list[dict[str, Any]]) -> int:
    return db.save_etf_daily_metrics_snapshots(rows)


def get_latest_etf_daily_metrics_snapshot(db: DatabaseManager, stock_code: str):
    return db.get_latest_etf_daily_metrics_snapshot(stock_code)


def save_stock_belong_boards_cache(db: DatabaseManager, **kwargs: Any) -> None:
    db.save_stock_belong_boards_cache(**kwargs)


def get_stock_belong_boards_cache(db: DatabaseManager, stock_code: str):
    return db.get_stock_belong_boards_cache(stock_code)


def upsert_stock_watchlist_item(db: DatabaseManager, **kwargs: Any):
    return db.upsert_stock_watchlist_item(**kwargs)


def list_stock_watchlist_items(db: DatabaseManager):
    return db.list_stock_watchlist_items()


def get_stock_watchlist_item(db: DatabaseManager, stock_code: str):
    return db.get_stock_watchlist_item(stock_code)


def delete_stock_watchlist_item(db: DatabaseManager, stock_code: str) -> bool:
    return db.delete_stock_watchlist_item(stock_code)


def upsert_stock_alert_rule(db: DatabaseManager, **kwargs: Any):
    return db.upsert_stock_alert_rule(**kwargs)


def list_stock_alert_rules(db: DatabaseManager, *, stock_code: str | None = None):
    return db.list_stock_alert_rules(stock_code=stock_code)


def get_stock_alert_rule(db: DatabaseManager, rule_id: int):
    return db.get_stock_alert_rule(rule_id)


def update_stock_alert_rule(db: DatabaseManager, **kwargs: Any):
    return db.update_stock_alert_rule(**kwargs)


def delete_stock_alert_rule(db: DatabaseManager, rule_id: int) -> bool:
    return db.delete_stock_alert_rule(rule_id)


def create_stock_alert_event(db: DatabaseManager, **kwargs: Any):
    return db.create_stock_alert_event(**kwargs)


def list_stock_alert_events(
    db: DatabaseManager,
    *,
    limit: int = 50,
    stock_code: str | None = None,
    unread_only: bool = False,
):
    return db.list_stock_alert_events(limit=limit, stock_code=stock_code, unread_only=unread_only)


def mark_stock_alert_event_read(db: DatabaseManager, event_id: int):
    return db.mark_stock_alert_event_read(event_id)


def mark_all_stock_alert_events_read(db: DatabaseManager, *, stock_code: str | None = None) -> int:
    return db.mark_all_stock_alert_events_read(stock_code=stock_code)


def save_stock_deep_analysis_record(db: DatabaseManager, **kwargs: Any):
    return db.save_stock_deep_analysis_history(**kwargs)


def get_stock_deep_analysis_record(db: DatabaseManager, analysis_id: str):
    return db.get_stock_deep_analysis_history(analysis_id)


def list_stock_deep_analysis_records(
    db: DatabaseManager,
    *,
    stock_code: str | None = None,
    limit: int = 20,
):
    return db.list_stock_deep_analysis_history(stock_code=stock_code, limit=limit)


def create_stock_deep_analysis_message(db: DatabaseManager, **kwargs: Any):
    return db.create_stock_deep_analysis_message(**kwargs)


def list_stock_deep_analysis_messages(db: DatabaseManager, *, analysis_id: str, limit: int = 50):
    return db.list_stock_deep_analysis_messages(analysis_id=analysis_id, limit=limit)


__all__ = [
    "EtfQueryHistory",
    "EtfDailyMetricsSnapshot",
    "StockQueryHistory",
    "StockAlertEvent",
    "StockAlertRule",
    "StockDeepAnalysisHistory",
    "StockDeepAnalysisMessage",
    "StockWatchlist",
    "ThemePickerTaskHistory",
    "get_theme_picker_db",
    "save_stock_query_record",
    "save_etf_query_record",
    "save_etf_daily_metrics_snapshots",
    "save_task_history",
    "get_stock_query_record",
    "get_etf_query_record",
    "get_latest_etf_daily_metrics_snapshot",
    "get_task_history",
    "list_stock_query_records",
    "list_etf_query_records",
    "save_stock_belong_boards_cache",
    "get_stock_belong_boards_cache",
    "upsert_stock_watchlist_item",
    "list_stock_watchlist_items",
    "get_stock_watchlist_item",
    "delete_stock_watchlist_item",
    "upsert_stock_alert_rule",
    "list_stock_alert_rules",
    "get_stock_alert_rule",
    "update_stock_alert_rule",
    "delete_stock_alert_rule",
    "create_stock_alert_event",
    "list_stock_alert_events",
    "mark_stock_alert_event_read",
    "mark_all_stock_alert_events_read",
    "save_stock_deep_analysis_record",
    "get_stock_deep_analysis_record",
    "list_stock_deep_analysis_records",
    "create_stock_deep_analysis_message",
    "list_stock_deep_analysis_messages",
    "list_task_history",
    "list_task_history_by_statuses",
    "cleanup_task_history",
]
