# -*- coding: utf-8 -*-
"""Candidate-layer ranking helpers for box-strategy backtest trades."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb

RankMode = Literal["signal_score", "cohort_ev", "cohort_ev_walk_forward"]
SQLITE_FILE_HEADER = b"SQLite format 3\x00"


@dataclass(slots=True)
class LayeredRankingConfig:
    rank_mode: RankMode = "signal_score"
    max_per_day: int = 3
    pullback_quota: int = 2
    breakout_quota: int = 1
    max_open_positions: int = 0
    min_cohort_trades: int = 8
    min_rank_score: float | None = None
    fill_unused_slots: bool = True

    def normalized(self) -> "LayeredRankingConfig":
        return LayeredRankingConfig(
            rank_mode=self.rank_mode,
            max_per_day=max(1, int(self.max_per_day)),
            pullback_quota=max(0, int(self.pullback_quota)),
            breakout_quota=max(0, int(self.breakout_quota)),
            max_open_positions=max(0, int(self.max_open_positions)),
            min_cohort_trades=max(1, int(self.min_cohort_trades)),
            min_rank_score=self.min_rank_score,
            fill_unused_slots=bool(self.fill_unused_slots),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


@dataclass(slots=True)
class LoadedBacktestRun:
    input_source: str
    run_id: str
    run_name: str
    database_path: str
    source_path: str | None
    strategy: str | None
    start_date: str | None
    end_date: str | None
    aggregate: dict[str, Any]
    trades: list[dict[str, Any]]


def load_db_backtest_runs(
    run_ids: list[str] | tuple[str, ...],
    *,
    database_path: str | Path | None = None,
    root_dir: Path | None = None,
) -> list[LoadedBacktestRun]:
    """Load imported backtest trades from DuckDB without touching backend services."""

    if not run_ids:
        return []
    db_path = resolve_backtest_database_path(database_path, root_dir=root_dir)
    try:
        with _connect_readonly_duckdb(db_path) as conn:
            return [
                _load_db_backtest_run(conn, run_id=str(run_id).strip(), database_path=db_path)
                for run_id in run_ids
            ]
    except duckdb.Error as exc:
        text = str(exc).lower()
        if "no such table" in text or "does not exist" in text:
            raise RuntimeError(
                "DuckDB database does not contain imported backtest tables. "
                "Run scripts/import_backtest_json.py first, or use --run with JSON artifacts."
            ) from exc
        if _is_duckdb_lock_error(exc):
            raise RuntimeError(
                "DuckDB database is locked by another process. Stop the theme_picker server/import job "
                "that has the database open, or rerun this command after it exits."
            ) from exc
        raise


def resolve_backtest_database_path(
    database_path: str | Path | None = None,
    *,
    root_dir: Path | None = None,
) -> Path:
    raw_value = database_path or os.getenv("DATABASE_PATH") or "data/stock_analysis.duckdb"
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = (root_dir or Path.cwd()) / path
    return path.resolve()


def normalize_trade_candidate(trade: dict[str, Any], *, run_name: str = "") -> dict[str, Any]:
    metadata = trade.get("entry_signal_metadata") or {}
    signal_type = str(metadata.get("signal_type") or trade.get("entry_signal_reason") or "")
    score = to_float(trade.get("entry_signal_score"), default=None)
    return {
        "run_name": run_name,
        "stock_code": trade.get("stock_code"),
        "entry_date": trade.get("entry_date"),
        "exit_date": trade.get("exit_date"),
        "entry_signal_reason": trade.get("entry_signal_reason"),
        "signal_type": signal_type,
        "entry_signal_score": score,
        "score_bin": score_bin(score),
        "style_bucket": metadata.get("style_bucket"),
        "signal_number": to_int(metadata.get("signal_number")),
        "breakout_cluster_count": to_int(metadata.get("breakout_cluster_count")),
        "exit_reason": trade.get("exit_reason"),
        "return_pct": to_float(trade.get("return_pct"), default=0.0),
        "holding_days": to_int(trade.get("holding_days")),
        "max_favorable_excursion_pct": to_float(trade.get("max_favorable_excursion_pct"), default=None),
        "max_adverse_excursion_pct": to_float(trade.get("max_adverse_excursion_pct"), default=None),
        "volume_ratio": to_float(metadata.get("volume_ratio"), default=None),
        "turnover_rate": to_float(metadata.get("turnover_rate"), default=None),
        "trend": metadata.get("trend"),
        "rr_ratio": to_float(metadata.get("rr_ratio"), default=None),
        "box_height": to_float(metadata.get("box_height"), default=None),
        "box_height_pct": to_float(metadata.get("box_height_pct"), default=None),
        "box_stack_lift_pct": to_float(metadata.get("box_stack_lift_pct"), default=None),
        "box_support": to_float(metadata.get("box_support"), default=None),
        "box_resistance": to_float(metadata.get("box_resistance"), default=None),
        "ma10_bias_pct": to_float(metadata.get("ma10_bias_pct"), default=None),
        "support_touches": to_int(metadata.get("support_touches")),
        "resistance_touches": to_int(metadata.get("resistance_touches")),
        "pullback_low_vs_resistance_pct": to_float(
            metadata.get("pullback_low_vs_resistance_pct"),
            default=None,
        ),
        "pullback_close_above_resistance_pct": to_float(
            metadata.get("pullback_close_above_resistance_pct"),
            default=None,
        ),
        "breakout_extension_pct": to_float(metadata.get("breakout_extension_pct"), default=None),
        "breakout_body_pct": to_float(metadata.get("breakout_body_pct"), default=None),
        "breakout_close_above_resistance_pct": to_float(
            metadata.get("breakout_close_above_resistance_pct"),
            default=None,
        ),
        "breakout_upper_shadow_ratio": to_float(metadata.get("breakout_upper_shadow_ratio"), default=None),
    }


def rank_trade_candidates(
    trades: list[dict[str, Any]],
    *,
    run_name: str,
    config: LayeredRankingConfig,
) -> list[dict[str, Any]]:
    runtime_config = config.normalized()
    scorer = None
    if runtime_config.rank_mode != "cohort_ev_walk_forward":
        scorer = _build_scorer(
            trades,
            rank_mode=runtime_config.rank_mode,
            min_cohort_trades=runtime_config.min_cohort_trades,
        )
    rows: list[dict[str, Any]] = []
    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)

    for index, trade in enumerate(trades):
        row = dict(trade)
        row["candidate_id"] = f"{run_name}:{index + 1}"
        row["entry_day"] = parse_iso_date(row.get("entry_date"))
        row["exit_day"] = parse_iso_date(row.get("exit_date"))
        row["rank_mode"] = runtime_config.rank_mode
        row["rank_score"] = round(scorer(row), 6) if scorer is not None else 0.0
        row["selected"] = False
        row["selected_order"] = None
        row["selected_layer"] = None
        row["daily_candidate_rank"] = None
        row["daily_candidate_count"] = None
        row["rank_filter_passed"] = False
        if row["entry_day"] is not None:
            by_date[row["entry_day"]].append(row)
            rows.append(row)

    open_rows: list[dict[str, Any]] = []
    selected_order = 0
    quotas = (
        ("pullback_bounce", runtime_config.pullback_quota),
        ("breakout_long", runtime_config.breakout_quota),
    )

    for entry_day in sorted(by_date):
        if runtime_config.rank_mode == "cohort_ev_walk_forward":
            closed_history = [
                row
                for row in rows
                if row.get("entry_day") is not None
                and row["entry_day"] < entry_day
                and row.get("exit_day") is not None
                and row["exit_day"] < entry_day
            ]
            day_scorer = _build_scorer(
                closed_history,
                rank_mode="cohort_ev",
                min_cohort_trades=runtime_config.min_cohort_trades,
            )
            for row in by_date[entry_day]:
                row["rank_score"] = round(day_scorer(row), 6)

        all_day_candidates = sorted(by_date[entry_day], key=_rank_sort_key)
        candidates = [
            row
            for row in all_day_candidates
            if runtime_config.min_rank_score is None
            or to_float(row.get("rank_score"), default=0.0) >= runtime_config.min_rank_score
        ]
        candidate_ids = {row["candidate_id"] for row in candidates}
        for daily_rank, row in enumerate(all_day_candidates, start=1):
            row["daily_candidate_rank"] = daily_rank
            row["daily_candidate_count"] = len(all_day_candidates)
            row["rank_filter_passed"] = row["candidate_id"] in candidate_ids

        open_rows = [
            row for row in open_rows if row.get("exit_day") is not None and row["exit_day"] >= entry_day
        ]
        available_slots = runtime_config.max_per_day
        if runtime_config.max_open_positions > 0:
            available_slots = min(available_slots, max(0, runtime_config.max_open_positions - len(open_rows)))
        if available_slots <= 0:
            continue

        selected_today: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        for signal_type, quota in quotas:
            if quota <= 0 or len(selected_today) >= available_slots:
                continue
            signal_candidates = [row for row in candidates if row.get("signal_type") == signal_type]
            for row in signal_candidates[:quota]:
                if row["candidate_id"] in selected_ids:
                    continue
                _select_row(row, selected_today, selected_ids, selected_layer=f"quota:{signal_type}")
                if len(selected_today) >= available_slots:
                    break

        if runtime_config.fill_unused_slots and len(selected_today) < available_slots:
            for row in candidates:
                if row["candidate_id"] in selected_ids:
                    continue
                _select_row(row, selected_today, selected_ids, selected_layer="fill")
                if len(selected_today) >= available_slots:
                    break

        for row in selected_today:
            selected_order += 1
            row["selected_order"] = selected_order
            if runtime_config.max_open_positions > 0:
                open_rows.append(row)

    return sorted(rows, key=lambda row: (str(row.get("entry_date")), int(row.get("daily_candidate_rank") or 0)))


def build_selection_summary(
    *,
    run_name: str,
    candidate_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    config: LayeredRankingConfig,
    aggregate: dict[str, Any] | None = None,
    missing_result_path_count: int = 0,
) -> dict[str, Any]:
    runtime_config = config.normalized()
    selected_stats = trade_stats(selected_rows)
    candidate_stats = trade_stats(candidate_rows)
    aggregate = aggregate or {}
    selected_days = {row.get("entry_date") for row in selected_rows if row.get("entry_date")}
    candidate_days = {row.get("entry_date") for row in candidate_rows if row.get("entry_date")}
    return {
        "run_name": run_name,
        **runtime_config.to_dict(),
        "candidate_trade_count": len(candidate_rows),
        "selected_trade_count": len(selected_rows),
        "selected_fraction_pct": round_float(
            (len(selected_rows) / len(candidate_rows) * 100.0) if candidate_rows else 0.0
        ),
        "candidate_entry_days": len(candidate_days),
        "selected_entry_days": len(selected_days),
        "avg_selected_per_entry_day": round_float(
            len(selected_rows) / len(selected_days) if selected_days else 0.0
        ),
        "candidate_avg_return_pct": candidate_stats.get("avg_return_pct"),
        "candidate_win_rate_pct": candidate_stats.get("win_rate_pct"),
        "candidate_sum_return_pct": candidate_stats.get("sum_return_pct"),
        "selected_avg_return_pct": selected_stats.get("avg_return_pct"),
        "selected_win_rate_pct": selected_stats.get("win_rate_pct"),
        "selected_sum_return_pct": selected_stats.get("sum_return_pct"),
        "selected_profit_factor": selected_stats.get("profit_factor"),
        "selected_avg_mfe_pct": selected_stats.get("avg_mfe_pct"),
        "selected_avg_mae_pct": selected_stats.get("avg_mae_pct"),
        "selected_pullback_count": count_signal(selected_rows, "pullback_bounce"),
        "selected_breakout_count": count_signal(selected_rows, "breakout_long"),
        "aggregate_return_pct": aggregate.get("aggregate_return_pct"),
        "aggregate_trade_count": aggregate.get("total_trade_count"),
        "missing_result_path_count": int(missing_result_path_count),
    }


def trade_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [to_float(trade.get("return_pct"), default=0.0) for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    mfe_values = [to_float(trade.get("max_favorable_excursion_pct"), default=None) for trade in trades]
    mae_values = [to_float(trade.get("max_adverse_excursion_pct"), default=None) for trade in trades]
    holding_days = [to_int(trade.get("holding_days")) for trade in trades]
    return {
        "trade_count": len(trades),
        "win_rate_pct": round_float(len(wins) / len(trades) * 100.0 if trades else 0.0),
        "avg_return_pct": round_float(sum(returns) / len(returns) if returns else 0.0),
        "sum_return_pct": round_float(sum(returns)),
        "avg_win_pct": round_float(sum(wins) / len(wins) if wins else 0.0),
        "avg_loss_pct": round_float(sum(losses) / len(losses) if losses else 0.0),
        "profit_factor": round_float(gross_win / gross_loss) if gross_loss else None,
        "avg_mfe_pct": round_float(average_present(mfe_values)),
        "avg_mae_pct": round_float(average_present(mae_values)),
        "avg_holding_days": round_float(average_present(holding_days)),
    }


def candidate_fieldnames() -> list[str]:
    return [
        "run_name",
        "candidate_id",
        "stock_code",
        "entry_date",
        "exit_date",
        "signal_type",
        "entry_signal_score",
        "score_bin",
        "rank_mode",
        "rank_score",
        "rank_filter_passed",
        "daily_candidate_rank",
        "daily_candidate_count",
        "selected",
        "selected_order",
        "selected_layer",
        "style_bucket",
        "signal_number",
        "exit_reason",
        "return_pct",
        "holding_days",
        "max_favorable_excursion_pct",
        "max_adverse_excursion_pct",
        "volume_ratio",
        "turnover_rate",
        "trend",
        "rr_ratio",
        "box_height",
        "box_height_pct",
        "box_stack_lift_pct",
        "ma10_bias_pct",
        "pullback_low_vs_resistance_pct",
        "pullback_close_above_resistance_pct",
        "breakout_extension_pct",
        "breakout_body_pct",
        "breakout_close_above_resistance_pct",
        "breakout_upper_shadow_ratio",
    ]


def summary_fieldnames() -> list[str]:
    return [
        "run_name",
        "rank_mode",
        "max_per_day",
        "pullback_quota",
        "breakout_quota",
        "max_open_positions",
        "min_cohort_trades",
        "min_rank_score",
        "fill_unused_slots",
        "candidate_trade_count",
        "selected_trade_count",
        "selected_fraction_pct",
        "candidate_entry_days",
        "selected_entry_days",
        "avg_selected_per_entry_day",
        "candidate_avg_return_pct",
        "candidate_win_rate_pct",
        "candidate_sum_return_pct",
        "selected_avg_return_pct",
        "selected_win_rate_pct",
        "selected_sum_return_pct",
        "selected_profit_factor",
        "selected_avg_mfe_pct",
        "selected_avg_mae_pct",
        "selected_pullback_count",
        "selected_breakout_count",
        "aggregate_return_pct",
        "aggregate_trade_count",
        "missing_result_path_count",
    ]


def score_bin(score: float | None) -> str:
    if score is None:
        return "None"
    lower = int(score // 10) * 10
    upper = lower + 9
    return f"{lower:03d}-{upper:03d}" if lower >= 100 else f"{lower:02d}-{upper:02d}"


def count_signal(rows: list[dict[str, Any]], signal_type: str) -> int:
    return len([row for row in rows if row.get("signal_type") == signal_type])


def average_present(values: list[float | int | None]) -> float:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else 0.0


def parse_iso_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def to_float(value: Any, *, default: float | None = 0.0) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def round_float(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _build_scorer(trades: list[dict[str, Any]], *, rank_mode: RankMode, min_cohort_trades: int):
    if rank_mode == "signal_score":
        return lambda row: to_float(row.get("entry_signal_score"), default=0.0) or 0.0

    signal_stats = _stats_by(trades, ("signal_type",))
    signal_score_stats = _stats_by(trades, ("signal_type", "score_bin"))
    style_number_stats = _stats_by(trades, ("signal_type", "style_bucket", "signal_number"))

    def cohort_ev_score(row: dict[str, Any]) -> float:
        signal_key = (_value(row.get("signal_type")),)
        score_key = (_value(row.get("signal_type")), _value(row.get("score_bin")))
        style_number_key = (
            _value(row.get("signal_type")),
            _value(row.get("style_bucket")),
            _value(row.get("signal_number")),
        )
        signal_ev = _shrunk_avg(signal_stats.get(signal_key), fallback=0.0, min_cohort_trades=min_cohort_trades)
        score_ev = _shrunk_avg(
            signal_score_stats.get(score_key),
            fallback=signal_ev,
            min_cohort_trades=min_cohort_trades,
        )
        style_ev = _shrunk_avg(
            style_number_stats.get(style_number_key),
            fallback=score_ev,
            min_cohort_trades=min_cohort_trades,
        )
        raw_score = to_float(row.get("entry_signal_score"), default=0.0) or 0.0
        return (style_ev * 0.6) + (score_ev * 0.3) + (signal_ev * 0.1) + (raw_score * 0.01)

    return cohort_ev_score


def _stats_by(trades: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[tuple[Any, ...], dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        key = tuple(_value(trade.get(field)) for field in fields)
        buckets[key].append(trade)
    return {key: trade_stats(bucket) for key, bucket in buckets.items()}


def _shrunk_avg(stats: dict[str, Any] | None, *, fallback: float, min_cohort_trades: int) -> float:
    if not stats:
        return fallback
    count = int(stats.get("trade_count") or 0)
    raw_avg_return = to_float(stats.get("avg_return_pct"), default=None)
    avg_return = fallback if raw_avg_return is None else raw_avg_return
    if count <= 0:
        return fallback
    return ((avg_return * count) + (fallback * min_cohort_trades)) / (count + min_cohort_trades)


def _rank_sort_key(row: dict[str, Any]) -> tuple[float, float, str]:
    return (
        -(to_float(row.get("rank_score"), default=0.0) or 0.0),
        -(to_float(row.get("entry_signal_score"), default=0.0) or 0.0),
        str(row.get("stock_code") or ""),
    )


def _select_row(
    row: dict[str, Any],
    selected_today: list[dict[str, Any]],
    selected_ids: set[str],
    *,
    selected_layer: str,
) -> None:
    row["selected"] = True
    row["selected_layer"] = selected_layer
    selected_today.append(row)
    selected_ids.add(str(row["candidate_id"]))


def _value(value: Any) -> Any:
    if value is None or value == "":
        return "None"
    return value


def _connect_readonly_duckdb(path: Path) -> duckdb.DuckDBPyConnection:
    if not path.exists():
        raise FileNotFoundError(f"backtest database not found: {path}")
    if _is_sqlite_database_file(path):
        raise RuntimeError(
            f"backtest database path points to a SQLite database: {path}. "
            "Run scripts/migrate_sqlite_to_duckdb.py and use data/stock_analysis.duckdb."
        )
    return duckdb.connect(str(path), read_only=True)


def _is_sqlite_database_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_FILE_HEADER)) == SQLITE_FILE_HEADER
    except OSError:
        return False


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "could not set lock" in text or "conflicting lock" in text


def _fetchone_dict(conn: duckdb.DuckDBPyConnection, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    result = conn.execute(sql, params)
    row = result.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in result.description]
    return dict(zip(columns, row))


def _fetchall_dict(conn: duckdb.DuckDBPyConnection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    result = conn.execute(sql, params)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def _load_db_backtest_run(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    database_path: Path,
) -> LoadedBacktestRun:
    if not run_id:
        raise ValueError("db run id is required")
    run_row = _fetchone_dict(
        conn,
        """
        select
          run_id,
          run_name,
          strategy,
          start_date,
          end_date,
          source_path,
          aggregate_payload,
          aggregate_return_pct,
          total_trade_count,
          win_rate_pct,
          profit_factor,
          max_drawdown_pct,
          total_pnl
        from strategy_backtest_run
        where run_id = ?
        """,
        (run_id,),
    )
    if run_row is None:
        raise FileNotFoundError(f"backtest run not found in DB: {run_id}")

    trade_rows = _fetchall_dict(
        conn,
        """
        select
          trade_id,
          stock_code,
          stock_name,
          entry_date,
          exit_date,
          entry_price,
          exit_price,
          shares,
          gross_pnl,
          net_pnl,
          return_pct,
          holding_days,
          exit_reason,
          entry_signal_reason,
          entry_signal_score,
          highest_price_seen,
          lowest_price_seen,
          max_favorable_excursion_pct,
          max_adverse_excursion_pct,
          entry_signal_metadata_payload,
          raw_trade_payload
        from strategy_backtest_trade
        where run_id = ?
        order by entry_date asc, id asc
        """,
        (run_id,),
    )

    aggregate = _loads_json_object(run_row["aggregate_payload"])
    aggregate.update(
        {
            key: run_row[key]
            for key in (
                "aggregate_return_pct",
                "total_trade_count",
                "win_rate_pct",
                "profit_factor",
                "max_drawdown_pct",
                "total_pnl",
            )
            if run_row[key] is not None
        }
    )
    run_name = str(run_row["run_name"] or run_row["source_path"] or run_row["run_id"])
    return LoadedBacktestRun(
        input_source="duckdb",
        run_id=str(run_row["run_id"]),
        run_name=run_name,
        database_path=str(database_path),
        source_path=run_row["source_path"],
        strategy=run_row["strategy"],
        start_date=_date_str(run_row["start_date"]),
        end_date=_date_str(run_row["end_date"]),
        aggregate=aggregate,
        trades=[_db_trade_row_to_payload(row) for row in trade_rows],
    )


def _db_trade_row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = _loads_json_object(row["raw_trade_payload"])
    metadata = _loads_json_object(row["entry_signal_metadata_payload"])
    if not metadata and isinstance(raw_payload.get("entry_signal_metadata"), dict):
        metadata = raw_payload["entry_signal_metadata"]

    payload = dict(raw_payload)
    payload.update(
        {
            "trade_id": row["trade_id"],
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "entry_date": _date_str(row["entry_date"]),
            "exit_date": _date_str(row["exit_date"]),
            "entry_price": row["entry_price"],
            "exit_price": row["exit_price"],
            "shares": row["shares"],
            "gross_pnl": row["gross_pnl"],
            "net_pnl": row["net_pnl"],
            "return_pct": row["return_pct"],
            "holding_days": row["holding_days"],
            "exit_reason": row["exit_reason"],
            "entry_signal_reason": row["entry_signal_reason"],
            "entry_signal_score": row["entry_signal_score"],
            "highest_price_seen": row["highest_price_seen"],
            "lowest_price_seen": row["lowest_price_seen"],
            "max_favorable_excursion_pct": row["max_favorable_excursion_pct"],
            "max_adverse_excursion_pct": row["max_adverse_excursion_pct"],
            "entry_signal_metadata": metadata,
        }
    )
    return payload


def _loads_json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _date_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
