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
        if self._settings.wal_enabled:
            with self.engine.begin() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                conn.exec_driver_sql(f"PRAGMA busy_timeout={self._settings.busy_timeout_ms};")

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


def get_db() -> DatabaseManager:
    return DatabaseManager.get_instance()

