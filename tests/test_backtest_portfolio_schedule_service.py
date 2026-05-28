from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from theme_picker.application.backtest_portfolio_schedule_service import BacktestPortfolioScheduleService
from theme_picker.storage import (
    DatabaseManager,
    StrategyBacktestPortfolioCandidate,
    StrategyBacktestPortfolioSchedule,
    StrategyBacktestRun,
    StrategyBacktestTrade,
)


def test_portfolio_schedule_service_ranks_and_persists_candidates(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path / "stock_analysis.duckdb"))
    try:
        with db.session_scope() as session:
            session.add(
                StrategyBacktestRun(
                    run_id="bt_schedule_test",
                    run_name="schedule test",
                    artifact_digest="digest_schedule_test",
                    strategy="a_share_box",
                    aggregate_payload=json.dumps({"aggregate_return_pct": 12.3, "total_trade_count": 3}),
                )
            )
            session.add_all(
                [
                    _trade(
                        trade_id="t1",
                        code="000001",
                        entry_date=date(2026, 1, 5),
                        signal_type="pullback_bounce",
                        score=72.0,
                        return_pct=4.2,
                    ),
                    _trade(
                        trade_id="t2",
                        code="000002",
                        entry_date=date(2026, 1, 5),
                        signal_type="breakout_long",
                        score=83.0,
                        return_pct=-2.0,
                    ),
                    _trade(
                        trade_id="t3",
                        code="000003",
                        entry_date=date(2026, 1, 5),
                        signal_type="pullback_bounce",
                        score=65.0,
                        return_pct=1.0,
                    ),
                ]
            )

        service = BacktestPortfolioScheduleService(db=db)
        payload = service.create_schedule(
            "bt_schedule_test",
            config_payload={
                "rankMode": "signal_score",
                "maxPerDay": 2,
                "pullbackQuota": 1,
                "breakoutQuota": 1,
            },
        )

        assert payload["schedule"]["run_id"] == "bt_schedule_test"
        assert payload["config"]["max_per_day"] == 2
        assert payload["summary"]["candidate_trade_count"] == 3
        assert payload["summary"]["selected_trade_count"] == 2
        assert len(payload["candidates"]) == 3
        selected = [row for row in payload["candidates"] if row["selected"]]
        assert {row["signal_type"] for row in selected} == {"pullback_bounce", "breakout_long"}

        schedule_id = payload["schedule"]["schedule_id"]
        with db.session_scope() as session:
            schedule_count = session.execute(select(StrategyBacktestPortfolioSchedule)).scalars().all()
            candidate_count = session.execute(select(StrategyBacktestPortfolioCandidate)).scalars().all()
            assert len(schedule_count) == 1
            assert len(candidate_count) == 3
            assert all(row.candidate_id.startswith(f"{schedule_id}:") for row in candidate_count)

        detail = service.get_schedule(schedule_id, limit=2)
        assert detail["candidate_page"] == {"limit": 2, "offset": 0, "returned": 2, "total": 3}
        listing = service.list_schedules("bt_schedule_test")
        assert listing["items"][0]["schedule_id"] == schedule_id
    finally:
        db.close()


def _trade(
    *,
    trade_id: str,
    code: str,
    entry_date: date,
    signal_type: str,
    score: float,
    return_pct: float,
) -> StrategyBacktestTrade:
    metadata = {
        "signal_type": signal_type,
        "style_bucket": "balanced_trend",
        "signal_number": 2,
        "turnover_rate": 6.5,
    }
    return StrategyBacktestTrade(
        trade_id=trade_id,
        run_id="bt_schedule_test",
        stock_code=code,
        stock_name=f"股票{code}",
        entry_date=entry_date,
        exit_date=date(2026, 1, 10),
        net_pnl=return_pct * 1000.0,
        return_pct=return_pct,
        holding_days=5,
        exit_reason="max_holding_days_reached",
        entry_signal_type=signal_type,
        entry_signal_reason=signal_type,
        entry_signal_score=score,
        max_favorable_excursion_pct=max(return_pct, 0.0) + 2.0,
        max_adverse_excursion_pct=-1.5,
        entry_signal_metadata_payload=json.dumps(metadata),
        raw_trade_payload=json.dumps({"entry_signal_metadata": metadata}),
    )
