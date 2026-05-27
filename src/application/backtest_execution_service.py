# -*- coding: utf-8 -*-
"""Async execution helpers for strategy backtest runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from theme_picker.storage import (
    DatabaseManager,
    StrategyBacktestRun,
    StrategyBacktestStockPoolMember,
    get_db,
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_slug(value: Any, fallback: str = "backtest") -> str:
    text = str(value or "").strip().lower()
    chars = [ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in text]
    slug = "".join(chars).strip("-_")
    return slug or fallback


@dataclass
class BacktestExecutionJob:
    job_id: str
    status: str = "pending"
    progress: int = 0
    message: str = "回测任务已加入队列"
    request_payload: dict[str, Any] = field(default_factory=dict)
    command: list[str] = field(default_factory=list)
    output_dir: Optional[str] = None
    summary_path: Optional[str] = None
    return_code: Optional[int] = None
    stdout_tail: Optional[str] = None
    stderr_tail: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "request_payload": self.request_payload,
            "command": self.command,
            "output_dir": self.output_dir,
            "summary_path": self.summary_path,
            "return_code": self.return_code,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BacktestExecutionJob":
        return cls(
            job_id=str(payload.get("job_id") or ""),
            status=str(payload.get("status") or "pending"),
            progress=int(payload.get("progress") or 0),
            message=str(payload.get("message") or ""),
            request_payload=payload.get("request_payload") if isinstance(payload.get("request_payload"), dict) else {},
            command=payload.get("command") if isinstance(payload.get("command"), list) else [],
            output_dir=payload.get("output_dir"),
            summary_path=payload.get("summary_path"),
            return_code=payload.get("return_code"),
            stdout_tail=payload.get("stdout_tail"),
            stderr_tail=payload.get("stderr_tail"),
            created_at=str(payload.get("created_at") or _now_iso()),
            started_at=payload.get("started_at"),
            completed_at=payload.get("completed_at"),
        )


class BacktestExecutionService:
    """Run batch backtests from the API without blocking the request thread."""

    _instance: Optional["BacktestExecutionService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, project_root: str | Path | None = None, max_workers: int = 1):
        if getattr(self, "_initialized", False):
            return
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.data_dir = self.project_root / "data" / "backtests"
        self.jobs_dir = self.data_dir / "jobs"
        self.params_dir = self.data_dir / "generated_params"
        self.output_root = self.data_dir / "api_runs"
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="backtest_run_")
        self._lock = threading.RLock()
        self._db: DatabaseManager = get_db()
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.params_dir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        job_id = self._make_job_id(normalized)
        job = BacktestExecutionJob(job_id=job_id, request_payload=normalized)
        self._save_job(job)
        self._executor.submit(self._run_job, job_id)
        return job.to_dict()

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        return BacktestExecutionJob.from_dict(json.loads(path.read_text(encoding="utf-8"))).to_dict()

    def _run_job(self, job_id: str) -> None:
        job = BacktestExecutionJob.from_dict(json.loads(self._job_path(job_id).read_text(encoding="utf-8")))
        try:
            job.status = "running"
            job.progress = 15
            job.started_at = _now_iso()
            job.message = "正在准备回测参数"
            self._save_job(job)

            command, output_dir = self._build_command(job)
            job.command = command
            job.output_dir = str(output_dir)
            job.summary_path = str(output_dir / "summary.json")
            job.progress = 35
            job.message = "正在执行回测脚本"
            self._save_job(job)

            completed = subprocess.run(
                command,
                cwd=str(self.project_root),
                check=False,
                capture_output=True,
                text=True,
            )
            job.return_code = completed.returncode
            job.stdout_tail = self._tail(completed.stdout)
            job.stderr_tail = self._tail(completed.stderr)
            job.completed_at = _now_iso()
            job.progress = 100
            if completed.returncode == 0:
                job.status = "completed"
                job.message = "回测已完成并导入数据库"
            else:
                job.status = "failed"
                job.message = "回测脚本执行失败"
        except Exception as exc:
            job.status = "failed"
            job.progress = 100
            job.message = f"回测任务失败: {exc}"
            job.stderr_tail = str(exc)
            job.completed_at = _now_iso()
        self._save_job(job)

    def _build_command(self, job: BacktestExecutionJob) -> tuple[list[str], Path]:
        payload = job.request_payload
        strategy = str(payload.get("strategy") or "a_share_box")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = self.output_root / f"{timestamp}_{job.job_id}_{_safe_slug(strategy)}"
        output_dir.mkdir(parents=True, exist_ok=True)

        params_path = self.params_dir / f"{job.job_id}.json"
        params_path.write_text(
            json.dumps(payload.get("params") or {}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        stock_codes_arg, stock_pool_path = self._resolve_stock_codes_arg(payload, job.job_id)
        command = [
            sys.executable,
            str(self.project_root / "scripts" / "run_backtest_batch.py"),
            "--stock-codes",
            stock_codes_arg,
            "--start-date",
            str(payload.get("start_date")),
            "--end-date",
            str(payload.get("end_date")),
            "--strategy",
            strategy,
            "--price-adjustment",
            str(payload.get("price_adjustment") or "qfq"),
            "--trading-constraints",
            str(payload.get("trading_constraints") or "daily_limits"),
            "--params-file",
            str(params_path),
            "--output-dir",
            str(output_dir),
            "--import-db",
            "--import-equity-mode",
            str(payload.get("equity_mode") or "traded_daily"),
        ]
        if stock_pool_path:
            command.extend(["--import-stock-pool", stock_pool_path])
        return command, output_dir

    def _resolve_stock_codes_arg(self, payload: dict[str, Any], job_id: str) -> tuple[str, Optional[str]]:
        stock_pool_path = payload.get("stock_pool_path")
        if stock_pool_path:
            path = self._resolve_project_path(str(stock_pool_path))
            return str(path), str(path)

        stock_codes = payload.get("stock_codes")
        if isinstance(stock_codes, list) and stock_codes:
            return ",".join(str(code).strip().upper() for code in stock_codes if str(code).strip()), None

        base_run_id = str(payload.get("base_run_id") or "").strip()
        if base_run_id:
            codes = self._stock_codes_from_run(base_run_id)
            if codes:
                path = self.params_dir / f"{job_id}-stock-pool.json"
                path.write_text(json.dumps({"stock_codes": codes}, ensure_ascii=False, indent=2), encoding="utf-8")
                return str(path), str(path)

        raise ValueError("执行回测需要 stockPoolPath、stockCodes 或 baseRunId")

    def _stock_codes_from_run(self, run_id: str) -> list[str]:
        with self._db.session_scope() as session:
            run = session.execute(
                select(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id).limit(1)
            ).scalars().first()
            if run is None or not run.stock_pool_id:
                return []
            rows = session.execute(
                select(StrategyBacktestStockPoolMember.stock_code)
                .where(StrategyBacktestStockPoolMember.pool_id == run.stock_pool_id)
                .order_by(StrategyBacktestStockPoolMember.position.asc())
            ).all()
        return [str(row[0]).strip().upper() for row in rows if row and row[0]]

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload or {})
        if not normalized.get("start_date"):
            raise ValueError("startDate 不能为空")
        if not normalized.get("end_date"):
            raise ValueError("endDate 不能为空")
        normalized["strategy"] = str(normalized.get("strategy") or "a_share_box")
        normalized["params"] = normalized.get("params") if isinstance(normalized.get("params"), dict) else {}
        return normalized

    def _resolve_project_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{_safe_slug(job_id)}.json"

    def _save_job(self, job: BacktestExecutionJob) -> None:
        with self._lock:
            self._job_path(job.job_id).write_text(
                json.dumps(job.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    @staticmethod
    def _tail(text: str, limit: int = 6000) -> str:
        return (text or "")[-limit:]

    @staticmethod
    def _make_job_id(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True) + datetime.now().isoformat(timespec="microseconds")
        return "btj_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
