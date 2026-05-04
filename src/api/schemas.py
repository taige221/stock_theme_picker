# -*- coding: utf-8 -*-
"""
===================================
主题选股 API Schemas
===================================
"""

from __future__ import annotations

from typing import List, Optional, Dict

from pydantic import BaseModel, Field, model_validator


class ThemePickerScanRequest(BaseModel):
    theme_id: Optional[str] = Field(None, description="注册表中的主题 ID")
    theme_name: Optional[str] = Field(None, description="用户直接输入的主题名称")
    board_code: Optional[str] = Field(None, description="板块代码，例如 BK1188 或 000858.DC")
    board_name: Optional[str] = Field(None, description="板块名称，例如 DeepSeek概念 或 AI应用")
    strategy_mode: str = Field(default="event", description="技术评估口径：event 或 holding")
    max_candidates: int = Field(default=8, ge=1, le=50, description="最终参与筛选的候选股上限")
    include_untriggered: bool = Field(default=False, description="是否保留未触发主题")

    @model_validator(mode="after")
    def validate_input_presence(self):
        if not any(
            [
                (self.theme_id or "").strip(),
                (self.theme_name or "").strip(),
                (self.board_code or "").strip(),
                (self.board_name or "").strip(),
            ]
        ):
            raise ValueError("theme_id、theme_name、board_code、board_name 至少需要提供一个")
        if self.strategy_mode not in {"event", "holding"}:
            raise ValueError("strategy_mode 仅支持 event 或 holding")
        return self


class ThemePickerQuerySchema(BaseModel):
    theme_id: Optional[str] = None
    theme_name: Optional[str] = None
    board_code: Optional[str] = None
    board_name: Optional[str] = None
    strategy_mode: str
    max_candidates: int


class ThemeInsightSchema(BaseModel):
    theme_name: str
    event_status: str
    event_score: Optional[float] = None
    matched_keywords: List[str] = Field(default_factory=list)
    news_count: int = 0
    heat_level: Optional[str] = None
    board_mapping_path: Optional[str] = None
    board_candidate_count: Optional[int] = None
    primary_catalyst: Optional[str] = None


class ThemePickerStockItemSchema(BaseModel):
    rank: int
    stock_code: str
    stock_name: str
    signal_level: str
    current_pattern: Optional[str] = None
    selection_reason: str
    risk_note: Optional[str] = None
    current_price: Optional[float] = None
    support_level: Optional[float] = None
    pressure_level: Optional[float] = None
    trend_score: Optional[float] = None
    pct_chg: Optional[float] = None
    volume_ratio: Optional[float] = None
    turnover_rate: Optional[float] = None
    buy_signal: Optional[str] = None
    data_completeness: Optional[str] = None
    mini_reasons: List[str] = Field(default_factory=list)


class ThemePickerSelectedStockSchema(BaseModel):
    stock_code: str
    stock_name: str
    theme_relevance: Optional[str] = None
    current_price: Optional[float] = None
    pct_chg: Optional[float] = None
    volume_ratio: Optional[float] = None
    turnover_rate: Optional[float] = None
    trend_score: Optional[float] = None
    trend_status: Optional[str] = None
    buy_signal: Optional[str] = None
    current_pattern: Optional[str] = None
    data_completeness: Optional[str] = None
    resonance_count: Optional[int] = None
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    bias_ma5: Optional[float] = None
    bias_ma10: Optional[float] = None
    bias_ma20: Optional[float] = None
    recent_strong_days: Optional[int] = None
    support_level: Optional[float] = None
    pressure_level: Optional[float] = None
    news_summary: List[str] = Field(default_factory=list)
    selected_reasons: List[str] = Field(default_factory=list)
    risk_reasons: List[str] = Field(default_factory=list)
    data_sources: Dict[str, Optional[str]] = Field(default_factory=dict)


class ThemePickerSourceInfoSchema(BaseModel):
    board_source: Optional[str] = None
    board_fallback_used: Optional[bool] = None
    cache_hit: Optional[bool] = None
    source_pills: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    response_schema_version: int = 2
    history_repaired: Optional[bool] = None
    key_levels_backfilled: Optional[bool] = None
    board_source_confidence: Optional[str] = None
    pricing_source: Optional[str] = None


class ThemePickerScanResponse(BaseModel):
    query: ThemePickerQuerySchema
    theme_insight: ThemeInsightSchema
    stocks: List[ThemePickerStockItemSchema] = Field(default_factory=list)
    selected_stock: Optional[ThemePickerSelectedStockSchema] = None
    source_info: ThemePickerSourceInfoSchema
    empty_reason: Optional[str] = None


class ThemePickerTaskAcceptedSchema(BaseModel):
    task_id: str
    status: str = Field(default="pending")
    message: str


class ThemePickerTaskStatusSchema(BaseModel):
    task_id: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    message: Optional[str] = None
    result: Optional[ThemePickerScanResponse] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ThemePickerTaskHistoryItemSchema(BaseModel):
    task_id: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    query: Optional[ThemePickerQuerySchema] = None
    theme_name: Optional[str] = None
    board_mapping_path: Optional[str] = None
    stock_count: int = 0
    top_stock_names: List[str] = Field(default_factory=list)
    can_retry: bool = False
    result: Optional[ThemePickerScanResponse] = None
    error: Optional[str] = None


class ThemePickerTaskHistoryListResponse(BaseModel):
    items: List[ThemePickerTaskHistoryItemSchema] = Field(default_factory=list)


class ThemePickerThemeListItemSchema(BaseModel):
    id: str
    name: str
    board_codes: List[str] = Field(default_factory=list)
    board_names: List[str] = Field(default_factory=list)
    strategy_mode: str = "event"
    enabled: bool = True


class ThemePickerThemeListResponse(BaseModel):
    items: List[ThemePickerThemeListItemSchema] = Field(default_factory=list)
