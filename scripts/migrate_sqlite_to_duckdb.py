# -*- coding: utf-8 -*-
"""Copy an existing theme_picker SQLite database into the DuckDB schema."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import Sequence

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.storage import Base, DatabaseManager  # noqa: E402

DEFAULT_SQLITE_PATH = ROOT_DIR / "data" / "stock_analysis.db"
DEFAULT_DUCKDB_PATH = ROOT_DIR / "data" / "stock_analysis.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate local theme_picker data from SQLite to DuckDB")
    parser.add_argument("--sqlite-path", default=str(DEFAULT_SQLITE_PATH), help="Source SQLite database path")
    parser.add_argument("--duckdb-path", default=str(DEFAULT_DUCKDB_PATH), help="Target DuckDB database path")
    parser.add_argument("--overwrite", action="store_true", help="Replace the target DuckDB file if it exists")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Rows copied per executemany batch")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    duckdb_path = Path(args.duckdb_path).expanduser().resolve()
    chunk_size = max(1, int(args.chunk_size or 1000))

    if sqlite_path == duckdb_path:
        raise ValueError(
            "source SQLite path and target DuckDB path must be different; "
            "in-place migration is not supported"
        )
    if not sqlite_path.exists():
        raise FileNotFoundError(f"source SQLite database not found: {sqlite_path}")
    if duckdb_path.exists():
        if not args.overwrite:
            raise FileExistsError(f"target DuckDB database already exists: {duckdb_path}; pass --overwrite to replace it")
        duckdb_path.unlink()

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    manager = DatabaseManager(str(duckdb_path))
    source = sqlite3.connect(str(sqlite_path))
    source.row_factory = sqlite3.Row

    copied: dict[str, int] = {}
    try:
        with manager.engine.begin() as target:
            attached_sqlite = _attach_sqlite_source(target, sqlite_path)
            for table in Base.metadata.sorted_tables:
                table_name = table.name
                if not _sqlite_table_exists(source, table_name):
                    continue
                source_columns = _sqlite_columns(source, table_name)
                model_columns = [column.name for column in table.columns]
                columns = [column for column in model_columns if column in source_columns]
                if not columns:
                    continue
                copied[table_name] = _copy_table(
                    source,
                    target,
                    table_name=table_name,
                    columns=columns,
                    chunk_size=chunk_size,
                    attached_sqlite=attached_sqlite,
                )
            _sync_sequences(target)
    finally:
        source.close()
        manager.close()

    print(
        json.dumps(
            {
                "source": str(sqlite_path),
                "target": str(duckdb_path),
                "tables_copied": len(copied),
                "rows_copied": sum(copied.values()),
                "tables": copied,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "select 1 from sqlite_master where type = 'table' and name = ? limit 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _sqlite_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"pragma table_info({_quote_identifier(table_name)})").fetchall()
    return {str(row["name"]) for row in rows}


def _copy_table(
    source: sqlite3.Connection,
    target: Any,
    *,
    table_name: str,
    columns: list[str],
    chunk_size: int,
    attached_sqlite: bool,
) -> int:
    if attached_sqlite:
        return _copy_table_from_attached_sqlite(source, target, table_name=table_name, columns=columns)

    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    select_sql = f"select {quoted_columns} from {_quote_identifier(table_name)}"
    insert_sql = f"insert into {_quote_identifier(table_name)} ({quoted_columns}) values ({placeholders})"
    cursor = source.execute(select_sql)
    copied = 0
    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            break
        params = [tuple(row[column] for column in columns) for row in rows]
        target.exec_driver_sql(insert_sql, params)
        copied += len(params)
    return copied


def _attach_sqlite_source(target: Any, sqlite_path: Path) -> bool:
    try:
        target.exec_driver_sql("load sqlite")
        target.exec_driver_sql(f"attach '{_quote_string_literal(str(sqlite_path))}' as sqlite_source (type sqlite)")
        return True
    except Exception as exc:
        print(
            f"[migrate] DuckDB sqlite extension unavailable; falling back to Python copy: {exc}",
            file=sys.stderr,
        )
        return False


def _copy_table_from_attached_sqlite(
    source: sqlite3.Connection,
    target: Any,
    *,
    table_name: str,
    columns: list[str],
) -> int:
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    count = source.execute(f"select count(*) from {_quote_identifier(table_name)}").fetchone()[0]
    target.exec_driver_sql(
        f"insert into {_quote_identifier(table_name)} ({quoted_columns}) "
        f"select {quoted_columns} from sqlite_source.{_quote_identifier(table_name)}"
    )
    return int(count or 0)


def _sync_sequences(target: Any) -> None:
    for table in Base.metadata.sorted_tables:
        id_column = table.c.get("id")
        if id_column is None or not isinstance(id_column.default, Sequence):
            continue
        sequence_name = id_column.default.name
        max_id = target.exec_driver_sql(
            f"select coalesce(max(id), 0) from {_quote_identifier(table.name)}"
        ).scalar()
        max_id = int(max_id or 0)
        if max_id <= 0:
            continue
        next_value = max_id + 1
        try:
            target.exec_driver_sql(f"alter sequence {_quote_identifier(sequence_name)} restart with {next_value}")
        except Exception:
            target.exec_driver_sql(f"select max(nextval('{sequence_name}')) from range({max_id})")


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _quote_string_literal(value: str) -> str:
    return str(value).replace("'", "''")


if __name__ == "__main__":
    raise SystemExit(main())
