# -*- coding: utf-8 -*-
"""Import robustness/regime-aware diagnostic outputs into DuckDB schedule tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from theme_picker.storage import (
        DatabaseManager,
        StrategyBacktestPortfolioCandidate,
        StrategyBacktestPortfolioSchedule,
        StrategyBacktestRun,
    )
except ModuleNotFoundError:
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from src.storage import (  # type: ignore[no-redef]
        DatabaseManager,
        StrategyBacktestPortfolioCandidate,
        StrategyBacktestPortfolioSchedule,
        StrategyBacktestRun,
    )


DEFAULT_PROFILES = (
    ("conservative", "data/backtests/diagnostics/p3_candidate_conservative_broad_pause_bt_4008f88677a1_v1"),
    ("balanced", "data/backtests/diagnostics/p3_regime_euphoric_pause_full_bt_4008f88677a1_v1"),
    ("aggressive", "data/backtests/diagnostics/p3_candidate_attack_12_04_12_euphoric_pause_full_bt_4008f88677a1_v1"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import P3 robustness profile outputs into DB")
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Profile in name=diagnostic_dir form. Can be supplied multiple times. Defaults to the three current tiers.",
    )
    parser.add_argument("--database-path", help="DuckDB path. Defaults to DATABASE_PATH or data/stock_analysis.duckdb.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print counts without writing DB.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile_specs = _profile_specs(args.profile)
    db = DatabaseManager(args.database_path) if args.database_path else DatabaseManager()
    try:
        results = [import_profile(db, name=name, directory=directory, dry_run=args.dry_run) for name, directory in profile_specs]
    finally:
        db.close()
    print(json.dumps({"dry_run": bool(args.dry_run), "items": results}, ensure_ascii=False, indent=2))
    return 0


def import_profile(
    db: DatabaseManager,
    *,
    name: str,
    directory: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    summary_path = directory / "robustness_summary.json"
    candidates_path = directory / "regime_aware_candidates.csv"
    if not summary_path.exists():
        raise FileNotFoundError(f"robustness_summary.json not found: {summary_path}")
    if not candidates_path.exists():
        raise FileNotFoundError(f"regime_aware_candidates.csv not found: {candidates_path}")

    summary_payload = _load_json(summary_path)
    candidate_rows = _load_csv(candidates_path)
    source_run = summary_payload.get("source_run") or {}
    source_run_id = str(source_run.get("run_id") or "").strip()
    if not source_run_id:
        raise ValueError(f"missing source_run.run_id in {summary_path}")

    schedule_id = _schedule_id(name=name, summary_path=summary_path)
    created_at = datetime.now()
    entry_dates = [_parse_date(row.get("entry_date")) for row in candidate_rows if row.get("entry_date")]
    selected_rows = [row for row in candidate_rows if _truthy(row.get("selected"))]
    config_payload = _build_config_payload(name=name, directory=directory, summary=summary_payload)
    compact_summary = _build_summary_payload(summary_payload)
    raw_payload = {
        "imported_from": str(summary_path),
        "diagnostic_dir": str(directory),
        "source_run": source_run,
        "output_files": summary_payload.get("output_files") or {},
        "generated_at": summary_payload.get("generated_at"),
    }

    result = {
        "name": name,
        "schedule_id": schedule_id,
        "source_run_id": source_run_id,
        "summary_path": str(summary_path),
        "candidate_count": len(candidate_rows),
        "selected_count": len(selected_rows),
        "first_entry_date": min(entry_dates).isoformat() if entry_dates else None,
        "last_entry_date": max(entry_dates).isoformat() if entry_dates else None,
    }
    if dry_run:
        return result

    with db.session_scope() as session:
        exists = session.execute(
            select(StrategyBacktestRun.run_id).where(StrategyBacktestRun.run_id == source_run_id).limit(1)
        ).first()
        if exists is None:
            raise FileNotFoundError(f"source backtest run not found in DB: {source_run_id}")

        session.execute(
            delete(StrategyBacktestPortfolioCandidate).where(
                StrategyBacktestPortfolioCandidate.schedule_id == schedule_id
            )
        )
        session.execute(
            delete(StrategyBacktestPortfolioSchedule).where(
                StrategyBacktestPortfolioSchedule.schedule_id == schedule_id
            )
        )
        session.add(
            StrategyBacktestPortfolioSchedule(
                schedule_id=schedule_id,
                run_id=source_run_id,
                schedule_name=f"robustness_{name}",
                rank_mode=_rank_mode(summary_payload),
                status="finished",
                candidate_count=len(candidate_rows),
                selected_count=len(selected_rows),
                first_entry_date=min(entry_dates) if entry_dates else None,
                last_entry_date=max(entry_dates) if entry_dates else None,
                config_payload=_dumps(config_payload),
                summary_payload=_dumps(compact_summary),
                raw_payload=_dumps(raw_payload),
                created_at=created_at,
                updated_at=created_at,
            )
        )
        if candidate_rows:
            session.bulk_save_objects(
                [
                    _candidate_object(
                        schedule_id=schedule_id,
                        run_id=source_run_id,
                        ordinal=index,
                        row=row,
                    )
                    for index, row in enumerate(candidate_rows, start=1)
                ]
            )
    return result


def _candidate_object(
    *,
    schedule_id: str,
    run_id: str,
    ordinal: int,
    row: dict[str, Any],
) -> StrategyBacktestPortfolioCandidate:
    entry_date = _parse_date(row.get("entry_date")) or date(1970, 1, 1)
    raw_payload = _normalize_row(row)
    return StrategyBacktestPortfolioCandidate(
        candidate_id=f"{schedule_id}:{ordinal:06d}",
        schedule_id=schedule_id,
        run_id=run_id,
        entry_date=entry_date,
        stock_code=str(row.get("stock_code") or ""),
        stock_name=_optional_str(row.get("stock_name")),
        signal_type=_optional_str(row.get("signal_type")),
        rank_score=_optional_float(row.get("rank_score")),
        daily_candidate_rank=_optional_int(row.get("daily_candidate_rank")),
        selected=1 if _truthy(row.get("selected")) else 0,
        selected_order=_optional_int(row.get("selected_order")),
        selected_layer=_optional_str(row.get("selected_layer")),
        return_pct=_optional_float(row.get("return_pct")),
        net_pnl=_optional_float(row.get("net_pnl")),
        exit_date=_parse_date(row.get("exit_date")),
        exit_reason=_optional_str(row.get("exit_reason")),
        trade_id=_optional_str(row.get("trade_id")),
        metadata_payload=_dumps(_candidate_metadata(row)),
        raw_payload=_dumps(raw_payload),
    )


def _candidate_metadata(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "market_regime",
        "raw_market_regime",
        "market_regime_override_reason",
        "selected_profile",
        "rank_filter_reason",
        "position_size_pct",
        "heat_score",
        "raw_daily_rank",
        "eligible_daily_rank",
        "eligible_candidate_count",
        "entry_signal_score",
        "max_favorable_excursion_pct",
        "max_adverse_excursion_pct",
        "box_support",
        "box_resistance",
        "box_height_pct",
        "volume_ratio",
        "turnover_rate",
        "ma10_bias_pct",
        "quality_signal_score",
        "quality_stock_score",
        "quality_stock_signal_score",
        "quality_signal_confidence",
        "quality_stock_confidence",
        "quality_stock_signal_confidence",
    )
    return {key: _json_value(row.get(key)) for key in keys if row.get(key) not in (None, "")}


def _build_config_payload(*, name: str, directory: Path, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_name": name,
        "profile_kind": "robustness_regime_aware",
        "diagnostic_dir": str(directory),
        "ranking_config": summary.get("ranking_config") or {},
        "account_config": summary.get("account_config") or {},
        "market_regime_config": summary.get("market_regime_config") or {},
        "market_regime_override_config": summary.get("market_regime_override_config") or {},
        "profile_map": (summary.get("regime_aware") or {}).get("profile_map") or {},
    }


def _build_summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    regime_aware = summary.get("regime_aware") or {}
    return {
        "source_run": summary.get("source_run") or {},
        "baseline_summary": summary.get("baseline_summary") or {},
        "regime_aware_summary": regime_aware.get("summary") or {},
        "monte_carlo": regime_aware.get("monte_carlo") or {},
        "rank_filter_summary": regime_aware.get("rank_filter_summary") or [],
        "rank_score_bins": regime_aware.get("rank_score_bins") or [],
    }


def _rank_mode(summary: dict[str, Any]) -> str:
    rank_mode = str((summary.get("ranking_config") or {}).get("rank_mode") or "unknown")
    return f"regime_aware_{rank_mode}"[:64]


def _profile_specs(values: list[str]) -> list[tuple[str, Path]]:
    raw_specs = values or [f"{name}={path}" for name, path in DEFAULT_PROFILES]
    specs: list[tuple[str, Path]] = []
    for raw in raw_specs:
        if "=" not in raw:
            raise ValueError(f"--profile must be name=path: {raw}")
        name, path = raw.split("=", 1)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError(f"profile name is empty: {raw}")
        directory = Path(path.strip()).expanduser()
        if not directory.is_absolute():
            directory = ROOT_DIR / directory
        specs.append((clean_name, directory.resolve()))
    return specs


def _schedule_id(*, name: str, summary_path: Path) -> str:
    digest = hashlib.sha1(str(summary_path.resolve()).encode("utf-8")).hexdigest()[:14]
    safe_name = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "_")[:24] or "profile"
    return f"brp_{safe_name}_{digest}"[:64]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in row.items()}


def _json_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in {"true", "false"}:
            return text.lower() == "true"
        number = _optional_float(text)
        if number is not None:
            return number
        return value
    return value


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    return int(number) if number is not None else None


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())
