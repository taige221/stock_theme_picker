from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import inspect, select

from theme_picker.storage import (
    DatabaseManager,
    StrategyBacktestPortfolioCandidate,
    StrategyBacktestPortfolioSchedule,
)


def test_portfolio_schedule_tables_are_created_and_writable(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path / "stock_analysis.duckdb"))
    try:
        inspector = inspect(db.engine)
        assert "strategy_backtest_portfolio_schedule" in inspector.get_table_names()
        assert "strategy_backtest_portfolio_candidate" in inspector.get_table_names()

        schedule_columns = {column["name"] for column in inspector.get_columns("strategy_backtest_portfolio_schedule")}
        candidate_columns = {column["name"] for column in inspector.get_columns("strategy_backtest_portfolio_candidate")}

        assert {
            "schedule_id",
            "run_id",
            "rank_mode",
            "config_payload",
            "summary_payload",
            "candidate_count",
            "selected_count",
        }.issubset(schedule_columns)
        assert {
            "candidate_id",
            "schedule_id",
            "run_id",
            "entry_date",
            "stock_code",
            "stock_name",
            "signal_type",
            "rank_score",
            "daily_candidate_rank",
            "selected",
            "selected_order",
            "selected_layer",
            "return_pct",
            "net_pnl",
            "metadata_payload",
            "raw_payload",
        }.issubset(candidate_columns)

        with db.session_scope() as session:
            session.add(
                StrategyBacktestPortfolioSchedule(
                    schedule_id="sched_test",
                    run_id="bt_test",
                    rank_mode="layered_score",
                    candidate_count=1,
                    selected_count=1,
                    first_entry_date=date(2026, 1, 5),
                    last_entry_date=date(2026, 1, 5),
                    config_payload='{"max_per_day": 2}',
                    summary_payload='{"selected_count": 1}',
                )
            )
            session.add(
                StrategyBacktestPortfolioCandidate(
                    candidate_id="sched_test:2026-01-05:000001:pullback_bounce",
                    schedule_id="sched_test",
                    run_id="bt_test",
                    entry_date=date(2026, 1, 5),
                    stock_code="000001",
                    stock_name="平安银行",
                    signal_type="pullback_bounce",
                    rank_score=83.5,
                    daily_candidate_rank=1,
                    selected=1,
                    selected_order=1,
                    selected_layer="pullback_top",
                    return_pct=4.2,
                    net_pnl=4200.0,
                    metadata_payload='{"turnover_rate": 6.5}',
                    raw_payload='{"source": "pytest"}',
                )
            )

        with db.session_scope() as session:
            row = session.execute(
                select(StrategyBacktestPortfolioCandidate).where(
                    StrategyBacktestPortfolioCandidate.schedule_id == "sched_test"
                )
            ).scalar_one()
            assert row.stock_name == "平安银行"
            assert row.selected == 1
            assert row.selected_layer == "pullback_top"
    finally:
        db.close()
