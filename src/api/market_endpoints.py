# -*- coding: utf-8 -*-
"""Unified market data endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from theme_picker.api.schemas import MarketDailyBarsResponse
from theme_picker.infrastructure.daily_bar_service import get_daily_bar_resolver

router = APIRouter()


@router.get(
    "/daily-bars/{stock_code}",
    response_model=MarketDailyBarsResponse,
    responses={
        200: {"description": "统一日K数据", "model": MarketDailyBarsResponse},
        400: {"description": "请求参数错误"},
        500: {"description": "服务器错误"},
    },
    summary="获取统一日K",
    description="对 A 股普通股和 ETF 走本地缓存优先、缺失补拉、合并回写后的统一日K入口。",
)
def get_market_daily_bars(stock_code: str, bars: int = 240) -> MarketDailyBarsResponse:
    try:
        resolver = get_daily_bar_resolver()
        result = resolver.resolve_daily_bars(
            stock_code,
            bars=bars,
            minimum_rows=min(max(1, bars), 30),
        )
        rows = resolver.serialize_frame(result.frame)
        latest_trade_date = result.latest_trade_date.isoformat() if result.latest_trade_date else None
        return MarketDailyBarsResponse(
            stock_code=result.stock_code,
            base_code=result.base_code,
            instrument_type=result.instrument_type,
            instrument_label=result.instrument_label,
            requested_bars=max(1, int(bars or 240)),
            returned_bars=len(rows),
            latest_trade_date=latest_trade_date,
            data_source=result.data_source,
            cache_status=result.cache_status,
            daily_bars=rows,
            errors=result.errors,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"统一日K获取失败: {exc}"},
        ) from exc
