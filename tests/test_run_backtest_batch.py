# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from theme_picker.backtest.core.models import BacktestResult, EquityPoint


def _load_batch_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_backtest_batch.py"
    spec = importlib.util.spec_from_file_location("run_backtest_batch", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


batch = _load_batch_module()


def _result() -> BacktestResult:
    return BacktestResult(
        strategy_name="a_share_box",
        stock_code="000001.SZ",
        start_date="2024-01-01",
        end_date="2024-01-03",
        config={},
        params={},
        metrics={"trade_count": 0},
        equity_curve=[
            EquityPoint(
                trade_date=date(2024, 1, 2),
                cash=100000.0,
                market_value=0.0,
                equity=100000.0,
            )
        ],
    )


def test_result_to_artifact_full_keeps_equity_curve() -> None:
    payload = batch._result_to_artifact(_result(), detail_mode=batch.DETAIL_MODE_FULL)

    assert payload["artifact_detail_mode"] == batch.DETAIL_MODE_FULL
    assert len(payload["equity_curve"]) == 1
    assert "equity_curve_omitted" not in payload


def test_result_to_artifact_trades_only_omits_equity_curve() -> None:
    payload = batch._result_to_artifact(_result(), detail_mode=batch.DETAIL_MODE_TRADES_ONLY)

    assert payload["artifact_detail_mode"] == batch.DETAIL_MODE_TRADES_ONLY
    assert payload["equity_curve"] == []
    assert payload["equity_curve_omitted"] is True


def test_timing_fields_and_summary_are_millisecond_based() -> None:
    row = {
        "status": "ok",
        **batch._timing_fields(
            load_elapsed=0.0012,
            run_elapsed=0.0205,
            write_elapsed=0.003,
            total_elapsed=0.025,
            row_count=3,
        ),
    }

    assert row["row_count"] == 3
    assert row["load_ms"] == 1.2
    assert row["run_ms"] == 20.5
    assert row["write_ms"] == 3.0
    assert row["total_ms"] == 25.0

    summary = batch._build_timing_summary([row, {"status": "error", "load_ms": 999.0}])

    assert summary["ok_symbols"] == 1
    assert summary["load"]["total_ms"] == 1.2
    assert summary["run"]["avg_ms"] == 20.5
