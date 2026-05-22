# -*- coding: utf-8 -*-
"""Populate stock_daily cache before running read-only backtests."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.infrastructure.daily_bar_service import get_daily_bar_resolver
from theme_picker.infrastructure.stock_pool_service import canonicalize_stock_code

DEFAULT_CHUNK_DAYS = 2000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync daily bars into stock_daily cache")
    parser.add_argument(
        "--stock-codes",
        required=True,
        help="Comma-separated stock codes, such as 000001.SZ,159995.SZ",
    )
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD")
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=DEFAULT_CHUNK_DAYS,
        help="Calendar-day chunk size used to avoid single-fetch bar limits",
    )
    parser.add_argument(
        "--without-proxy",
        action="store_true",
        help="Disable proxy env while fetching daily bars",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_stock_codes(value: str) -> list[str]:
    items = []
    for raw in str(value or "").split(","):
        code = canonicalize_stock_code(raw)
        if code and code not in items:
            items.append(code)
    if not items:
        raise ValueError("至少提供一个有效的 stock code")
    return items


def iter_date_chunks(*, start_date: date, end_date: date, chunk_days: int):
    normalized_chunk_days = max(30, int(chunk_days or DEFAULT_CHUNK_DAYS))
    current = start_date
    while current <= end_date:
        chunk_end = min(end_date, current + timedelta(days=normalized_chunk_days - 1))
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def main() -> int:
    args = parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if end_date < start_date:
        raise ValueError("end_date 不能早于 start_date")

    stock_codes = parse_stock_codes(args.stock_codes)
    resolver = get_daily_bar_resolver()
    total_chunks = 0

    for stock_code in stock_codes:
        print(f"[sync] stock_code={stock_code}")
        for chunk_start, chunk_end in iter_date_chunks(
            start_date=start_date,
            end_date=end_date,
            chunk_days=args.chunk_days,
        ):
            result = resolver.resolve_daily_bars(
                stock_code,
                start_date=chunk_start,
                end_date=chunk_end,
                bars=240,
                minimum_rows=1,
                allow_stale_fallback=False,
                without_proxy=bool(args.without_proxy),
            )
            total_chunks += 1
            print(
                "[sync] chunk=%s~%s cache_status=%s rows=%s source=%s latest=%s"
                % (
                    chunk_start.isoformat(),
                    chunk_end.isoformat(),
                    result.cache_status,
                    len(result.frame),
                    result.data_source,
                    result.latest_trade_date.isoformat() if result.latest_trade_date else None,
                )
            )

    print(f"[sync] completed stocks={len(stock_codes)} chunks={total_chunks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
