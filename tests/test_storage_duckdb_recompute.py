from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from theme_picker.storage import DatabaseManager


def _open_manager(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(str(tmp_path / "stock_analysis.duckdb"))


def _assert_float(actual: float | None, expected: Any) -> None:
    if pd.isna(expected):
        assert actual is None
    else:
        assert actual is not None
        assert math.isclose(actual, round(float(expected), 4), rel_tol=0, abs_tol=5e-4)


def _style_bucket(row: pd.Series) -> str | None:
    turnover_median = row.get("turnover_rate_median_20")
    atr_pct = row.get("atr_pct_20")
    if pd.isna(turnover_median) or pd.isna(atr_pct):
        return None
    turnover_value = float(turnover_median)
    atr_value = float(atr_pct)
    if atr_value >= 5.5:
        return "high_beta"
    if turnover_value >= 5.0:
        return "high_beta"
    if atr_value >= 4.5 and turnover_value >= 2.0:
        return "high_beta"
    if turnover_value < 1.5 and atr_value < 3.5:
        return "slow_large"
    return "balanced_trend"


def _expected_aux_frame(raw_rows: list[dict[str, Any]], aux_rows: list[dict[str, Any]]) -> pd.DataFrame:
    raw_frame = pd.DataFrame(raw_rows).sort_values("trade_date").reset_index(drop=True)
    aux_frame = pd.DataFrame(aux_rows)[["trade_date", "turnover_rate"]]
    frame = raw_frame.merge(aux_frame, on="trade_date", how="inner").sort_values("trade_date").reset_index(drop=True)

    qfq_ready = frame[["high_qfq", "low_qfq", "close_qfq"]].notna().all(axis=1).any()
    high_col = "high_qfq" if qfq_ready else "high"
    low_col = "low_qfq" if qfq_ready else "low"
    close_col = "close_qfq" if qfq_ready else "close"

    frame["feature_high"] = pd.to_numeric(frame[high_col], errors="coerce")
    frame["feature_low"] = pd.to_numeric(frame[low_col], errors="coerce")
    frame["feature_close"] = pd.to_numeric(frame[close_col], errors="coerce")
    frame["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce")

    previous_close = frame["feature_close"].shift(1)
    true_range_components = pd.concat(
        [
            frame["feature_high"] - frame["feature_low"],
            (frame["feature_high"] - previous_close).abs(),
            (frame["feature_low"] - previous_close).abs(),
        ],
        axis=1,
    )
    frame["true_range"] = true_range_components.max(axis=1, skipna=True)
    frame["turnover_rate_median_20"] = frame["turnover_rate"].rolling(window=20, min_periods=5).median()
    frame["atr_20"] = frame["true_range"].rolling(window=20, min_periods=5).mean()
    frame["atr_pct_20"] = (frame["atr_20"] / frame["feature_close"] * 100.0).replace(
        [float("inf"), float("-inf")],
        pd.NA,
    )
    frame["style_bucket"] = frame.apply(_style_bucket, axis=1)
    return frame


def _make_raw_and_aux_rows(
    ts_code: str,
    start_date: date,
    count: int,
    *,
    with_adj_factor: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows: list[dict[str, Any]] = []
    aux_rows: list[dict[str, Any]] = []
    for index in range(count):
        trade_date = start_date + timedelta(days=index)
        raw_rows.append(
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "open": 10.0 + index,
                "high": 11.0 + index,
                "low": 9.0 + index,
                "close": 10.5 + index,
                "pre_close": 10.0 + index - 1 if index else None,
                "vol": 1000.0 + index,
                "amount": 10000.0 + index,
                "adj_factor": 1.0 + index * 0.03 if with_adj_factor else None,
                "open_qfq": None,
                "high_qfq": None,
                "low_qfq": None,
                "close_qfq": None,
                "sync_batch_id": "raw-batch",
                "data_source": "pytest",
            }
        )
        aux_rows.append(
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "turnover_rate": (index % 7) + 0.5,
                "sync_batch_id": "old-batch",
                "data_source": "pytest",
            }
        )
    return raw_rows, aux_rows


def test_recompute_stock_daily_features_matches_pandas_reference(tmp_path: Path) -> None:
    ts_code = "000001.SZ"
    start_date = date(2026, 1, 1)
    raw_rows, aux_rows = _make_raw_and_aux_rows(ts_code, start_date, 25, with_adj_factor=True)
    db = _open_manager(tmp_path)
    try:
        assert db.save_stock_daily_raw_rows(raw_rows) == 25
        assert db.save_stock_daily_aux_rows(aux_rows) == 25

        assert db.recompute_stock_daily_raw_qfq(ts_code) == 25
        latest_adj = raw_rows[-1]["adj_factor"]
        assert latest_adj is not None
        for row in raw_rows:
            ratio = float(row["adj_factor"]) / float(latest_adj)
            row["open_qfq"] = round(float(row["open"]) * ratio, 4)
            row["high_qfq"] = round(float(row["high"]) * ratio, 4)
            row["low_qfq"] = round(float(row["low"]) * ratio, 4)
            row["close_qfq"] = round(float(row["close"]) * ratio, 4)

        assert db.recompute_stock_daily_aux_features(ts_code, sync_batch_id="feature-batch") == 25

        raw_by_date = {
            row.trade_date: row
            for row in db.get_stock_daily_raw_range(ts_code, start_date, start_date + timedelta(days=24))
        }
        for expected in raw_rows:
            actual = raw_by_date[expected["trade_date"]]
            _assert_float(actual.open_qfq, expected["open_qfq"])
            _assert_float(actual.high_qfq, expected["high_qfq"])
            _assert_float(actual.low_qfq, expected["low_qfq"])
            _assert_float(actual.close_qfq, expected["close_qfq"])

        expected_aux = _expected_aux_frame(raw_rows, aux_rows)
        expected_by_date = {row.trade_date: row for row in expected_aux.itertuples(index=False)}
        for actual in db.get_stock_daily_aux_range(ts_code, start_date, start_date + timedelta(days=24)):
            expected = expected_by_date[actual.trade_date]
            _assert_float(actual.turnover_rate_median_20, expected.turnover_rate_median_20)
            _assert_float(actual.atr_pct_20, expected.atr_pct_20)
            assert actual.style_bucket == expected.style_bucket
            assert actual.sync_batch_id == "feature-batch"
    finally:
        db.close()


def test_bulk_upsert_preserves_last_duplicate_conflict_key(tmp_path: Path) -> None:
    ts_code = "000003.SZ"
    trade_date = date(2026, 1, 5)
    raw_rows = [
        {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "adj_factor": 1.0,
            "data_source": "first",
        },
        {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "open": 20.0,
            "high": 21.0,
            "low": 19.0,
            "close": 20.5,
            "adj_factor": 2.0,
            "data_source": "second",
        },
    ]
    db = _open_manager(tmp_path)
    try:
        assert db.save_stock_daily_raw_rows(raw_rows) == 2
        rows = db.get_stock_daily_raw_range(ts_code, trade_date, trade_date)
        assert len(rows) == 1
        assert rows[0].close == 20.5
        assert rows[0].adj_factor == 2.0
        assert rows[0].data_source == "second"
    finally:
        db.close()


def test_recompute_stock_daily_features_falls_back_to_raw_prices(tmp_path: Path) -> None:
    ts_code = "000002.SZ"
    start_date = date(2026, 2, 1)
    raw_rows, aux_rows = _make_raw_and_aux_rows(ts_code, start_date, 8, with_adj_factor=False)
    db = _open_manager(tmp_path)
    try:
        assert db.save_stock_daily_raw_rows(raw_rows) == 8
        assert db.save_stock_daily_aux_rows(aux_rows) == 8

        assert db.recompute_stock_daily_raw_qfq(ts_code) == 0
        assert db.recompute_stock_daily_aux_features(ts_code, sync_batch_id="") == 8

        expected_aux = _expected_aux_frame(raw_rows, aux_rows)
        expected_by_date = {row.trade_date: row for row in expected_aux.itertuples(index=False)}
        for actual in db.get_stock_daily_aux_range(ts_code, start_date, start_date + timedelta(days=7)):
            expected = expected_by_date[actual.trade_date]
            _assert_float(actual.turnover_rate_median_20, expected.turnover_rate_median_20)
            _assert_float(actual.atr_pct_20, expected.atr_pct_20)
            assert actual.style_bucket == expected.style_bucket
            assert actual.sync_batch_id == "old-batch"
    finally:
        db.close()
