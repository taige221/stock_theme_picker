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
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from theme_picker.config import get_config

logger = logging.getLogger(__name__)

Base = declarative_base()
_UNSET = object()
UNSET = _UNSET


class StockDaily(Base):
    __tablename__ = "stock_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
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


class ThemePickerTaskHistory(Base):
    __tablename__ = "theme_picker_task_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, unique=True, index=True)
    boards_payload = Column(Text, nullable=False)
    source = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_belong_boards_cache_updated", "updated_at"),
    )


class StockWatchlist(Base):
    __tablename__ = "stock_watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=False)
    rule_type = Column(String(32), nullable=False, index=True)
    threshold_value = Column(Float, nullable=True)
    scan_interval_minutes = Column(Integer, nullable=False, default=5)
    enabled = Column(Integer, nullable=False, default=1)
    note = Column(Text, nullable=True)
    source_query_id = Column(String(64), nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True, index=True)
    last_triggered_at = Column(DateTime, nullable=True, index=True)
    last_trigger_key = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("stock_code", "rule_type", name="uix_stock_alert_rule_code_type"),
        Index("ix_stock_alert_rule_code_updated", "stock_code", "updated_at"),
    )


class StockAlertEvent(Base):
    __tablename__ = "stock_alert_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_stock_deep_analysis_message_created", "analysis_id", "created_at"),
    )


class InformationWatchItem(Base):
    __tablename__ = "information_watch_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
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


@dataclass
class _SqliteSettings:
    database_path: Path
    wal_enabled: bool
    busy_timeout_ms: int


class DatabaseManager:
    """Minimal database manager extracted for theme picker."""

    _instance: Optional["DatabaseManager"] = None

    def __init__(self, database_path: Optional[str] = None) -> None:
        cfg = get_config()
        db_path = Path(database_path or cfg.database_path).expanduser()
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._settings = _SqliteSettings(
            database_path=db_path,
            wal_enabled=bool(getattr(cfg, "sqlite_wal_enabled", True)),
            busy_timeout_ms=int(getattr(cfg, "sqlite_busy_timeout_ms", 5000) or 5000),
        )
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        self._SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=self.engine,
            future=True,
        )
        self._is_sqlite_engine = True
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
        if self._settings.wal_enabled:
            with self.engine.begin() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                conn.exec_driver_sql(f"PRAGMA busy_timeout={self._settings.busy_timeout_ms};")

    def _run_post_create_migrations(self) -> None:
        self._ensure_sqlite_column(
            table_name="stock_alert_rule",
            column_name="scan_interval_minutes",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN scan_interval_minutes INTEGER NOT NULL DEFAULT 5",
        )
        self._ensure_sqlite_column(
            table_name="stock_alert_rule",
            column_name="last_evaluated_at",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_evaluated_at DATETIME NULL",
        )
        self._ensure_sqlite_column(
            table_name="stock_alert_rule",
            column_name="last_triggered_at",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_triggered_at DATETIME NULL",
        )
        self._ensure_sqlite_column(
            table_name="information_event",
            column_name="source_mode",
            alter_sql="ALTER TABLE information_event ADD COLUMN source_mode VARCHAR(20) NOT NULL DEFAULT 'watch'",
        )
        self._ensure_sqlite_index(
            index_name="ix_information_event_source_mode_created",
            create_sql="CREATE INDEX IF NOT EXISTS ix_information_event_source_mode_created ON information_event (source_mode, created_at)",
        )
        self._ensure_sqlite_column(
            table_name="stock_alert_rule",
            column_name="last_trigger_key",
            alter_sql="ALTER TABLE stock_alert_rule ADD COLUMN last_trigger_key VARCHAR(128) NULL",
        )

    def _ensure_sqlite_column(self, *, table_name: str, column_name: str, alter_sql: str) -> None:
        with self.engine.begin() as conn:
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table_name});").fetchall()
            existing = {str(row[1]) for row in rows if len(row) > 1}
            if column_name not in existing:
                conn.exec_driver_sql(alter_sql)

    def _ensure_sqlite_index(self, *, index_name: str, create_sql: str) -> None:
        with self.engine.begin() as conn:
            rows = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index' AND name = :index_name",
                {"index_name": index_name},
            ).fetchall()
            if not rows:
                conn.exec_driver_sql(create_sql)

    def close(self) -> None:
        try:
            self.engine.dispose()
        except Exception:
            pass

    @staticmethod
    def _normalize_daily_date(value: Any) -> Any:
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _normalize_sql_value(value: Any) -> Any:
        return None if pd.isna(value) else value

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

        with self.session_scope() as session:
            for item in records:
                stmt = sqlite_insert(StockDaily).values(item)
                excluded = stmt.excluded
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["code", "date"],
                        set_={
                            "open": excluded.open,
                            "high": excluded.high,
                            "low": excluded.low,
                            "close": excluded.close,
                            "volume": excluded.volume,
                            "amount": excluded.amount,
                            "pct_chg": excluded.pct_chg,
                            "ma5": excluded.ma5,
                            "ma10": excluded.ma10,
                            "ma20": excluded.ma20,
                            "volume_ratio": excluded.volume_ratio,
                            "data_source": excluded.data_source,
                            "updated_at": excluded.updated_at,
                        },
                    )
                )
        return len(records)

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
            stmt = sqlite_insert(ThemePickerTaskHistory).values(values)
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
            stmt = sqlite_insert(StockQueryHistory).values(values)
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
            stmt = sqlite_insert(EtfQueryHistory).values(values)
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

        with self.session_scope() as session:
            for item in normalized_rows:
                stmt = sqlite_insert(EtfDailyMetricsSnapshot).values(item)
                excluded = stmt.excluded
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["stock_code", "trade_date"],
                        set_={
                            "fund_shares": excluded.fund_shares,
                            "nav": excluded.nav,
                            "derived_fund_size_yi": excluded.derived_fund_size_yi,
                            "exchange": excluded.exchange,
                            "data_source": excluded.data_source,
                            "updated_at": excluded.updated_at,
                        },
                    )
                )
        return len(normalized_rows)

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
            stmt = sqlite_insert(StockBelongBoardsCache).values(values)
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
            stmt = sqlite_insert(StockWatchlist).values(
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
            stmt = sqlite_insert(StockAlertRule).values(
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
            stmt = sqlite_insert(StockDeepAnalysisHistory).values(values)
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
            stmt = sqlite_insert(InformationWatchItem).values(values)
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
            stmt = sqlite_insert(OpenDiscoveryProfile).values(values)
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
            stmt = sqlite_insert(InformationEvent).values(values)
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
            stmt = sqlite_insert(ThemeFactorScanHistory).values(values)
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
