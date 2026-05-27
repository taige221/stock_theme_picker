# -*- coding: utf-8 -*-
"""Theme picker persistence adapters."""

from __future__ import annotations

from typing import Any

from theme_picker.storage import (
    DatabaseManager,
    EtfDailyMetricsSnapshot,
    EtfQueryHistory,
    InformationEvent,
    InformationWatchItem,
    OpenDiscoveryProfile,
    StockCorporateAction,
    StockDailyAux,
    StockDailyRaw,
    StockAlertEvent,
    StockAlertRule,
    StockDeepAnalysisHistory,
    StockDeepAnalysisMessage,
    StockQueryHistory,
    StockWatchlist,
    ThemeFactorScanHistory,
    ThemePickerTaskHistory,
    TradeCalendar,
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


def save_stock_daily_raw_rows(db: DatabaseManager, rows: list[dict[str, Any]]) -> int:
    return db.save_stock_daily_raw_rows(rows)


def get_stock_daily_raw_range(db: DatabaseManager, ts_code: str, start_date, end_date):
    return db.get_stock_daily_raw_range(ts_code, start_date, end_date)


def save_stock_daily_aux_rows(db: DatabaseManager, rows: list[dict[str, Any]]) -> int:
    return db.save_stock_daily_aux_rows(rows)


def get_stock_daily_aux_range(db: DatabaseManager, ts_code: str, start_date, end_date):
    return db.get_stock_daily_aux_range(ts_code, start_date, end_date)


def recompute_stock_daily_aux_features(db: DatabaseManager, ts_code: str, *, sync_batch_id: str | None = None) -> int:
    return db.recompute_stock_daily_aux_features(ts_code, sync_batch_id=sync_batch_id)


def save_stock_corporate_action_rows(db: DatabaseManager, rows: list[dict[str, Any]]) -> int:
    return db.save_stock_corporate_action_rows(rows)


def list_stock_corporate_actions(db: DatabaseManager, *, ts_code: str, start_date=None, end_date=None):
    return db.list_stock_corporate_actions(ts_code=ts_code, start_date=start_date, end_date=end_date)


def save_trade_calendar_rows(db: DatabaseManager, rows: list[dict[str, Any]]) -> int:
    return db.save_trade_calendar_rows(rows)


def list_trade_calendar(db: DatabaseManager, *, exchange: str = "SSE", start_date=None, end_date=None, is_open: int | None = None):
    return db.list_trade_calendar(exchange=exchange, start_date=start_date, end_date=end_date, is_open=is_open)


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


def upsert_information_watch_item(db: DatabaseManager, **kwargs: Any):
    return db.upsert_information_watch_item(**kwargs)


def upsert_open_discovery_profile(db: DatabaseManager, **kwargs: Any):
    return db.upsert_open_discovery_profile(**kwargs)


def list_information_watch_items(db: DatabaseManager, *, enabled_only: bool = False):
    return db.list_information_watch_items(enabled_only=enabled_only)


def list_open_discovery_profiles(db: DatabaseManager, *, enabled_only: bool = False):
    return db.list_open_discovery_profiles(enabled_only=enabled_only)


def get_information_watch_item(db: DatabaseManager, item_id: str):
    return db.get_information_watch_item(item_id)


def delete_information_watch_item(db: DatabaseManager, item_id: str) -> bool:
    return db.delete_information_watch_item(item_id)


def save_information_event(db: DatabaseManager, **kwargs: Any):
    return db.save_information_event(**kwargs)


def get_information_event(db: DatabaseManager, event_id: str):
    return db.get_information_event(event_id)


def get_latest_information_event_by_duplicate_key(db: DatabaseManager, duplicate_key: str):
    return db.get_latest_information_event_by_duplicate_key(duplicate_key)


def list_information_events(
    db: DatabaseManager,
    *,
    limit: int = 50,
    status: str | None = None,
    promoted_only: bool = False,
    source_mode: str | None = None,
):
    return db.list_information_events(limit=limit, status=status, promoted_only=promoted_only, source_mode=source_mode)


def save_theme_factor_scan_record(db: DatabaseManager, **kwargs: Any):
    return db.save_theme_factor_scan_history(**kwargs)


def get_theme_factor_scan_record(db: DatabaseManager, scan_id: str):
    return db.get_theme_factor_scan_history(scan_id)


def list_theme_factor_scan_records(db: DatabaseManager, *, limit: int = 20, event_id: str | None = None):
    return db.list_theme_factor_scan_history(limit=limit, event_id=event_id)


__all__ = [
    "EtfQueryHistory",
    "EtfDailyMetricsSnapshot",
    "StockQueryHistory",
    "StockAlertEvent",
    "StockAlertRule",
    "StockDeepAnalysisHistory",
    "StockDeepAnalysisMessage",
    "StockWatchlist",
    "InformationWatchItem",
    "OpenDiscoveryProfile",
    "InformationEvent",
    "ThemeFactorScanHistory",
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
    "save_stock_daily_raw_rows",
    "get_stock_daily_raw_range",
    "save_stock_daily_aux_rows",
    "get_stock_daily_aux_range",
    "recompute_stock_daily_aux_features",
    "save_stock_corporate_action_rows",
    "list_stock_corporate_actions",
    "save_trade_calendar_rows",
    "list_trade_calendar",
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
    "upsert_information_watch_item",
    "upsert_open_discovery_profile",
    "list_information_watch_items",
    "list_open_discovery_profiles",
    "get_information_watch_item",
    "delete_information_watch_item",
    "save_information_event",
    "get_information_event",
    "get_latest_information_event_by_duplicate_key",
    "list_information_events",
    "save_theme_factor_scan_record",
    "get_theme_factor_scan_record",
    "list_theme_factor_scan_records",
    "list_task_history",
    "list_task_history_by_statuses",
    "cleanup_task_history",
]
