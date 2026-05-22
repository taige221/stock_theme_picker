# -*- coding: utf-8 -*-
"""Sync 2000-point Tushare historical warehouse tables into the local SQLite DB."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import sys
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.data_provider.tushare_fetcher import TushareFetcher
from theme_picker.infrastructure.persistence import get_theme_picker_db

DEFAULT_CHUNK_DAYS = 1200
DEFAULT_SECTIONS = ("calendar", "raw", "aux", "corporate")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync 2000-point Tushare historical warehouse tables")
    parser.add_argument("--ts-codes", help="Comma-separated ts_code values, such as 000001.SZ,600519.SH")
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD")
    parser.add_argument(
        "--sections",
        default="all",
        help="Comma-separated subset of calendar,raw,aux,corporate. Default: all",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=DEFAULT_CHUNK_DAYS,
        help="Calendar-day chunk size for daily/raw/aux sync",
    )
    parser.add_argument(
        "--exchange",
        default="SSE",
        help="Trade calendar exchange, default SSE",
    )
    parser.add_argument(
        "--dividend-date-field",
        default="ex_date",
        choices=("ex_date", "record_date", "ann_date", "imp_ann_date"),
        help="Dividend query key used for per-day event sync",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_sections(value: str) -> list[str]:
    raw = str(value or "all").strip().lower()
    if raw in {"", "all"}:
        return list(DEFAULT_SECTIONS)
    items = []
    for item in raw.split(","):
        normalized = item.strip().lower()
        if normalized and normalized not in items:
            items.append(normalized)
    invalid = [item for item in items if item not in DEFAULT_SECTIONS]
    if invalid:
        raise ValueError(f"Unsupported sections: {','.join(invalid)}")
    return items


def iter_date_chunks(*, start_date: date, end_date: date, chunk_days: int):
    normalized_chunk_days = max(30, int(chunk_days or DEFAULT_CHUNK_DAYS))
    current = start_date
    while current <= end_date:
        chunk_end = min(end_date, current + timedelta(days=normalized_chunk_days - 1))
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def iter_calendar_days(*, start_date: date, end_date: date) -> Iterable[str]:
    current = start_date
    while current <= end_date:
        yield current.strftime("%Y%m%d")
        current += timedelta(days=1)


def normalize_ts_codes(fetcher: TushareFetcher, value: str | None) -> list[str]:
    items: list[str] = []
    for raw in str(value or "").split(","):
        code = str(raw or "").strip()
        if not code:
            continue
        ts_code = fetcher.convert_stock_code(code)
        if ts_code not in items:
            items.append(ts_code)
    return items


def sync_trade_calendar(
    *,
    fetcher: TushareFetcher,
    db,
    exchange: str,
    start_date: date,
    end_date: date,
    sync_batch_id: str,
) -> pd.DataFrame:
    df = fetcher.call_api(
        "trade_cal",
        exchange=exchange,
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["exchange", "cal_date", "is_open", "pretrade_date"])

    rows = []
    ingested_at = datetime.now()
    for _, row in df.iterrows():
        rows.append(
            {
                "exchange": row.get("exchange") or exchange,
                "cal_date": _normalize_yyyymmdd(row.get("cal_date")),
                "is_open": int(row.get("is_open") or 0),
                "pretrade_date": _normalize_yyyymmdd(row.get("pretrade_date")),
                "sync_batch_id": sync_batch_id,
                "data_source": "tushare.trade_cal",
                "ingested_at": ingested_at,
            }
        )
    db.save_trade_calendar_rows(rows)
    print(f"[sync] trade_calendar rows={len(rows)} exchange={exchange}")
    return df


def sync_stock_daily_raw(
    *,
    fetcher: TushareFetcher,
    db,
    ts_codes: Sequence[str],
    start_date: date,
    end_date: date,
    chunk_days: int,
    sync_batch_id: str,
) -> int:
    total_rows = 0
    for ts_code in ts_codes:
        for chunk_start, chunk_end in iter_date_chunks(start_date=start_date, end_date=end_date, chunk_days=chunk_days):
            daily_df = fetcher.call_api(
                "daily",
                ts_code=ts_code,
                start_date=chunk_start.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
            )
            adj_df = fetcher.call_api(
                "adj_factor",
                ts_code=ts_code,
                start_date=chunk_start.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
                fields="ts_code,trade_date,adj_factor",
            )
            merged = _merge_by_code_date(daily_df, adj_df)
            if merged.empty:
                print(f"[sync] raw empty ts_code={ts_code} chunk={chunk_start}~{chunk_end}")
                continue

            rows = []
            ingested_at = datetime.now()
            for _, row in merged.iterrows():
                amount = _safe_float(row.get("amount"))
                rows.append(
                    {
                        "ts_code": row.get("ts_code"),
                        "trade_date": _normalize_yyyymmdd(row.get("trade_date")),
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "close": _safe_float(row.get("close")),
                        "pre_close": _safe_float(row.get("pre_close")),
                        "vol": _safe_float(row.get("vol")),
                        "amount": amount * 1000.0 if amount is not None else None,
                        "adj_factor": _safe_float(row.get("adj_factor")),
                        "sync_batch_id": sync_batch_id,
                        "data_source": "tushare.daily+adj_factor",
                        "ingested_at": ingested_at,
                    }
                )
            inserted = db.save_stock_daily_raw_rows(rows)
            total_rows += inserted
            print(f"[sync] raw ts_code={ts_code} chunk={chunk_start}~{chunk_end} rows={inserted}")
        qfq_updated = db.recompute_stock_daily_raw_qfq(ts_code)
        print(f"[sync] raw ts_code={ts_code} recomputed_qfq_rows={qfq_updated}")
    return total_rows


def sync_stock_daily_aux(
    *,
    fetcher: TushareFetcher,
    db,
    ts_codes: Sequence[str],
    start_date: date,
    end_date: date,
    chunk_days: int,
    sync_batch_id: str,
) -> int:
    total_rows = 0
    for ts_code in ts_codes:
        for chunk_start, chunk_end in iter_date_chunks(start_date=start_date, end_date=end_date, chunk_days=chunk_days):
            basic_df = fetcher.call_api(
                "daily_basic",
                ts_code=ts_code,
                start_date=chunk_start.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
                fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,float_share,free_share,total_share,circ_mv,total_mv",
            )
            limit_df = fetcher.call_api(
                "stk_limit",
                ts_code=ts_code,
                start_date=chunk_start.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
                fields="ts_code,trade_date,up_limit,down_limit",
            )
            suspend_df = fetcher.call_api(
                "suspend_d",
                ts_code=ts_code,
                start_date=chunk_start.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
                fields="ts_code,trade_date,suspend_type",
            )
            merged = _merge_by_code_date(basic_df, limit_df)
            merged = _merge_by_code_date(merged, suspend_df)
            if merged.empty:
                print(f"[sync] aux empty ts_code={ts_code} chunk={chunk_start}~{chunk_end}")
                continue

            rows = []
            ingested_at = datetime.now()
            for _, row in merged.iterrows():
                suspend_type = str(row.get("suspend_type") or "").strip().upper() or None
                is_suspended = 1 if suspend_type == "S" else 0
                rows.append(
                    {
                        "ts_code": row.get("ts_code"),
                        "trade_date": _normalize_yyyymmdd(row.get("trade_date")),
                        "turnover_rate": _safe_float(row.get("turnover_rate")),
                        "turnover_rate_f": _safe_float(row.get("turnover_rate_f")),
                        "volume_ratio": _safe_float(row.get("volume_ratio")),
                        "float_share": _safe_float(row.get("float_share")),
                        "free_share": _safe_float(row.get("free_share")),
                        "total_share": _safe_float(row.get("total_share")),
                        "circ_mv": _safe_float(row.get("circ_mv")),
                        "total_mv": _safe_float(row.get("total_mv")),
                        "up_limit": _safe_float(row.get("up_limit")),
                        "down_limit": _safe_float(row.get("down_limit")),
                        "is_suspended": is_suspended,
                        "suspend_type": suspend_type,
                        "sync_batch_id": sync_batch_id,
                        "data_source": "tushare.daily_basic+stk_limit+suspend_d",
                        "ingested_at": ingested_at,
                    }
                )
            inserted = db.save_stock_daily_aux_rows(rows)
            total_rows += inserted
            print(f"[sync] aux ts_code={ts_code} chunk={chunk_start}~{chunk_end} rows={inserted}")
    return total_rows


def sync_stock_corporate_actions(
    *,
    fetcher: TushareFetcher,
    db,
    ts_codes: Sequence[str],
    trade_calendar_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    date_field: str,
    sync_batch_id: str,
) -> int:
    uses_trade_days = date_field in {"ex_date", "record_date"}
    if uses_trade_days and (trade_calendar_df is None or trade_calendar_df.empty):
        print("[sync] corporate skipped because trade_calendar is empty")
        return 0

    if uses_trade_days:
        query_days = sorted(
            {
                str(value)
                for value in trade_calendar_df.loc[trade_calendar_df["is_open"].astype(int) == 1, "cal_date"].astype(str).tolist()
                if str(value).strip()
            }
        )
    else:
        query_days = list(iter_calendar_days(start_date=start_date, end_date=end_date))

    ts_code_set = {str(code).strip().upper() for code in ts_codes}
    total_rows = 0
    for query_day in query_days:
        payload = {date_field: query_day}
        df = fetcher.call_api(
            "dividend",
            fields="ts_code,ann_date,div_proc,stk_div,cash_div,cash_div_tax,record_date,ex_date,pay_date,imp_ann_date",
            **payload,
        )
        if df is None or df.empty:
            continue
        filtered = df[df["ts_code"].astype(str).str.upper().isin(ts_code_set)].copy()
        if filtered.empty:
            continue

        rows = []
        ingested_at = datetime.now()
        for _, row in filtered.iterrows():
            ts_code = str(row.get("ts_code") or "").strip().upper()
            ann_date = _normalize_yyyymmdd(row.get("ann_date"))
            record_date = _normalize_yyyymmdd(row.get("record_date"))
            ex_date = _normalize_yyyymmdd(row.get("ex_date"))
            pay_date = _normalize_yyyymmdd(row.get("pay_date"))
            div_proc = str(row.get("div_proc") or "").strip() or None
            action_key = "|".join(
                [
                    ts_code,
                    ann_date.isoformat() if ann_date else "",
                    record_date.isoformat() if record_date else "",
                    ex_date.isoformat() if ex_date else "",
                    div_proc or "",
                ]
            )
            rows.append(
                {
                    "action_key": action_key,
                    "ts_code": ts_code,
                    "ann_date": ann_date,
                    "record_date": record_date,
                    "ex_date": ex_date,
                    "pay_date": pay_date,
                    "div_proc": div_proc,
                    "stk_div": _safe_float(row.get("stk_div")),
                    "cash_div": _safe_float(row.get("cash_div")),
                    "cash_div_tax": _safe_float(row.get("cash_div_tax")),
                    "sync_batch_id": sync_batch_id,
                    "data_source": f"tushare.dividend[{date_field}]",
                    "ingested_at": ingested_at,
                }
            )
        inserted = db.save_stock_corporate_action_rows(rows)
        total_rows += inserted
        print(f"[sync] corporate {date_field}={query_day} rows={inserted}")
    return total_rows


def _merge_by_code_date(left: pd.DataFrame | None, right: pd.DataFrame | None) -> pd.DataFrame:
    if left is None or left.empty:
        return right.copy() if isinstance(right, pd.DataFrame) else pd.DataFrame()
    if right is None or right.empty:
        return left.copy()
    left_working = left.copy()
    right_working = right.copy()
    return left_working.merge(right_working, on=["ts_code", "trade_date"], how="outer")


def _normalize_yyyymmdd(value) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def main() -> int:
    args = parse_args()
    sections = parse_sections(args.sections)
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if end_date < start_date:
        raise ValueError("end_date 不能早于 start_date")

    fetcher = TushareFetcher()
    if not fetcher.is_available():
        raise RuntimeError("Tushare API 未初始化，请先配置 TUSHARE_TOKEN")

    ts_codes = normalize_ts_codes(fetcher, args.ts_codes)
    needs_codes = any(section in {"raw", "aux", "corporate"} for section in sections)
    if needs_codes and not ts_codes:
        raise ValueError("sections 包含 raw/aux/corporate 时，必须传 --ts-codes")

    db = get_theme_picker_db()
    sync_batch_id = datetime.now().strftime("tushare-%Y%m%d-%H%M%S")
    trade_calendar_df = pd.DataFrame(columns=["exchange", "cal_date", "is_open", "pretrade_date"])

    if "calendar" in sections or "corporate" in sections:
        trade_calendar_df = sync_trade_calendar(
            fetcher=fetcher,
            db=db,
            exchange=str(args.exchange or "SSE").strip().upper(),
            start_date=start_date,
            end_date=end_date,
            sync_batch_id=sync_batch_id,
        )

    if "raw" in sections:
        sync_stock_daily_raw(
            fetcher=fetcher,
            db=db,
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
            chunk_days=args.chunk_days,
            sync_batch_id=sync_batch_id,
        )

    if "aux" in sections:
        sync_stock_daily_aux(
            fetcher=fetcher,
            db=db,
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
            chunk_days=args.chunk_days,
            sync_batch_id=sync_batch_id,
        )

    if "corporate" in sections:
        sync_stock_corporate_actions(
            fetcher=fetcher,
            db=db,
            ts_codes=ts_codes,
            trade_calendar_df=trade_calendar_df,
            start_date=start_date,
            end_date=end_date,
            date_field=args.dividend_date_field,
            sync_batch_id=sync_batch_id,
        )

    print(f"[sync] completed batch={sync_batch_id} sections={','.join(sections)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
