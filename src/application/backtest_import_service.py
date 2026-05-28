# -*- coding: utf-8 -*-
"""Import strategy backtest JSON artifacts into DuckDB-backed history."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Literal, Optional, cast

from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import OperationalError

from theme_picker.storage import (
    DatabaseManager,
    StockDaily,
    StockDailyRaw,
    StrategyBacktestEquityPoint,
    StrategyBacktestImportBatch,
    StrategyBacktestRun,
    StrategyBacktestStockPool,
    StrategyBacktestStockPoolMember,
    StrategyBacktestSymbolResult,
    StrategyBacktestTrade,
    get_db,
)
from theme_picker.strategy import STRATEGY_METADATA, STRATEGY_REGISTRY
from theme_picker.strategy.params import StrategyParams

EquityImportMode = Literal["portfolio_only", "traded_daily", "all_daily"]
EQUITY_IMPORT_MODES = {"portfolio_only", "traded_daily", "all_daily"}
DEFAULT_EQUITY_IMPORT_MODE: EquityImportMode = "traded_daily"


@dataclass(frozen=True)
class BacktestImportResult:
    import_id: str
    status: str
    run_id: Optional[str]
    artifact_digest: Optional[str]
    counts: dict[str, Any]
    warnings: list[str]
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_id": self.import_id,
            "status": self.status,
            "run_id": self.run_id,
            "artifact_digest": self.artifact_digest,
            "counts": self.counts,
            "warnings": self.warnings,
            "dry_run": self.dry_run,
        }


class BacktestImportService:
    """Imports batch summary JSON plus per-stock JSON detail files.

    The importer treats JSON artifacts as reproducible outputs. Re-importing the
    same artifact is idempotent: run-level rows are updated and child rows are
    rebuilt from the current files.
    """

    def __init__(self, db: Optional[DatabaseManager] = None, *, project_root: Optional[Path] = None) -> None:
        self.db = db or get_db()
        self.project_root = Path(project_root or Path(__file__).resolve().parents[2])

    def import_artifact(
        self,
        source_path: str | Path,
        *,
        stock_pool_path: str | Path | None = None,
        mode: str = "upsert",
        dry_run: bool = False,
        equity_mode: EquityImportMode | str = DEFAULT_EQUITY_IMPORT_MODE,
    ) -> BacktestImportResult:
        started_at = datetime.now()
        warnings: list[str] = []
        normalized_equity_mode = self._normalize_equity_import_mode(equity_mode)
        source = self._resolve_summary_path(source_path)
        stock_pool = self._resolve_project_path(stock_pool_path) if stock_pool_path else None
        summary = self._read_json(source)
        self._validate_summary(summary, source)

        symbol_payloads = self._load_symbol_payloads(summary, source.parent, warnings)
        artifact_digest = self._artifact_digest(source, summary, symbol_payloads)
        logical_signature = self._logical_signature(summary, stock_pool, symbol_payloads)
        run_id = self._make_id("bt", artifact_digest)
        import_id = self._make_id("bti", f"{artifact_digest}:{started_at.isoformat(timespec='microseconds')}")
        stock_pool_info = self._build_stock_pool(summary, stock_pool, symbol_payloads)
        aggregate = summary.get("aggregate") or {}
        portfolio_points = self._derive_portfolio_equity(symbol_payloads)
        derived = self._derive_trade_metrics(symbol_payloads)
        derived.update(self._derive_portfolio_metrics(portfolio_points))
        symbol_equity_point_count = self._symbol_equity_point_count(
            symbol_payloads,
            equity_mode=normalized_equity_mode,
        )
        symbol_equity_points_seen = sum(
            len((item.get("_detail") or {}).get("equity_curve") or []) for item in symbol_payloads
        )
        run_values = self._run_values(
            run_id=run_id,
            source=source,
            summary=summary,
            aggregate=aggregate,
            artifact_digest=artifact_digest,
            logical_signature=logical_signature,
            stock_pool_info=stock_pool_info,
            derived=derived,
            generated_at=self._parse_datetime(summary.get("generated_at")) or started_at,
        )
        counts = {
            "symbols_seen": len(summary.get("results") or []),
            "symbols_imported": len(symbol_payloads),
            "symbols_missing_detail": sum(1 for item in symbol_payloads if item.get("_detail") is None),
            "trades_imported": sum(len((item.get("_detail") or {}).get("trades") or []) for item in symbol_payloads),
            "symbol_equity_points_seen": symbol_equity_points_seen,
            "symbol_equity_points_imported": symbol_equity_point_count,
            "portfolio_equity_points_imported": len(portfolio_points),
            "equity_import_mode": normalized_equity_mode,
        }

        if dry_run:
            return BacktestImportResult(
                import_id=import_id,
                status="dry_run",
                run_id=run_id,
                artifact_digest=artifact_digest,
                counts=counts,
                warnings=warnings,
                dry_run=True,
            )

        try:
            with self.db.session_scope() as session:
                self._upsert_stock_pool(session, stock_pool_info)
                existing = session.execute(
                    select(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id).limit(1)
                ).scalars().first()
                if existing is None:
                    session.add(StrategyBacktestRun(**run_values))
                else:
                    for key, value in run_values.items():
                        setattr(existing, key, value)

                self._delete_run_children(session, run_id)
                session.flush()
                self._bulk_save(session, self._symbol_rows(run_id, symbol_payloads, stock_pool_info, aggregate))
                self._bulk_save(session, self._trade_rows(run_id, symbol_payloads, stock_pool_info))
                self._bulk_save(
                    session,
                    self._symbol_equity_rows(
                        run_id,
                        symbol_payloads,
                        equity_mode=normalized_equity_mode,
                    ),
                )
                self._bulk_save(session, self._portfolio_equity_rows(run_id, portfolio_points))
                session.add(
                    StrategyBacktestImportBatch(
                        import_id=import_id,
                        status="finished",
                        source_path=self._display_path(source),
                        stock_pool_path=self._display_path(stock_pool) if stock_pool else None,
                        mode=mode,
                        dry_run=0,
                        run_id=run_id,
                        artifact_digest=artifact_digest,
                        counts_payload=self._dumps(counts),
                        warnings_payload=self._dumps(warnings),
                        started_at=started_at,
                        completed_at=datetime.now(),
                    )
                )
        except OperationalError as exc:
            text = str(exc).lower()
            if "database is locked" in text or "single-writer" in text or "conflicting lock" in text:
                raise RuntimeError(
                    "DuckDB database is locked. Backtest import is a single-writer operation; "
                    "stop other theme_picker servers/import jobs or retry after the current write finishes."
                ) from exc
            raise

        return BacktestImportResult(
            import_id=import_id,
            status="finished",
            run_id=run_id,
            artifact_digest=artifact_digest,
            counts=counts,
            warnings=warnings,
            dry_run=False,
        )

    def list_runs(self, *, limit: int = 20, strategy: str | None = None, status: str | None = None) -> dict[str, Any]:
        stmt = select(StrategyBacktestRun)
        if strategy:
            stmt = stmt.where(StrategyBacktestRun.strategy == strategy)
        if status:
            stmt = stmt.where(StrategyBacktestRun.status == status)
        stmt = stmt.order_by(desc(StrategyBacktestRun.generated_at), desc(StrategyBacktestRun.id)).limit(max(1, limit))
        with self.db.session_scope() as session:
            items = [self._run_to_list_item(row) for row in session.execute(stmt).scalars().all()]
        return {"items": items, "next_cursor": None}

    def list_presets(self) -> dict[str, Any]:
        default_params = StrategyParams().to_dict()
        with self.db.session_scope() as session:
            run_rows = (
                session.execute(
                    select(StrategyBacktestRun)
                    .where(StrategyBacktestRun.strategy.in_(list(STRATEGY_REGISTRY.keys())))
                    .order_by(desc(StrategyBacktestRun.generated_at), desc(StrategyBacktestRun.id))
                    .limit(120)
                )
                .scalars()
                .all()
            )

        rows_by_strategy: dict[str, list[StrategyBacktestRun]] = defaultdict(list)
        for row in run_rows:
            if len(rows_by_strategy[row.strategy]) < 8:
                rows_by_strategy[row.strategy].append(row)

        builtin_items = []
        for strategy_id in STRATEGY_REGISTRY.keys():
            metadata = STRATEGY_METADATA.get(strategy_id, {})
            latest_rows = rows_by_strategy.get(strategy_id, [])
            latest = latest_rows[0] if latest_rows else None
            latest_params = self._loads(latest.params_payload) if latest else None
            params = {**default_params, **(latest_params if isinstance(latest_params, dict) else {})}
            stock_pool = None
            if latest is not None:
                member_summary = self._stock_pool_member_summary(latest.stock_pool_id)
                stock_pool = {
                    "pool_id": latest.stock_pool_id,
                    "name": latest.stock_pool_name,
                    "source_path": self._stock_pool_source_path(latest.stock_pool_id),
                    "total_symbols": latest.total_symbols,
                    "description": self._stock_pool_description(latest.stock_pool_name, latest.total_symbols),
                    "named_symbols": member_summary["named_symbols"],
                    "members_preview": member_summary["members_preview"],
                }
            versions = [
                {
                    "run_id": row.run_id,
                    "strategy_version": row.strategy_version,
                    "stock_pool_name": row.stock_pool_name,
                    "total_symbols": row.total_symbols,
                    "start_date": self._date_to_str(row.start_date),
                    "end_date": self._date_to_str(row.end_date),
                    "generated_at": self._datetime_to_str(row.generated_at),
                }
                for row in latest_rows
            ]
            builtin_items.append(
                {
                    "preset_id": strategy_id,
                    "name": metadata.get("name") or strategy_id,
                    "strategy": strategy_id,
                    "strategy_version": latest.strategy_version if latest else None,
                    "description": metadata.get("description") or "已注册的本地回测策略。",
                    "category": metadata.get("category") or "custom",
                    "is_builtin": True,
                    "is_default": bool(metadata.get("is_default")),
                    "params": params,
                    "default_params": default_params,
                    "imported_run_id": latest.run_id if latest else None,
                    "imported_versions": versions,
                    "stock_pool": stock_pool,
                    "stock_pool_summary": stock_pool["description"] if stock_pool else "尚未导入股票池；导入 summary.json 后会显示真实股票池。",
                    "constraints": {
                        "price_adjustment": latest.price_adjustment if latest else "qfq",
                        "trading_constraints": latest.trading_constraints if latest else "daily_limits",
                    },
                }
            )
        saved_items = self._load_saved_presets()
        return {"items": [*builtin_items, *saved_items]}

    def save_preset(
        self,
        *,
        name: str,
        strategy: str,
        params: dict[str, Any],
        constraints: dict[str, Any],
        description: str | None = None,
        stock_pool: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        payload = {
            "name": str(name).strip(),
            "strategy": str(strategy or "a_share_box").strip(),
            "description": description,
            "params": params if isinstance(params, dict) else {},
            "constraints": constraints if isinstance(constraints, dict) else {},
            "stock_pool": stock_pool if isinstance(stock_pool, dict) else None,
            "updated_at": now,
        }
        preset_id = self._make_id("preset", json.dumps(payload, ensure_ascii=False, sort_keys=True))
        item = {
            "preset_id": preset_id,
            "is_builtin": False,
            "is_default": False,
            "created_at": now,
            **payload,
        }
        path = self._saved_presets_path()
        presets = [preset for preset in self._load_saved_presets() if preset.get("preset_id") != preset_id]
        presets.insert(0, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(presets[:50], ensure_ascii=False, indent=2), encoding="utf-8")
        return {"item": item}

    def delete_preset(self, preset_id: str) -> dict[str, Any]:
        preset_id = str(preset_id or "").strip()
        if not preset_id:
            raise ValueError("preset_id 不能为空")
        if preset_id in STRATEGY_REGISTRY:
            raise ValueError("内置策略预设不能删除")
        presets = self._load_saved_presets()
        remaining = [item for item in presets if item.get("preset_id") != preset_id]
        if len(remaining) == len(presets):
            raise FileNotFoundError(f"preset not found: {preset_id}")
        path = self._saved_presets_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "deleted", "preset_id": preset_id}

    def delete_run(self, run_id: str) -> dict[str, Any]:
        run_id = str(run_id or "").strip()
        if not run_id:
            raise ValueError("run_id 不能为空")
        with self.db.session_scope() as session:
            row = session.execute(
                select(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id).limit(1)
            ).scalars().first()
            if row is None:
                raise FileNotFoundError(f"backtest run not found: {run_id}")
            stock_pool_id = row.stock_pool_id
            self._delete_run_children(session, run_id)
            session.execute(delete(StrategyBacktestImportBatch).where(StrategyBacktestImportBatch.run_id == run_id))
            session.execute(delete(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id))
            self._delete_orphan_stock_pool(session, stock_pool_id)
        return {"status": "deleted", "run_id": run_id}

    def _saved_presets_path(self) -> Path:
        return self.project_root / "data" / "backtests" / "saved_presets.json"

    def _load_saved_presets(self) -> list[dict[str, Any]]:
        path = self._saved_presets_path()
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict) and item.get("preset_id")]

    def _stock_pool_source_path(self, pool_id: Any) -> Optional[str]:
        if not pool_id:
            return None
        with self.db.session_scope() as session:
            row = session.execute(
                select(StrategyBacktestStockPool.source_path)
                .where(StrategyBacktestStockPool.pool_id == str(pool_id))
                .limit(1)
            ).first()
        return str(row[0]) if row and row[0] else None

    def _stock_pool_member_summary(self, pool_id: Any, limit: int = 12) -> dict[str, Any]:
        if not pool_id:
            return {"named_symbols": 0, "members_preview": []}
        with self.db.session_scope() as session:
            rows = (
                session.execute(
                    select(
                        StrategyBacktestStockPoolMember.stock_code,
                        StrategyBacktestStockPoolMember.stock_name,
                    )
                    .where(StrategyBacktestStockPoolMember.pool_id == str(pool_id))
                    .order_by(StrategyBacktestStockPoolMember.rank.asc(), StrategyBacktestStockPoolMember.id.asc())
                )
                .all()
            )
        members = [
            {
                "stock_code": str(code),
                "stock_name": name,
            }
            for code, name in rows
            if code
        ]
        named_symbols = sum(1 for item in members if item.get("stock_name"))
        return {
            "named_symbols": named_symbols,
            "members_preview": members[:limit],
        }

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self.db.session_scope() as session:
            row = session.execute(
                select(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id).limit(1)
            ).scalars().first()
            if row is None:
                return None
            return self._run_to_detail(session, row)

    def get_equity_curve(
        self,
        run_id: str,
        *,
        scope: str = "portfolio",
        stock_code: str | None = None,
        limit: int = 5000,
    ) -> dict[str, Any]:
        stmt = select(StrategyBacktestEquityPoint).where(
            StrategyBacktestEquityPoint.run_id == run_id,
            StrategyBacktestEquityPoint.scope == scope,
        )
        if stock_code:
            stmt = stmt.where(StrategyBacktestEquityPoint.stock_code == stock_code)
        stmt = stmt.order_by(StrategyBacktestEquityPoint.trade_date.asc()).limit(max(1, limit))
        with self.db.session_scope() as session:
            rows = session.execute(stmt).scalars().all()
        return {
            "run_id": run_id,
            "scope": scope,
            "stock_code": stock_code,
            "points": [self._equity_to_dict(row) for row in rows],
        }

    def list_stocks(
        self,
        run_id: str,
        *,
        result_filter: str = "all",
        sort: str = "total_return_pct",
        order: str = "desc",
        limit: int = 200,
    ) -> dict[str, Any]:
        sort_columns = {
            "total_return_pct": StrategyBacktestSymbolResult.total_return_pct,
            "trade_count": StrategyBacktestSymbolResult.trade_count,
            "win_rate_pct": StrategyBacktestSymbolResult.win_rate_pct,
            "final_equity": StrategyBacktestSymbolResult.final_equity,
            "stock_code": StrategyBacktestSymbolResult.stock_code,
        }
        stmt = select(StrategyBacktestSymbolResult).where(StrategyBacktestSymbolResult.run_id == run_id)
        if result_filter == "profitable":
            stmt = stmt.where(StrategyBacktestSymbolResult.total_return_pct > 0)
        elif result_filter == "losing":
            stmt = stmt.where(StrategyBacktestSymbolResult.total_return_pct < 0)
        elif result_filter == "flat":
            stmt = stmt.where(StrategyBacktestSymbolResult.total_return_pct == 0)
        elif result_filter == "error":
            stmt = stmt.where(StrategyBacktestSymbolResult.status == "error")
        column = sort_columns.get(sort, StrategyBacktestSymbolResult.total_return_pct)
        stmt = stmt.order_by(column.asc() if order == "asc" else desc(column)).limit(max(1, limit))
        with self.db.session_scope() as session:
            rows = session.execute(stmt).scalars().all()
            counts = self._stock_counts(session, run_id)
        return {"items": [self._symbol_to_dict(row) for row in rows], "counts": counts}

    def get_stock_detail(self, run_id: str, stock_code: str) -> Optional[dict[str, Any]]:
        stock_candidates = self._stock_code_candidates(stock_code)
        with self.db.session_scope() as session:
            row = session.execute(
                select(StrategyBacktestSymbolResult).where(
                    StrategyBacktestSymbolResult.run_id == run_id,
                    StrategyBacktestSymbolResult.stock_code.in_(stock_candidates),
                )
            ).scalars().first()
            if row is None:
                return None
            trades = session.execute(
                select(StrategyBacktestTrade)
                .where(StrategyBacktestTrade.run_id == run_id, StrategyBacktestTrade.stock_code == row.stock_code)
                .order_by(StrategyBacktestTrade.entry_date.asc(), StrategyBacktestTrade.id.asc())
            ).scalars().all()
            equity = session.execute(
                select(StrategyBacktestEquityPoint)
                .where(
                    StrategyBacktestEquityPoint.run_id == run_id,
                    StrategyBacktestEquityPoint.scope == "symbol",
                    StrategyBacktestEquityPoint.stock_code == row.stock_code,
                )
                .order_by(StrategyBacktestEquityPoint.trade_date.asc())
            ).scalars().all()
            return {
                **self._symbol_to_dict(row, include_payloads=True),
                "trades": [self._trade_to_dict(item) for item in trades],
                "equity_curve": [self._equity_to_dict(item) for item in equity],
                "holding_ranges": [
                    {
                        "entry_date": self._date_to_str(item.entry_date),
                        "exit_date": self._date_to_str(item.exit_date),
                        "entry_price": item.entry_price,
                        "exit_price": item.exit_price,
                        "return_pct": item.return_pct,
                    }
                    for item in trades
                ],
                "raw_available": {
                    "metrics": bool(row.metrics_payload),
                    "data_context": bool(row.data_context_payload),
                    "latest_signal_metadata": bool(row.latest_signal_metadata_payload),
                    "open_position": bool(row.open_position_payload),
                    "raw_result": bool(row.raw_result_payload),
                },
                "raw_result_summary": self._raw_payload_summary(self._loads(row.raw_result_payload)),
            }

    def get_stock_chart(self, run_id: str, stock_code: str) -> Optional[dict[str, Any]]:
        stock_candidates = self._stock_code_candidates(stock_code)
        with self.db.session_scope() as session:
            run = session.execute(
                select(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id).limit(1)
            ).scalars().first()
            symbol = session.execute(
                select(StrategyBacktestSymbolResult).where(
                    StrategyBacktestSymbolResult.run_id == run_id,
                    StrategyBacktestSymbolResult.stock_code.in_(stock_candidates),
                )
            ).scalars().first()
            if run is None or symbol is None:
                return None
            trades = session.execute(
                select(StrategyBacktestTrade)
                .where(
                    StrategyBacktestTrade.run_id == run_id,
                    StrategyBacktestTrade.stock_code == symbol.stock_code,
                )
                .order_by(StrategyBacktestTrade.entry_date.asc(), StrategyBacktestTrade.id.asc())
            ).scalars().all()
            start_date = symbol.effective_start_date or symbol.requested_start_date or run.start_date
            end_date = symbol.end_date or run.end_date
            raw_rows = self._query_raw_daily_rows(session, symbol.stock_code, start_date, end_date)
            legacy_rows = [] if raw_rows else self._query_legacy_daily_rows(session, symbol.stock_code, start_date, end_date)

        bars = self._chart_bars_from_raw(raw_rows, price_adjustment=run.price_adjustment)
        source = "stock_daily_raw"
        if not bars:
            bars = self._chart_bars_from_legacy(legacy_rows)
            source = "stock_daily"
        bars = self._with_moving_averages(bars)
        markers = self._trade_markers(trades)
        return {
            "run_id": run_id,
            "stock_code": symbol.stock_code,
            "stock_name": symbol.stock_name,
            "price_adjustment": run.price_adjustment,
            "start_date": self._date_to_str(start_date),
            "end_date": self._date_to_str(end_date),
            "data_source": source if bars else None,
            "bars": bars,
            "markers": markers,
            "trades": [self._trade_to_dict(item) for item in trades],
            "latest_signal_metadata": self._loads(symbol.latest_signal_metadata_payload),
            "read_only": True,
        }

    def list_trades(
        self,
        run_id: str,
        *,
        stock_code: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        stmt = select(StrategyBacktestTrade).where(StrategyBacktestTrade.run_id == run_id)
        if stock_code:
            stmt = stmt.where(StrategyBacktestTrade.stock_code.in_(self._stock_code_candidates(stock_code)))
        stmt = stmt.order_by(desc(StrategyBacktestTrade.entry_date), desc(StrategyBacktestTrade.id)).limit(max(1, limit))
        with self.db.session_scope() as session:
            rows = session.execute(stmt).scalars().all()
        return {"items": [self._trade_to_dict(row) for row in rows], "next_cursor": None}

    def _resolve_summary_path(self, value: str | Path) -> Path:
        path = self._resolve_project_path(value)
        if path.is_dir():
            path = path / "summary.json"
        if not path.is_file():
            raise FileNotFoundError(f"summary.json not found: {path}")
        return path

    def _resolve_project_path(self, value: str | Path | None) -> Path:
        if value is None:
            raise ValueError("path is required")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _normalize_equity_import_mode(self, value: EquityImportMode | str | None) -> EquityImportMode:
        normalized = str(value or DEFAULT_EQUITY_IMPORT_MODE).strip().lower()
        if normalized not in EQUITY_IMPORT_MODES:
            allowed = ", ".join(sorted(EQUITY_IMPORT_MODES))
            raise ValueError(f"unsupported equity_mode: {value!r}; expected one of {allowed}")
        return cast(EquityImportMode, normalized)

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _validate_summary(self, summary: Any, source: Path) -> None:
        if not isinstance(summary, dict):
            raise ValueError(f"summary must be an object: {source}")
        for key in ("strategy", "start_date", "end_date", "aggregate", "results"):
            if key not in summary:
                raise ValueError(f"summary missing key {key}: {source}")

    def _load_symbol_payloads(self, summary: dict[str, Any], base_dir: Path, warnings: list[str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for result in summary.get("results") or []:
            if not isinstance(result, dict):
                continue
            detail = None
            result_path = result.get("result_path")
            stock_code = str(result.get("stock_code") or "").strip()
            fallback_path = (base_dir / f"{stock_code.replace('.', '_')}.json").resolve() if stock_code else None
            path = self._resolve_project_path(result_path) if result_path else fallback_path
            if path is not None:
                if result_path and not path.exists():
                    path = (base_dir / Path(result_path).name).resolve()
                if (not result_path or not path.exists()) and fallback_path is not None:
                    path = fallback_path
                if path.exists():
                    try:
                        detail = self._read_json(path)
                    except (OSError, json.JSONDecodeError) as exc:
                        warnings.append(f"invalid result_path for {result.get('stock_code')}: {result_path} ({exc})")
                else:
                    warnings.append(f"missing result_path for {result.get('stock_code')}: {result_path}")
            item = dict(result)
            if not item.get("result_path") and fallback_path is not None and fallback_path.exists():
                item["result_path"] = self._display_path(fallback_path)
            if detail is not None and not isinstance(detail, dict):
                warnings.append(f"ignored non-object detail for {result.get('stock_code')}: {result_path}")
            item["_detail"] = detail if isinstance(detail, dict) else None
            items.append(item)
        return items

    def _artifact_digest(self, source: Path, summary: dict[str, Any], symbol_payloads: list[dict[str, Any]]) -> str:
        hasher = hashlib.sha256()
        hasher.update(self._canonical_json(summary).encode("utf-8"))
        for item in sorted(symbol_payloads, key=lambda value: str(value.get("stock_code") or "")):
            detail = item.get("_detail")
            if detail is not None:
                hasher.update(str(item.get("stock_code") or "").encode("utf-8"))
                hasher.update(self._canonical_json(detail).encode("utf-8"))
        hasher.update(self._display_path(source).encode("utf-8"))
        return hasher.hexdigest()

    def _logical_signature(
        self,
        summary: dict[str, Any],
        stock_pool_path: Path | None,
        symbol_payloads: list[dict[str, Any]],
    ) -> str:
        stock_codes = [str(item.get("stock_code") or "") for item in symbol_payloads if item.get("stock_code")]
        payload = {
            "strategy": summary.get("strategy"),
            "start_date": summary.get("start_date"),
            "end_date": summary.get("end_date"),
            "price_adjustment": summary.get("price_adjustment"),
            "trading_constraints": summary.get("trading_constraints"),
            "params": summary.get("params") or {},
            "stock_pool_path": self._display_path(stock_pool_path) if stock_pool_path else None,
            "stock_codes": sorted(stock_codes),
        }
        return hashlib.sha256(self._canonical_json(payload).encode("utf-8")).hexdigest()

    def _build_stock_pool(
        self,
        summary: dict[str, Any],
        stock_pool_path: Path | None,
        symbol_payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw_payload = self._read_json(stock_pool_path) if stock_pool_path and stock_pool_path.exists() else None
        members = self._extract_stock_pool_members(raw_payload)
        if not members:
            members = [
                {
                    "stock_code": str(item.get("stock_code") or "").strip(),
                    "stock_name": item.get("stock_name") or item.get("name"),
                    "source_payload": item,
                }
                for item in symbol_payloads
                if item.get("stock_code")
            ]
        unique_members: list[dict[str, Any]] = []
        seen: set[str] = set()
        for idx, member in enumerate(members, start=1):
            code = str(member.get("stock_code") or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            unique_members.append(
                {
                    **member,
                    "stock_code": code,
                    "stock_name": member.get("stock_name"),
                    "rank": idx,
                }
            )
        source_digest = hashlib.sha256(self._canonical_json(unique_members).encode("utf-8")).hexdigest()
        pool_id = self._make_id("pool", source_digest)
        return {
            "pool_id": pool_id,
            "name": stock_pool_path.name if stock_pool_path else "summary.results",
            "source_type": "json_file" if stock_pool_path else "summary_results",
            "source_path": self._display_path(stock_pool_path) if stock_pool_path else None,
            "source_digest": source_digest,
            "total_symbols": len(unique_members),
            "raw_payload": raw_payload,
            "members": unique_members,
        }

    def _extract_stock_pool_members(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        raw_items: Iterable[Any]
        if isinstance(payload, list):
            raw_items = payload
        elif isinstance(payload, dict):
            raw_items = payload.get("stock_codes") or payload.get("items") or payload.get("results") or []
        else:
            return []
        members: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, str):
                members.append({"stock_code": item, "stock_name": None, "source_payload": item})
            elif isinstance(item, dict):
                members.append(
                    {
                        "stock_code": item.get("stock_code") or item.get("code") or item.get("ts_code"),
                        "stock_name": item.get("stock_name") or item.get("name"),
                        "source_payload": item,
                    }
                )
        return members

    def _stock_name_from_payload(self, *payloads: Any) -> Optional[str]:
        for payload in payloads:
            if not isinstance(payload, dict):
                if payload:
                    return str(payload)
                continue
            value = payload.get("stock_name") or payload.get("name")
            if value:
                return str(value)
        return None

    def _entry_signal_type(self, trade: dict[str, Any]) -> Optional[str]:
        value = trade.get("entry_signal_type") or trade.get("signal_type")
        metadata = trade.get("entry_signal_metadata")
        if value is None and isinstance(metadata, dict):
            value = metadata.get("signal_type")
        return str(value) if value else None

    def _derive_trade_metrics(self, symbol_payloads: list[dict[str, Any]]) -> dict[str, Any]:
        trades = [trade for item in symbol_payloads for trade in ((item.get("_detail") or {}).get("trades") or [])]
        wins = [trade for trade in trades if self._float(trade.get("net_pnl")) is not None and self._float(trade.get("net_pnl")) > 0]
        losses = [
            trade for trade in trades if self._float(trade.get("net_pnl")) is not None and self._float(trade.get("net_pnl")) < 0
        ]
        gross_profit = sum(self._float(trade.get("net_pnl")) or 0.0 for trade in wins)
        gross_loss = abs(sum(self._float(trade.get("net_pnl")) or 0.0 for trade in losses))
        holding_values = [self._float(trade.get("holding_days")) for trade in trades if self._float(trade.get("holding_days")) is not None]
        return {
            "win_rate_pct": round(len(wins) * 100 / len(trades), 4) if trades else None,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
            "average_holding_days": round(sum(holding_values) / len(holding_values), 4) if holding_values else None,
        }

    def _derive_portfolio_equity(self, symbol_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_date: dict[date, dict[str, float]] = defaultdict(lambda: {"cash": 0.0, "market_value": 0.0, "equity": 0.0})
        for item in symbol_payloads:
            for point in (item.get("_detail") or {}).get("equity_curve") or []:
                trade_date = self._parse_date(point.get("trade_date"))
                if trade_date is None:
                    continue
                values = by_date[trade_date]
                values["cash"] += self._float(point.get("cash")) or 0.0
                values["market_value"] += self._float(point.get("market_value")) or 0.0
                values["equity"] += self._float(point.get("equity")) or 0.0
        points: list[dict[str, Any]] = []
        initial_equity: float | None = None
        peak: float | None = None
        for trade_date in sorted(by_date):
            values = by_date[trade_date]
            equity = values["equity"]
            if initial_equity is None and equity:
                initial_equity = equity
            if peak is None or equity > peak:
                peak = equity
            return_pct = ((equity / initial_equity - 1) * 100) if initial_equity else None
            drawdown_pct = ((equity / peak - 1) * 100) if peak else None
            points.append(
                {
                    "trade_date": trade_date,
                    "cash": values["cash"],
                    "market_value": values["market_value"],
                    "equity": equity,
                    "return_pct": return_pct,
                    "drawdown_pct": drawdown_pct,
                }
            )
        return points

    def _derive_portfolio_metrics(self, points: list[dict[str, Any]]) -> dict[str, Any]:
        drawdowns = [
            self._float(point.get("drawdown_pct"))
            for point in points
            if self._float(point.get("drawdown_pct")) is not None
        ]
        max_drawdown_pct = abs(min(drawdowns)) if drawdowns else None
        return {
            "sample_days": len(points) or None,
            "max_drawdown_pct": round(max_drawdown_pct, 4) if max_drawdown_pct is not None else None,
        }

    def _run_values(
        self,
        *,
        run_id: str,
        source: Path,
        summary: dict[str, Any],
        aggregate: dict[str, Any],
        artifact_digest: str,
        logical_signature: str,
        stock_pool_info: dict[str, Any],
        derived: dict[str, Any],
        generated_at: datetime,
    ) -> dict[str, Any]:
        version = self._infer_strategy_version(source, summary)
        name_parts = [str(summary.get("strategy") or "backtest")]
        if version:
            name_parts.append(version)
        if stock_pool_info.get("name"):
            name_parts.append(str(stock_pool_info["name"]))
        return {
            "run_id": run_id,
            "run_name": " · ".join(name_parts),
            "status": "finished",
            "source_type": "json_import",
            "source_path": self._display_path(source),
            "artifact_digest": artifact_digest,
            "logical_signature": logical_signature,
            "strategy": str(summary.get("strategy") or ""),
            "strategy_version": version,
            "stock_pool_id": stock_pool_info["pool_id"],
            "stock_pool_name": stock_pool_info.get("name"),
            "start_date": self._parse_date(summary.get("start_date")),
            "end_date": self._parse_date(summary.get("end_date")),
            "price_adjustment": summary.get("price_adjustment"),
            "trading_constraints": summary.get("trading_constraints"),
            "total_symbols": self._int(aggregate.get("total_symbols")),
            "ok_symbols": self._int(aggregate.get("ok_symbols")),
            "error_symbols": self._int(aggregate.get("error_symbols")),
            "profitable_symbols": self._int(aggregate.get("profitable_symbols")),
            "losing_symbols": self._int(aggregate.get("losing_symbols")),
            "flat_symbols": self._int(aggregate.get("flat_symbols")),
            "total_initial_cash": self._float(aggregate.get("total_initial_cash")),
            "total_final_equity": self._float(aggregate.get("total_final_equity")),
            "total_pnl": self._float(aggregate.get("total_pnl")),
            "aggregate_return_pct": self._float(aggregate.get("aggregate_return_pct")),
            "average_return_pct": self._float(aggregate.get("average_return_pct")),
            "total_trade_count": self._int(aggregate.get("total_trade_count")),
            "max_drawdown_pct": derived.get("max_drawdown_pct"),
            "win_rate_pct": derived.get("win_rate_pct"),
            "profit_factor": derived.get("profit_factor"),
            "average_holding_days": derived.get("average_holding_days"),
            "params_payload": self._dumps(summary.get("params") or {}),
            "config_payload": self._dumps(
                {
                    "price_adjustment": summary.get("price_adjustment"),
                    "trading_constraints": summary.get("trading_constraints"),
                }
            ),
            "aggregate_payload": self._dumps(aggregate),
            "raw_summary_payload": self._dumps(summary),
            "completed_at": generated_at,
            "generated_at": generated_at,
            "updated_at": datetime.now(),
        }

    def _upsert_stock_pool(self, session, stock_pool_info: dict[str, Any]) -> None:
        existing = session.execute(
            select(StrategyBacktestStockPool)
            .where(StrategyBacktestStockPool.pool_id == stock_pool_info["pool_id"])
            .limit(1)
        ).scalars().first()
        values = {
            "pool_id": stock_pool_info["pool_id"],
            "name": stock_pool_info.get("name"),
            "source_type": stock_pool_info.get("source_type"),
            "source_path": stock_pool_info.get("source_path"),
            "source_digest": stock_pool_info.get("source_digest"),
            "total_symbols": stock_pool_info.get("total_symbols"),
            "raw_payload": self._dumps(stock_pool_info.get("raw_payload")),
            "updated_at": datetime.now(),
        }
        if existing is None:
            session.add(StrategyBacktestStockPool(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.execute(
            delete(StrategyBacktestStockPoolMember).where(
                StrategyBacktestStockPoolMember.pool_id == stock_pool_info["pool_id"]
            )
        )
        self._bulk_save(
            session,
            [
                StrategyBacktestStockPoolMember(
                    pool_id=stock_pool_info["pool_id"],
                    stock_code=member["stock_code"],
                    stock_name=member.get("stock_name"),
                    rank=member.get("rank"),
                    source_payload=self._dumps(member.get("source_payload")),
                )
                for member in stock_pool_info.get("members") or []
            ],
        )

    def _bulk_save(self, session, rows: list[Any]) -> None:
        if rows:
            session.bulk_save_objects(rows)

    def _delete_run_children(self, session, run_id: str) -> None:
        for model in (
            StrategyBacktestSymbolResult,
            StrategyBacktestTrade,
            StrategyBacktestEquityPoint,
        ):
            session.execute(delete(model).where(model.run_id == run_id))

    def _delete_orphan_stock_pool(self, session, stock_pool_id: Any) -> None:
        if not stock_pool_id:
            return
        remaining = session.execute(
            select(func.count(StrategyBacktestRun.id)).where(StrategyBacktestRun.stock_pool_id == str(stock_pool_id))
        ).scalar_one()
        if int(remaining or 0) > 0:
            return
        session.execute(
            delete(StrategyBacktestStockPoolMember).where(StrategyBacktestStockPoolMember.pool_id == str(stock_pool_id))
        )
        session.execute(delete(StrategyBacktestStockPool).where(StrategyBacktestStockPool.pool_id == str(stock_pool_id)))

    def _symbol_rows(
        self,
        run_id: str,
        symbol_payloads: list[dict[str, Any]],
        stock_pool_info: dict[str, Any],
        aggregate: dict[str, Any],
    ) -> list[StrategyBacktestSymbolResult]:
        name_by_code = {item["stock_code"]: item.get("stock_name") for item in stock_pool_info.get("members") or []}
        total_initial_cash = self._float(aggregate.get("total_initial_cash")) or 0.0
        rows: list[StrategyBacktestSymbolResult] = []
        for item in symbol_payloads:
            detail = item.get("_detail") or {}
            metrics = detail.get("metrics") or {}
            latest_metadata = (detail.get("data_context") or {}).get("latest_signal_metadata")
            initial_cash = self._float(self._pick_value(metrics, item, detail, key="initial_cash"))
            final_equity = self._float(self._pick_value(metrics, item, detail, key="final_equity"))
            contribution_pct = None
            if total_initial_cash and final_equity is not None and initial_cash is not None:
                contribution_pct = round((final_equity - initial_cash) / total_initial_cash * 100, 6)
            code = str(item.get("stock_code") or detail.get("stock_code") or "").strip().upper()
            open_position = detail.get("open_position")
            has_open_position = self._pick_value(metrics, item, detail, key="has_open_position")
            if has_open_position is None:
                has_open_position = bool(open_position)
            stock_name = self._stock_name_from_payload(item, detail, name_by_code.get(code))
            rows.append(
                StrategyBacktestSymbolResult(
                    run_id=run_id,
                    stock_code=code,
                    stock_name=stock_name,
                    status=str(item.get("status") or detail.get("status") or "ok"),
                    error=item.get("error") or detail.get("error"),
                    requested_start_date=self._parse_date(item.get("requested_start_date") or detail.get("start_date")),
                    effective_start_date=self._parse_date(item.get("effective_start_date") or detail.get("start_date")),
                    end_date=self._parse_date(detail.get("end_date")),
                    initial_cash=initial_cash,
                    final_equity=final_equity,
                    total_return_pct=self._float(self._pick_value(metrics, item, detail, key="total_return_pct")),
                    max_drawdown_pct=self._float(self._pick_value(metrics, item, detail, key="max_drawdown_pct")),
                    trade_count=self._int(self._pick_value(metrics, item, detail, key="trade_count")),
                    win_rate_pct=self._float(self._pick_value(metrics, item, detail, key="win_rate_pct")),
                    avg_win_pct=self._float(self._pick_value(metrics, item, detail, key="avg_win_pct")),
                    avg_loss_pct=self._float(self._pick_value(metrics, item, detail, key="avg_loss_pct")),
                    profit_factor=self._float(self._pick_value(metrics, item, detail, key="profit_factor")),
                    has_open_position=1 if has_open_position else 0,
                    open_position_market_value=self._float(
                        self._pick_value(metrics, item, detail, key="open_position_market_value")
                    ),
                    final_unrealized_pnl=self._float(self._pick_value(metrics, item, detail, key="final_unrealized_pnl")),
                    final_unrealized_pnl_pct=self._float(
                        self._pick_value(metrics, item, detail, key="final_unrealized_pnl_pct")
                    ),
                    max_trade_mfe_pct=self._float(self._pick_value(metrics, item, detail, key="max_trade_mfe_pct")),
                    max_trade_mae_pct=self._float(self._pick_value(metrics, item, detail, key="max_trade_mae_pct")),
                    contribution_pct=contribution_pct,
                    result_path=item.get("result_path"),
                    params_payload=self._dumps(detail.get("params")),
                    config_payload=self._dumps(detail.get("config")),
                    metrics_payload=self._dumps(metrics),
                    data_context_payload=self._dumps(detail.get("data_context")),
                    latest_signal_metadata_payload=self._dumps(latest_metadata),
                    open_position_payload=self._dumps(open_position),
                    raw_result_payload=self._dumps(detail) if detail else None,
                )
            )
        return rows

    def _trade_rows(
        self,
        run_id: str,
        symbol_payloads: list[dict[str, Any]],
        stock_pool_info: dict[str, Any],
    ) -> list[StrategyBacktestTrade]:
        name_by_code = {item["stock_code"]: item.get("stock_name") for item in stock_pool_info.get("members") or []}
        rows: list[StrategyBacktestTrade] = []
        for item in symbol_payloads:
            detail = item.get("_detail") or {}
            code = str(item.get("stock_code") or detail.get("stock_code") or "").strip().upper()
            stock_name = self._stock_name_from_payload(item, detail, name_by_code.get(code))
            for idx, trade in enumerate(detail.get("trades") or [], start=1):
                trade_id = f"{run_id}:{code}:{idx:06d}"
                rows.append(
                    StrategyBacktestTrade(
                        trade_id=trade_id,
                        run_id=run_id,
                        stock_code=code,
                        stock_name=trade.get("stock_name") or trade.get("name") or stock_name,
                        entry_date=self._parse_date(trade.get("entry_date")),
                        exit_date=self._parse_date(trade.get("exit_date")),
                        entry_price=self._float(trade.get("entry_price")),
                        exit_price=self._float(trade.get("exit_price")),
                        shares=self._int(trade.get("shares")),
                        gross_pnl=self._float(trade.get("gross_pnl")),
                        net_pnl=self._float(trade.get("net_pnl")),
                        return_pct=self._float(trade.get("return_pct")),
                        holding_days=self._int(trade.get("holding_days")),
                        exit_reason=trade.get("exit_reason"),
                        entry_signal_type=self._entry_signal_type(trade),
                        entry_signal_reason=trade.get("entry_signal_reason"),
                        entry_signal_score=self._float(trade.get("entry_signal_score")),
                        highest_price_seen=self._float(trade.get("highest_price_seen")),
                        lowest_price_seen=self._float(trade.get("lowest_price_seen")),
                        max_favorable_excursion_pct=self._float(trade.get("max_favorable_excursion_pct")),
                        max_adverse_excursion_pct=self._float(trade.get("max_adverse_excursion_pct")),
                        entry_signal_metadata_payload=self._dumps(trade.get("entry_signal_metadata")),
                        raw_trade_payload=self._dumps(trade),
                    )
                )
        return rows

    def _symbol_equity_point_count(
        self,
        symbol_payloads: list[dict[str, Any]],
        *,
        equity_mode: EquityImportMode,
    ) -> int:
        return sum(1 for _ in self._iter_symbol_equity_points(symbol_payloads, equity_mode=equity_mode))

    def _symbol_equity_rows(
        self,
        run_id: str,
        symbol_payloads: list[dict[str, Any]],
        *,
        equity_mode: EquityImportMode,
    ) -> list[StrategyBacktestEquityPoint]:
        rows: list[StrategyBacktestEquityPoint] = []
        for code, trade_date, point in self._iter_symbol_equity_points(symbol_payloads, equity_mode=equity_mode):
            rows.append(
                StrategyBacktestEquityPoint(
                    run_id=run_id,
                    scope="symbol",
                    stock_code=code,
                    trade_date=trade_date,
                    cash=self._float(point.get("cash")),
                    market_value=self._float(point.get("market_value")),
                    equity=self._float(point.get("equity")),
                    return_pct=self._float(point.get("return_pct")),
                    drawdown_pct=self._float(point.get("drawdown_pct")),
                    source="json_import",
                )
            )
        return rows

    def _iter_symbol_equity_points(
        self,
        symbol_payloads: list[dict[str, Any]],
        *,
        equity_mode: EquityImportMode,
    ) -> Iterable[tuple[str, date, dict[str, Any]]]:
        if equity_mode == "portfolio_only":
            return
        for item in symbol_payloads:
            detail = item.get("_detail") or {}
            code = str(item.get("stock_code") or detail.get("stock_code") or "").strip().upper()
            if not code:
                continue
            dated_points = [
                (point, trade_date)
                for point in (detail.get("equity_curve") or [])
                if (trade_date := self._parse_date(point.get("trade_date"))) is not None
            ]
            if equity_mode == "all_daily":
                for point, trade_date in dated_points:
                    yield code, trade_date, point
                continue

            active_ranges = self._active_trade_ranges(item, detail, dated_points)
            metrics = detail.get("metrics") if isinstance(detail.get("metrics"), dict) else {}
            has_trade_activity = bool(active_ranges) or self._int(self._pick_value(metrics, item, key="trade_count"))
            final_trade_date = dated_points[-1][1] if dated_points and has_trade_activity else None
            for point, trade_date in dated_points:
                market_value = self._float(point.get("market_value")) or 0.0
                if (
                    abs(market_value) > 0.000001
                    or self._date_in_ranges(trade_date, active_ranges)
                    or (final_trade_date is not None and trade_date == final_trade_date)
                ):
                    yield code, trade_date, point

    def _active_trade_ranges(
        self,
        item: dict[str, Any],
        detail: dict[str, Any],
        dated_points: list[tuple[dict[str, Any], date]],
    ) -> list[tuple[date, date]]:
        fallback_end = dated_points[-1][1] if dated_points else None
        ranges: list[tuple[date, date]] = []
        for trade in detail.get("trades") or []:
            entry_date = self._parse_date(trade.get("entry_date"))
            if entry_date is None:
                continue
            exit_date = self._parse_date(trade.get("exit_date")) or fallback_end or entry_date
            if exit_date < entry_date:
                exit_date = entry_date
            ranges.append((entry_date, exit_date))

        open_position = detail.get("open_position")
        if isinstance(open_position, dict) and open_position:
            entry_date = self._parse_date(
                open_position.get("entry_date")
                or open_position.get("buy_date")
                or open_position.get("opened_at")
            )
            if entry_date and fallback_end:
                ranges.append((entry_date, fallback_end))
        elif item.get("has_open_position") and fallback_end:
            ranges.append((fallback_end, fallback_end))
        return ranges

    @staticmethod
    def _date_in_ranges(value: date, ranges: list[tuple[date, date]]) -> bool:
        return any(start <= value <= end for start, end in ranges)

    def _portfolio_equity_rows(self, run_id: str, points: list[dict[str, Any]]) -> list[StrategyBacktestEquityPoint]:
        return [
            StrategyBacktestEquityPoint(
                run_id=run_id,
                scope="portfolio",
                trade_date=point["trade_date"],
                cash=point.get("cash"),
                market_value=point.get("market_value"),
                equity=point.get("equity"),
                return_pct=point.get("return_pct"),
                drawdown_pct=point.get("drawdown_pct"),
                source="import_derived",
            )
            for point in points
        ]

    def _run_to_list_item(self, row: StrategyBacktestRun) -> dict[str, Any]:
        return {
            "run_id": row.run_id,
            "name": row.run_name,
            "status": row.status,
            "source_type": row.source_type,
            "strategy": row.strategy,
            "strategy_version": row.strategy_version,
            "stock_pool_name": row.stock_pool_name,
            "start_date": self._date_to_str(row.start_date),
            "end_date": self._date_to_str(row.end_date),
            "total_symbols": row.total_symbols,
            "total_trade_count": row.total_trade_count,
            "aggregate_return_pct": row.aggregate_return_pct,
            "max_drawdown_pct": row.max_drawdown_pct,
            "win_rate_pct": row.win_rate_pct,
            "generated_at": self._datetime_to_str(row.generated_at),
        }

    def _run_to_detail(self, session, row: StrategyBacktestRun) -> dict[str, Any]:
        symbol_counts = self._stock_counts(session, row.run_id)
        portfolio_stats = self._portfolio_stats(session, row.run_id)
        params = self._loads(row.params_payload) or {}
        config = self._loads(row.config_payload) or {}
        aggregate = self._loads(row.aggregate_payload) or {}
        raw_summary = self._loads(row.raw_summary_payload)
        stock_pool_source_path = self._stock_pool_source_path(row.stock_pool_id)
        member_summary = self._stock_pool_member_summary(row.stock_pool_id)
        stock_rows = (
            session.execute(
                select(StrategyBacktestSymbolResult)
                .where(StrategyBacktestSymbolResult.run_id == row.run_id)
                .order_by(desc(StrategyBacktestSymbolResult.total_return_pct), StrategyBacktestSymbolResult.stock_code.asc())
                .limit(1000)
            )
            .scalars()
            .all()
        )
        trade_rows = (
            session.execute(
                select(StrategyBacktestTrade)
                .where(StrategyBacktestTrade.run_id == row.run_id)
                .order_by(desc(StrategyBacktestTrade.entry_date), desc(StrategyBacktestTrade.id))
                .limit(2000)
            )
            .scalars()
            .all()
        )
        return {
            "run": {
                **self._run_to_list_item(row),
                "sample_days": portfolio_stats["sample_days"],
                "source_path": row.source_path,
                "price_adjustment": row.price_adjustment,
                "trading_constraints": row.trading_constraints,
                "completed_at": self._datetime_to_str(row.completed_at),
            },
            "strategy_card": {
                "universe": {
                    "pool_id": row.stock_pool_id,
                    "name": row.stock_pool_name,
                    "source_path": stock_pool_source_path,
                    "total_symbols": row.total_symbols,
                    "named_symbols": member_summary["named_symbols"],
                    "members_preview": member_summary["members_preview"],
                    "summary": self._stock_pool_description(row.stock_pool_name, row.total_symbols),
                },
                "stock_pool": {
                    "pool_id": row.stock_pool_id,
                    "name": row.stock_pool_name,
                    "source_path": stock_pool_source_path,
                    "total_symbols": row.total_symbols,
                    "named_symbols": member_summary["named_symbols"],
                    "members_preview": member_summary["members_preview"],
                },
                "capital": {
                    "initial_cash": self._infer_initial_cash_per_symbol(row),
                    "total_initial_cash": row.total_initial_cash,
                    "total_final_equity": row.total_final_equity,
                    "total_pnl": row.total_pnl,
                    "position_pct": params.get("position_size_pct") if isinstance(params, dict) else None,
                    "max_positions": None,
                },
                "entry": self._entry_summary(params),
                "exit": self._exit_summary(params),
                "costs": self._cost_summary(config, raw_summary),
                "entry_summary": self._entry_summary_text(params),
                "exit_summary": self._exit_summary_text(params),
                "cost_summary": self._cost_summary_text(config, raw_summary),
                "constraints": {
                    "price_adjustment": row.price_adjustment,
                    "trading_constraints": row.trading_constraints,
                },
                "params": params,
                "config": config,
                "raw_summary": self._raw_payload_summary(raw_summary),
            },
            "kpis": {
                "aggregate_return_pct": row.aggregate_return_pct,
                "average_return_pct": row.average_return_pct,
                "max_drawdown_pct": row.max_drawdown_pct or portfolio_stats["max_drawdown_pct"],
                "total_pnl": row.total_pnl,
                "win_rate_pct": row.win_rate_pct,
                "profit_factor": row.profit_factor,
                "average_holding_days": row.average_holding_days,
                "total_trade_count": row.total_trade_count,
                "profitable_symbols": row.profitable_symbols,
                "losing_symbols": row.losing_symbols,
                "flat_symbols": row.flat_symbols,
                "error_symbols": row.error_symbols,
            },
            "counts": symbol_counts,
            "aggregate": aggregate,
            "params_snapshot": params,
            "config_snapshot": config,
            "stocks": {
                "items": [self._symbol_to_dict(item) for item in stock_rows],
                "counts": symbol_counts,
                "next_cursor": None,
            },
            "stock_results": [self._symbol_to_dict(item) for item in stock_rows],
            "trades": {
                "items": [self._trade_to_dict(item) for item in trade_rows],
                "next_cursor": None,
            },
            "trade_items": [self._trade_to_dict(item) for item in trade_rows],
            "raw_available": {
                "params": bool(row.params_payload),
                "config": bool(row.config_payload),
                "aggregate": bool(row.aggregate_payload),
                "summary": bool(row.raw_summary_payload),
            },
            "raw_payload_summary": {
                "params": self._raw_payload_summary(params),
                "config": self._raw_payload_summary(config),
                "aggregate": self._raw_payload_summary(aggregate),
                "summary": self._raw_payload_summary(raw_summary),
            },
        }

    def _portfolio_stats(self, session, run_id: str) -> dict[str, Any]:
        sample_days = session.execute(
            select(func.count(StrategyBacktestEquityPoint.id)).where(
                StrategyBacktestEquityPoint.run_id == run_id,
                StrategyBacktestEquityPoint.scope == "portfolio",
            )
        ).scalar_one()
        min_drawdown = session.execute(
            select(func.min(StrategyBacktestEquityPoint.drawdown_pct)).where(
                StrategyBacktestEquityPoint.run_id == run_id,
                StrategyBacktestEquityPoint.scope == "portfolio",
            )
        ).scalar_one()
        drawdown = self._float(min_drawdown)
        return {
            "sample_days": int(sample_days or 0) or None,
            "max_drawdown_pct": abs(drawdown) if drawdown is not None else None,
        }

    def _stock_counts(self, session, run_id: str) -> dict[str, int]:
        rows = session.execute(
            select(
                StrategyBacktestSymbolResult.status,
                func.count(StrategyBacktestSymbolResult.id),
            )
            .where(StrategyBacktestSymbolResult.run_id == run_id)
            .group_by(StrategyBacktestSymbolResult.status)
        ).all()
        all_count = sum(int(row[1]) for row in rows)
        profitable = session.execute(
            select(func.count(StrategyBacktestSymbolResult.id)).where(
                StrategyBacktestSymbolResult.run_id == run_id,
                StrategyBacktestSymbolResult.total_return_pct > 0,
            )
        ).scalar_one()
        losing = session.execute(
            select(func.count(StrategyBacktestSymbolResult.id)).where(
                StrategyBacktestSymbolResult.run_id == run_id,
                StrategyBacktestSymbolResult.total_return_pct < 0,
            )
        ).scalar_one()
        flat = session.execute(
            select(func.count(StrategyBacktestSymbolResult.id)).where(
                StrategyBacktestSymbolResult.run_id == run_id,
                StrategyBacktestSymbolResult.total_return_pct == 0,
            )
        ).scalar_one()
        error = sum(int(row[1]) for row in rows if row[0] == "error")
        return {"all": all_count, "profitable": int(profitable), "losing": int(losing), "flat": int(flat), "error": error}

    def _symbol_to_dict(self, row: StrategyBacktestSymbolResult, *, include_payloads: bool = False) -> dict[str, Any]:
        payload = {
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "status": row.status,
            "error": row.error,
            "initial_cash": row.initial_cash,
            "final_equity": row.final_equity,
            "total_return_pct": row.total_return_pct,
            "max_drawdown_pct": row.max_drawdown_pct,
            "trade_count": row.trade_count,
            "win_rate_pct": row.win_rate_pct,
            "avg_win_pct": row.avg_win_pct,
            "avg_loss_pct": row.avg_loss_pct,
            "profit_factor": row.profit_factor,
            "has_open_position": bool(row.has_open_position),
            "open_position_market_value": row.open_position_market_value,
            "final_unrealized_pnl": row.final_unrealized_pnl,
            "final_unrealized_pnl_pct": row.final_unrealized_pnl_pct,
            "max_trade_mfe_pct": row.max_trade_mfe_pct,
            "max_trade_mae_pct": row.max_trade_mae_pct,
            "contribution_pct": row.contribution_pct,
        }
        if include_payloads:
            payload.update(
                {
                    "params": self._loads(row.params_payload),
                    "config": self._loads(row.config_payload),
                    "metrics": self._loads(row.metrics_payload),
                    "data_context": self._loads(row.data_context_payload),
                    "latest_signal_metadata": self._loads(row.latest_signal_metadata_payload),
                    "open_position": self._loads(row.open_position_payload),
                }
            )
        return payload

    def _trade_to_dict(self, row: StrategyBacktestTrade) -> dict[str, Any]:
        return {
            "trade_id": row.trade_id,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "entry_date": self._date_to_str(row.entry_date),
            "exit_date": self._date_to_str(row.exit_date),
            "entry_price": row.entry_price,
            "exit_price": row.exit_price,
            "shares": row.shares,
            "gross_pnl": row.gross_pnl,
            "net_pnl": row.net_pnl,
            "return_pct": row.return_pct,
            "holding_days": row.holding_days,
            "exit_reason": row.exit_reason,
            "entry_signal_type": row.entry_signal_type,
            "signal_type": row.entry_signal_type,
            "entry_signal_reason": row.entry_signal_reason,
            "entry_signal_score": row.entry_signal_score,
            "max_favorable_excursion_pct": row.max_favorable_excursion_pct,
            "max_adverse_excursion_pct": row.max_adverse_excursion_pct,
            "mfe_pct": row.max_favorable_excursion_pct,
            "mae_pct": row.max_adverse_excursion_pct,
            "entry_signal_metadata": self._loads(row.entry_signal_metadata_payload),
        }

    def _equity_to_dict(self, row: StrategyBacktestEquityPoint) -> dict[str, Any]:
        return {
            "trade_date": self._date_to_str(row.trade_date),
            "cash": row.cash,
            "market_value": row.market_value,
            "equity": row.equity,
            "return_pct": row.return_pct,
            "drawdown_pct": row.drawdown_pct,
            "source": row.source,
        }

    def _stock_pool_description(self, name: Any, total_symbols: Any) -> str:
        total = self._int(total_symbols)
        label = str(name or "summary.results").strip()
        if total:
            return f"{label}，共 {total} 只股票"
        return label

    def _infer_initial_cash_per_symbol(self, row: StrategyBacktestRun) -> Optional[float]:
        if row.total_initial_cash is None or not row.total_symbols:
            return None
        return round(float(row.total_initial_cash) / int(row.total_symbols), 4)

    def _entry_summary(self, params: Any) -> dict[str, Any]:
        params = params if isinstance(params, dict) else {}
        return {
            "box_lookback_days": params.get("box_lookback_days"),
            "min_breakout_pct": params.get("min_breakout_pct"),
            "min_volume_ratio": params.get("min_volume_ratio"),
            "min_turnover_rate": params.get("min_turnover_rate"),
            "breakout_retest_window": params.get("breakout_retest_window"),
            "pullback_reclaim_pct": params.get("pullback_reclaim_pct"),
            "require_uptrend_for_entry": params.get("require_uptrend_for_entry"),
            "breakout_min_signal_score": params.get("breakout_min_signal_score"),
            "pullback_min_signal_score": params.get("pullback_min_signal_score"),
        }

    def _exit_summary(self, params: Any) -> dict[str, Any]:
        params = params if isinstance(params, dict) else {}
        return {
            "stop_loss_pct": params.get("stop_loss_pct"),
            "take_profit_pct": params.get("take_profit_pct"),
            "max_holding_days": params.get("max_holding_days"),
            "breakout_take_profit_pct": params.get("breakout_take_profit_pct"),
            "pullback_take_profit_pct": params.get("pullback_take_profit_pct"),
            "breakout_max_holding_days": params.get("breakout_max_holding_days"),
            "pullback_max_holding_days": params.get("pullback_max_holding_days"),
            "enable_trailing_stop": params.get("enable_trailing_stop"),
            "enable_ma10_confirm_exit": params.get("enable_ma10_confirm_exit"),
        }

    def _cost_summary(self, config: Any, raw_summary: Any) -> dict[str, Any]:
        payloads = [value for value in (config, raw_summary) if isinstance(value, dict)]
        costs: dict[str, Any] = {}
        for payload in payloads:
            for key in ("costs", "commission", "commission_rate", "stamp_tax_rate", "slippage_pct"):
                if key in payload and payload.get(key) is not None:
                    costs[key] = payload.get(key)
        return costs

    def _entry_summary_text(self, params: Any) -> str:
        entry = self._entry_summary(params)
        return (
            f"箱体 {entry.get('box_lookback_days')} 日，突破阈值 {entry.get('min_breakout_pct')}%，"
            f"量比 >= {entry.get('min_volume_ratio')}，换手 >= {entry.get('min_turnover_rate')}。"
        )

    def _exit_summary_text(self, params: Any) -> str:
        exit_summary = self._exit_summary(params)
        return (
            f"止损 {exit_summary.get('stop_loss_pct')}，止盈 {exit_summary.get('take_profit_pct')}，"
            f"最长持有 {exit_summary.get('max_holding_days')} 日。"
        )

    def _cost_summary_text(self, config: Any, raw_summary: Any) -> str:
        costs = self._cost_summary(config, raw_summary)
        if not costs:
            return "未在导入 payload 中声明交易成本。"
        return "，".join(f"{key}={value}" for key, value in costs.items())

    def _raw_payload_summary(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "type": "object",
                "keys": sorted(str(key) for key in value.keys())[:40],
                "key_count": len(value),
            }
        if isinstance(value, list):
            return {"type": "array", "length": len(value)}
        if value is None:
            return {"type": "null"}
        return {"type": type(value).__name__}

    def _query_raw_daily_rows(self, session, stock_code: str, start_date: Any, end_date: Any) -> list[StockDailyRaw]:
        candidates = self._ts_code_candidates(stock_code)
        if not candidates or start_date is None or end_date is None:
            return []
        rows = (
            session.execute(
                select(StockDailyRaw)
                .where(
                    StockDailyRaw.ts_code.in_(candidates),
                    StockDailyRaw.trade_date >= start_date,
                    StockDailyRaw.trade_date <= end_date,
                )
                .order_by(StockDailyRaw.trade_date.asc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def _query_legacy_daily_rows(self, session, stock_code: str, start_date: Any, end_date: Any) -> list[StockDaily]:
        candidates = self._legacy_code_candidates(stock_code)
        if not candidates or start_date is None or end_date is None:
            return []
        rows = (
            session.execute(
                select(StockDaily)
                .where(
                    StockDaily.code.in_(candidates),
                    StockDaily.date >= start_date,
                    StockDaily.date <= end_date,
                )
                .order_by(StockDaily.date.asc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def _chart_bars_from_raw(self, rows: list[StockDailyRaw], *, price_adjustment: Any) -> list[dict[str, Any]]:
        use_qfq = str(price_adjustment or "").lower() == "qfq"
        bars: list[dict[str, Any]] = []
        for row in rows:
            open_price = row.open_qfq if use_qfq and row.open_qfq is not None else row.open
            high_price = row.high_qfq if use_qfq and row.high_qfq is not None else row.high
            low_price = row.low_qfq if use_qfq and row.low_qfq is not None else row.low
            close_price = row.close_qfq if use_qfq and row.close_qfq is not None else row.close
            bars.append(
                {
                    "trade_date": self._date_to_str(row.trade_date),
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": row.vol,
                    "amount": row.amount,
                    "data_source": row.data_source,
                }
            )
        return bars

    def _chart_bars_from_legacy(self, rows: list[StockDaily]) -> list[dict[str, Any]]:
        return [
            {
                "trade_date": self._date_to_str(row.date),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "amount": row.amount,
                "pct_chg": row.pct_chg,
                "ma5": row.ma5,
                "ma10": row.ma10,
                "ma20": row.ma20,
                "data_source": row.data_source,
            }
            for row in rows
        ]

    def _with_moving_averages(self, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        closes: list[float | None] = [self._float(item.get("close")) for item in bars]
        for idx, bar in enumerate(bars):
            for window in (5, 10, 20):
                key = f"ma{window}"
                if bar.get(key) is not None:
                    continue
                window_values = [value for value in closes[max(0, idx - window + 1) : idx + 1] if value is not None]
                bar[key] = round(sum(window_values) / window, 4) if len(window_values) == window else None
        self._with_macd(bars, closes=closes)
        return bars

    def _with_macd(self, bars: list[dict[str, Any]], *, closes: list[float | None]) -> None:
        ema12 = self._ema(closes, span=12)
        ema26 = self._ema(closes, span=26)
        dif_values: list[float | None] = [
            (fast - slow) if fast is not None and slow is not None else None
            for fast, slow in zip(ema12, ema26)
        ]
        dea_values = self._ema(dif_values, span=9)
        hist_values: list[float | None] = [
            (dif - dea) * 2.0 if dif is not None and dea is not None else None
            for dif, dea in zip(dif_values, dea_values)
        ]
        for idx, bar in enumerate(bars):
            dif = dif_values[idx] if idx < len(dif_values) else None
            dea = dea_values[idx] if idx < len(dea_values) else None
            hist = hist_values[idx] if idx < len(hist_values) else None
            prior_hist = hist_values[idx - 3] if idx >= 3 else None
            bar["macd_dif"] = round(dif, 4) if dif is not None else None
            bar["macd_dea"] = round(dea, 4) if dea is not None else None
            bar["macd_hist"] = round(hist, 4) if hist is not None else None
            bar["macd_hist_slope_3"] = (
                round(hist - prior_hist, 4) if hist is not None and prior_hist is not None else None
            )

    @staticmethod
    def _ema(values: list[float | None], *, span: int) -> list[float | None]:
        alpha = 2.0 / (float(span) + 1.0)
        current: float | None = None
        result: list[float | None] = []
        for value in values:
            if value is None:
                result.append(None)
                continue
            current = float(value) if current is None else alpha * float(value) + (1.0 - alpha) * current
            result.append(current)
        return result

    def _trade_markers(self, trades: list[StrategyBacktestTrade]) -> list[dict[str, Any]]:
        markers: list[dict[str, Any]] = []
        for trade in trades:
            if trade.entry_date:
                markers.append(
                    {
                        "type": "buy",
                        "trade_id": trade.trade_id,
                        "trade_date": self._date_to_str(trade.entry_date),
                        "price": trade.entry_price,
                        "shares": trade.shares,
                        "reason": trade.entry_signal_reason,
                        "score": trade.entry_signal_score,
                        "metadata": self._loads(trade.entry_signal_metadata_payload),
                    }
                )
            if trade.exit_date:
                markers.append(
                    {
                        "type": "sell",
                        "trade_id": trade.trade_id,
                        "trade_date": self._date_to_str(trade.exit_date),
                        "price": trade.exit_price,
                        "shares": trade.shares,
                        "reason": trade.exit_reason,
                        "return_pct": trade.return_pct,
                    }
                )
        return sorted(markers, key=lambda item: (str(item.get("trade_date") or ""), str(item.get("type") or "")))

    def _ts_code_candidates(self, stock_code: str) -> list[str]:
        code = str(stock_code or "").strip().upper()
        if not code:
            return []
        if "." in code:
            bare, suffix = code.split(".", 1)
            return [code, f"{bare}_{suffix}"]
        if "_" in code:
            bare, suffix = code.split("_", 1)
            return [code, f"{bare}.{suffix}"]
        suffix = "SH" if code.startswith(("5", "6", "9")) else "BJ" if code.startswith(("4", "8")) else "SZ"
        return [f"{code}.{suffix}", f"{code}_{suffix}", code]

    def _stock_code_candidates(self, stock_code: str) -> list[str]:
        code = str(stock_code or "").strip().upper()
        if not code:
            return [""]
        bare = code.split(".", 1)[0].split("_", 1)[0]
        return list(dict.fromkeys([code, bare, *self._ts_code_candidates(code)]))

    def _legacy_code_candidates(self, stock_code: str) -> list[str]:
        candidates = self._ts_code_candidates(stock_code)
        code = str(stock_code or "").strip().upper()
        bare = code.split(".", 1)[0].split("_", 1)[0]
        return list(dict.fromkeys([code, bare, *candidates]))

    def _infer_strategy_version(self, source: Path, summary: dict[str, Any]) -> Optional[str]:
        if isinstance(summary.get("params"), dict):
            version = summary["params"].get("version") or summary["params"].get("strategy_version")
            if version:
                return str(version)
        parent_name = source.parent.name
        for part in parent_name.split("_"):
            if part.startswith("v") and part[1:].isdigit():
                return part
        return None

    def _make_id(self, prefix: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _canonical_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    def _dumps(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, default=str)

    def _pick_value(self, *payloads: dict[str, Any], key: str) -> Any:
        for payload in payloads:
            if key in payload and payload.get(key) is not None:
                return payload.get(key)
        return None

    def _loads(self, value: Optional[str]) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def _display_path(self, path: Path | None) -> Optional[str]:
        if path is None:
            return None
        try:
            return str(path.resolve().relative_to(self.project_root))
        except ValueError:
            return str(path)

    def _parse_date(self, value: Any) -> Optional[date]:
        if value in (None, ""):
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        text = str(value).strip()
        for pattern in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            parsed_date = self._parse_date(value)
            return datetime.combine(parsed_date, datetime.min.time()) if parsed_date else None

    def _date_to_str(self, value: Any) -> Optional[str]:
        return value.isoformat() if value else None

    def _datetime_to_str(self, value: Any) -> Optional[str]:
        return value.isoformat() if value else None

    def _float(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
