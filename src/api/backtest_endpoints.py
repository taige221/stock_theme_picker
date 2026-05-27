# -*- coding: utf-8 -*-
"""Strategy backtest history and import APIs."""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional, TypeVar

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from theme_picker.application.backtest_execution_service import BacktestExecutionService
from theme_picker.application.backtest_import_service import BacktestImportService

router = APIRouter()
T = TypeVar("T")


class BacktestImportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    source_path: str = Field(
        ...,
        alias="sourcePath",
        min_length=1,
        description="Project-local summary.json path or its parent directory",
    )
    stock_pool_path: Optional[str] = Field(
        default=None,
        alias="stockPoolPath",
        description="Optional stock pool JSON path",
    )
    mode: Literal["upsert"] = Field(default="upsert", description="Import mode")
    equity_mode: Literal["portfolio_only", "traded_daily", "all_daily"] = Field(
        default="traded_daily",
        alias="equityMode",
        description="Equity curve persistence mode",
    )
    dry_run: bool = Field(
        default=False,
        alias="dryRun",
        description="Validate and summarize without writing rows",
    )


class BacktestPresetSaveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=80)
    strategy: str = Field(default="a_share_box", min_length=1, max_length=64)
    description: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    stock_pool: Optional[dict[str, Any]] = Field(default=None, alias="stockPool")


class BacktestExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    strategy: str = Field(default="a_share_box", min_length=1, max_length=64)
    start_date: str = Field(..., alias="startDate", min_length=10, max_length=10)
    end_date: str = Field(..., alias="endDate", min_length=10, max_length=10)
    params: dict[str, Any] = Field(default_factory=dict)
    price_adjustment: str = Field(default="qfq", alias="priceAdjustment")
    trading_constraints: str = Field(default="daily_limits", alias="tradingConstraints")
    stock_pool_path: Optional[str] = Field(default=None, alias="stockPoolPath")
    stock_codes: Optional[list[str]] = Field(default=None, alias="stockCodes")
    base_run_id: Optional[str] = Field(default=None, alias="baseRunId")
    equity_mode: Literal["portfolio_only", "traded_daily", "all_daily"] = Field(
        default="traded_daily",
        alias="equityMode",
    )


def _service() -> BacktestImportService:
    return BacktestImportService()


def _execution_service() -> BacktestExecutionService:
    return BacktestExecutionService()


def _run_service(action: Callable[[BacktestImportService], T]) -> T:
    try:
        return action(_service())
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail={"message": "backtest storage query failed"}) from exc


def _get_run_or_404(service: BacktestImportService, run_id: str) -> dict:
    result = service.get_run(run_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "backtest run not found", "run_id": run_id},
        )
    return result


@router.get("/presets")
def list_backtest_presets() -> dict:
    return _run_service(lambda service: service.list_presets())


@router.post("/presets")
def save_backtest_preset(request: BacktestPresetSaveRequest) -> dict:
    return _run_service(
        lambda service: service.save_preset(
            name=request.name,
            strategy=request.strategy,
            params=request.params,
            constraints=request.constraints,
            description=request.description,
            stock_pool=request.stock_pool,
        )
    )


@router.delete("/presets/{preset_id}")
def delete_backtest_preset(preset_id: str) -> dict:
    return _run_service(lambda service: service.delete_preset(preset_id))


@router.post("/runs/execute", status_code=202)
def execute_backtest(request: BacktestExecuteRequest) -> dict:
    try:
        return _execution_service().submit(request.model_dump(by_alias=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": f"submit backtest failed: {exc}"}) from exc


@router.get("/jobs/{job_id}")
def get_backtest_job(job_id: str) -> dict:
    job = _execution_service().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"message": "backtest job not found", "job_id": job_id})
    return job


@router.delete("/runs/{run_id}")
def delete_backtest_run(run_id: str) -> dict:
    return _run_service(lambda service: service.delete_run(run_id))


@router.get("/runs")
def list_backtest_runs(
    strategy: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    return _run_service(
        lambda service: service.list_runs(strategy=strategy, status=status, limit=limit)
    )


@router.get("/runs/latest")
def get_latest_backtest_run(
    strategy: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="finished"),
) -> dict:
    def action(service: BacktestImportService) -> dict:
        runs = service.list_runs(strategy=strategy, status=status, limit=1)
        items = runs.get("items") or []
        if not items:
            raise HTTPException(
                status_code=404,
                detail={"message": "no backtest run found", "strategy": strategy, "status": status},
            )
        return _get_run_or_404(service, str(items[0]["run_id"]))

    return _run_service(action)


@router.get("/runs/{run_id}")
def get_backtest_run(run_id: str) -> dict:
    return _run_service(lambda service: _get_run_or_404(service, run_id))


@router.get("/runs/{run_id}/equity-curve")
def get_backtest_equity_curve(
    run_id: str,
    scope: str = Query(default="portfolio", pattern="^(portfolio|symbol)$"),
    stock_code: Optional[str] = Query(default=None, alias="stockCode"),
    legacy_stock_code: Optional[str] = Query(default=None, alias="stock_code", include_in_schema=False),
    limit: int = Query(default=5000, ge=1, le=20000),
) -> dict:
    effective_stock_code = stock_code or legacy_stock_code
    if scope == "symbol" and not effective_stock_code:
        raise HTTPException(
            status_code=400,
            detail={"message": "stockCode is required when scope is symbol"},
        )

    def action(service: BacktestImportService) -> dict:
        _get_run_or_404(service, run_id)
        return service.get_equity_curve(run_id, scope=scope, stock_code=effective_stock_code, limit=limit)

    return _run_service(action)


@router.get("/runs/{run_id}/stocks")
def list_backtest_stocks(
    run_id: str,
    result_filter: str = Query(
        default="all",
        alias="resultFilter",
        pattern="^(all|profitable|losing|flat|error)$",
    ),
    legacy_filter: Optional[str] = Query(
        default=None,
        alias="filter",
        pattern="^(all|profitable|losing|flat|error)$",
        include_in_schema=False,
    ),
    sort: str = Query(
        default="total_return_pct",
        pattern="^(total_return_pct|trade_count|win_rate_pct|final_equity|stock_code)$",
    ),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    effective_filter = legacy_filter or result_filter

    def action(service: BacktestImportService) -> dict:
        _get_run_or_404(service, run_id)
        return service.list_stocks(
            run_id,
            result_filter=effective_filter,
            sort=sort,
            order=order,
            limit=limit,
        )

    return _run_service(action)


@router.get("/runs/{run_id}/stocks/{stock_code}")
def get_backtest_stock_detail(run_id: str, stock_code: str) -> dict:
    def action(service: BacktestImportService) -> dict:
        _get_run_or_404(service, run_id)
        result = service.get_stock_detail(run_id, stock_code)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "backtest stock result not found",
                    "run_id": run_id,
                    "stock_code": stock_code,
                },
            )
        return result

    return _run_service(action)


@router.get("/runs/{run_id}/stocks/{stock_code}/chart")
def get_backtest_stock_chart(run_id: str, stock_code: str) -> dict:
    def action(service: BacktestImportService) -> dict:
        _get_run_or_404(service, run_id)
        result = service.get_stock_chart(run_id, stock_code)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "backtest stock result not found",
                    "run_id": run_id,
                    "stock_code": stock_code,
                },
            )
        return result

    return _run_service(action)


@router.get("/runs/{run_id}/trades")
def list_backtest_trades(
    run_id: str,
    stock_code: Optional[str] = Query(default=None, alias="stockCode"),
    legacy_stock_code: Optional[str] = Query(default=None, alias="stock_code", include_in_schema=False),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    effective_stock_code = stock_code or legacy_stock_code

    def action(service: BacktestImportService) -> dict:
        _get_run_or_404(service, run_id)
        return service.list_trades(run_id, stock_code=effective_stock_code, limit=limit)

    return _run_service(action)


@router.post("/imports")
def import_backtest_json(request: BacktestImportRequest) -> dict:
    return _run_service(
        lambda service: service.import_artifact(
            request.source_path,
            stock_pool_path=request.stock_pool_path,
            mode=request.mode,
            dry_run=request.dry_run,
            equity_mode=request.equity_mode,
        ).to_dict()
    )
