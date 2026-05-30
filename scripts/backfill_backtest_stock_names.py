# -*- coding: utf-8 -*-
"""Backfill stock names for imported strategy backtest rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from theme_picker.data.stock_index_loader import get_stock_name_index_map
    from theme_picker.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
    from theme_picker.data_provider.tushare_fetcher import TushareFetcher
except ModuleNotFoundError:
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from src.data.stock_index_loader import get_stock_name_index_map  # type: ignore[no-redef]
    from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name  # type: ignore[no-redef]
    from src.data_provider.tushare_fetcher import TushareFetcher  # type: ignore[no-redef]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill stock names for an imported backtest run")
    parser.add_argument("--run-id", required=True, help="strategy_backtest_run.run_id to backfill")
    parser.add_argument("--database-path", default=str(ROOT_DIR / "data" / "stock_analysis.duckdb"))
    parser.add_argument("--no-tushare", action="store_true", help="Only use local mappings and style-pool files")
    parser.add_argument("--dry-run", action="store_true", help="Print coverage without writing DB")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.database_path)
    name_map = _load_name_map(use_tushare=not args.no_tushare)
    result = backfill_run_stock_names(
        db_path=db_path,
        run_id=str(args.run_id).strip(),
        name_map=name_map,
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def backfill_run_stock_names(
    *,
    db_path: Path,
    run_id: str,
    name_map: dict[str, str],
    dry_run: bool = False,
) -> dict[str, Any]:
    if not run_id:
        raise ValueError("--run-id is required")
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    con = duckdb.connect(str(db_path), read_only=dry_run)
    try:
        run_row = con.execute(
            """
            select run_id, strategy, run_name, stock_pool_id
            from strategy_backtest_run
            where run_id = ?
            """,
            [run_id],
        ).fetchone()
        if run_row is None:
            raise FileNotFoundError(f"backtest run not found: {run_id}")

        codes = [
            _normalize_code(row[0])
            for row in con.execute(
                """
                select distinct stock_code
                from strategy_backtest_symbol_result
                where run_id = ?
                order by stock_code
                """,
                [run_id],
            ).fetchall()
        ]
        codes = [code for code in codes if code]
        missing = [code for code in codes if not name_map.get(code)]
        before = _named_counts(con, run_id=run_id, pool_id=run_row[3])

        if dry_run:
            return {
                "status": "dry_run",
                "run_id": run_id,
                "strategy": run_row[1],
                "run_name": run_row[2],
                "pool_id": run_row[3],
                "symbol_count": len(codes),
                "mapped_symbol_count": len(codes) - len(missing),
                "missing_symbol_count": len(missing),
                "missing_symbols": missing,
                "before": before,
            }

        if missing:
            raise RuntimeError(f"stock names missing for {len(missing)} symbols: {missing[:30]}")

        con.execute("create temporary table tmp_backtest_stock_name_map(stock_code varchar, stock_name varchar)")
        con.executemany(
            "insert into tmp_backtest_stock_name_map values (?, ?)",
            [(code, name_map[code]) for code in codes],
        )

        _update_run_table(
            con,
            table_name="strategy_backtest_symbol_result",
            run_id=run_id,
        )
        _update_run_table(
            con,
            table_name="strategy_backtest_trade",
            run_id=run_id,
        )
        _update_run_table(
            con,
            table_name="strategy_backtest_portfolio_candidate",
            run_id=run_id,
        )
        if run_row[3]:
            con.execute(
                """
                update strategy_backtest_stock_pool_member as target
                set stock_name = names.stock_name
                from tmp_backtest_stock_name_map as names
                where target.pool_id = ?
                  and target.stock_code = names.stock_code
                  and (target.stock_name is null or target.stock_name = '')
                """,
                [run_row[3]],
            )

        after = _named_counts(con, run_id=run_id, pool_id=run_row[3])
        sample = con.execute(
            """
            select stock_code, stock_name
            from strategy_backtest_symbol_result
            where run_id = ?
            order by stock_code
            limit 12
            """,
            [run_id],
        ).fetchall()
        return {
            "status": "finished",
            "run_id": run_id,
            "strategy": run_row[1],
            "run_name": run_row[2],
            "pool_id": run_row[3],
            "symbol_count": len(codes),
            "before": before,
            "after": after,
            "sample": sample,
        }
    finally:
        con.close()


def _load_name_map(*, use_tushare: bool) -> dict[str, str]:
    names: dict[str, str] = {}
    for code, name in STOCK_NAME_MAP.items():
        _set_name(names, code, name)

    for code, name in get_stock_name_index_map().items():
        _set_name(names, code, name)

    for path in sorted((ROOT_DIR / "data" / "backtests" / "style_pools").glob("style_*.json")):
        payload = _read_json(path)
        for item in payload.get("stock_codes") or []:
            if isinstance(item, dict):
                _set_name(names, item.get("stock_code"), item.get("stock_name"))

    if use_tushare:
        names.update(_load_tushare_stock_basic_names())
    return names


def _load_tushare_stock_basic_names() -> dict[str, str]:
    fetcher = TushareFetcher()
    if not fetcher.is_available():
        return {}
    df = fetcher.call_api(
        "stock_basic",
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )
    if df is None or df.empty:
        return {}

    names: dict[str, str] = {}
    for _, row in df.iterrows():
        _set_name(names, row.get("symbol"), row.get("name"))
    return names


def _named_counts(con: duckdb.DuckDBPyConnection, *, run_id: str, pool_id: str | None) -> dict[str, int | None]:
    return {
        "symbol_result": _count_named(con, "strategy_backtest_symbol_result", "run_id", run_id),
        "trade": _count_named(con, "strategy_backtest_trade", "run_id", run_id),
        "portfolio_candidate": _count_named(con, "strategy_backtest_portfolio_candidate", "run_id", run_id),
        "stock_pool_member": _count_named(con, "strategy_backtest_stock_pool_member", "pool_id", pool_id)
        if pool_id
        else None,
    }


def _count_named(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    key_column: str,
    key_value: str | None,
) -> int:
    if not key_value:
        return 0
    return int(
        con.execute(
            f"""
            select count(*)
            from {table_name}
            where {key_column} = ?
              and stock_name is not null
              and stock_name <> ''
            """,
            [key_value],
        ).fetchone()[0]
    )


def _update_run_table(con: duckdb.DuckDBPyConnection, *, table_name: str, run_id: str) -> None:
    con.execute(
        f"""
        update {table_name} as target
        set stock_name = names.stock_name
        from tmp_backtest_stock_name_map as names
        where target.run_id = ?
          and target.stock_code = names.stock_code
          and (target.stock_name is null or target.stock_name = '')
        """,
        [run_id],
    )


def _set_name(names: dict[str, str], code: object, name: object) -> None:
    normalized_code = _normalize_code(code)
    normalized_name = str(name or "").strip()
    if normalized_code and is_meaningful_stock_name(normalized_name, normalized_code):
        names[normalized_code] = normalized_name


def _normalize_code(code: object) -> str:
    raw = str(code or "").strip().upper()
    if not raw:
        return ""
    if "." in raw:
        raw = raw.split(".", 1)[0]
    if raw.startswith(("SH", "SZ", "BJ")):
        raw = raw[2:]
    if raw.isdigit():
        return raw.zfill(6)
    return raw


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
