# -*- coding: utf-8 -*-
"""Analyze trade cohorts from saved backtest artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from theme_picker.backtest.signal_ranking import load_db_backtest_runs
except ModuleNotFoundError:
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from src.backtest.signal_ranking import load_db_backtest_runs  # type: ignore[no-redef]


GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("run", ("run_name",)),
    ("run_signal", ("run_name", "signal_type")),
    ("run_score_bin", ("run_name", "score_bin")),
    ("run_signal_score_bin", ("run_name", "signal_type", "score_bin")),
    ("run_signal_style_number", ("run_name", "signal_type", "style_bucket", "signal_number")),
    ("run_exit", ("run_name", "exit_reason")),
    ("run_signal_exit", ("run_name", "signal_type", "exit_reason")),
    ("signal_type", ("signal_type",)),
    ("score_bin", ("score_bin",)),
    ("signal_score_bin", ("signal_type", "score_bin")),
    ("style_bucket", ("style_bucket",)),
    ("signal_style", ("signal_type", "style_bucket")),
    ("signal_number", ("signal_type", "signal_number")),
    ("signal_style_number", ("signal_type", "style_bucket", "signal_number")),
    ("exit_reason", ("exit_reason",)),
    ("signal_exit", ("signal_type", "exit_reason")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze trade cohorts from backtest summary artifacts")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="Backtest run directory or summary.json path. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--db-run-id",
        action="append",
        default=[],
        help="Imported SQLite backtest run_id. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--database-path",
        help="SQLite database path for --db-run-id. Defaults to DATABASE_PATH or data/stock_analysis.db.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for diagnostics outputs. Defaults to data/backtests/diagnostics/<timestamp>.",
    )
    parser.add_argument(
        "--min-cohort-size",
        type=int,
        default=5,
        help="Minimum trades for worst/best cohort rankings. Default 5.",
    )
    parser.add_argument(
        "--top-trades",
        type=int,
        default=20,
        help="Number of top losing/winning trades to include. Default 20.",
    )
    args = parser.parse_args()
    if not args.run and not args.db_run_id:
        parser.error("supply at least one --run JSON artifact or --db-run-id imported run")
    return args


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    trades: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for raw_run in args.run:
        summary_path = _resolve_summary_path(Path(raw_run))
        run_name = summary_path.parent.name
        summary_payload = _load_json(summary_path)
        run_trades, missing_paths = _load_run_trades(summary_payload, run_name=run_name)
        trades.extend(run_trades)
        runs.append(
            {
                "run_name": run_name,
                "input_source": "json_artifact",
                "summary_path": str(summary_path),
                "strategy": summary_payload.get("strategy"),
                "start_date": summary_payload.get("start_date"),
                "end_date": summary_payload.get("end_date"),
                "aggregate": summary_payload.get("aggregate") or {},
                "trade_count_loaded": len(run_trades),
                "missing_result_paths": missing_paths,
            }
        )

    for db_run in load_db_backtest_runs(args.db_run_id, database_path=args.database_path, root_dir=ROOT_DIR):
        run_trades = [_normalize_trade(trade, run_name=db_run.run_name) for trade in db_run.trades]
        trades.extend(run_trades)
        runs.append(
            {
                "run_name": db_run.run_name,
                "run_id": db_run.run_id,
                "input_source": db_run.input_source,
                "database_path": db_run.database_path,
                "source_path": db_run.source_path,
                "strategy": db_run.strategy,
                "start_date": db_run.start_date,
                "end_date": db_run.end_date,
                "aggregate": db_run.aggregate,
                "trade_count_loaded": len(run_trades),
                "missing_result_paths": [],
            }
        )

    cohort_rows = _build_cohort_rows(trades)
    diagnostics = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runs": runs,
        "total_trades_loaded": len(trades),
        "cohorts": cohort_rows,
        "worst_cohorts": _rank_cohorts(
            cohort_rows,
            min_cohort_size=max(1, args.min_cohort_size),
            reverse=False,
        )[:20],
        "best_cohorts": _rank_cohorts(
            cohort_rows,
            min_cohort_size=max(1, args.min_cohort_size),
            reverse=True,
        )[:20],
        "top_losing_trades": sorted(trades, key=lambda row: row["return_pct"])[: max(0, args.top_trades)],
        "top_winning_trades": sorted(trades, key=lambda row: row["return_pct"], reverse=True)[
            : max(0, args.top_trades)
        ],
    }

    diagnostics_path = output_dir / "diagnostics.json"
    trades_path = output_dir / "trades.csv"
    cohorts_path = output_dir / "cohorts.csv"
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(trades_path, trades, fieldnames=_trade_fieldnames())
    _write_csv(cohorts_path, cohort_rows, fieldnames=_cohort_fieldnames())

    _print_console_summary(runs=runs, cohort_rows=cohort_rows)
    print(f"saved_diagnostics={diagnostics_path}")
    print(f"saved_trades_csv={trades_path}")
    print(f"saved_cohorts_csv={cohorts_path}")
    return 0


def _resolve_summary_path(path: Path) -> Path:
    if not path.is_absolute():
        path = ROOT_DIR / path
    if path.is_dir():
        path = path / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"summary artifact not found: {path}")
    if path.name != "summary.json":
        raise ValueError(f"expected a summary.json path or run directory: {path}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _load_run_trades(summary_payload: dict[str, Any], *, run_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    trades: list[dict[str, Any]] = []
    missing_paths: list[str] = []
    for result_row in summary_payload.get("results") or []:
        if not isinstance(result_row, dict) or result_row.get("status") != "ok":
            continue
        raw_path = str(result_row.get("result_path") or "").strip()
        if not raw_path:
            continue
        result_path = Path(raw_path)
        if not result_path.is_absolute():
            result_path = ROOT_DIR / result_path
        if not result_path.is_file():
            missing_paths.append(raw_path)
            continue
        result_payload = _load_json(result_path)
        for trade in result_payload.get("trades") or []:
            if isinstance(trade, dict):
                trades.append(_normalize_trade(trade, run_name=run_name))
    return trades, missing_paths


def _normalize_trade(trade: dict[str, Any], *, run_name: str) -> dict[str, Any]:
    metadata = trade.get("entry_signal_metadata") or {}
    signal_type = str(metadata.get("signal_type") or trade.get("entry_signal_reason") or "")
    score = _to_float(trade.get("entry_signal_score"))
    return {
        "run_name": run_name,
        "stock_code": trade.get("stock_code"),
        "entry_date": trade.get("entry_date"),
        "exit_date": trade.get("exit_date"),
        "entry_signal_reason": trade.get("entry_signal_reason"),
        "signal_type": signal_type,
        "entry_signal_score": score,
        "score_bin": _score_bin(score),
        "style_bucket": metadata.get("style_bucket"),
        "signal_number": _to_int(metadata.get("signal_number")),
        "breakout_cluster_count": _to_int(metadata.get("breakout_cluster_count")),
        "exit_reason": trade.get("exit_reason"),
        "return_pct": _to_float(trade.get("return_pct"), default=0.0),
        "holding_days": _to_int(trade.get("holding_days")),
        "max_favorable_excursion_pct": _to_float(trade.get("max_favorable_excursion_pct")),
        "max_adverse_excursion_pct": _to_float(trade.get("max_adverse_excursion_pct")),
        "volume_ratio": _to_float(metadata.get("volume_ratio")),
        "turnover_rate": _to_float(metadata.get("turnover_rate")),
        "trend": metadata.get("trend"),
        "rr_ratio": _to_float(metadata.get("rr_ratio")),
        "box_height": _to_float(metadata.get("box_height")),
        "box_height_pct": _to_float(metadata.get("box_height_pct")),
        "box_stack_lift_pct": _to_float(metadata.get("box_stack_lift_pct")),
        "box_support": _to_float(metadata.get("box_support")),
        "box_resistance": _to_float(metadata.get("box_resistance")),
        "ma10_bias_pct": _to_float(metadata.get("ma10_bias_pct")),
        "support_touches": _to_int(metadata.get("support_touches")),
        "resistance_touches": _to_int(metadata.get("resistance_touches")),
        "pullback_low_vs_resistance_pct": _to_float(metadata.get("pullback_low_vs_resistance_pct")),
        "pullback_close_above_resistance_pct": _to_float(metadata.get("pullback_close_above_resistance_pct")),
        "breakout_extension_pct": _to_float(metadata.get("breakout_extension_pct")),
        "breakout_body_pct": _to_float(metadata.get("breakout_body_pct")),
        "breakout_close_above_resistance_pct": _to_float(metadata.get("breakout_close_above_resistance_pct")),
        "breakout_upper_shadow_ratio": _to_float(metadata.get("breakout_upper_shadow_ratio")),
    }


def _build_cohort_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_name, fields in GROUPS:
        buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for trade in trades:
            buckets[tuple(_display_value(trade.get(field)) for field in fields)].append(trade)
        for key, bucket in buckets.items():
            row = {
                "group": group_name,
                "keys": " | ".join(str(item) for item in key),
            }
            for field, value in zip(fields, key):
                row[field] = value
            row.update(_trade_stats(bucket))
            rows.append(row)
    return sorted(rows, key=lambda item: (str(item.get("group")), str(item.get("keys"))))


def _trade_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [_to_float(trade.get("return_pct"), default=0.0) for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    mfe_values = [_to_float(trade.get("max_favorable_excursion_pct")) for trade in trades]
    mae_values = [_to_float(trade.get("max_adverse_excursion_pct")) for trade in trades]
    holding_days = [_to_int(trade.get("holding_days")) for trade in trades]
    return {
        "trade_count": len(trades),
        "win_rate_pct": _round(len(wins) / len(trades) * 100.0 if trades else 0.0),
        "avg_return_pct": _round(sum(returns) / len(returns) if returns else 0.0),
        "sum_return_pct": _round(sum(returns)),
        "avg_win_pct": _round(sum(wins) / len(wins) if wins else 0.0),
        "avg_loss_pct": _round(sum(losses) / len(losses) if losses else 0.0),
        "profit_factor": _round(gross_win / gross_loss) if gross_loss else None,
        "avg_mfe_pct": _round(_average_present(mfe_values)),
        "avg_mae_pct": _round(_average_present(mae_values)),
        "avg_holding_days": _round(_average_present(holding_days)),
    }


def _rank_cohorts(
    cohort_rows: list[dict[str, Any]],
    *,
    min_cohort_size: int,
    reverse: bool,
) -> list[dict[str, Any]]:
    eligible = [
        row
        for row in cohort_rows
        if int(row.get("trade_count") or 0) >= min_cohort_size
        and str(row.get("group"))
        not in {"run", "exit_reason", "signal_exit", "run_exit", "run_signal_exit"}
    ]
    return sorted(
        eligible,
        key=lambda row: (
            _to_float(row.get("avg_return_pct"), default=0.0),
            _to_float(row.get("sum_return_pct"), default=0.0),
        ),
        reverse=reverse,
    )


def _print_console_summary(*, runs: list[dict[str, Any]], cohort_rows: list[dict[str, Any]]) -> None:
    print("runs:")
    for run in runs:
        aggregate = run.get("aggregate") or {}
        print(
            "  "
            + json.dumps(
                {
                    "run_name": run.get("run_name"),
                    "loaded_trades": run.get("trade_count_loaded"),
                    "aggregate_return_pct": aggregate.get("aggregate_return_pct"),
                    "total_trade_count": aggregate.get("total_trade_count"),
                },
                ensure_ascii=False,
            )
        )
    print("signal cohorts:")
    for row in cohort_rows:
        if row.get("group") == "signal_type":
            print("  " + _format_cohort(row))
    print("signal score-bin cohorts:")
    rows = [row for row in cohort_rows if row.get("group") == "signal_score_bin"]
    rows.sort(key=lambda row: (str(row.get("signal_type")), str(row.get("score_bin"))))
    for row in rows:
        print("  " + _format_cohort(row))


def _format_cohort(row: dict[str, Any]) -> str:
    return (
        f"{row.get('keys')}: n={row.get('trade_count')} win={row.get('win_rate_pct')}% "
        f"avg={row.get('avg_return_pct')}% sum={row.get('sum_return_pct')}%"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _trade_fieldnames() -> list[str]:
    return [
        "run_name",
        "stock_code",
        "entry_date",
        "exit_date",
        "entry_signal_reason",
        "signal_type",
        "entry_signal_score",
        "score_bin",
        "style_bucket",
        "signal_number",
        "breakout_cluster_count",
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
    ]


def _cohort_fieldnames() -> list[str]:
    return [
        "group",
        "keys",
        "run_name",
        "signal_type",
        "score_bin",
        "style_bucket",
        "signal_number",
        "exit_reason",
        "trade_count",
        "win_rate_pct",
        "avg_return_pct",
        "sum_return_pct",
        "avg_win_pct",
        "avg_loss_pct",
        "profit_factor",
        "avg_mfe_pct",
        "avg_mae_pct",
        "avg_holding_days",
    ]


def _default_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT_DIR / "data" / "backtests" / "diagnostics" / timestamp


def _score_bin(score: float | None) -> str:
    if score is None:
        return "None"
    lower = int(score // 10) * 10
    upper = lower + 9
    return f"{lower:03d}-{upper:03d}" if lower >= 100 else f"{lower:02d}-{upper:02d}"


def _average_present(values: list[float | int | None]) -> float:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else 0.0


def _display_value(value: Any) -> Any:
    if value is None or value == "":
        return "None"
    return value


def _to_float(value: Any, *, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
