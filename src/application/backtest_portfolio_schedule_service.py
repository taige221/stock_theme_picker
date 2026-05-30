# -*- coding: utf-8 -*-
"""Portfolio-level scheduling service for ranked backtest trade candidates."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import delete, desc, select

from theme_picker.backtest.analysis.signal_ranking import (
    LayeredRankingConfig,
    build_selection_summary,
    normalize_trade_candidate,
    rank_trade_candidates,
)
from theme_picker.storage import (
    DatabaseManager,
    StrategyBacktestPortfolioCandidate,
    StrategyBacktestPortfolioSchedule,
    StrategyBacktestRun,
    StrategyBacktestTrade,
    get_db,
)


class BacktestPortfolioScheduleService:
    """Build, persist, and read portfolio scheduling overlays for a backtest run."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db()

    def create_schedule(
        self,
        run_id: str,
        *,
        config_payload: dict[str, Any] | None = None,
        schedule_name: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        run_id = str(run_id or "").strip()
        if not run_id:
            raise ValueError("run_id 不能为空")
        config = self._ranking_config(config_payload or {})
        created_at = datetime.now()

        with self.db.session_scope() as session:
            run = session.execute(
                select(StrategyBacktestRun).where(StrategyBacktestRun.run_id == run_id).limit(1)
            ).scalars().first()
            if run is None:
                raise FileNotFoundError(f"backtest run not found: {run_id}")

            trades = (
                session.execute(
                    select(StrategyBacktestTrade)
                    .where(StrategyBacktestTrade.run_id == run_id)
                    .order_by(StrategyBacktestTrade.entry_date.asc(), StrategyBacktestTrade.id.asc())
                )
                .scalars()
                .all()
            )
            run_name = str(run.run_name or run.source_path or run.run_id)
            trade_payloads = [self._trade_to_payload(trade) for trade in trades]
            normalized_trades = [
                normalize_trade_candidate(trade, run_name=run_name)
                for trade in trade_payloads
                if trade.get("entry_date")
            ]
            candidate_rows = rank_trade_candidates(normalized_trades, run_name=run_name, config=config)
            selected_rows = [row for row in candidate_rows if row.get("selected")]
            aggregate = self._loads(run.aggregate_payload) or {}
            summary = build_selection_summary(
                run_name=run_name,
                candidate_rows=candidate_rows,
                selected_rows=selected_rows,
                config=config,
                aggregate=aggregate,
                missing_result_path_count=0,
            )
            schedule_id = self._make_schedule_id(
                run_id=run_id,
                config=config.to_dict(),
                created_at=created_at,
                candidate_count=len(candidate_rows),
            )

            entry_days = [self._parse_date(row.get("entry_date")) for row in candidate_rows if row.get("entry_date")]
            schedule_row = StrategyBacktestPortfolioSchedule(
                schedule_id=schedule_id,
                run_id=run_id,
                schedule_name=schedule_name,
                rank_mode=config.rank_mode,
                status="finished",
                candidate_count=len(candidate_rows),
                selected_count=len(selected_rows),
                first_entry_date=min(entry_days) if entry_days else None,
                last_entry_date=max(entry_days) if entry_days else None,
                config_payload=self._dumps(config.to_dict()),
                summary_payload=self._dumps(summary),
                raw_payload=self._dumps(
                    {
                        "run_id": run_id,
                        "run_name": run_name,
                        "created_at": created_at.isoformat(timespec="seconds"),
                    }
                ),
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(schedule_row)
            session.flush()
            if candidate_rows:
                session.bulk_save_objects(
                    [
                        self._candidate_row(
                            run_id=run_id,
                            schedule_id=schedule_id,
                            ordinal=index,
                            row=row,
                        )
                        for index, row in enumerate(candidate_rows, start=1)
                    ]
                )

            return self._schedule_payload(
                schedule=schedule_row,
                candidates=[
                    self._candidate_payload_from_row(schedule_id=schedule_id, ordinal=index, row=row)
                    for index, row in enumerate(candidate_rows[: max(1, limit)], start=1)
                ],
                candidate_limit=limit,
            )

    def list_schedules(self, run_id: str, *, limit: int = 50) -> dict[str, Any]:
        run_id = str(run_id or "").strip()
        if not run_id:
            raise ValueError("run_id 不能为空")
        with self.db.session_scope() as session:
            exists = session.execute(
                select(StrategyBacktestRun.run_id).where(StrategyBacktestRun.run_id == run_id).limit(1)
            ).first()
            if exists is None:
                raise FileNotFoundError(f"backtest run not found: {run_id}")
            rows = (
                session.execute(
                    select(StrategyBacktestPortfolioSchedule)
                    .where(StrategyBacktestPortfolioSchedule.run_id == run_id)
                    .order_by(desc(StrategyBacktestPortfolioSchedule.created_at), desc(StrategyBacktestPortfolioSchedule.id))
                    .limit(max(1, limit))
                )
                .scalars()
                .all()
            )
        return {"items": [self._schedule_list_item(row) for row in rows], "next_cursor": None}

    def get_schedule(self, schedule_id: str, *, limit: int = 500, offset: int = 0) -> dict[str, Any]:
        schedule_id = str(schedule_id or "").strip()
        if not schedule_id:
            raise ValueError("schedule_id 不能为空")
        with self.db.session_scope() as session:
            schedule = session.execute(
                select(StrategyBacktestPortfolioSchedule)
                .where(StrategyBacktestPortfolioSchedule.schedule_id == schedule_id)
                .limit(1)
            ).scalars().first()
            if schedule is None:
                raise FileNotFoundError(f"portfolio schedule not found: {schedule_id}")
            candidates = (
                session.execute(
                    select(StrategyBacktestPortfolioCandidate)
                    .where(StrategyBacktestPortfolioCandidate.schedule_id == schedule_id)
                    .order_by(
                        StrategyBacktestPortfolioCandidate.entry_date.asc(),
                        StrategyBacktestPortfolioCandidate.daily_candidate_rank.asc(),
                        StrategyBacktestPortfolioCandidate.id.asc(),
                    )
                    .offset(max(0, offset))
                    .limit(max(1, limit))
                )
                .scalars()
                .all()
            )
            return self._schedule_payload(
                schedule=schedule,
                candidates=[self._candidate_to_dict(row) for row in candidates],
                candidate_limit=limit,
                candidate_offset=offset,
            )

    def delete_run_schedules(self, session, run_id: str) -> None:
        schedule_ids = [
            str(row[0])
            for row in session.execute(
                select(StrategyBacktestPortfolioSchedule.schedule_id).where(
                    StrategyBacktestPortfolioSchedule.run_id == run_id
                )
            ).all()
        ]
        if schedule_ids:
            session.execute(
                delete(StrategyBacktestPortfolioCandidate).where(
                    StrategyBacktestPortfolioCandidate.schedule_id.in_(schedule_ids)
                )
            )
        session.execute(delete(StrategyBacktestPortfolioSchedule).where(StrategyBacktestPortfolioSchedule.run_id == run_id))

    def _ranking_config(self, payload: dict[str, Any]) -> LayeredRankingConfig:
        rank_mode = str(payload.get("rank_mode") or payload.get("rankMode") or "signal_score")
        if rank_mode not in {"signal_score", "cohort_ev", "cohort_ev_walk_forward", "stock_quality", "stock_quality_walk_forward"}:
            raise ValueError(f"unsupported rankMode: {rank_mode}")
        return LayeredRankingConfig(
            rank_mode=rank_mode,  # type: ignore[arg-type]
            max_per_day=self._int(payload.get("max_per_day", payload.get("maxPerDay", 3)), default=3),
            pullback_quota=self._int(payload.get("pullback_quota", payload.get("pullbackQuota", 2)), default=2),
            breakout_quota=self._int(payload.get("breakout_quota", payload.get("breakoutQuota", 1)), default=1),
            max_open_positions=self._int(
                payload.get("max_open_positions", payload.get("maxOpenPositions", 0)),
                default=0,
            ),
            min_cohort_trades=self._int(
                payload.get("min_cohort_trades", payload.get("minCohortTrades", 8)),
                default=8,
            ),
            min_rank_score=self._optional_float(payload.get("min_rank_score", payload.get("minRankScore"))),
            heat_score_cap=self._optional_float(
                payload.get(
                    "heat_score_cap",
                    payload.get("heatScoreCap", payload.get("max_heat_score", payload.get("maxHeatScore"))),
                )
            ),
            fill_unused_slots=bool(payload.get("fill_unused_slots", payload.get("fillUnusedSlots", True))),
        ).normalized()

    def _candidate_row(
        self,
        *,
        run_id: str,
        schedule_id: str,
        ordinal: int,
        row: dict[str, Any],
    ) -> StrategyBacktestPortfolioCandidate:
        return StrategyBacktestPortfolioCandidate(
            candidate_id=self._stored_candidate_id(schedule_id, ordinal),
            schedule_id=schedule_id,
            run_id=run_id,
            entry_date=self._parse_date(row.get("entry_date")) or date(1970, 1, 1),
            stock_code=str(row.get("stock_code") or ""),
            stock_name=row.get("stock_name"),
            signal_type=row.get("signal_type"),
            rank_score=self._optional_float(row.get("rank_score")),
            daily_candidate_rank=self._optional_int(row.get("daily_candidate_rank")),
            selected=1 if row.get("selected") else 0,
            selected_order=self._optional_int(row.get("selected_order")),
            selected_layer=row.get("selected_layer"),
            return_pct=self._optional_float(row.get("return_pct")),
            net_pnl=self._optional_float(row.get("net_pnl")),
            exit_date=self._parse_date(row.get("exit_date")),
            exit_reason=row.get("exit_reason"),
            trade_id=row.get("trade_id"),
            metadata_payload=self._dumps(self._candidate_metadata(row)),
            raw_payload=self._dumps(row),
        )

    def _candidate_payload_from_row(self, *, schedule_id: str, ordinal: int, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        payload["stored_candidate_id"] = self._stored_candidate_id(schedule_id, ordinal)
        payload["metadata"] = self._candidate_metadata(row)
        return self._json_ready(payload)

    def _candidate_to_dict(self, row: StrategyBacktestPortfolioCandidate) -> dict[str, Any]:
        raw = self._loads(row.raw_payload) or {}
        payload = {
            **raw,
            "stored_candidate_id": row.candidate_id,
            "schedule_id": row.schedule_id,
            "run_id": row.run_id,
            "entry_date": self._date_to_str(row.entry_date),
            "exit_date": self._date_to_str(row.exit_date),
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "signal_type": row.signal_type,
            "rank_score": row.rank_score,
            "daily_candidate_rank": row.daily_candidate_rank,
            "selected": bool(row.selected),
            "selected_order": row.selected_order,
            "selected_layer": row.selected_layer,
            "return_pct": row.return_pct,
            "net_pnl": row.net_pnl,
            "exit_reason": row.exit_reason,
            "trade_id": row.trade_id,
            "metadata": self._loads(row.metadata_payload) or {},
        }
        return self._json_ready(payload)

    def _schedule_payload(
        self,
        *,
        schedule: StrategyBacktestPortfolioSchedule,
        candidates: list[dict[str, Any]],
        candidate_limit: int,
        candidate_offset: int = 0,
    ) -> dict[str, Any]:
        summary = self._loads(schedule.summary_payload) or {}
        config = self._loads(schedule.config_payload) or {}
        return {
            "schedule": self._schedule_list_item(schedule),
            "config": config,
            "summary": summary,
            "candidates": candidates,
            "candidate_page": {
                "limit": max(1, candidate_limit),
                "offset": max(0, candidate_offset),
                "returned": len(candidates),
                "total": schedule.candidate_count or 0,
            },
        }

    def _schedule_list_item(self, row: StrategyBacktestPortfolioSchedule) -> dict[str, Any]:
        return {
            "schedule_id": row.schedule_id,
            "run_id": row.run_id,
            "schedule_name": row.schedule_name,
            "rank_mode": row.rank_mode,
            "status": row.status,
            "candidate_count": row.candidate_count,
            "selected_count": row.selected_count,
            "first_entry_date": self._date_to_str(row.first_entry_date),
            "last_entry_date": self._date_to_str(row.last_entry_date),
            "created_at": self._datetime_to_str(row.created_at),
            "updated_at": self._datetime_to_str(row.updated_at),
        }

    def _trade_to_payload(self, row: StrategyBacktestTrade) -> dict[str, Any]:
        raw = self._loads(row.raw_trade_payload) or {}
        metadata = self._loads(row.entry_signal_metadata_payload) or {}
        return {
            **raw,
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
            "entry_signal_reason": row.entry_signal_reason,
            "entry_signal_score": row.entry_signal_score,
            "highest_price_seen": row.highest_price_seen,
            "lowest_price_seen": row.lowest_price_seen,
            "max_favorable_excursion_pct": row.max_favorable_excursion_pct,
            "max_adverse_excursion_pct": row.max_adverse_excursion_pct,
            "entry_signal_metadata": metadata,
        }

    def _candidate_metadata(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata_fields = (
            "rank_mode",
            "rank_filter_passed",
            "daily_candidate_count",
            "score_bin",
            "style_bucket",
            "signal_number",
            "breakout_cluster_count",
            "entry_signal_score",
            "volume_ratio",
            "turnover_rate",
            "trend",
            "rr_ratio",
            "box_height",
            "box_height_pct",
            "box_stack_lift_pct",
            "box_support",
            "box_resistance",
            "ma10_bias_pct",
            "support_touches",
            "resistance_touches",
            "pullback_low_vs_resistance_pct",
            "pullback_close_above_resistance_pct",
            "breakout_extension_pct",
            "breakout_body_pct",
            "breakout_close_above_resistance_pct",
            "breakout_upper_shadow_ratio",
        )
        return {field: row.get(field) for field in metadata_fields if row.get(field) is not None}

    def _make_schedule_id(
        self,
        *,
        run_id: str,
        config: dict[str, Any],
        created_at: datetime,
        candidate_count: int,
    ) -> str:
        digest = hashlib.sha256(
            self._dumps(
                {
                    "run_id": run_id,
                    "config": config,
                    "created_at": created_at.isoformat(timespec="microseconds"),
                    "candidate_count": candidate_count,
                }
            ).encode("utf-8")
        ).hexdigest()[:12]
        return f"bps_{digest}"

    @staticmethod
    def _stored_candidate_id(schedule_id: str, ordinal: int) -> str:
        return f"{schedule_id}:{ordinal:06d}"

    @staticmethod
    def _dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)

    @staticmethod
    def _loads(value: Any) -> Any:
        if not value:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _int(value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _date_to_str(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _datetime_to_str(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat(timespec="seconds")
        return str(value)

    def _json_ready(self, value: Any) -> Any:
        return self._loads(self._dumps(value))
