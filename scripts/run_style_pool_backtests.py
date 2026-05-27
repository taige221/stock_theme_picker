# -*- coding: utf-8 -*-
"""Run style-pool backtest experiments across strategy profiles."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean


CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent

DEFAULT_POOL_DIR = ROOT_DIR / "data" / "backtests" / "style_pools"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "data" / "backtests" / "style_profile_runs"
DEFAULT_PROFILES = {
    "v53": ROOT_DIR / "data" / "backtests" / "params_turnover_loose_v53.json",
    "v57": ROOT_DIR / "data" / "backtests" / "params_turnover_loose_v57.json",
    "v60": ROOT_DIR / "data" / "backtests" / "params_turnover_loose_v60.json",
    "v64": ROOT_DIR / "data" / "backtests" / "params_turnover_loose_v64.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run style-pool profile backtests")
    parser.add_argument("--pool-dir", default=str(DEFAULT_POOL_DIR))
    parser.add_argument("--pool", action="append", help="Specific pool JSON path or pool id; can repeat")
    parser.add_argument("--profiles", default="v53,v57,v60,v64")
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2026-05-21")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--price-adjustment", default="qfq", choices=("raw", "qfq"))
    parser.add_argument("--trading-constraints", default="daily_limits", choices=("legacy_pct", "daily_limits"))
    parser.add_argument("--import-db", action="store_true")
    parser.add_argument(
        "--import-equity-mode",
        default="portfolio_only",
        choices=("portfolio_only", "traded_daily", "all_daily"),
    )
    parser.add_argument("--reuse-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pool_dir = Path(args.pool_dir)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    pools = resolve_pools(pool_dir, args.pool)
    profiles = resolve_profiles(args.profiles)
    if not pools:
        raise ValueError(f"No style pool JSON files found in {pool_dir}")
    if not profiles:
        raise ValueError("No profiles resolved")

    summary_rows = []
    for pool_path in pools:
        pool_id = pool_path.stem
        for profile_id, params_path in profiles:
            run_dir = output_root / f"{pool_id}_{profile_id}"
            summary_path = run_dir / "summary.json"
            if args.reuse_existing and summary_path.exists():
                print(f"[style-run] reuse pool={pool_id} profile={profile_id} path={summary_path}")
            else:
                run_backtest(
                    pool_path=pool_path,
                    profile_id=profile_id,
                    params_path=params_path,
                    run_dir=run_dir,
                    args=args,
                )
            if summary_path.exists():
                summary_rows.append(summarize_run(pool_id, profile_id, pool_path, params_path, summary_path))

    summary_rows.sort(key=lambda row: (row["pool_id"], -float(row["aggregate_return_pct"] or 0.0), row["profile_id"]))
    write_summary(output_root, summary_rows)
    print(json.dumps({"runs": len(summary_rows), "output_root": str(output_root)}, ensure_ascii=False, indent=2))
    return 0


def resolve_pools(pool_dir: Path, requested: list[str] | None) -> list[Path]:
    if not requested:
        return sorted(path for path in pool_dir.glob("style_*.json") if path.name != "style_pool_summary.json")
    pools: list[Path] = []
    for value in requested:
        candidate = Path(value)
        if not candidate.exists():
            candidate = pool_dir / f"{value}.json"
        if not candidate.exists():
            raise FileNotFoundError(value)
        pools.append(candidate)
    return pools


def resolve_profiles(value: str) -> list[tuple[str, Path]]:
    profiles: list[tuple[str, Path]] = []
    for raw in str(value or "").split(","):
        item = raw.strip()
        if not item:
            continue
        if "=" in item:
            profile_id, path_text = item.split("=", 1)
            path = Path(path_text.strip())
        else:
            profile_id = item
            path = DEFAULT_PROFILES.get(profile_id)
            if path is None:
                raise ValueError(f"Unknown profile {profile_id}; use id=/path/to/params.json")
        if not path.exists():
            raise FileNotFoundError(str(path))
        profiles.append((profile_id.strip(), path))
    return profiles


def run_backtest(
    *,
    pool_path: Path,
    profile_id: str,
    params_path: Path,
    run_dir: Path,
    args: argparse.Namespace,
) -> None:
    command = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "run_backtest_batch.py"),
        "--stock-codes",
        str(pool_path),
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--strategy",
        "a_share_box",
        "--price-adjustment",
        args.price_adjustment,
        "--trading-constraints",
        args.trading_constraints,
        "--params-file",
        str(params_path),
        "--output-dir",
        str(run_dir),
    ]
    if args.import_db:
        command.extend(
            [
                "--import-db",
                "--import-stock-pool",
                str(pool_path),
                "--import-equity-mode",
                args.import_equity_mode,
            ]
        )

    print(f"[style-run] start pool={pool_path.stem} profile={profile_id}")
    completed = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True)
    if completed.returncode != 0:
        print(completed.stdout[-4000:])
        print(completed.stderr[-4000:], file=sys.stderr)
        raise RuntimeError(f"Backtest failed pool={pool_path.stem} profile={profile_id}")
    print(f"[style-run] done pool={pool_path.stem} profile={profile_id}")


def summarize_run(pool_id: str, profile_id: str, pool_path: Path, params_path: Path, summary_path: Path) -> dict[str, object]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    aggregate = summary.get("aggregate") or {}
    trades = []
    signal_stats: dict[str, dict[str, float]] = {}
    for item in summary.get("results") or []:
        result_path = Path(str(item.get("result_path") or ""))
        if not result_path.is_absolute():
            result_path = ROOT_DIR / result_path
        if not result_path.exists():
            continue
        detail = json.loads(result_path.read_text(encoding="utf-8"))
        for trade in detail.get("trades") or []:
            pnl = float(trade.get("net_pnl") or trade.get("gross_pnl") or 0.0)
            return_pct = trade.get("return_pct")
            signal = str(trade.get("entry_signal_reason") or "unknown")
            trades.append({"pnl": pnl, "return_pct": return_pct, "signal": signal})
            bucket = signal_stats.setdefault(signal, {"count": 0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0})
            bucket["count"] += 1
            if pnl > 0:
                bucket["wins"] += 1
                bucket["gross_win"] += pnl
            elif pnl < 0:
                bucket["gross_loss"] += abs(pnl)

    gross_win = sum(item["pnl"] for item in trades if item["pnl"] > 0)
    gross_loss = sum(abs(item["pnl"]) for item in trades if item["pnl"] < 0)
    wins = sum(1 for item in trades if item["pnl"] > 0)
    returns = [float(item["return_pct"]) for item in trades if item.get("return_pct") is not None]
    trade_count = len(trades)
    signal_summary = {
        signal: {
            "count": int(stats["count"]),
            "win_rate_pct": round(stats["wins"] / stats["count"] * 100.0, 2) if stats["count"] else 0.0,
            "profit_factor": round(stats["gross_win"] / stats["gross_loss"], 4) if stats["gross_loss"] else None,
        }
        for signal, stats in sorted(signal_stats.items())
    }
    return {
        "pool_id": pool_id,
        "profile_id": profile_id,
        "pool_path": str(pool_path),
        "params_path": str(params_path),
        "summary_path": str(summary_path),
        "ok_symbols": aggregate.get("ok_symbols"),
        "total_symbols": aggregate.get("total_symbols"),
        "profitable_symbols": aggregate.get("profitable_symbols"),
        "losing_symbols": aggregate.get("losing_symbols"),
        "flat_symbols": aggregate.get("flat_symbols"),
        "aggregate_return_pct": aggregate.get("aggregate_return_pct"),
        "total_pnl": aggregate.get("total_pnl"),
        "summary_trade_count": aggregate.get("total_trade_count"),
        "trade_count": trade_count,
        "trade_win_rate_pct": round(wins / trade_count * 100.0, 2) if trade_count else 0.0,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None,
        "avg_trade_return_pct": round(mean(returns), 4) if returns else 0.0,
        "signal_summary": signal_summary,
    }


def write_summary(output_root: Path, rows: list[dict[str, object]]) -> None:
    generated_at = datetime.now().isoformat(timespec="seconds")
    payload = {"generated_at": generated_at, "runs": rows}
    (output_root / "style_profile_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fieldnames = [
        "pool_id",
        "profile_id",
        "aggregate_return_pct",
        "total_pnl",
        "trade_count",
        "trade_win_rate_pct",
        "profit_factor",
        "avg_trade_return_pct",
        "profitable_symbols",
        "losing_symbols",
        "flat_symbols",
        "summary_path",
    ]
    with (output_root / "style_profile_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


if __name__ == "__main__":
    raise SystemExit(main())
