# -*- coding: utf-8 -*-

from __future__ import annotations

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
