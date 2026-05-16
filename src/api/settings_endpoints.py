# -*- coding: utf-8 -*-
"""Editable runtime settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from theme_picker.api.schemas import (
    RuntimeSettingsResponseSchema,
    RuntimeSettingsUpdateRequestSchema,
    RuntimeSettingsUpdateResponseSchema,
)
from theme_picker.application.settings_service import RuntimeSettingsService

router = APIRouter()


@router.get(
    "",
    response_model=RuntimeSettingsResponseSchema,
    summary="读取可编辑运行设置",
    description="返回允许在 Web UI 中直接编辑的环境变量白名单。",
)
def get_runtime_settings() -> RuntimeSettingsResponseSchema:
    try:
        return RuntimeSettingsService().get_settings()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"读取设置失败: {exc}"},
        ) from exc


@router.put(
    "",
    response_model=RuntimeSettingsUpdateResponseSchema,
    summary="保存运行设置",
    description="校验并写回白名单环境变量到 .env，然后重载当前进程配置。",
)
def update_runtime_settings(
    request: RuntimeSettingsUpdateRequestSchema,
) -> RuntimeSettingsUpdateResponseSchema:
    try:
        return RuntimeSettingsService().update_settings(request.values)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"保存设置失败: {exc}"},
        ) from exc
