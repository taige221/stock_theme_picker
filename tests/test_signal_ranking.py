# -*- coding: utf-8 -*-

from __future__ import annotations

from theme_picker.api.backtest_endpoints import BacktestPortfolioScheduleRequest
from theme_picker.application.backtest_portfolio_schedule_service import BacktestPortfolioScheduleService
from theme_picker.backtest.analysis.signal_ranking import LayeredRankingConfig, rank_trade_candidates


def _trade(
    stock_code: str,
    entry_date: str,
    exit_date: str,
    signal_type: str,
    score: float,
) -> dict:
    return {
        "stock_code": stock_code,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "signal_type": signal_type,
        "entry_signal_score": score,
        "return_pct": 1.0,
        "holding_days": 1,
    }


def test_layered_ranking_config_normalized_bounds_values() -> None:
    config = LayeredRankingConfig(
        max_per_day=0,
        pullback_quota=-2,
        breakout_quota=-1,
        max_open_positions=-3,
        min_cohort_trades=0,
        min_rank_score=70.0,
        fill_unused_slots=0,  # type: ignore[arg-type]
    ).normalized()

    assert config.max_per_day == 1
    assert config.pullback_quota == 0
    assert config.breakout_quota == 0
    assert config.max_open_positions == 0
    assert config.min_cohort_trades == 1
    assert config.min_rank_score == 70.0
    assert config.fill_unused_slots is False


def test_layered_ranking_config_serializes_heat_score_cap_only() -> None:
    config = LayeredRankingConfig(heat_score_cap=55.0).normalized()
    payload = config.to_dict()

    assert config.heat_score_cap == 55.0
    assert payload["heat_score_cap"] == 55.0
    assert "max_heat_score" not in payload


def test_portfolio_schedule_request_accepts_legacy_max_heat_score() -> None:
    request = BacktestPortfolioScheduleRequest.model_validate({"maxHeatScore": 55.0})
    payload = request.model_dump(by_alias=False)

    assert request.heat_score_cap == 55.0
    assert payload["heat_score_cap"] == 55.0
    assert "max_heat_score" not in payload


def test_portfolio_schedule_service_migrates_legacy_max_heat_score_payload() -> None:
    service = BacktestPortfolioScheduleService.__new__(BacktestPortfolioScheduleService)

    config = service._ranking_config({"maxHeatScore": 55.0})

    assert config.heat_score_cap == 55.0
    assert "max_heat_score" not in config.to_dict()


def test_rank_trade_candidates_respects_daily_signal_quotas() -> None:
    trades = [
        _trade("000001", "2024-01-02", "2024-01-05", "pullback_bounce", 95.0),
        _trade("000002", "2024-01-02", "2024-01-05", "pullback_bounce", 80.0),
        _trade("000003", "2024-01-02", "2024-01-05", "breakout_long", 90.0),
        _trade("000004", "2024-01-02", "2024-01-05", "breakout_long", 70.0),
    ]

    ranked = rank_trade_candidates(
        trades,
        run_name="quota",
        config=LayeredRankingConfig(
            max_per_day=2,
            pullback_quota=1,
            breakout_quota=1,
            fill_unused_slots=False,
        ),
    )

    selected = [row for row in ranked if row["selected"]]
    assert {row["stock_code"] for row in selected} == {"000001", "000003"}
    assert [row["stock_code"] for row in sorted(selected, key=lambda row: row["selected_order"])] == [
        "000001",
        "000003",
    ]
    assert [row["selected_layer"] for row in selected] == [
        "quota:pullback_bounce",
        "quota:breakout_long",
    ]
    assert all(row["daily_candidate_count"] == 4 for row in ranked)


def test_rank_trade_candidates_respects_max_open_positions() -> None:
    trades = [
        _trade("000001", "2024-01-02", "2024-01-04", "pullback_bounce", 95.0),
        _trade("000002", "2024-01-03", "2024-01-05", "pullback_bounce", 96.0),
        _trade("000003", "2024-01-04", "2024-01-06", "pullback_bounce", 97.0),
        _trade("000004", "2024-01-05", "2024-01-07", "pullback_bounce", 98.0),
    ]

    ranked = rank_trade_candidates(
        trades,
        run_name="open_cap",
        config=LayeredRankingConfig(
            max_per_day=1,
            pullback_quota=1,
            breakout_quota=0,
            max_open_positions=1,
            fill_unused_slots=False,
        ),
    )

    selected = [row for row in ranked if row["selected"]]
    assert [row["stock_code"] for row in selected] == ["000001", "000004"]
    assert [row["selected_order"] for row in selected] == [1, 2]


def test_rank_trade_candidates_applies_min_rank_score_before_fill() -> None:
    trades = [
        _trade("000001", "2024-01-02", "2024-01-05", "pullback_bounce", 80.0),
        _trade("000002", "2024-01-02", "2024-01-05", "breakout_long", 79.0),
        _trade("000003", "2024-01-02", "2024-01-05", "breakout_long", 90.0),
    ]

    ranked = rank_trade_candidates(
        trades,
        run_name="score_filter",
        config=LayeredRankingConfig(
            max_per_day=3,
            pullback_quota=1,
            breakout_quota=1,
            min_rank_score=80.0,
            fill_unused_slots=True,
        ),
    )

    selected = [row for row in ranked if row["selected"]]
    filtered_out = [row for row in ranked if not row["rank_filter_passed"]]
    assert {row["stock_code"] for row in selected} == {"000001", "000003"}
    assert [row["stock_code"] for row in sorted(selected, key=lambda row: row["selected_order"])] == [
        "000001",
        "000003",
    ]
    assert [row["stock_code"] for row in filtered_out] == ["000002"]


def test_rank_trade_candidates_applies_heat_score_cap_before_fill() -> None:
    trades = [
        _trade("000001", "2024-01-02", "2024-01-05", "pullback_bounce", 80.0),
        _trade("000002", "2024-01-02", "2024-01-05", "breakout_long", 99.0),
        _trade("000003", "2024-01-02", "2024-01-05", "breakout_long", 70.0),
    ]

    ranked = rank_trade_candidates(
        trades,
        run_name="score_cap",
        config=LayeredRankingConfig(
            max_per_day=3,
            pullback_quota=1,
            breakout_quota=1,
            heat_score_cap=90.0,
            fill_unused_slots=True,
        ),
    )

    selected = [row for row in ranked if row["selected"]]
    filtered_out = [row for row in ranked if not row["rank_filter_passed"]]
    assert {row["stock_code"] for row in selected} == {"000001", "000003"}
    assert [row["stock_code"] for row in filtered_out] == ["000002"]


def test_stock_quality_walk_forward_prefers_prior_stronger_symbol_over_raw_signal_score() -> None:
    trades = [
        {**_trade("000001", "2024-01-02", "2024-01-03", "pullback_bounce", 40.0), "return_pct": 8.0},
        {**_trade("000001", "2024-01-03", "2024-01-04", "pullback_bounce", 40.0), "return_pct": 6.0},
        {**_trade("000001", "2024-01-04", "2024-01-05", "pullback_bounce", 40.0), "return_pct": -2.0},
        {**_trade("000001", "2024-01-05", "2024-01-06", "pullback_bounce", 40.0), "return_pct": -1.0},
        {**_trade("000002", "2024-01-02", "2024-01-03", "pullback_bounce", 99.0), "return_pct": -5.0},
        {**_trade("000002", "2024-01-03", "2024-01-04", "pullback_bounce", 99.0), "return_pct": -4.0},
        {**_trade("000002", "2024-01-04", "2024-01-05", "pullback_bounce", 99.0), "return_pct": -3.0},
        {**_trade("000002", "2024-01-05", "2024-01-06", "pullback_bounce", 99.0), "return_pct": -2.0},
        _trade("000001", "2024-01-10", "2024-01-11", "pullback_bounce", 60.0),
        _trade("000002", "2024-01-10", "2024-01-11", "pullback_bounce", 98.0),
    ]

    signal_ranked = rank_trade_candidates(
        trades,
        run_name="signal",
        config=LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0),
    )
    quality_ranked = rank_trade_candidates(
        trades,
        run_name="quality",
        config=LayeredRankingConfig(
            rank_mode="stock_quality_walk_forward",
            max_per_day=1,
            pullback_quota=1,
            breakout_quota=0,
            min_cohort_trades=4,
        ),
    )

    signal_day2_selected = [
        row["stock_code"]
        for row in signal_ranked
        if row["entry_date"] == "2024-01-10" and row["selected"]
    ]
    quality_day2_selected = [
        row
        for row in quality_ranked
        if row["entry_date"] == "2024-01-10" and row["selected"]
    ]
    quality_day2_rejected = [
        row
        for row in quality_ranked
        if row["entry_date"] == "2024-01-10" and row["stock_code"] == "000002"
    ][0]

    assert signal_day2_selected == ["000002"]
    assert [row["stock_code"] for row in quality_day2_selected] == ["000001"]
    assert quality_day2_selected[0]["stock_quality_trade_count"] == 4
    assert quality_day2_selected[0]["stock_quality_win_rate_pct"] == 50.0
    assert quality_day2_selected[0]["stock_signal_quality_trade_count"] == 4
    assert quality_day2_selected[0]["signal_quality_trade_count"] == 8
    assert quality_day2_selected[0]["quality_stock_confidence"] == 0.5
    assert quality_day2_selected[0]["rank_score"] > quality_day2_rejected["rank_score"]


def test_stock_quality_walk_forward_filters_heat_score_separately_from_rank_score() -> None:
    trades = [
        {**_trade("000001", "2024-01-02", "2024-01-03", "pullback_bounce", 40.0), "return_pct": 8.0},
        {**_trade("000001", "2024-01-03", "2024-01-04", "pullback_bounce", 40.0), "return_pct": 6.0},
        {**_trade("000001", "2024-01-04", "2024-01-05", "pullback_bounce", 40.0), "return_pct": 7.0},
        {**_trade("000001", "2024-01-05", "2024-01-06", "pullback_bounce", 40.0), "return_pct": 5.0},
        {**_trade("000002", "2024-01-02", "2024-01-03", "pullback_bounce", 99.0), "return_pct": -5.0},
        {**_trade("000002", "2024-01-03", "2024-01-04", "pullback_bounce", 99.0), "return_pct": -4.0},
        {**_trade("000002", "2024-01-04", "2024-01-05", "pullback_bounce", 99.0), "return_pct": -3.0},
        {**_trade("000002", "2024-01-05", "2024-01-06", "pullback_bounce", 99.0), "return_pct": -2.0},
        _trade("000001", "2024-01-10", "2024-01-11", "pullback_bounce", 20.0),
        _trade("000002", "2024-01-10", "2024-01-11", "pullback_bounce", 99.0),
    ]

    ranked = rank_trade_candidates(
        trades,
        run_name="heat",
        config=LayeredRankingConfig(
            rank_mode="stock_quality_walk_forward",
            max_per_day=1,
            pullback_quota=1,
            breakout_quota=0,
            min_cohort_trades=4,
            heat_score_cap=55.0,
        ),
    )

    hot_row = [
        row
        for row in ranked
        if row["entry_date"] == "2024-01-10" and row["stock_code"] == "000001"
    ][0]
    cold_row = [
        row
        for row in ranked
        if row["entry_date"] == "2024-01-10" and row["stock_code"] == "000002"
    ][0]

    assert hot_row["rank_score"] > cold_row["rank_score"]
    assert hot_row["heat_score"] > 55.0
    assert hot_row["rank_filter_reason"] == "above_heat_score_cap"
    assert cold_row["rank_filter_passed"] is True
