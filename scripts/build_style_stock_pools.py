# -*- coding: utf-8 -*-
"""Build style-specific A-share stock pools from local backtest data.

The script is intentionally read-mostly: it reads the local Tushare warehouse
tables, optionally enriches names/industries via Tushare stock_basic, then
writes reproducible JSON pools for backtest experiments.
"""

from __future__ import annotations

import argparse
import csv
import duckdb
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Callable, Iterable


CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.data_provider.tushare_fetcher import TushareFetcher
from theme_picker.infrastructure.stock_pool_service import infer_exchange_suffix


DEFAULT_DATABASE_PATH = ROOT_DIR / "data" / "stock_analysis.duckdb"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "backtests" / "style_pools"
DEFAULT_START_DATE = date(2020, 1, 1)
DEFAULT_END_DATE = date(2026, 5, 26)
SQLITE_FILE_HEADER = b"SQLite format 3\x00"
WEB_SEED_CODES = {
    # AI / optical / semiconductor names seen in current public screens and
    # already present in the local warehouse are preferred by the tech pool.
    "300308",
    "300502",
    "688041",
    "688981",
    "603501",
    "002371",
    "002230",
    "300418",
    "688256",
    "688008",
    # High-dividend / lower-volatility anchors commonly used as defensive style
    # examples; final selection still depends on local data metrics.
    "601088",
    "601225",
    "600188",
    "600900",
    "601288",
    "601166",
    "600036",
    "601318",
}


@dataclass
class StockStyleMetrics:
    stock_code: str
    ts_code: str
    stock_name: str | None
    industry: str | None
    market: str | None
    latest_date: str
    row_count: int
    latest_close: float | None
    return_60d_pct: float | None
    return_120d_pct: float | None
    return_250d_pct: float | None
    drawdown_250d_pct: float | None
    volatility_60d_pct: float | None
    range_60d_pct: float | None
    turnover_median_60d: float | None
    atr_median_60d_pct: float | None
    circ_mv_yi: float | None
    latest_style_bucket: str | None
    style_bucket_mode_60d: str | None
    web_seeded: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build style stock pools from local DuckDB data")
    parser.add_argument("--database-path", default=str(DEFAULT_DATABASE_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=DEFAULT_END_DATE.isoformat())
    parser.add_argument("--pool-size", type=int, default=24)
    parser.add_argument(
        "--no-tushare-stock-basic",
        action="store_true",
        help="Skip Tushare stock_basic enrichment and only emit local metric fields",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    args = parse_args()
    database_path = Path(args.database_path)
    output_dir = Path(args.output_dir)
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    pool_size = max(6, int(args.pool_size or 24))

    output_dir.mkdir(parents=True, exist_ok=True)
    names = {} if args.no_tushare_stock_basic else load_stock_basic()
    metrics = load_metrics(database_path, start_date=start_date, end_date=end_date, names=names)
    if not metrics:
        raise RuntimeError("No eligible stock metrics found. Please sync stock_daily_raw/aux first.")

    metrics_path = output_dir / "style_pool_candidates.csv"
    write_metrics_csv(metrics_path, metrics)

    definitions = build_pool_definitions(pool_size)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database_path": str(database_path),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "candidate_count": len(metrics),
        "pool_size": pool_size,
        "pools": [],
    }

    used_by_pool: dict[str, set[str]] = {}
    for pool_id, label, description, selector, ranker in definitions:
        selected = select_pool(metrics, selector=selector, ranker=ranker, limit=pool_size)
        used_by_pool[pool_id] = {item.stock_code for item in selected}
        pool_payload = {
            "name": label,
            "description": description,
            "generated_at": summary["generated_at"],
            "source": {
                "type": "local_duckdb_metrics+tushare_stock_basic",
                "database_path": str(database_path),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "candidate_count": len(metrics),
            },
            "filters": {
                "pool_id": pool_id,
                "pool_size": pool_size,
                "note": "股票池用于回测风格适配，不构成推荐或买卖建议。",
            },
            "stock_codes": [pool_member(item, pool_id) for item in selected],
        }
        path = output_dir / f"{pool_id}.json"
        path.write_text(json.dumps(pool_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary["pools"].append(
            {
                "pool_id": pool_id,
                "path": str(path),
                "name": label,
                "count": len(selected),
                "codes": [item.stock_code for item in selected],
            }
        )

    (output_dir / "style_pool_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def load_stock_basic() -> dict[str, dict[str, str]]:
    fetcher = TushareFetcher()
    if not fetcher.is_available():
        print("[style-pool] Tushare unavailable; continuing without stock_basic names", file=sys.stderr)
        return {}
    df = fetcher.call_api(
        "stock_basic",
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )
    if df is None or df.empty:
        return {}
    records: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        ts_code = str(row.get("ts_code") or "").strip().upper()
        symbol = str(row.get("symbol") or "").strip()
        if not ts_code:
            continue
        records[ts_code] = {
            "stock_code": symbol,
            "stock_name": str(row.get("name") or "").strip() or None,
            "industry": str(row.get("industry") or "").strip() or None,
            "market": str(row.get("market") or "").strip() or None,
        }
    return records


def load_metrics(
    database_path: Path,
    *,
    start_date: date,
    end_date: date,
    names: dict[str, dict[str, str]],
) -> list[StockStyleMetrics]:
    if _is_sqlite_database_file(database_path):
        raise RuntimeError(
            f"database path points to a SQLite database: {database_path}. "
            "Run scripts/migrate_sqlite_to_duckdb.py and use data/stock_analysis.duckdb."
        )
    try:
        con = duckdb.connect(str(database_path), read_only=True)
    except duckdb.Error as exc:
        if _is_duckdb_lock_error(exc):
            raise RuntimeError(
                "DuckDB database is locked by another process. Stop the theme_picker server/import job "
                "that has the database open, or rerun this command after it exits."
            ) from exc
        raise
    try:
        raw_codes = [
            str(row[0]).upper()
            for row in con.execute(
                """
                select ts_code
                from stock_daily_raw
                group by ts_code
                having count(*) >= 180
                   and min(trade_date) <= ?
                   and max(trade_date) >= ?
                order by ts_code
                """,
                ((start_date + timedelta(days=20)).isoformat(), end_date.isoformat()),
            ).fetchall()
        ]
        metrics: list[StockStyleMetrics] = []
        for ts_code in raw_codes:
            rows = _fetchall_dict(
                con,
                """
                select
                  r.trade_date,
                  coalesce(r.close_qfq, r.close) as close_price,
                  r.pre_close,
                  a.turnover_rate,
                  a.turnover_rate_median_20,
                  a.atr_pct_20,
                  a.circ_mv,
                  a.style_bucket
                from stock_daily_raw r
                left join stock_daily_aux a
                  on a.ts_code = r.ts_code and a.trade_date = r.trade_date
                where r.ts_code = ?
                  and r.trade_date between ? and ?
                order by r.trade_date
                """,
                (ts_code, start_date.isoformat(), end_date.isoformat()),
            )
            if len(rows) < 180:
                continue
            item = compute_metrics(ts_code, rows, names.get(ts_code) or {})
            if item is not None:
                metrics.append(item)
        return metrics
    finally:
        con.close()


def _is_sqlite_database_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_FILE_HEADER)) == SQLITE_FILE_HEADER
    except OSError:
        return False


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "could not set lock" in text or "conflicting lock" in text


def _fetchall_dict(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    result = con.execute(sql, params)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def compute_metrics(ts_code: str, rows: list[dict[str, Any]], name_info: dict[str, str]) -> StockStyleMetrics | None:
    closes = [_safe_float(row["close_price"]) for row in rows]
    valid_pairs = [(idx, value) for idx, value in enumerate(closes) if value and value > 0]
    if len(valid_pairs) < 180:
        return None

    latest_idx, latest_close = valid_pairs[-1]
    latest_row = rows[latest_idx]

    def close_n_sessions_ago(n: int) -> float | None:
        if len(valid_pairs) <= n:
            return None
        return valid_pairs[-1 - n][1]

    recent_60 = [value for _, value in valid_pairs[-60:]]
    recent_250 = [value for _, value in valid_pairs[-250:]]
    returns_60 = daily_returns(recent_60)
    style_values = [str(row["style_bucket"] or "").strip() for row in rows[max(0, len(rows) - 60) :]]
    turnover_values = [_safe_float(row["turnover_rate"]) for row in rows[max(0, len(rows) - 60) :]]
    turnover_values = [value for value in turnover_values if value is not None]
    atr_values = [_safe_float(row["atr_pct_20"]) for row in rows[max(0, len(rows) - 60) :]]
    atr_values = [value for value in atr_values if value is not None]

    stock_code = normalize_ts_code(ts_code)
    return StockStyleMetrics(
        stock_code=stock_code,
        ts_code=ts_code,
        stock_name=name_info.get("stock_name"),
        industry=name_info.get("industry"),
        market=name_info.get("market"),
        latest_date=str(latest_row["trade_date"]),
        row_count=len(rows),
        latest_close=round(latest_close, 4),
        return_60d_pct=return_pct(close_n_sessions_ago(60), latest_close),
        return_120d_pct=return_pct(close_n_sessions_ago(120), latest_close),
        return_250d_pct=return_pct(close_n_sessions_ago(250), latest_close),
        drawdown_250d_pct=drawdown_pct(recent_250, latest_close),
        volatility_60d_pct=round(pstdev(returns_60), 4) if len(returns_60) >= 2 else None,
        range_60d_pct=range_pct(recent_60),
        turnover_median_60d=round(median(turnover_values), 4) if turnover_values else None,
        atr_median_60d_pct=round(median(atr_values), 4) if atr_values else None,
        circ_mv_yi=round((_safe_float(latest_row["circ_mv"]) or 0.0) / 10000.0, 2)
        if _safe_float(latest_row["circ_mv"]) is not None
        else None,
        latest_style_bucket=str(latest_row["style_bucket"] or "").strip() or None,
        style_bucket_mode_60d=mode_text(style_values),
        web_seeded=stock_code in WEB_SEED_CODES,
    )


def build_pool_definitions(pool_size: int):
    tech_industries = ("半导体", "通信", "软件", "元器件", "电器仪表", "互联网")
    defensive_industries = ("银行", "保险", "煤炭", "石油", "电力", "白酒", "家用电器", "水运")

    return [
        (
            "style_high_beta_growth",
            "高弹性成长池",
            "高波动、高换手、趋势不弱，主要测试高 beta 箱体和突破规则。",
            lambda x: (x.latest_style_bucket == "high_beta" or value(x.volatility_60d_pct) >= 3.0)
            and value(x.turnover_median_60d) >= 2.0
            and value(x.return_120d_pct) >= -5.0,
            lambda x: (
                value(x.return_120d_pct) * 1.5
                + value(x.return_60d_pct)
                + value(x.volatility_60d_pct) * 5
                + (8 if x.web_seeded else 0)
            ),
        ),
        (
            "style_balanced_trend",
            "均衡趋势池",
            "中等波动、120/250 日趋势较好，测试普通趋势箱体的稳定性。",
            lambda x: (x.latest_style_bucket == "balanced_trend" or x.style_bucket_mode_60d == "balanced_trend")
            and value(x.return_120d_pct) > 0
            and value(x.drawdown_250d_pct) > -30.0
            and 1.0 <= value(x.turnover_median_60d) <= 8.0,
            lambda x: value(x.return_250d_pct) + value(x.return_120d_pct) * 1.2 - abs(value(x.drawdown_250d_pct)) * 0.4,
        ),
        (
            "style_slow_large_value",
            "低波大盘池",
            "大市值、低换手、低波动，近似高股息/防御风格，测试箱体策略是否需要更宽松节奏。",
            lambda x: (x.latest_style_bucket == "slow_large" or value(x.circ_mv_yi) >= 500.0)
            and value(x.volatility_60d_pct) <= 2.5
            and value(x.turnover_median_60d) <= 3.0,
            lambda x: (
                value(x.circ_mv_yi) * 0.02
                - value(x.volatility_60d_pct) * 8
                - value(x.turnover_median_60d)
                + (8 if contains_any(x.industry, defensive_industries) else 0)
                + (6 if x.web_seeded else 0)
            ),
        ),
        (
            "style_box_compression",
            "箱体压缩池",
            "60 日区间收敛、波动不高、趋势不极端，测试最贴近箱体原型的样本。",
            lambda x: value(x.range_60d_pct) <= 24.0
            and abs(value(x.return_60d_pct)) <= 12.0
            and value(x.volatility_60d_pct) <= 2.6
            and value(x.turnover_median_60d) >= 0.5,
            lambda x: -value(x.range_60d_pct) * 2 - abs(value(x.return_60d_pct)) + value(x.turnover_median_60d),
        ),
        (
            "style_pullback_repair",
            "回踩修复池",
            "中期趋势仍可，但从 250 日高点回撤较深，测试 pullback 失败退出和冷却规则。",
            lambda x: value(x.return_250d_pct) > -20.0
            and -45.0 <= value(x.drawdown_250d_pct) <= -12.0
            and value(x.return_60d_pct) > -18.0
            and value(x.turnover_median_60d) >= 0.8,
            lambda x: value(x.return_60d_pct) * 1.5 - abs(value(x.drawdown_250d_pct) + 22.0) + value(x.turnover_median_60d),
        ),
        (
            "style_ai_semiconductor_web",
            "AI半导体网络种子池",
            "网络检索确认的 AI、光模块、半导体主线作风格锚点，再用本地动量和换手排序。",
            lambda x: x.web_seeded or contains_any(x.industry, tech_industries),
            lambda x: (
                (20 if x.web_seeded else 0)
                + value(x.return_120d_pct) * 1.2
                + value(x.turnover_median_60d) * 2
                + value(x.volatility_60d_pct) * 2
            ),
        ),
    ]


def select_pool(
    metrics: list[StockStyleMetrics],
    *,
    selector: Callable[[StockStyleMetrics], bool],
    ranker: Callable[[StockStyleMetrics], float],
    limit: int,
) -> list[StockStyleMetrics]:
    selected = [item for item in metrics if selector(item)]
    selected.sort(key=ranker, reverse=True)
    return selected[:limit]


def pool_member(item: StockStyleMetrics, pool_id: str) -> dict[str, object]:
    return {
        "stock_code": item.stock_code,
        "stock_name": item.stock_name,
        "ts_code": item.ts_code,
        "style_pool": pool_id,
        "industry": item.industry,
        "market": item.market,
        "metrics": {
            "latest_date": item.latest_date,
            "return_60d_pct": item.return_60d_pct,
            "return_120d_pct": item.return_120d_pct,
            "return_250d_pct": item.return_250d_pct,
            "drawdown_250d_pct": item.drawdown_250d_pct,
            "volatility_60d_pct": item.volatility_60d_pct,
            "range_60d_pct": item.range_60d_pct,
            "turnover_median_60d": item.turnover_median_60d,
            "atr_median_60d_pct": item.atr_median_60d_pct,
            "circ_mv_yi": item.circ_mv_yi,
            "latest_style_bucket": item.latest_style_bucket,
            "style_bucket_mode_60d": item.style_bucket_mode_60d,
            "web_seeded": item.web_seeded,
        },
    }


def write_metrics_csv(path: Path, metrics: list[StockStyleMetrics]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(metrics[0]).keys()))
        writer.writeheader()
        for item in metrics:
            writer.writerow(asdict(item))


def normalize_ts_code(ts_code: str) -> str:
    text = str(ts_code or "").strip().upper()
    if "." in text:
        return text.split(".", 1)[0]
    if text.isdigit() and len(text) == 6:
        return text
    suffix = infer_exchange_suffix(text)
    return text.replace(suffix or "", "")


def daily_returns(closes: list[float]) -> list[float]:
    values: list[float] = []
    for prev, current in zip(closes, closes[1:]):
        if prev and prev > 0:
            values.append((current - prev) / prev * 100.0)
    return values


def return_pct(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start <= 0:
        return None
    return round((end - start) / start * 100.0, 4)


def drawdown_pct(closes: list[float], latest: float | None) -> float | None:
    if latest is None or not closes:
        return None
    high = max(closes)
    if high <= 0:
        return None
    return round((latest - high) / high * 100.0, 4)


def range_pct(closes: list[float]) -> float | None:
    if not closes:
        return None
    low = min(closes)
    high = max(closes)
    if low <= 0:
        return None
    return round((high - low) / low * 100.0, 4)


def mode_text(values: Iterable[str]) -> str | None:
    counts: dict[str, int] = {}
    for value_ in values:
        if not value_:
            continue
        counts[value_] = counts.get(value_, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def contains_any(value_: str | None, needles: Iterable[str]) -> bool:
    text = str(value_ or "")
    return any(needle in text for needle in needles)


def value(value_: float | int | None) -> float:
    if value_ is None:
        return 0.0
    try:
        numeric = float(value_)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numeric) or math.isinf(numeric):
        return 0.0
    return numeric


def _safe_float(value_: object) -> float | None:
    if value_ is None:
        return None
    text = str(value_).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
