# -*- coding: utf-8 -*-
"""Simulate layered signal ranking from saved box-strategy backtest trades."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from theme_picker.backtest.signal_ranking import (
        LayeredRankingConfig,
        build_selection_summary,
        candidate_fieldnames,
        load_db_backtest_runs,
        normalize_trade_candidate,
        rank_trade_candidates,
        summary_fieldnames,
    )
except ModuleNotFoundError:
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from src.backtest.signal_ranking import (  # type: ignore[no-redef]
        LayeredRankingConfig,
        build_selection_summary,
        candidate_fieldnames,
        load_db_backtest_runs,
        normalize_trade_candidate,
        rank_trade_candidates,
        summary_fieldnames,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank box-strategy trades by layered signal buckets")
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
        help="Imported DuckDB backtest run_id. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--database-path",
        help="DuckDB database path for --db-run-id. Defaults to DATABASE_PATH or data/stock_analysis.duckdb.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for ranking outputs. Defaults to data/backtests/diagnostics/layered_rank_<timestamp>.",
    )
    parser.add_argument(
        "--rank-mode",
        choices=("signal_score", "cohort_ev", "cohort_ev_walk_forward"),
        default="signal_score",
        help="Ranking score inside each signal layer. Default signal_score.",
    )
    parser.add_argument("--max-per-day", type=int, default=3, help="Maximum selected entries per entry date.")
    parser.add_argument("--pullback-quota", type=int, default=2, help="Daily quota for pullback_bounce.")
    parser.add_argument("--breakout-quota", type=int, default=1, help="Daily quota for breakout_long.")
    parser.add_argument(
        "--max-open-positions",
        type=int,
        default=0,
        help="Optional portfolio-level cap for concurrently selected trades. 0 disables the cap.",
    )
    parser.add_argument(
        "--min-cohort-trades",
        type=int,
        default=8,
        help="Shrinkage strength for cohort_ev ranking. Default 8.",
    )
    parser.add_argument(
        "--min-rank-score",
        type=float,
        help="Optional minimum layered rank score before a candidate can be selected.",
    )
    parser.add_argument(
        "--no-fill",
        action="store_true",
        help="Do not fill unused daily slots after signal quotas are applied.",
    )
    args = parser.parse_args()
    if not args.run and not args.db_run_id:
        parser.error("supply at least one --run JSON artifact or --db-run-id imported run")
    return args


def main() -> int:
    args = parse_args()
    config = LayeredRankingConfig(
        rank_mode=args.rank_mode,
        max_per_day=args.max_per_day,
        pullback_quota=args.pullback_quota,
        breakout_quota=args.breakout_quota,
        max_open_positions=args.max_open_positions,
        min_cohort_trades=args.min_cohort_trades,
        min_rank_score=args.min_rank_score,
        fill_unused_slots=not args.no_fill,
    ).normalized()
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    all_candidate_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for raw_run in args.run:
        summary_path = _resolve_summary_path(Path(raw_run))
        run_name = summary_path.parent.name
        summary_payload = _load_json(summary_path)
        trades, missing_paths = _load_run_trades(summary_payload, run_name=run_name)
        ranked_rows = rank_trade_candidates(trades, run_name=run_name, config=config)
        all_candidate_rows.extend(ranked_rows)
        selected_rows = [row for row in ranked_rows if row.get("selected")]
        summary_rows.append(
            build_selection_summary(
                run_name=run_name,
                candidate_rows=ranked_rows,
                selected_rows=selected_rows,
                config=config,
                aggregate=summary_payload.get("aggregate") or {},
                missing_result_path_count=len(missing_paths),
            )
        )

    for db_run in load_db_backtest_runs(args.db_run_id, database_path=args.database_path, root_dir=ROOT_DIR):
        trades = [normalize_trade_candidate(trade, run_name=db_run.run_name) for trade in db_run.trades]
        ranked_rows = rank_trade_candidates(trades, run_name=db_run.run_name, config=config)
        all_candidate_rows.extend(ranked_rows)
        selected_rows = [row for row in ranked_rows if row.get("selected")]
        summary_rows.append(
            build_selection_summary(
                run_name=db_run.run_name,
                candidate_rows=ranked_rows,
                selected_rows=selected_rows,
                config=config,
                aggregate=db_run.aggregate,
                missing_result_path_count=0,
            )
        )

    _write_csv(output_dir / "ranked_candidates.csv", all_candidate_rows, fieldnames=candidate_fieldnames())
    _write_csv(output_dir / "selection_summary.csv", summary_rows, fieldnames=summary_fieldnames())
    summary_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": config.to_dict(),
        "runs": summary_rows,
        "notes": [
            "This is a portfolio/candidate-layer overlay built from completed single-symbol backtest trades.",
            "It validates ranking and quota ideas before changing strategy entry logic.",
            "WARNING: cohort_ev is sample-internal and must not be promoted to a default live rule.",
            "Use cohort_ev only for diagnostics unless the input run is split into train/apply windows externally.",
            "cohort_ev_walk_forward only scores with prior closed trades to reduce look-ahead leakage, but it is still a research overlay.",
        ],
    }
    (output_dir / "selection_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_summary(summary_rows)
    print(f"saved_ranked_candidates={output_dir / 'ranked_candidates.csv'}")
    print(f"saved_selection_summary={output_dir / 'selection_summary.csv'}")
    print(f"saved_selection_json={output_dir / 'selection_summary.json'}")
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
                trades.append(normalize_trade_candidate(trade, run_name=run_name))
    return trades, missing_paths


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _default_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT_DIR / "data" / "backtests" / "diagnostics" / f"layered_rank_{timestamp}"


def _print_summary(rows: list[dict[str, Any]]) -> None:
    print("layered ranking summary:")
    for row in rows:
        print(
            json.dumps(
                {
                    "run_name": row.get("run_name"),
                    "rank_mode": row.get("rank_mode"),
                    "candidate_trade_count": row.get("candidate_trade_count"),
                    "selected_trade_count": row.get("selected_trade_count"),
                    "candidate_avg_return_pct": row.get("candidate_avg_return_pct"),
                    "selected_avg_return_pct": row.get("selected_avg_return_pct"),
                    "candidate_win_rate_pct": row.get("candidate_win_rate_pct"),
                    "selected_win_rate_pct": row.get("selected_win_rate_pct"),
                    "selected_pullback_count": row.get("selected_pullback_count"),
                    "selected_breakout_count": row.get("selected_breakout_count"),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
