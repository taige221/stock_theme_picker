# -*- coding: utf-8 -*-
"""Standalone storage layer for theme picker."""

from __future__ import annotations

import atexit
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    and_,
    create_engine,
    delete,
    desc,
    func,
    or_,
    select,
    text,
)
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import insert as duckdb_insert
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from theme_picker.config import get_config

logger = logging.getLogger(__name__)

Base = declarative_base()
_UNSET = object()
UNSET = _UNSET
SQLITE_FILE_HEADER = b"SQLite format 3\x00"


def _id_column(sequence_name: str) -> Column:
    return Column(Integer, Sequence(sequence_name), primary_key=True)


def _is_sqlite_database_file(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_FILE_HEADER)) == SQLITE_FILE_HEADER
    except OSError:
        return False


class StockDaily(Base):
    __tablename__ = "stock_daily"

    id = _id_column("stock_daily_id_seq")
    code = Column(String(16), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    pct_chg = Column(Float)
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    volume_ratio = Column(Float)
    data_source = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("code", "date", name="uix_theme_picker_code_date"),
        Index("ix_theme_picker_code_date", "code", "date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "pct_chg": self.pct_chg,
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "volume_ratio": self.volume_ratio,
            "data_source": self.data_source,
        }


class StockDailyRaw(Base):
    __tablename__ = "stock_daily_raw"

    id = _id_column("stock_daily_raw_id_seq")
    ts_code = Column(String(16), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    pre_close = Column(Float, nullable=True)
    vol = Column(Float, nullable=True)
    amount = Column(Float, nullable=True)
    adj_factor = Column(Float, nullable=True)
    open_qfq = Column(Float, nullable=True)
    high_qfq = Column(Float, nullable=True)
    low_qfq = Column(Float, nullable=True)
    close_qfq = Column(Float, nullable=True)
    sync_batch_id = Column(String(64), nullable=True, index=True)
    data_source = Column(String(64), nullable=True)
    ingested_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_stock_daily_raw_code_date"),
        Index("ix_stock_daily_raw_code_date", "ts_code", "trade_date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts_code": self.ts_code,
            "trade_date": self.trade_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "pre_close": self.pre_close,
            "vol": self.vol,
            "amount": self.amount,
            "adj_factor": self.adj_factor,
            "open_qfq": self.open_qfq,
            "high_qfq": self.high_qfq,
            "low_qfq": self.low_qfq,
            "close_qfq": self.close_qfq,
            "sync_batch_id": self.sync_batch_id,
            "data_source": self.data_source,
            "ingested_at": self.ingested_at,
            "updated_at": self.updated_at,
        }


class StockDailyAux(Base):
    __tablename__ = "stock_daily_aux"

    id = _id_column("stock_daily_aux_id_seq")
    ts_code = Column(String(16), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    turnover_rate = Column(Float, nullable=True)
    turnover_rate_f = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)
    float_share = Column(Float, nullable=True)
    free_share = Column(Float, nullable=True)
    total_share = Column(Float, nullable=True)
    circ_mv = Column(Float, nullable=True)
    total_mv = Column(Float, nullable=True)
    up_limit = Column(Float, nullable=True)
    down_limit = Column(Float, nullable=True)
    turnover_rate_median_20 = Column(Float, nullable=True)
    atr_pct_20 = Column(Float, nullable=True)
    style_bucket = Column(String(32), nullable=True, index=True)
    is_suspended = Column(Integer, nullable=True, index=True)
    suspend_type = Column(String(8), nullable=True)
    sync_batch_id = Column(String(64), nullable=True, index=True)
    data_source = Column(String(64), nullable=True)
    ingested_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_stock_daily_aux_code_date"),
        Index("ix_stock_daily_aux_code_date", "ts_code", "trade_date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts_code": self.ts_code,
            "trade_date": self.trade_date,
            "turnover_rate": self.turnover_rate,
            "turnover_rate_f": self.turnover_rate_f,
            "volume_ratio": self.volume_ratio,
            "float_share": self.float_share,
            "free_share": self.free_share,
            "total_share": self.total_share,
            "circ_mv": self.circ_mv,
            "total_mv": self.total_mv,
            "up_limit": self.up_limit,
            "down_limit": self.down_limit,
            "turnover_rate_median_20": self.turnover_rate_median_20,
            "atr_pct_20": self.atr_pct_20,
            "style_bucket": self.style_bucket,
            "is_suspended": self.is_suspended,
            "suspend_type": self.suspend_type,
            "sync_batch_id": self.sync_batch_id,
            "data_source": self.data_source,
            "ingested_at": self.ingested_at,
            "updated_at": self.updated_at,
        }


class StockCorporateAction(Base):
    __tablename__ = "stock_corporate_action"

    id = _id_column("stock_corporate_action_id_seq")
    action_key = Column(String(128), nullable=False, unique=True, index=True)
    ts_code = Column(String(16), nullable=False, index=True)
    ann_date = Column(Date, nullable=True, index=True)
    record_date = Column(Date, nullable=True, index=True)
    ex_date = Column(Date, nullable=True, index=True)
    pay_date = Column(Date, nullable=True, index=True)
    div_proc = Column(String(32), nullable=True, index=True)
    stk_div = Column(Float, nullable=True)
    cash_div = Column(Float, nullable=True)
    cash_div_tax = Column(Float, nullable=True)
    sync_batch_id = Column(String(64), nullable=True, index=True)
    data_source = Column(String(64), nullable=True)
    ingested_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_corporate_action_code_ex_date", "ts_code", "ex_date"),
        Index("ix_stock_corporate_action_code_record_date", "ts_code", "record_date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_key": self.action_key,
            "ts_code": self.ts_code,
            "ann_date": self.ann_date,
            "record_date": self.record_date,
            "ex_date": self.ex_date,
            "pay_date": self.pay_date,
            "div_proc": self.div_proc,
            "stk_div": self.stk_div,
            "cash_div": self.cash_div,
            "cash_div_tax": self.cash_div_tax,
            "sync_batch_id": self.sync_batch_id,
            "data_source": self.data_source,
            "ingested_at": self.ingested_at,
            "updated_at": self.updated_at,
        }


class TradeCalendar(Base):
    __tablename__ = "trade_calendar"

    id = _id_column("trade_calendar_id_seq")
    exchange = Column(String(16), nullable=False, index=True)
    cal_date = Column(Date, nullable=False, index=True)
    is_open = Column(Integer, nullable=False, index=True)
    pretrade_date = Column(Date, nullable=True)
    sync_batch_id = Column(String(64), nullable=True, index=True)
    data_source = Column(String(64), nullable=True)
    ingested_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("exchange", "cal_date", name="uix_trade_calendar_exchange_date"),
        Index("ix_trade_calendar_exchange_date", "exchange", "cal_date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exchange": self.exchange,
            "cal_date": self.cal_date,
            "is_open": self.is_open,
            "pretrade_date": self.pretrade_date,
            "sync_batch_id": self.sync_batch_id,
            "data_source": self.data_source,
            "ingested_at": self.ingested_at,
            "updated_at": self.updated_at,
        }


class ThemePickerTaskHistory(Base):
    __tablename__ = "theme_picker_task_history"

    id = _id_column("theme_picker_task_history_id_seq")
    task_id = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, index=True)
    progress = Column(Integer, nullable=False, default=0)
    message = Column(Text)
    error = Column(Text)
    request_payload = Column(Text, nullable=False)
    result_payload = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (Index("ix_theme_picker_task_created", "created_at"),)


class StockQueryHistory(Base):
    __tablename__ = "stock_query_history"

    id = _id_column("stock_query_history_id_seq")
    query_id = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, index=True, default="completed")
    query_text = Column(String(128), nullable=True, index=True)
    stock_code = Column(String(16), nullable=True, index=True)
    stock_name = Column(String(64), nullable=True)
    signal = Column(String(32), nullable=True)
    error = Column(Text)
    request_payload = Column(Text, nullable=False)
    result_payload = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_stock_query_history_created", "created_at"),
        Index("ix_stock_query_history_stock_created", "stock_code", "created_at"),
    )


class EtfQueryHistory(Base):
    __tablename__ = "etf_query_history"

    id = _id_column("etf_query_history_id_seq")
    query_id = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, index=True, default="completed")
    query_text = Column(String(128), nullable=True, index=True)
    stock_code = Column(String(16), nullable=True, index=True)
    stock_name = Column(String(64), nullable=True)
    error = Column(Text)
    request_payload = Column(Text, nullable=False)
    result_payload = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_etf_query_history_created", "created_at"),
        Index("ix_etf_query_history_stock_created", "stock_code", "created_at"),
    )


class EtfDailyMetricsSnapshot(Base):
    __tablename__ = "etf_daily_metrics_snapshot"

    id = _id_column("etf_daily_metrics_snapshot_id_seq")
    stock_code = Column(String(16), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    fund_shares = Column(Float, nullable=True)
    nav = Column(Float, nullable=True)
    derived_fund_size_yi = Column(Float, nullable=True)
    exchange = Column(String(16), nullable=True)
    data_source = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uix_etf_daily_metrics_stock_date"),
        Index("ix_etf_daily_metrics_stock_date", "stock_code", "trade_date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "fund_shares": self.fund_shares,
            "nav": self.nav,
            "derived_fund_size_yi": self.derived_fund_size_yi,
            "exchange": self.exchange,
            "data_source": self.data_source,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StockBelongBoardsCache(Base):
    __tablename__ = "stock_belong_boards_cache"

    id = _id_column("stock_belong_boards_cache_id_seq")
    stock_code = Column(String(16), nullable=False, unique=True, index=True)
    boards_payload = Column(Text, nullable=False)
    source = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_belong_boards_cache_updated", "updated_at"),
    )


class StockWatchlist(Base):
    __tablename__ = "stock_watchlist"

    id = _id_column("stock_watchlist_id_seq")
    stock_code = Column(String(16), nullable=False, unique=True, index=True)
    stock_name = Column(String(64), nullable=False)
    group_name = Column(String(64), nullable=True, index=True)
    note = Column(Text, nullable=True)
    latest_signal = Column(String(32), nullable=True)
    latest_theme = Column(String(64), nullable=True)
    alert_enabled = Column(Integer, nullable=False, default=0)
    source_query_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_watchlist_group_updated", "group_name", "updated_at"),
    )


class StockAlertRule(Base):
    __tablename__ = "stock_alert_rule"

    id = _id_column("stock_alert_rule_id_seq")
    stock_code = Column(String(16), nullable=False)
    stock_name = Column(String(64), nullable=False)
    rule_type = Column(String(32), nullable=False)
    threshold_value = Column(Float, nullable=True)
    scan_interval_minutes = Column(Integer, nullable=False, default=5)
    enabled = Column(Integer, nullable=False, default=1)
    note = Column(Text, nullable=True)
    source_query_id = Column(String(64), nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    last_triggered_at = Column(DateTime, nullable=True)
    last_trigger_key = Column(String(128), nullable=True)
    last_scan_status = Column(String(32), nullable=True)
    last_scan_reason = Column(Text, nullable=True)
    last_quote_source = Column(String(64), nullable=True)
    last_quote_price = Column(Float, nullable=True)
    last_scan_payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("stock_code", "rule_type", name="uix_stock_alert_rule_code_type"),
    )


class StockAlertEvent(Base):
    __tablename__ = "stock_alert_event"

    id = _id_column("stock_alert_event_id_seq")
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=False)
    rule_id = Column(Integer, nullable=False, index=True)
    rule_type = Column(String(32), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    message = Column(Text, nullable=False)
    dedupe_key = Column(String(160), nullable=True, index=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    read_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_stock_alert_event_stock_created", "stock_code", "created_at"),
        Index("ix_stock_alert_event_rule_created", "rule_id", "created_at"),
    )


class StockDeepAnalysisHistory(Base):
    __tablename__ = "stock_deep_analysis_history"

    id = _id_column("stock_deep_analysis_history_id_seq")
    analysis_id = Column(String(64), nullable=False, unique=True, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=False)
    source_query_id = Column(String(64), nullable=True, index=True)
    status = Column(String(20), nullable=False, index=True, default="completed")
    action = Column(String(32), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    trade_plan_json = Column(Text, nullable=True)
    technical_json = Column(Text, nullable=True)
    fundamental_json = Column(Text, nullable=True)
    risk_json = Column(Text, nullable=True)
    context_snapshot_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_deep_analysis_stock_created", "stock_code", "created_at"),
        Index("ix_stock_deep_analysis_query_created", "source_query_id", "created_at"),
    )


class StockDeepAnalysisMessage(Base):
    __tablename__ = "stock_deep_analysis_message"

    id = _id_column("stock_deep_analysis_message_id_seq")
    analysis_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_deep_analysis_message_created", "analysis_id", "created_at"),
    )


class InformationWatchItem(Base):
    __tablename__ = "information_watch_item"

    id = _id_column("information_watch_item_id_seq")
    item_id = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    enabled = Column(Integer, nullable=False, default=1, index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    seed_terms_json = Column(Text, nullable=False)
    aliases_json = Column(Text, nullable=False)
    themes_json = Column(Text, nullable=False)
    chain_tags_json = Column(Text, nullable=False)
    source_tiers_json = Column(Text, nullable=False)
    freshness_days = Column(Integer, nullable=False, default=3)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_information_watch_item_enabled_priority", "enabled", "priority"),
    )


class OpenDiscoveryProfile(Base):
    __tablename__ = "open_discovery_profile"

    id = _id_column("open_discovery_profile_id_seq")
    profile_id = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    enabled = Column(Integer, nullable=False, default=1, index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    query_templates_json = Column(Text, nullable=False)
    themes_json = Column(Text, nullable=False)
    chain_tags_json = Column(Text, nullable=False)
    source_tiers_json = Column(Text, nullable=False)
    freshness_days = Column(Integer, nullable=False, default=2)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_open_discovery_profile_enabled_priority", "enabled", "priority"),
    )


class InformationEvent(Base):
    __tablename__ = "information_event"

    id = _id_column("information_event_id_seq")
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    watch_item_id = Column(String(64), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    summary = Column(Text, nullable=True)
    event_type = Column(String(32), nullable=False, index=True)
    impact_direction = Column(String(32), nullable=True, index=True)
    source_mode = Column(String(20), nullable=False, default="watch", index=True)
    source_tier = Column(String(16), nullable=False, index=True)
    provider = Column(String(32), nullable=True, index=True)
    url = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    first_seen_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    is_new_event = Column(Integer, nullable=False, default=1, index=True)
    duplicate_key = Column(String(160), nullable=True, index=True)
    themes_json = Column(Text, nullable=False)
    chain_tags_json = Column(Text, nullable=False)
    entities_json = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False)
    freshness_score = Column(Float, nullable=False, default=0.0, index=True)
    credibility_score = Column(Float, nullable=False, default=0.0, index=True)
    signal_strength = Column(Float, nullable=False, default=0.0, index=True)
    status = Column(String(20), nullable=False, default="new", index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_information_event_watch_created", "watch_item_id", "created_at"),
        Index("ix_information_event_status_created", "status", "created_at"),
        Index("ix_information_event_signal_created", "signal_strength", "created_at"),
        Index("ix_information_event_source_mode_created", "source_mode", "created_at"),
    )


class ThemeFactorScanHistory(Base):
    __tablename__ = "theme_factor_scan_history"

    id = _id_column("theme_factor_scan_history_id_seq")
    scan_id = Column(String(64), nullable=False, unique=True, index=True)
    event_id = Column(String(64), nullable=False, index=True)
    theme_id = Column(String(64), nullable=True, index=True)
    theme_name = Column(String(128), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="completed", index=True)
    event_score = Column(Float, nullable=True)
    etf_confirmation_score = Column(Float, nullable=True)
    leader_confirmation_score = Column(Float, nullable=True)
    theme_factor_score = Column(Float, nullable=True, index=True)
    request_payload = Column(Text, nullable=False)
    result_payload = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_theme_factor_scan_event_created", "event_id", "created_at"),
        Index("ix_theme_factor_scan_theme_created", "theme_id", "created_at"),
    )


class StrategyBacktestRun(Base):
    __tablename__ = "strategy_backtest_run"

    id = _id_column("strategy_backtest_run_id_seq")
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    run_name = Column(String(160), nullable=True)
    status = Column(String(24), nullable=False, default="finished", index=True)
    source_type = Column(String(32), nullable=False, default="json_import", index=True)
    source_path = Column(Text, nullable=True)
    artifact_digest = Column(String(64), nullable=False, unique=True, index=True)
    logical_signature = Column(String(64), nullable=True, index=True)
    strategy = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(64), nullable=True, index=True)
    preset_id = Column(String(64), nullable=True, index=True)
    stock_pool_id = Column(String(64), nullable=True, index=True)
    stock_pool_name = Column(String(160), nullable=True)
    start_date = Column(Date, nullable=True, index=True)
    end_date = Column(Date, nullable=True, index=True)
    price_adjustment = Column(String(24), nullable=True)
    trading_constraints = Column(String(32), nullable=True)
    total_symbols = Column(Integer, nullable=True)
    ok_symbols = Column(Integer, nullable=True)
    error_symbols = Column(Integer, nullable=True)
    profitable_symbols = Column(Integer, nullable=True)
    losing_symbols = Column(Integer, nullable=True)
    flat_symbols = Column(Integer, nullable=True)
    total_initial_cash = Column(Float, nullable=True)
    total_final_equity = Column(Float, nullable=True)
    total_pnl = Column(Float, nullable=True)
    aggregate_return_pct = Column(Float, nullable=True)
    average_return_pct = Column(Float, nullable=True)
    total_trade_count = Column(Integer, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    win_rate_pct = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    average_holding_days = Column(Float, nullable=True)
    params_payload = Column(Text, nullable=True)
    config_payload = Column(Text, nullable=True)
    aggregate_payload = Column(Text, nullable=True)
    raw_summary_payload = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    generated_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_strategy_backtest_run_strategy_generated", "strategy", "generated_at"),
        Index("ix_strategy_backtest_run_pool_generated", "stock_pool_id", "generated_at"),
        Index("ix_strategy_backtest_run_status_created", "status", "created_at"),
    )


class StrategyBacktestSymbolResult(Base):
    __tablename__ = "strategy_backtest_symbol_result"

    id = _id_column("strategy_backtest_symbol_result_id_seq")
    run_id = Column(String(64), nullable=False, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    status = Column(String(24), nullable=False, default="ok", index=True)
    error = Column(Text, nullable=True)
    requested_start_date = Column(Date, nullable=True)
    effective_start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    initial_cash = Column(Float, nullable=True)
    final_equity = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    trade_count = Column(Integer, nullable=True)
    win_rate_pct = Column(Float, nullable=True)
    avg_win_pct = Column(Float, nullable=True)
    avg_loss_pct = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    has_open_position = Column(Integer, nullable=False, default=0)
    open_position_market_value = Column(Float, nullable=True)
    final_unrealized_pnl = Column(Float, nullable=True)
    final_unrealized_pnl_pct = Column(Float, nullable=True)
    max_trade_mfe_pct = Column(Float, nullable=True)
    max_trade_mae_pct = Column(Float, nullable=True)
    contribution_pct = Column(Float, nullable=True)
    result_path = Column(Text, nullable=True)
    params_payload = Column(Text, nullable=True)
    config_payload = Column(Text, nullable=True)
    metrics_payload = Column(Text, nullable=True)
    data_context_payload = Column(Text, nullable=True)
    latest_signal_metadata_payload = Column(Text, nullable=True)
    open_position_payload = Column(Text, nullable=True)
    raw_result_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("run_id", "stock_code", name="uix_strategy_backtest_symbol_run_code"),
        Index("ix_strategy_backtest_symbol_return", "run_id", "total_return_pct"),
        Index("ix_strategy_backtest_symbol_status", "run_id", "status"),
    )


class StrategyBacktestTrade(Base):
    __tablename__ = "strategy_backtest_trade"

    id = _id_column("strategy_backtest_trade_id_seq")
    trade_id = Column(String(96), nullable=False, unique=True, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    entry_date = Column(Date, nullable=True, index=True)
    exit_date = Column(Date, nullable=True, index=True)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    shares = Column(Integer, nullable=True)
    gross_pnl = Column(Float, nullable=True)
    net_pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    exit_reason = Column(String(96), nullable=True)
    entry_signal_type = Column(String(96), nullable=True)
    entry_signal_reason = Column(String(160), nullable=True)
    entry_signal_score = Column(Float, nullable=True)
    highest_price_seen = Column(Float, nullable=True)
    lowest_price_seen = Column(Float, nullable=True)
    max_favorable_excursion_pct = Column(Float, nullable=True)
    max_adverse_excursion_pct = Column(Float, nullable=True)
    entry_signal_metadata_payload = Column(Text, nullable=True)
    raw_trade_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_strategy_backtest_trade_entry", "run_id", "entry_date"),
        Index("ix_strategy_backtest_trade_stock_entry", "run_id", "stock_code", "entry_date"),
        Index("ix_strategy_backtest_trade_exit_reason", "run_id", "exit_reason"),
        Index("ix_strategy_backtest_trade_signal_type", "run_id", "entry_signal_type"),
        Index("ix_strategy_backtest_trade_entry_reason", "run_id", "entry_signal_reason"),
    )


class StrategyBacktestEquityPoint(Base):
    __tablename__ = "strategy_backtest_equity_point"

    id = _id_column("strategy_backtest_equity_point_id_seq")
    run_id = Column(String(64), nullable=False, index=True)
    scope = Column(String(24), nullable=False, index=True)
    stock_code = Column(String(16), nullable=True, index=True)
    benchmark_code = Column(String(32), nullable=True, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    cash = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    equity = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    drawdown_pct = Column(Float, nullable=True)
    source = Column(String(32), nullable=False, default="json_import")
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "scope",
            "stock_code",
            "benchmark_code",
            "trade_date",
            name="uix_strategy_backtest_equity_point",
        ),
        Index("ix_strategy_backtest_equity_run_scope_date", "run_id", "scope", "trade_date"),
    )


class StrategyBacktestPortfolioSchedule(Base):
    __tablename__ = "strategy_backtest_portfolio_schedule"

    id = _id_column("strategy_backtest_portfolio_schedule_id_seq")
    schedule_id = Column(String(64), nullable=False, unique=True, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    schedule_name = Column(String(160), nullable=True)
    rank_mode = Column(String(64), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="finished", index=True)
    candidate_count = Column(Integer, nullable=True)
    selected_count = Column(Integer, nullable=True)
    first_entry_date = Column(Date, nullable=True, index=True)
    last_entry_date = Column(Date, nullable=True, index=True)
    config_payload = Column(Text, nullable=True)
    summary_payload = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index("ix_strategy_backtest_portfolio_schedule_run_created", "run_id", "created_at"),
        Index("ix_strategy_backtest_portfolio_schedule_run_rank", "run_id", "rank_mode"),
    )


class StrategyBacktestPortfolioCandidate(Base):
    __tablename__ = "strategy_backtest_portfolio_candidate"

    id = _id_column("strategy_backtest_portfolio_candidate_id_seq")
    candidate_id = Column(String(128), nullable=False, unique=True, index=True)
    schedule_id = Column(String(64), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    signal_type = Column(String(96), nullable=True, index=True)
    rank_score = Column(Float, nullable=True)
    daily_candidate_rank = Column(Integer, nullable=True)
    selected = Column(Integer, nullable=False, default=0)
    selected_order = Column(Integer, nullable=True)
    selected_layer = Column(String(64), nullable=True, index=True)
    return_pct = Column(Float, nullable=True)
    net_pnl = Column(Float, nullable=True)
    exit_date = Column(Date, nullable=True)
    exit_reason = Column(String(96), nullable=True)
    trade_id = Column(String(96), nullable=True, index=True)
    metadata_payload = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("schedule_id", "entry_date", "stock_code", "signal_type", name="uix_strategy_backtest_portfolio_candidate"),
        Index("ix_strategy_backtest_portfolio_candidate_day_rank", "schedule_id", "entry_date", "daily_candidate_rank"),
        Index("ix_strategy_backtest_portfolio_candidate_selected", "schedule_id", "selected", "entry_date"),
        Index("ix_strategy_backtest_portfolio_candidate_run_entry", "run_id", "entry_date"),
    )


class StrategyBacktestStockPool(Base):
    __tablename__ = "strategy_backtest_stock_pool"

    id = _id_column("strategy_backtest_stock_pool_id_seq")
    pool_id = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(160), nullable=True)
    source_type = Column(String(32), nullable=False, default="json_file", index=True)
    source_path = Column(Text, nullable=True)
    source_digest = Column(String(64), nullable=False, unique=True, index=True)
    total_symbols = Column(Integer, nullable=True)
    filters_payload = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


class StrategyBacktestStockPoolMember(Base):
    __tablename__ = "strategy_backtest_stock_pool_member"

    id = _id_column("strategy_backtest_stock_pool_member_id_seq")
    pool_id = Column(String(64), nullable=False, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    rank = Column(Integer, nullable=True)
    weight = Column(Float, nullable=True)
    source_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("pool_id", "stock_code", name="uix_strategy_backtest_pool_member"),
        Index("ix_strategy_backtest_pool_member_rank", "pool_id", "rank"),
    )


class StrategyBacktestImportBatch(Base):
    __tablename__ = "strategy_backtest_import_batch"

    id = _id_column("strategy_backtest_import_batch_id_seq")
    import_id = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(24), nullable=False, index=True)
    source_path = Column(Text, nullable=False)
    stock_pool_path = Column(Text, nullable=True)
    mode = Column(String(24), nullable=False, default="upsert")
    dry_run = Column(Integer, nullable=False, default=0)
    run_id = Column(String(64), nullable=True, index=True)
    artifact_digest = Column(String(64), nullable=True, index=True)
    counts_payload = Column(Text, nullable=True)
    warnings_payload = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


@dataclass
class _DatabaseSettings:
    database_path: Path


class DatabaseManager:
    """Minimal database manager extracted for theme picker."""

    _instance: Optional["DatabaseManager"] = None

    def __init__(self, database_path: Optional[str] = None) -> None:
        cfg = get_config()
        db_path = Path(database_path or cfg.database_path).expanduser()
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_sqlite_database_file(db_path):
            raise RuntimeError(
                f"DATABASE_PATH points to a SQLite database: {db_path}. "
                "Run scripts/migrate_sqlite_to_duckdb.py and set DATABASE_PATH "
                "to ./data/stock_analysis.duckdb."
            )

        self._settings = _DatabaseSettings(database_path=db_path)
        self.engine = create_engine(
            f"duckdb:///{db_path}",
            future=True,
        )
        self._SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=self.engine,
            future=True,
        )
        self._dialect_name = self.engine.dialect.name
        self._init_database()
        atexit.register(self.close)

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_database(self) -> None:
        Base.metadata.create_all(bind=self.engine)
        self._run_post_create_migrations()

    def _run_post_create_migrations(self) -> None:
        for index_name in (
            "ix_stock_alert_rule_code_updated",
            "ix_stock_alert_rule_created_at",
            "ix_stock_alert_rule_last_evaluated_at",
            "ix_stock_alert_rule_last_triggered_at",
            "ix_stock_alert_rule_rule_type",
            "ix_stock_alert_rule_stock_code",
            "ix_stock_alert_rule_updated_at",
        ):
            self._drop_index_if_exists(index_name)

        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="scan_interval_minutes",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN scan_interval_minutes INTEGER NOT NULL DEFAULT 5",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_evaluated_at",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_evaluated_at DATETIME NULL",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_triggered_at",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_triggered_at DATETIME NULL",
        )
        self._ensure_column(
            table_name="information_event",
            column_name="source_mode",
            alter_sql="ALTER TABLE information_event ADD COLUMN source_mode VARCHAR(20) NOT NULL DEFAULT 'watch'",
        )
        self._ensure_index(
            index_name="ix_information_event_source_mode_created",
            create_sql="CREATE INDEX IF NOT EXISTS ix_information_event_source_mode_created ON information_event (source_mode, created_at)",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_trigger_key",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_trigger_key VARCHAR(128) NULL",
        )
        self._ensure_column(
            table_name="stock_daily_raw",
            column_name="open_qfq",
            alter_sql="ALTER TABLE stock_daily_raw ADD COLUMN open_qfq FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_daily_raw",
            column_name="high_qfq",
            alter_sql="ALTER TABLE stock_daily_raw ADD COLUMN high_qfq FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_daily_raw",
            column_name="low_qfq",
            alter_sql="ALTER TABLE stock_daily_raw ADD COLUMN low_qfq FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_daily_raw",
            column_name="close_qfq",
            alter_sql="ALTER TABLE stock_daily_raw ADD COLUMN close_qfq FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_daily_aux",
            column_name="turnover_rate_median_20",
            alter_sql="ALTER TABLE stock_daily_aux ADD COLUMN turnover_rate_median_20 FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_daily_aux",
            column_name="atr_pct_20",
            alter_sql="ALTER TABLE stock_daily_aux ADD COLUMN atr_pct_20 FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_daily_aux",
            column_name="style_bucket",
            alter_sql="ALTER TABLE stock_daily_aux ADD COLUMN style_bucket VARCHAR(32) NULL",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_scan_status",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_scan_status VARCHAR(32) NULL",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_scan_reason",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_scan_reason TEXT NULL",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_quote_source",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_quote_source VARCHAR(64) NULL",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_quote_price",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_quote_price FLOAT NULL",
        )
        self._ensure_column(
            table_name="stock_alert_rule",
            column_name="last_scan_payload_json",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_scan_payload_json TEXT NULL",
        )
        self._ensure_column(
            table_name="strategy_backtest_trade",
            column_name="entry_signal_type",
            alter_sql="ALTER TABLE strategy_backtest_trade ADD COLUMN entry_signal_type VARCHAR(96) NULL",
        )
        self._ensure_index(
            index_name="ix_strategy_backtest_trade_signal_type",
            create_sql=(
                "CREATE INDEX IF NOT EXISTS ix_strategy_backtest_trade_signal_type "
                "ON strategy_backtest_trade (run_id, entry_signal_type)"
            ),
        )

    def _ensure_column(self, *, table_name: str, column_name: str, alter_sql: str) -> None:
        existing = {column["name"] for column in inspect(self.engine).get_columns(table_name)}
        if column_name in existing:
            return
        with self.engine.begin() as conn:
            conn.exec_driver_sql(alter_sql)

    def _ensure_index(self, *, index_name: str, create_sql: str) -> None:
        with self.engine.begin() as conn:
            conn.exec_driver_sql(create_sql)

    def _drop_index_if_exists(self, index_name: str) -> None:
        with self.engine.begin() as conn:
            conn.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    def close(self) -> None:
        try:
            self.engine.dispose()
        except Exception:
            pass

    @staticmethod
    def _normalize_daily_date(value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            for pattern in ("%Y-%m-%d", "%Y%m%d"):
                try:
                    return datetime.strptime(normalized, pattern).date()
                except ValueError:
                    continue
            raise ValueError(f"Unsupported daily date string: {value}")
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _normalize_sql_value(value: Any) -> Any:
        return None if pd.isna(value) else value

    @staticmethod
    def _classify_style_bucket_from_row(row: pd.Series) -> Optional[str]:
        turnover_median = row.get("turnover_rate_median_20")
        atr_pct = row.get("atr_pct_20")
        if pd.isna(turnover_median) or pd.isna(atr_pct):
            return None
        turnover_value = float(turnover_median)
        atr_value = float(atr_pct)
        if atr_value >= 5.5:
            return "high_beta"
        if turnover_value >= 5.0:
            return "high_beta"
        if atr_value >= 4.5 and turnover_value >= 2.0:
            return "high_beta"
        if turnover_value < 1.5 and atr_value < 3.5:
            return "slow_large"
        return "balanced_trend"

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _safe_json_loads(value: Optional[str]) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @contextmanager
    def session_scope(self):
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _bulk_upsert_rows(
        self,
        model: Any,
        rows: List[Dict[str, Any]],
        *,
        conflict_columns: Iterable[str],
        update_columns: Iterable[str],
    ) -> int:
        if not rows:
            return 0
        conflict_keys = list(conflict_columns)
        rows_by_key: Dict[tuple[Any, ...], Dict[str, Any]] = {}
        ordered_keys: List[tuple[Any, ...]] = []
        for row in rows:
            item = dict(row)
            key = tuple(item.get(column) for column in conflict_keys)
            if key not in rows_by_key:
                ordered_keys.append(key)
            rows_by_key[key] = item
        payload = [rows_by_key[key] for key in ordered_keys]
        stmt = duckdb_insert(model).values(payload)
        excluded = stmt.excluded
        with self.session_scope() as session:
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=conflict_keys,
                    set_={column: getattr(excluded, column) for column in update_columns},
                )
            )
        return len(rows)

    def get_data_range(self, code: str, start_date, end_date) -> List[StockDaily]:
        normalized_start = self._normalize_daily_date(start_date)
        normalized_end = self._normalize_daily_date(end_date)
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(StockDaily)
                    .where(
                        and_(
                            StockDaily.code == code,
                            StockDaily.date >= normalized_start,
                            StockDaily.date <= normalized_end,
                        )
                    )
                    .order_by(StockDaily.date.asc())
                ).scalars().all()
            )

    def save_daily_data(self, df: pd.DataFrame, code: str, data_source: str) -> int:
        if df is None or df.empty:
            return 0

        records: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            item = {
                "code": code,
                "date": self._normalize_daily_date(row["date"]),
                "open": self._normalize_sql_value(row.get("open")),
                "high": self._normalize_sql_value(row.get("high")),
                "low": self._normalize_sql_value(row.get("low")),
                "close": self._normalize_sql_value(row.get("close")),
                "volume": self._normalize_sql_value(row.get("volume")),
                "amount": self._normalize_sql_value(row.get("amount")),
                "pct_chg": self._normalize_sql_value(row.get("pct_chg")),
                "ma5": self._normalize_sql_value(row.get("ma5")),
                "ma10": self._normalize_sql_value(row.get("ma10")),
                "ma20": self._normalize_sql_value(row.get("ma20")),
                "volume_ratio": self._normalize_sql_value(row.get("volume_ratio")),
                "data_source": data_source,
                "updated_at": datetime.now(),
            }
            records.append(item)

        return self._bulk_upsert_rows(
            StockDaily,
            records,
            conflict_columns=["code", "date"],
            update_columns=[
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "pct_chg",
                "ma5",
                "ma10",
                "ma20",
                "volume_ratio",
                "data_source",
                "updated_at",
            ],
        )

    def save_stock_daily_raw_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        prepared: List[Dict[str, Any]] = []
        for row in rows:
            prepared.append(
                {
                    "ts_code": str(row.get("ts_code") or "").strip().upper(),
                    "trade_date": self._normalize_daily_date(row.get("trade_date")),
                    "open": self._normalize_sql_value(row.get("open")),
                    "high": self._normalize_sql_value(row.get("high")),
                    "low": self._normalize_sql_value(row.get("low")),
                    "close": self._normalize_sql_value(row.get("close")),
                    "pre_close": self._normalize_sql_value(row.get("pre_close")),
                    "vol": self._normalize_sql_value(row.get("vol")),
                    "amount": self._normalize_sql_value(row.get("amount")),
                    "adj_factor": self._normalize_sql_value(row.get("adj_factor")),
                    "open_qfq": self._normalize_sql_value(row.get("open_qfq")),
                    "high_qfq": self._normalize_sql_value(row.get("high_qfq")),
                    "low_qfq": self._normalize_sql_value(row.get("low_qfq")),
                    "close_qfq": self._normalize_sql_value(row.get("close_qfq")),
                    "sync_batch_id": str(row.get("sync_batch_id") or "").strip() or None,
                    "data_source": str(row.get("data_source") or "").strip() or None,
                    "ingested_at": row.get("ingested_at") or datetime.now(),
                    "updated_at": datetime.now(),
                }
            )

        return self._bulk_upsert_rows(
            StockDailyRaw,
            prepared,
            conflict_columns=["ts_code", "trade_date"],
            update_columns=[
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "vol",
                "amount",
                "adj_factor",
                "open_qfq",
                "high_qfq",
                "low_qfq",
                "close_qfq",
                "sync_batch_id",
                "data_source",
                "ingested_at",
                "updated_at",
            ],
        )

    def get_stock_daily_raw_range(self, ts_code: str, start_date, end_date) -> List[StockDailyRaw]:
        normalized_start = self._normalize_daily_date(start_date)
        normalized_end = self._normalize_daily_date(end_date)
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(StockDailyRaw)
                    .where(
                        and_(
                            StockDailyRaw.ts_code == ts_code,
                            StockDailyRaw.trade_date >= normalized_start,
                            StockDailyRaw.trade_date <= normalized_end,
                        )
                    )
                    .order_by(StockDailyRaw.trade_date.asc())
                ).scalars().all()
            )

    def has_stock_daily_raw_coverage(self, ts_code: str, start_date, end_date) -> bool:
        normalized_code = str(ts_code or "").strip().upper()
        normalized_start = self._normalize_daily_date(start_date)
        normalized_end = self._normalize_daily_date(end_date)
        if not normalized_code or normalized_start is None or normalized_end is None:
            return False

        with self.session_scope() as session:
            min_date, max_date = session.execute(
                select(
                    func.min(StockDailyRaw.trade_date),
                    func.max(StockDailyRaw.trade_date),
                ).where(StockDailyRaw.ts_code == normalized_code)
            ).one()
        if min_date is None or max_date is None:
            return False
        return min_date <= normalized_start and max_date >= normalized_end

    def recompute_stock_daily_raw_qfq(self, ts_code: str) -> int:
        normalized_code = str(ts_code or "").strip().upper()
        if not normalized_code:
            return 0

        with self.session_scope() as session:
            latest_adj = session.execute(
                text(
                    """
                    SELECT adj_factor
                    FROM stock_daily_raw
                    WHERE ts_code = :ts_code
                      AND adj_factor IS NOT NULL
                      AND adj_factor > 0
                    ORDER BY trade_date DESC
                    LIMIT 1
                    """
                ),
                {"ts_code": normalized_code},
            ).scalar()
            if latest_adj is None or float(latest_adj) <= 0:
                return 0

            updated = session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM stock_daily_raw
                    WHERE ts_code = :ts_code
                      AND adj_factor IS NOT NULL
                      AND adj_factor > 0
                    """
                ),
                {"ts_code": normalized_code},
            ).scalar()
            if not updated:
                return 0

            session.execute(
                text(
                    """
                    UPDATE stock_daily_raw
                    SET
                        open_qfq = CASE
                            WHEN open IS NULL THEN NULL
                            ELSE ROUND(open * (adj_factor / :latest_adj), 4)
                        END,
                        high_qfq = CASE
                            WHEN high IS NULL THEN NULL
                            ELSE ROUND(high * (adj_factor / :latest_adj), 4)
                        END,
                        low_qfq = CASE
                            WHEN low IS NULL THEN NULL
                            ELSE ROUND(low * (adj_factor / :latest_adj), 4)
                        END,
                        close_qfq = CASE
                            WHEN close IS NULL THEN NULL
                            ELSE ROUND(close * (adj_factor / :latest_adj), 4)
                        END,
                        updated_at = :updated_at
                    WHERE ts_code = :ts_code
                      AND adj_factor IS NOT NULL
                      AND adj_factor > 0
                    """
                ),
                {
                    "ts_code": normalized_code,
                    "latest_adj": float(latest_adj),
                    "updated_at": datetime.now(),
                },
            )
            return int(updated)

    def save_stock_daily_aux_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        prepared: List[Dict[str, Any]] = []
        for row in rows:
            prepared.append(
                {
                    "ts_code": str(row.get("ts_code") or "").strip().upper(),
                    "trade_date": self._normalize_daily_date(row.get("trade_date")),
                    "turnover_rate": self._normalize_sql_value(row.get("turnover_rate")),
                    "turnover_rate_f": self._normalize_sql_value(row.get("turnover_rate_f")),
                    "volume_ratio": self._normalize_sql_value(row.get("volume_ratio")),
                    "float_share": self._normalize_sql_value(row.get("float_share")),
                    "free_share": self._normalize_sql_value(row.get("free_share")),
                    "total_share": self._normalize_sql_value(row.get("total_share")),
                    "circ_mv": self._normalize_sql_value(row.get("circ_mv")),
                    "total_mv": self._normalize_sql_value(row.get("total_mv")),
                    "up_limit": self._normalize_sql_value(row.get("up_limit")),
                    "down_limit": self._normalize_sql_value(row.get("down_limit")),
                    "turnover_rate_median_20": self._normalize_sql_value(row.get("turnover_rate_median_20")),
                    "atr_pct_20": self._normalize_sql_value(row.get("atr_pct_20")),
                    "style_bucket": str(row.get("style_bucket") or "").strip() or None,
                    "is_suspended": self._normalize_sql_value(row.get("is_suspended")),
                    "suspend_type": str(row.get("suspend_type") or "").strip() or None,
                    "sync_batch_id": str(row.get("sync_batch_id") or "").strip() or None,
                    "data_source": str(row.get("data_source") or "").strip() or None,
                    "ingested_at": row.get("ingested_at") or datetime.now(),
                    "updated_at": datetime.now(),
                }
            )

        return self._bulk_upsert_rows(
            StockDailyAux,
            prepared,
            conflict_columns=["ts_code", "trade_date"],
            update_columns=[
                "turnover_rate",
                "turnover_rate_f",
                "volume_ratio",
                "float_share",
                "free_share",
                "total_share",
                "circ_mv",
                "total_mv",
                "up_limit",
                "down_limit",
                "turnover_rate_median_20",
                "atr_pct_20",
                "style_bucket",
                "is_suspended",
                "suspend_type",
                "sync_batch_id",
                "data_source",
                "ingested_at",
                "updated_at",
            ],
        )

    def get_stock_daily_aux_range(self, ts_code: str, start_date, end_date) -> List[StockDailyAux]:
        normalized_start = self._normalize_daily_date(start_date)
        normalized_end = self._normalize_daily_date(end_date)
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(StockDailyAux)
                    .where(
                        and_(
                            StockDailyAux.ts_code == ts_code,
                            StockDailyAux.trade_date >= normalized_start,
                            StockDailyAux.trade_date <= normalized_end,
                        )
                    )
                    .order_by(StockDailyAux.trade_date.asc())
                ).scalars().all()
            )

    def has_stock_daily_aux_coverage(self, ts_code: str, start_date, end_date) -> bool:
        normalized_code = str(ts_code or "").strip().upper()
        normalized_start = self._normalize_daily_date(start_date)
        normalized_end = self._normalize_daily_date(end_date)
        if not normalized_code or normalized_start is None or normalized_end is None:
            return False

        with self.session_scope() as session:
            min_date, max_date = session.execute(
                select(
                    func.min(StockDailyAux.trade_date),
                    func.max(StockDailyAux.trade_date),
                ).where(StockDailyAux.ts_code == normalized_code)
            ).one()
        if min_date is None or max_date is None:
            return False
        return min_date <= normalized_start and max_date >= normalized_end

    def recompute_stock_daily_aux_features(self, ts_code: str, *, sync_batch_id: Optional[str] = None) -> int:
        normalized_code = str(ts_code or "").strip().upper()
        if not normalized_code:
            return 0

        with self.session_scope() as session:
            matched_count = session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM stock_daily_raw AS r
                    JOIN stock_daily_aux AS a
                      ON a.ts_code = r.ts_code
                     AND a.trade_date = r.trade_date
                    WHERE r.ts_code = :ts_code
                    """
                ),
                {"ts_code": normalized_code},
            ).scalar()
            if not matched_count:
                return 0

            qfq_ready = bool(
                session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM stock_daily_raw AS r
                        JOIN stock_daily_aux AS a
                          ON a.ts_code = r.ts_code
                         AND a.trade_date = r.trade_date
                        WHERE r.ts_code = :ts_code
                          AND r.high_qfq IS NOT NULL
                          AND r.low_qfq IS NOT NULL
                          AND r.close_qfq IS NOT NULL
                        """
                    ),
                    {"ts_code": normalized_code},
                ).scalar()
            )
            high_expr = "r.high_qfq" if qfq_ready else "r.high"
            low_expr = "r.low_qfq" if qfq_ready else "r.low"
            close_expr = "r.close_qfq" if qfq_ready else "r.close"
            normalized_batch_id = str(sync_batch_id).strip() if sync_batch_id is not None else None

            session.execute(
                text(
                    f"""
                    WITH source AS (
                        SELECT
                            r.ts_code,
                            r.trade_date,
                            {high_expr} AS feature_high,
                            {low_expr} AS feature_low,
                            {close_expr} AS feature_close,
                            a.turnover_rate AS turnover_rate
                        FROM stock_daily_raw AS r
                        JOIN stock_daily_aux AS a
                          ON a.ts_code = r.ts_code
                         AND a.trade_date = r.trade_date
                        WHERE r.ts_code = :ts_code
                    ),
                    lagged AS (
                        SELECT
                            ts_code,
                            trade_date,
                            feature_high,
                            feature_low,
                            feature_close,
                            turnover_rate,
                            LAG(feature_close) OVER (ORDER BY trade_date) AS previous_close
                        FROM source
                    ),
                    ranged AS (
                        SELECT
                            ts_code,
                            trade_date,
                            feature_close,
                            turnover_rate,
                            CASE
                                WHEN feature_high - feature_low IS NULL
                                 AND ABS(feature_high - previous_close) IS NULL
                                 AND ABS(feature_low - previous_close) IS NULL
                                THEN NULL
                                ELSE GREATEST(
                                    COALESCE(feature_high - feature_low, -1.7976931348623157e308),
                                    COALESCE(ABS(feature_high - previous_close), -1.7976931348623157e308),
                                    COALESCE(ABS(feature_low - previous_close), -1.7976931348623157e308)
                                )
                            END AS true_range
                        FROM lagged
                    ),
                    rolled AS (
                        SELECT
                            ts_code,
                            trade_date,
                            CASE
                                WHEN COUNT(turnover_rate) OVER rolling_window >= 5
                                THEN ROUND(MEDIAN(turnover_rate) OVER rolling_window, 4)
                                ELSE NULL
                            END AS turnover_rate_median_20,
                            CASE
                                WHEN COUNT(true_range) OVER rolling_window >= 5
                                 AND feature_close IS NOT NULL
                                 AND feature_close <> 0
                                THEN ROUND((AVG(true_range) OVER rolling_window / feature_close) * 100.0, 4)
                                ELSE NULL
                            END AS atr_pct_20
                        FROM ranged
                        WINDOW rolling_window AS (
                            ORDER BY trade_date
                            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                        )
                    ),
                    computed AS (
                        SELECT
                            ts_code,
                            trade_date,
                            turnover_rate_median_20,
                            atr_pct_20,
                            CASE
                                WHEN turnover_rate_median_20 IS NULL OR atr_pct_20 IS NULL THEN NULL
                                WHEN atr_pct_20 >= 5.5 THEN 'high_beta'
                                WHEN turnover_rate_median_20 >= 5.0 THEN 'high_beta'
                                WHEN atr_pct_20 >= 4.5 AND turnover_rate_median_20 >= 2.0 THEN 'high_beta'
                                WHEN turnover_rate_median_20 < 1.5 AND atr_pct_20 < 3.5 THEN 'slow_large'
                                ELSE 'balanced_trend'
                            END AS style_bucket
                        FROM rolled
                    )
                    UPDATE stock_daily_aux AS a
                    SET
                        turnover_rate_median_20 = c.turnover_rate_median_20,
                        atr_pct_20 = c.atr_pct_20,
                        style_bucket = c.style_bucket,
                        sync_batch_id = COALESCE(:sync_batch_id, a.sync_batch_id),
                        updated_at = :updated_at
                    FROM computed AS c
                    WHERE a.ts_code = c.ts_code
                      AND a.trade_date = c.trade_date
                      AND a.ts_code = :ts_code
                    """
                ),
                {
                    "ts_code": normalized_code,
                    "sync_batch_id": normalized_batch_id or None,
                    "updated_at": datetime.now(),
                },
            )
            return int(matched_count)

    def save_stock_corporate_action_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        prepared: List[Dict[str, Any]] = []
        for row in rows:
            prepared.append(
                {
                    "action_key": str(row.get("action_key") or "").strip(),
                    "ts_code": str(row.get("ts_code") or "").strip().upper(),
                    "ann_date": self._normalize_daily_date(row.get("ann_date")),
                    "record_date": self._normalize_daily_date(row.get("record_date")),
                    "ex_date": self._normalize_daily_date(row.get("ex_date")),
                    "pay_date": self._normalize_daily_date(row.get("pay_date")),
                    "div_proc": str(row.get("div_proc") or "").strip() or None,
                    "stk_div": self._normalize_sql_value(row.get("stk_div")),
                    "cash_div": self._normalize_sql_value(row.get("cash_div")),
                    "cash_div_tax": self._normalize_sql_value(row.get("cash_div_tax")),
                    "sync_batch_id": str(row.get("sync_batch_id") or "").strip() or None,
                    "data_source": str(row.get("data_source") or "").strip() or None,
                    "ingested_at": row.get("ingested_at") or datetime.now(),
                    "updated_at": datetime.now(),
                }
            )

        return self._bulk_upsert_rows(
            StockCorporateAction,
            prepared,
            conflict_columns=["action_key"],
            update_columns=[
                "ann_date",
                "record_date",
                "ex_date",
                "pay_date",
                "div_proc",
                "stk_div",
                "cash_div",
                "cash_div_tax",
                "sync_batch_id",
                "data_source",
                "ingested_at",
                "updated_at",
            ],
        )

    def list_stock_corporate_actions(
        self,
        *,
        ts_code: str,
        start_date=None,
        end_date=None,
    ) -> List[StockCorporateAction]:
        clauses = [StockCorporateAction.ts_code == ts_code]
        normalized_start = self._normalize_daily_date(start_date) if start_date is not None else None
        normalized_end = self._normalize_daily_date(end_date) if end_date is not None else None
        if normalized_start is not None:
            clauses.append(or_(StockCorporateAction.ex_date == None, StockCorporateAction.ex_date >= normalized_start))
        if normalized_end is not None:
            clauses.append(or_(StockCorporateAction.ex_date == None, StockCorporateAction.ex_date <= normalized_end))
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(StockCorporateAction)
                    .where(and_(*clauses))
                    .order_by(StockCorporateAction.ex_date.asc(), StockCorporateAction.ann_date.asc())
                ).scalars().all()
            )

    def save_trade_calendar_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        prepared: List[Dict[str, Any]] = []
        for row in rows:
            prepared.append(
                {
                    "exchange": str(row.get("exchange") or "").strip().upper() or "SSE",
                    "cal_date": self._normalize_daily_date(row.get("cal_date")),
                    "is_open": int(row.get("is_open") or 0),
                    "pretrade_date": self._normalize_daily_date(row.get("pretrade_date")),
                    "sync_batch_id": str(row.get("sync_batch_id") or "").strip() or None,
                    "data_source": str(row.get("data_source") or "").strip() or None,
                    "ingested_at": row.get("ingested_at") or datetime.now(),
                    "updated_at": datetime.now(),
                }
            )

        return self._bulk_upsert_rows(
            TradeCalendar,
            prepared,
            conflict_columns=["exchange", "cal_date"],
            update_columns=[
                "is_open",
                "pretrade_date",
                "sync_batch_id",
                "data_source",
                "ingested_at",
                "updated_at",
            ],
        )

    def list_trade_calendar(
        self,
        *,
        exchange: str = "SSE",
        start_date=None,
        end_date=None,
        is_open: Optional[int] = None,
    ) -> List[TradeCalendar]:
        clauses = [TradeCalendar.exchange == str(exchange or "SSE").strip().upper()]
        normalized_start = self._normalize_daily_date(start_date) if start_date is not None else None
        normalized_end = self._normalize_daily_date(end_date) if end_date is not None else None
        if normalized_start is not None:
            clauses.append(TradeCalendar.cal_date >= normalized_start)
        if normalized_end is not None:
            clauses.append(TradeCalendar.cal_date <= normalized_end)
        if is_open is not None:
            clauses.append(TradeCalendar.is_open == int(is_open))
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(TradeCalendar)
                    .where(and_(*clauses))
                    .order_by(TradeCalendar.cal_date.asc())
                ).scalars().all()
            )

    def save_theme_picker_task_history(
        self,
        *,
        task_id: str,
        status: str,
        progress: int,
        request_payload: Dict[str, Any],
        message: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        created_at: Optional[datetime] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> int:
        values = {
            "task_id": task_id,
            "status": status,
            "progress": int(progress),
            "message": message,
            "error": error,
            "request_payload": self._safe_json_dumps(request_payload or {}),
            "result_payload": self._safe_json_dumps(result_payload) if result_payload is not None else None,
            "created_at": created_at or datetime.now(),
            "started_at": started_at,
            "completed_at": completed_at,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(ThemePickerTaskHistory).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["task_id"],
                    set_={
                        "status": excluded.status,
                        "progress": excluded.progress,
                        "message": excluded.message,
                        "error": excluded.error,
                        "request_payload": excluded.request_payload,
                        "result_payload": excluded.result_payload,
                        "created_at": excluded.created_at,
                        "started_at": excluded.started_at,
                        "completed_at": excluded.completed_at,
                    },
                )
            )
        return 1

    def get_theme_picker_task_history(self, task_id: str) -> Optional[ThemePickerTaskHistory]:
        with self.session_scope() as session:
            return session.execute(
                select(ThemePickerTaskHistory)
                .where(ThemePickerTaskHistory.task_id == task_id)
                .limit(1)
            ).scalars().first()

    def list_theme_picker_task_history(self, limit: int = 20) -> List[ThemePickerTaskHistory]:
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(ThemePickerTaskHistory)
                    .order_by(desc(ThemePickerTaskHistory.created_at))
                    .limit(max(1, limit))
                ).scalars().all()
            )

    def list_theme_picker_task_history_by_statuses(
        self,
        statuses: List[str],
        *,
        limit: int = 50,
    ) -> List[ThemePickerTaskHistory]:
        normalized_statuses = [status for status in statuses if status]
        if not normalized_statuses:
            return []
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(ThemePickerTaskHistory)
                    .where(ThemePickerTaskHistory.status.in_(normalized_statuses))
                    .order_by(desc(ThemePickerTaskHistory.created_at))
                    .limit(max(1, limit))
                ).scalars().all()
            )

    def cleanup_theme_picker_task_history(
        self,
        *,
        retention_days: int,
        batch_size: int,
    ) -> int:
        if retention_days <= 0:
            return 0
        cutoff = datetime.now() - timedelta(days=retention_days)
        statuses = ("completed", "failed")
        with self.session_scope() as session:
            stale_ids = list(
                session.execute(
                    select(ThemePickerTaskHistory.id)
                    .where(
                        and_(
                            ThemePickerTaskHistory.status.in_(statuses),
                            or_(
                                ThemePickerTaskHistory.completed_at < cutoff,
                                and_(
                                    ThemePickerTaskHistory.completed_at.is_(None),
                                    ThemePickerTaskHistory.created_at < cutoff,
                                ),
                            ),
                        )
                    )
                    .order_by(
                        func.coalesce(
                            ThemePickerTaskHistory.completed_at,
                            ThemePickerTaskHistory.created_at,
                        ).asc()
                    )
                    .limit(max(1, batch_size))
                ).scalars().all()
            )
            if not stale_ids:
                return 0
            session.execute(delete(ThemePickerTaskHistory).where(ThemePickerTaskHistory.id.in_(stale_ids)))
            return len(stale_ids)

    def save_stock_query_history(
        self,
        *,
        query_id: str,
        status: str,
        request_payload: Dict[str, Any],
        query_text: Optional[str] = None,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        signal: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        created_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> int:
        values = {
            "query_id": query_id,
            "status": status,
            "query_text": query_text,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "signal": signal,
            "error": error,
            "request_payload": self._safe_json_dumps(request_payload or {}),
            "result_payload": self._safe_json_dumps(result_payload) if result_payload is not None else None,
            "created_at": created_at or datetime.now(),
            "completed_at": completed_at,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(StockQueryHistory).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["query_id"],
                    set_={
                        "status": excluded.status,
                        "query_text": excluded.query_text,
                        "stock_code": excluded.stock_code,
                        "stock_name": excluded.stock_name,
                        "signal": excluded.signal,
                        "error": excluded.error,
                        "request_payload": excluded.request_payload,
                        "result_payload": excluded.result_payload,
                        "created_at": excluded.created_at,
                        "completed_at": excluded.completed_at,
                    },
                )
            )
        return 1

    def get_stock_query_history(self, query_id: str) -> Optional[StockQueryHistory]:
        with self.session_scope() as session:
            return session.execute(
                select(StockQueryHistory)
                .where(StockQueryHistory.query_id == query_id)
                .limit(1)
            ).scalars().first()

    def list_stock_query_history(
        self,
        *,
        limit: int = 20,
        stock_code: Optional[str] = None,
    ) -> List[StockQueryHistory]:
        stmt = select(StockQueryHistory)
        if stock_code:
            stmt = stmt.where(StockQueryHistory.stock_code == stock_code)
        stmt = stmt.order_by(desc(StockQueryHistory.created_at)).limit(max(1, limit))
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def save_etf_query_history(
        self,
        *,
        query_id: str,
        status: str,
        request_payload: Dict[str, Any],
        query_text: Optional[str] = None,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        created_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> int:
        values = {
            "query_id": query_id,
            "status": status,
            "query_text": query_text,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "error": error,
            "request_payload": self._safe_json_dumps(request_payload or {}),
            "result_payload": self._safe_json_dumps(result_payload) if result_payload is not None else None,
            "created_at": created_at or datetime.now(),
            "completed_at": completed_at,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(EtfQueryHistory).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["query_id"],
                    set_={
                        "status": excluded.status,
                        "query_text": excluded.query_text,
                        "stock_code": excluded.stock_code,
                        "stock_name": excluded.stock_name,
                        "error": excluded.error,
                        "request_payload": excluded.request_payload,
                        "result_payload": excluded.result_payload,
                        "created_at": excluded.created_at,
                        "completed_at": excluded.completed_at,
                    },
                )
            )
        return 1

    def save_etf_daily_metrics_snapshots(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            stock_code = str(row.get("stock_code") or "").strip()
            trade_date = self._normalize_daily_date(row.get("trade_date"))
            if not stock_code or trade_date is None:
                continue
            normalized_rows.append(
                {
                    "stock_code": stock_code,
                    "trade_date": trade_date,
                    "fund_shares": self._normalize_sql_value(row.get("fund_shares")),
                    "nav": self._normalize_sql_value(row.get("nav")),
                    "derived_fund_size_yi": self._normalize_sql_value(row.get("derived_fund_size_yi")),
                    "exchange": row.get("exchange"),
                    "data_source": row.get("data_source"),
                    "updated_at": datetime.now(),
                }
            )

        if not normalized_rows:
            return 0

        return self._bulk_upsert_rows(
            EtfDailyMetricsSnapshot,
            normalized_rows,
            conflict_columns=["stock_code", "trade_date"],
            update_columns=[
                "fund_shares",
                "nav",
                "derived_fund_size_yi",
                "exchange",
                "data_source",
                "updated_at",
            ],
        )

    def get_latest_etf_daily_metrics_snapshot(self, stock_code: str) -> Optional[EtfDailyMetricsSnapshot]:
        with self.session_scope() as session:
            return session.execute(
                select(EtfDailyMetricsSnapshot)
                .where(EtfDailyMetricsSnapshot.stock_code == stock_code)
                .order_by(desc(EtfDailyMetricsSnapshot.trade_date))
                .limit(1)
            ).scalars().first()

    def get_etf_query_history(self, query_id: str) -> Optional[EtfQueryHistory]:
        with self.session_scope() as session:
            return session.execute(
                select(EtfQueryHistory)
                .where(EtfQueryHistory.query_id == query_id)
                .limit(1)
            ).scalars().first()

    def list_etf_query_history(
        self,
        *,
        limit: int = 20,
        stock_code: Optional[str] = None,
    ) -> List[EtfQueryHistory]:
        stmt = select(EtfQueryHistory)
        if stock_code:
            stmt = stmt.where(EtfQueryHistory.stock_code == stock_code)
        stmt = stmt.order_by(desc(EtfQueryHistory.created_at)).limit(max(1, limit))
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def save_stock_belong_boards_cache(
        self,
        *,
        stock_code: str,
        boards: List[Dict[str, Any]],
        source: Optional[str] = None,
        updated_at: Optional[datetime] = None,
    ) -> int:
        values = {
            "stock_code": stock_code,
            "boards_payload": self._safe_json_dumps(boards or []),
            "source": source,
            "updated_at": updated_at or datetime.now(),
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(StockBelongBoardsCache).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["stock_code"],
                    set_={
                        "boards_payload": excluded.boards_payload,
                        "source": excluded.source,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
        return 1

    def get_stock_belong_boards_cache(self, stock_code: str) -> Optional[StockBelongBoardsCache]:
        with self.session_scope() as session:
            return session.execute(
                select(StockBelongBoardsCache)
                .where(StockBelongBoardsCache.stock_code == stock_code)
                .limit(1)
            ).scalars().first()

    def upsert_stock_watchlist_item(
        self,
        *,
        stock_code: str,
        stock_name: str,
        group_name: Optional[str] = None,
        note: Optional[str] = None,
        latest_signal: Optional[str] = None,
        latest_theme: Optional[str] = None,
        alert_enabled: bool = False,
        source_query_id: Optional[str] = None,
    ) -> StockWatchlist:
        values = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "group_name": group_name,
            "note": note,
            "latest_signal": latest_signal,
            "latest_theme": latest_theme,
            "alert_enabled": 1 if alert_enabled else 0,
            "source_query_id": source_query_id,
            "updated_at": datetime.now(),
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(StockWatchlist).values(
                {
                    **values,
                    "created_at": datetime.now(),
                }
            )
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["stock_code"],
                    set_={
                        "stock_name": excluded.stock_name,
                        "group_name": excluded.group_name,
                        "note": func.coalesce(excluded.note, StockWatchlist.note),
                        "latest_signal": excluded.latest_signal,
                        "latest_theme": excluded.latest_theme,
                        "alert_enabled": excluded.alert_enabled,
                        "source_query_id": excluded.source_query_id,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(StockWatchlist)
                .where(StockWatchlist.stock_code == stock_code)
                .limit(1)
            ).scalars().first()

    def list_stock_watchlist_items(self) -> List[StockWatchlist]:
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(StockWatchlist)
                    .order_by(desc(StockWatchlist.updated_at), desc(StockWatchlist.created_at))
                ).scalars().all()
            )

    def get_stock_watchlist_item(self, stock_code: str) -> Optional[StockWatchlist]:
        with self.session_scope() as session:
            return session.execute(
                select(StockWatchlist)
                .where(StockWatchlist.stock_code == stock_code)
                .limit(1)
            ).scalars().first()

    def delete_stock_watchlist_item(self, stock_code: str) -> bool:
        with self.session_scope() as session:
            result = session.execute(
                delete(StockWatchlist).where(StockWatchlist.stock_code == stock_code)
            )
            return bool(result.rowcount)

    def upsert_stock_alert_rule(
        self,
        *,
        stock_code: str,
        stock_name: str,
        rule_type: str,
        threshold_value: Optional[float] = None,
        scan_interval_minutes: int = 5,
        enabled: bool = True,
        note: Optional[str] = None,
        source_query_id: Optional[str] = None,
    ) -> StockAlertRule:
        normalized_scan_interval = max(5, int(scan_interval_minutes or 5))
        now = datetime.now()
        with self.session_scope() as session:
            stmt = duckdb_insert(StockAlertRule).values(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "rule_type": rule_type,
                    "threshold_value": threshold_value,
                    "scan_interval_minutes": normalized_scan_interval,
                    "enabled": 1 if enabled else 0,
                    "note": note,
                    "source_query_id": source_query_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["stock_code", "rule_type"],
                    set_={
                        "stock_name": excluded.stock_name,
                        "threshold_value": excluded.threshold_value,
                        "scan_interval_minutes": excluded.scan_interval_minutes,
                        "enabled": excluded.enabled,
                        "note": func.coalesce(excluded.note, StockAlertRule.note),
                        "source_query_id": excluded.source_query_id,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(StockAlertRule)
                .where(
                    and_(
                        StockAlertRule.stock_code == stock_code,
                        StockAlertRule.rule_type == rule_type,
                    )
                )
                .limit(1)
            ).scalars().first()

    def list_stock_alert_rules(self, *, stock_code: Optional[str] = None) -> List[StockAlertRule]:
        stmt = select(StockAlertRule)
        if stock_code:
            stmt = stmt.where(StockAlertRule.stock_code == stock_code)
        stmt = stmt.order_by(desc(StockAlertRule.updated_at), desc(StockAlertRule.created_at))
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def get_stock_alert_rule(self, rule_id: int) -> Optional[StockAlertRule]:
        with self.session_scope() as session:
            return session.execute(
                select(StockAlertRule)
                .where(StockAlertRule.id == rule_id)
                .limit(1)
            ).scalars().first()

    def update_stock_alert_rule(
        self,
        *,
        rule_id: int,
        threshold_value: Any = _UNSET,
        scan_interval_minutes: Optional[int] = None,
        enabled: Optional[bool] = None,
        note: Optional[str] = None,
        last_evaluated_at: Optional[datetime] = None,
        last_triggered_at: Optional[datetime] = None,
        last_trigger_key: Any = _UNSET,
        last_scan_status: Any = _UNSET,
        last_scan_reason: Any = _UNSET,
        last_quote_source: Any = _UNSET,
        last_quote_price: Any = _UNSET,
        last_scan_payload: Any = _UNSET,
    ) -> Optional[StockAlertRule]:
        with self.session_scope() as session:
            record = session.execute(
                select(StockAlertRule)
                .where(StockAlertRule.id == rule_id)
                .limit(1)
            ).scalars().first()
            if record is None:
                return None

            if enabled is not None:
                record.enabled = 1 if enabled else 0
            if threshold_value is not _UNSET:
                record.threshold_value = threshold_value
            if scan_interval_minutes is not None:
                record.scan_interval_minutes = max(5, int(scan_interval_minutes))
            if note is not None:
                record.note = note
            if last_evaluated_at is not None:
                record.last_evaluated_at = last_evaluated_at
            if last_triggered_at is not None:
                record.last_triggered_at = last_triggered_at
            if last_trigger_key is not _UNSET:
                record.last_trigger_key = last_trigger_key
            if last_scan_status is not _UNSET:
                record.last_scan_status = last_scan_status
            if last_scan_reason is not _UNSET:
                record.last_scan_reason = last_scan_reason
            if last_quote_source is not _UNSET:
                record.last_quote_source = last_quote_source
            if last_quote_price is not _UNSET:
                record.last_quote_price = last_quote_price
            if last_scan_payload is not _UNSET:
                record.last_scan_payload_json = self._safe_json_dumps(last_scan_payload) if last_scan_payload is not None else None
            record.updated_at = datetime.now()
            session.flush()
            return record

    def delete_stock_alert_rule(self, rule_id: int) -> bool:
        with self.session_scope() as session:
            result = session.execute(
                delete(StockAlertRule).where(StockAlertRule.id == rule_id)
            )
            return bool(result.rowcount)

    def create_stock_alert_event(
        self,
        *,
        stock_code: str,
        stock_name: str,
        rule_id: int,
        rule_type: str,
        event_type: str,
        title: str,
        message: str,
        dedupe_key: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> StockAlertEvent:
        now = datetime.now()
        with self.session_scope() as session:
            record = StockAlertEvent(
                stock_code=stock_code,
                stock_name=stock_name,
                rule_id=rule_id,
                rule_type=rule_type,
                event_type=event_type,
                title=title,
                message=message,
                dedupe_key=dedupe_key,
                payload_json=self._safe_json_dumps(payload) if payload is not None else None,
                created_at=now,
            )
            session.add(record)
            session.flush()
            return record

    def list_stock_alert_events(
        self,
        *,
        limit: int = 50,
        stock_code: Optional[str] = None,
        unread_only: bool = False,
    ) -> List[StockAlertEvent]:
        stmt = select(StockAlertEvent)
        if stock_code:
            stmt = stmt.where(StockAlertEvent.stock_code == stock_code)
        if unread_only:
            stmt = stmt.where(StockAlertEvent.read_at.is_(None))
        stmt = stmt.order_by(desc(StockAlertEvent.created_at), desc(StockAlertEvent.id)).limit(max(1, int(limit)))
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def mark_stock_alert_event_read(self, event_id: int) -> Optional[StockAlertEvent]:
        with self.session_scope() as session:
            record = session.execute(
                select(StockAlertEvent).where(StockAlertEvent.id == event_id).limit(1)
            ).scalars().first()
            if record is None:
                return None
            if record.read_at is None:
                record.read_at = datetime.now()
                session.flush()
            return record

    def mark_all_stock_alert_events_read(self, *, stock_code: Optional[str] = None) -> int:
        with self.session_scope() as session:
            stmt = select(StockAlertEvent).where(StockAlertEvent.read_at.is_(None))
            if stock_code:
                stmt = stmt.where(StockAlertEvent.stock_code == stock_code)
            records = list(session.execute(stmt).scalars().all())
            if not records:
                return 0
            now = datetime.now()
            for record in records:
                record.read_at = now
            session.flush()
            return len(records)

    def save_stock_deep_analysis_history(
        self,
        *,
        analysis_id: str,
        stock_code: str,
        stock_name: str,
        source_query_id: Optional[str],
        status: str,
        action: Optional[str] = None,
        summary: Optional[str] = None,
        trade_plan: Optional[Dict[str, Any]] = None,
        technical: Optional[Dict[str, Any]] = None,
        fundamental: Optional[Dict[str, Any]] = None,
        risk: Optional[Dict[str, Any]] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> StockDeepAnalysisHistory:
        now = datetime.now()
        values = {
            "analysis_id": analysis_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "source_query_id": source_query_id,
            "status": status,
            "action": action,
            "summary": summary,
            "trade_plan_json": self._safe_json_dumps(trade_plan) if trade_plan is not None else None,
            "technical_json": self._safe_json_dumps(technical) if technical is not None else None,
            "fundamental_json": self._safe_json_dumps(fundamental) if fundamental is not None else None,
            "risk_json": self._safe_json_dumps(risk) if risk is not None else None,
            "context_snapshot_json": self._safe_json_dumps(context_snapshot) if context_snapshot is not None else None,
            "error": error,
            "created_at": now,
            "updated_at": now,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(StockDeepAnalysisHistory).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["analysis_id"],
                    set_={
                        "stock_code": excluded.stock_code,
                        "stock_name": excluded.stock_name,
                        "source_query_id": excluded.source_query_id,
                        "status": excluded.status,
                        "action": excluded.action,
                        "summary": excluded.summary,
                        "trade_plan_json": excluded.trade_plan_json,
                        "technical_json": excluded.technical_json,
                        "fundamental_json": excluded.fundamental_json,
                        "risk_json": excluded.risk_json,
                        "context_snapshot_json": excluded.context_snapshot_json,
                        "error": excluded.error,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(StockDeepAnalysisHistory)
                .where(StockDeepAnalysisHistory.analysis_id == analysis_id)
                .limit(1)
            ).scalars().first()

    def get_stock_deep_analysis_history(self, analysis_id: str) -> Optional[StockDeepAnalysisHistory]:
        with self.session_scope() as session:
            return session.execute(
                select(StockDeepAnalysisHistory)
                .where(StockDeepAnalysisHistory.analysis_id == analysis_id)
                .limit(1)
            ).scalars().first()

    def list_stock_deep_analysis_history(
        self,
        *,
        stock_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[StockDeepAnalysisHistory]:
        stmt = select(StockDeepAnalysisHistory)
        if stock_code:
            stmt = stmt.where(StockDeepAnalysisHistory.stock_code == stock_code)
        stmt = stmt.order_by(desc(StockDeepAnalysisHistory.created_at), desc(StockDeepAnalysisHistory.id)).limit(
            max(1, int(limit))
        )
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def create_stock_deep_analysis_message(
        self,
        *,
        analysis_id: str,
        role: str,
        content: str,
    ) -> StockDeepAnalysisMessage:
        with self.session_scope() as session:
            record = StockDeepAnalysisMessage(
                analysis_id=analysis_id,
                role=role,
                content=content,
                created_at=datetime.now(),
            )
            session.add(record)
            session.flush()
            return record

    def list_stock_deep_analysis_messages(
        self,
        *,
        analysis_id: str,
        limit: int = 50,
    ) -> List[StockDeepAnalysisMessage]:
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(StockDeepAnalysisMessage)
                    .where(StockDeepAnalysisMessage.analysis_id == analysis_id)
                    .order_by(StockDeepAnalysisMessage.created_at.asc(), StockDeepAnalysisMessage.id.asc())
                    .limit(max(1, int(limit)))
                ).scalars().all()
            )

    def upsert_information_watch_item(
        self,
        *,
        item_id: str,
        name: str,
        enabled: bool,
        priority: int,
        event_type: str,
        seed_terms: List[str],
        aliases: List[str],
        themes: List[str],
        chain_tags: List[str],
        source_tiers: List[str],
        freshness_days: int,
        notes: Optional[str] = None,
    ) -> InformationWatchItem:
        now = datetime.now()
        values = {
            "item_id": item_id,
            "name": name,
            "enabled": 1 if enabled else 0,
            "priority": int(priority),
            "event_type": event_type,
            "seed_terms_json": self._safe_json_dumps(seed_terms or []),
            "aliases_json": self._safe_json_dumps(aliases or []),
            "themes_json": self._safe_json_dumps(themes or []),
            "chain_tags_json": self._safe_json_dumps(chain_tags or []),
            "source_tiers_json": self._safe_json_dumps(source_tiers or []),
            "freshness_days": max(1, int(freshness_days or 3)),
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(InformationWatchItem).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["item_id"],
                    set_={
                        "name": excluded.name,
                        "enabled": excluded.enabled,
                        "priority": excluded.priority,
                        "event_type": excluded.event_type,
                        "seed_terms_json": excluded.seed_terms_json,
                        "aliases_json": excluded.aliases_json,
                        "themes_json": excluded.themes_json,
                        "chain_tags_json": excluded.chain_tags_json,
                        "source_tiers_json": excluded.source_tiers_json,
                        "freshness_days": excluded.freshness_days,
                        "notes": excluded.notes,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(InformationWatchItem).where(InformationWatchItem.item_id == item_id).limit(1)
            ).scalars().first()

    def upsert_open_discovery_profile(
        self,
        *,
        profile_id: str,
        name: str,
        enabled: bool,
        priority: int,
        event_type: str,
        query_templates: List[str],
        themes: List[str],
        chain_tags: List[str],
        source_tiers: List[str],
        freshness_days: int,
        notes: Optional[str] = None,
    ) -> OpenDiscoveryProfile:
        now = datetime.now()
        values = {
            "profile_id": profile_id,
            "name": name,
            "enabled": 1 if enabled else 0,
            "priority": int(priority),
            "event_type": event_type,
            "query_templates_json": self._safe_json_dumps(query_templates or []),
            "themes_json": self._safe_json_dumps(themes or []),
            "chain_tags_json": self._safe_json_dumps(chain_tags or []),
            "source_tiers_json": self._safe_json_dumps(source_tiers or []),
            "freshness_days": max(1, int(freshness_days or 2)),
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(OpenDiscoveryProfile).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["profile_id"],
                    set_={
                        "name": excluded.name,
                        "enabled": excluded.enabled,
                        "priority": excluded.priority,
                        "event_type": excluded.event_type,
                        "query_templates_json": excluded.query_templates_json,
                        "themes_json": excluded.themes_json,
                        "chain_tags_json": excluded.chain_tags_json,
                        "source_tiers_json": excluded.source_tiers_json,
                        "freshness_days": excluded.freshness_days,
                        "notes": excluded.notes,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(OpenDiscoveryProfile).where(OpenDiscoveryProfile.profile_id == profile_id).limit(1)
            ).scalars().first()

    def list_information_watch_items(self, *, enabled_only: bool = False) -> List[InformationWatchItem]:
        stmt = select(InformationWatchItem)
        if enabled_only:
            stmt = stmt.where(InformationWatchItem.enabled == 1)
        stmt = stmt.order_by(
            InformationWatchItem.priority.asc(),
            desc(InformationWatchItem.updated_at),
            desc(InformationWatchItem.created_at),
        )
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def list_open_discovery_profiles(self, *, enabled_only: bool = False) -> List[OpenDiscoveryProfile]:
        stmt = select(OpenDiscoveryProfile)
        if enabled_only:
            stmt = stmt.where(OpenDiscoveryProfile.enabled == 1)
        stmt = stmt.order_by(
            OpenDiscoveryProfile.priority.asc(),
            desc(OpenDiscoveryProfile.updated_at),
            desc(OpenDiscoveryProfile.created_at),
        )
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def get_information_watch_item(self, item_id: str) -> Optional[InformationWatchItem]:
        with self.session_scope() as session:
            return session.execute(
                select(InformationWatchItem).where(InformationWatchItem.item_id == item_id).limit(1)
            ).scalars().first()

    def delete_information_watch_item(self, item_id: str) -> bool:
        with self.session_scope() as session:
            result = session.execute(delete(InformationWatchItem).where(InformationWatchItem.item_id == item_id))
            return bool(result.rowcount)

    def save_information_event(
        self,
        *,
        event_id: str,
        watch_item_id: Optional[str],
        title: str,
        summary: Optional[str],
        event_type: str,
        impact_direction: Optional[str],
        source_tier: str,
        provider: Optional[str],
        url: Optional[str],
        published_at: Optional[datetime],
        first_seen_at: Optional[datetime],
        last_seen_at: Optional[datetime],
        source_mode: str,
        is_new_event: bool,
        duplicate_key: Optional[str],
        themes: List[str],
        chain_tags: List[str],
        entities: Dict[str, Any],
        metadata: Dict[str, Any],
        freshness_score: float,
        credibility_score: float,
        signal_strength: float,
        status: str,
    ) -> InformationEvent:
        now = datetime.now()
        values = {
            "event_id": event_id,
            "watch_item_id": watch_item_id,
            "title": title,
            "summary": summary,
            "event_type": event_type,
            "impact_direction": impact_direction,
            "source_tier": source_tier,
            "provider": provider,
            "url": url,
            "published_at": published_at,
            "first_seen_at": first_seen_at or now,
            "last_seen_at": last_seen_at or now,
            "source_mode": source_mode or "watch",
            "is_new_event": 1 if is_new_event else 0,
            "duplicate_key": duplicate_key,
            "themes_json": self._safe_json_dumps(themes or []),
            "chain_tags_json": self._safe_json_dumps(chain_tags or []),
            "entities_json": self._safe_json_dumps(entities or {}),
            "metadata_json": self._safe_json_dumps(metadata or {}),
            "freshness_score": float(freshness_score or 0.0),
            "credibility_score": float(credibility_score or 0.0),
            "signal_strength": float(signal_strength or 0.0),
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(InformationEvent).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["event_id"],
                    set_={
                        "watch_item_id": excluded.watch_item_id,
                        "title": excluded.title,
                        "summary": excluded.summary,
                        "event_type": excluded.event_type,
                        "impact_direction": excluded.impact_direction,
                        "source_tier": excluded.source_tier,
                        "provider": excluded.provider,
                        "url": excluded.url,
                        "published_at": excluded.published_at,
                        "first_seen_at": excluded.first_seen_at,
                        "last_seen_at": excluded.last_seen_at,
                        "source_mode": excluded.source_mode,
                        "is_new_event": excluded.is_new_event,
                        "duplicate_key": excluded.duplicate_key,
                        "themes_json": excluded.themes_json,
                        "chain_tags_json": excluded.chain_tags_json,
                        "entities_json": excluded.entities_json,
                        "metadata_json": excluded.metadata_json,
                        "freshness_score": excluded.freshness_score,
                        "credibility_score": excluded.credibility_score,
                        "signal_strength": excluded.signal_strength,
                        "status": excluded.status,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(InformationEvent).where(InformationEvent.event_id == event_id).limit(1)
            ).scalars().first()

    def get_information_event(self, event_id: str) -> Optional[InformationEvent]:
        with self.session_scope() as session:
            return session.execute(
                select(InformationEvent).where(InformationEvent.event_id == event_id).limit(1)
            ).scalars().first()

    def get_latest_information_event_by_duplicate_key(self, duplicate_key: str) -> Optional[InformationEvent]:
        with self.session_scope() as session:
            return session.execute(
                select(InformationEvent)
                .where(InformationEvent.duplicate_key == duplicate_key)
                .order_by(desc(InformationEvent.last_seen_at), desc(InformationEvent.created_at))
                .limit(1)
            ).scalars().first()

    def list_information_events(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
        promoted_only: bool = False,
        source_mode: Optional[str] = None,
    ) -> List[InformationEvent]:
        stmt = select(InformationEvent)
        if status:
            stmt = stmt.where(InformationEvent.status == status)
        if promoted_only:
            stmt = stmt.where(InformationEvent.status == "promoted")
        if source_mode:
            stmt = stmt.where(InformationEvent.source_mode == source_mode)
        stmt = stmt.order_by(
            desc(InformationEvent.last_seen_at),
            desc(InformationEvent.signal_strength),
            desc(InformationEvent.created_at),
        ).limit(max(1, int(limit)))
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())

    def save_theme_factor_scan_history(
        self,
        *,
        scan_id: str,
        event_id: str,
        theme_id: Optional[str],
        theme_name: str,
        status: str,
        event_score: Optional[float],
        etf_confirmation_score: Optional[float],
        leader_confirmation_score: Optional[float],
        theme_factor_score: Optional[float],
        request_payload: Dict[str, Any],
        result_payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> ThemeFactorScanHistory:
        now = datetime.now()
        values = {
            "scan_id": scan_id,
            "event_id": event_id,
            "theme_id": theme_id,
            "theme_name": theme_name,
            "status": status,
            "event_score": event_score,
            "etf_confirmation_score": etf_confirmation_score,
            "leader_confirmation_score": leader_confirmation_score,
            "theme_factor_score": theme_factor_score,
            "request_payload": self._safe_json_dumps(request_payload or {}),
            "result_payload": self._safe_json_dumps(result_payload) if result_payload is not None else None,
            "error": error,
            "created_at": now,
            "updated_at": now,
        }
        with self.session_scope() as session:
            stmt = duckdb_insert(ThemeFactorScanHistory).values(values)
            excluded = stmt.excluded
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["scan_id"],
                    set_={
                        "event_id": excluded.event_id,
                        "theme_id": excluded.theme_id,
                        "theme_name": excluded.theme_name,
                        "status": excluded.status,
                        "event_score": excluded.event_score,
                        "etf_confirmation_score": excluded.etf_confirmation_score,
                        "leader_confirmation_score": excluded.leader_confirmation_score,
                        "theme_factor_score": excluded.theme_factor_score,
                        "request_payload": excluded.request_payload,
                        "result_payload": excluded.result_payload,
                        "error": excluded.error,
                        "updated_at": excluded.updated_at,
                    },
                )
            )
            return session.execute(
                select(ThemeFactorScanHistory).where(ThemeFactorScanHistory.scan_id == scan_id).limit(1)
            ).scalars().first()

    def get_theme_factor_scan_history(self, scan_id: str) -> Optional[ThemeFactorScanHistory]:
        with self.session_scope() as session:
            return session.execute(
                select(ThemeFactorScanHistory).where(ThemeFactorScanHistory.scan_id == scan_id).limit(1)
            ).scalars().first()

    def list_theme_factor_scan_history(
        self,
        *,
        limit: int = 20,
        event_id: Optional[str] = None,
    ) -> List[ThemeFactorScanHistory]:
        stmt = select(ThemeFactorScanHistory)
        if event_id:
            stmt = stmt.where(ThemeFactorScanHistory.event_id == event_id)
        stmt = stmt.order_by(desc(ThemeFactorScanHistory.created_at), desc(ThemeFactorScanHistory.id)).limit(
            max(1, int(limit))
        )
        with self.session_scope() as session:
            return list(session.execute(stmt).scalars().all())


def get_db() -> DatabaseManager:
    return DatabaseManager.get_instance()
