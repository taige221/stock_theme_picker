# -*- coding: utf-8 -*-
"""
===================================
Information Watch Loop Service
===================================
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from theme_picker.application.information_watch_service import InformationWatchService
from theme_picker.application.open_discovery_pool_service import OpenDiscoveryPoolService
from theme_picker.application.theme_factor_scan_service import ThemeFactorScanService
from theme_picker.config import get_config

logger = logging.getLogger(__name__)


class InformationWatchLoopService:
    """Background loop that periodically scans the information watch pool."""

    def __init__(
        self,
        *,
        information_watch_service: Optional[InformationWatchService] = None,
        open_discovery_service: Optional[OpenDiscoveryPoolService] = None,
        theme_factor_scan_service: Optional[ThemeFactorScanService] = None,
        base_tick_seconds: Optional[int] = None,
    ) -> None:
        self.config = get_config()
        self.information_watch_service = information_watch_service or InformationWatchService()
        self.open_discovery_service = open_discovery_service or OpenDiscoveryPoolService()
        self.theme_factor_scan_service = theme_factor_scan_service or ThemeFactorScanService()
        configured_tick = int(getattr(self.config, "information_watch_loop_base_tick_seconds", 300) or 300)
        self.base_tick_seconds = max(30, int(base_tick_seconds or configured_tick))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.last_started_at: Optional[datetime] = None
        self.last_finished_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.last_scan_summary: Optional[dict] = None
        self.last_watch_scan_at: Optional[datetime] = None
        self.last_discovery_summary: Optional[dict] = None
        self.last_discovery_scan_at: Optional[datetime] = None
        self.last_factor_summary: Optional[dict] = None

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
                name="theme-picker-information-watch-loop",
                daemon=True,
            )
            self._thread.start()
            logger.info("[InformationWatchLoop] started with base_tick_seconds=%s", self.base_tick_seconds)
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
        logger.info("[InformationWatchLoop] stopped")
        return True

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.last_started_at = datetime.now()
                now = datetime.now()
                watch_interval_seconds = int(getattr(self.config, "information_watch_scan_interval_minutes", 60) or 60) * 60
                discovery_interval_seconds = int(getattr(self.config, "open_discovery_scan_interval_minutes", 120) or 120) * 60
                promoted_event_ids = set()

                if self._should_run(last_run_at=self.last_watch_scan_at, interval_seconds=watch_interval_seconds, now=now):
                    scan_summary = self.information_watch_service.run_once(limit=20)
                    self.last_scan_summary = {
                        "scanned_items": int(scan_summary.get("scanned_items") or 0),
                        "created_events": int(scan_summary.get("created_events") or 0),
                        "promoted_events": int(scan_summary.get("promoted_events") or 0),
                    }
                    promoted_event_ids.update(
                        str(event_id).strip()
                        for event_id in (scan_summary.get("promoted_event_ids") or [])
                        if str(event_id).strip()
                    )
                    self.last_watch_scan_at = now
                if bool(getattr(self.config, "open_discovery_pool_enabled", False)):
                    if self._should_run(last_run_at=self.last_discovery_scan_at, interval_seconds=discovery_interval_seconds, now=now):
                        discovery_summary = self.open_discovery_service.run_once(limit=8)
                        self.last_discovery_summary = {
                            "scanned_profiles": int(discovery_summary.get("scanned_profiles") or 0),
                            "created_events": int(discovery_summary.get("created_events") or 0),
                            "promoted_events": int(discovery_summary.get("promoted_events") or 0),
                        }
                        promoted_event_ids.update(
                            str(event_id).strip()
                            for event_id in (discovery_summary.get("promoted_event_ids") or [])
                            if str(event_id).strip()
                        )
                        self.last_discovery_scan_at = now
                if bool(getattr(self.config, "theme_factor_scan_auto_enabled", False)) and promoted_event_ids:
                    factor_summary = self.theme_factor_scan_service.run_once(
                        event_ids=sorted(promoted_event_ids),
                        limit=len(promoted_event_ids),
                    )
                    self.last_factor_summary = {
                        "scanned_events": int(factor_summary.get("scanned_events") or 0),
                        "generated_scans": int(factor_summary.get("generated_scans") or 0),
                    }
                self.last_finished_at = datetime.now()
                self.last_error = None
                logger.info("[InformationWatchLoop] cycle complete summary=%s", self.last_scan_summary)
            except Exception as exc:
                self.last_finished_at = datetime.now()
                self.last_error = str(exc)
                logger.exception("[InformationWatchLoop] cycle failed")
            wait_seconds = max(
                self.base_tick_seconds,
                min(
                    int(getattr(self.config, "information_watch_scan_interval_minutes", 60) or 60) * 60,
                    int(getattr(self.config, "open_discovery_scan_interval_minutes", 120) or 120) * 60,
                )
                if bool(getattr(self.config, "open_discovery_pool_enabled", False))
                else int(getattr(self.config, "information_watch_scan_interval_minutes", 60) or 60) * 60,
            )
            if self._stop_event.wait(timeout=wait_seconds):
                break

    @staticmethod
    def _should_run(*, last_run_at: Optional[datetime], interval_seconds: int, now: datetime) -> bool:
        if last_run_at is None:
            return True
        return (now - last_run_at).total_seconds() >= max(30, int(interval_seconds))

    def status(self) -> dict:
        return {
            "running": self.is_running,
            "base_tick_seconds": self.base_tick_seconds,
            "last_started_at": self.last_started_at.isoformat() if self.last_started_at else None,
            "last_finished_at": self.last_finished_at.isoformat() if self.last_finished_at else None,
            "last_error": self.last_error,
            "last_scan_summary": self.last_scan_summary,
            "last_discovery_summary": self.last_discovery_summary,
            "last_factor_summary": self.last_factor_summary,
        }
