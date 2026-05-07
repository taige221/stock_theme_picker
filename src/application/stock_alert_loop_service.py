# -*- coding: utf-8 -*-
"""
===================================
Single Stock Alert Loop Service
===================================
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from dataclasses import asdict
from typing import Optional

from theme_picker.application.stock_alert_service import StockAlertService
from theme_picker.config import get_config

logger = logging.getLogger(__name__)


class StockAlertLoopService:
    """Background loop that periodically runs the stock alert scanner."""

    def __init__(
        self,
        *,
        alert_service: Optional[StockAlertService] = None,
        base_tick_seconds: Optional[int] = None,
    ) -> None:
        self.config = get_config()
        self.alert_service = alert_service or StockAlertService()
        configured_tick = int(getattr(self.config, "stock_alert_loop_base_tick_seconds", 60) or 60)
        self.base_tick_seconds = max(5, int(base_tick_seconds or configured_tick))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.last_started_at: Optional[datetime] = None
        self.last_finished_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.last_summary: Optional[dict] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        with self._lock:
            if self.is_running:
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self.run_forever,
                name="theme-picker-stock-alert-loop",
                daemon=True,
            )
            self._thread.start()
            logger.info("[StockAlertLoop] started with base_tick_seconds=%s", self.base_tick_seconds)
            return True

    def stop(self, *, join_timeout_seconds: float = 5.0) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return False
            self._stop_event.set()
        thread.join(timeout=max(0.1, float(join_timeout_seconds)))
        with self._lock:
            self._thread = None
        logger.info("[StockAlertLoop] stopped")
        return True

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.last_started_at = datetime.now()
                summary = self.alert_service.run_once()
                self.last_finished_at = datetime.now()
                self.last_error = None
                self.last_summary = asdict(summary)
                logger.info(
                    "[StockAlertLoop] cycle complete scanned_rules=%s due_rules=%s triggered_events=%s skipped_rules=%s",
                    summary.scanned_rules,
                    summary.due_rules,
                    summary.triggered_events,
                    summary.skipped_rules,
                )
            except Exception as exc:
                self.last_finished_at = datetime.now()
                self.last_error = str(exc)
                logger.exception("[StockAlertLoop] cycle failed")
            if self._stop_event.wait(timeout=self.base_tick_seconds):
                break

    def status(self) -> dict:
        return {
            "running": self.is_running,
            "base_tick_seconds": self.base_tick_seconds,
            "last_started_at": self.last_started_at.isoformat() if self.last_started_at else None,
            "last_finished_at": self.last_finished_at.isoformat() if self.last_finished_at else None,
            "last_error": self.last_error,
            "last_summary": self.last_summary,
        }
