# -*- coding: utf-8 -*-
"""
===================================
主题选股 API Schemas
===================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


class StockQueryAnalyzeRequest(BaseModel):
    query: Optional[str] = Field(None, description="股票代码或股票名称")
    stock_code: Optional[str] = Field(None, description="显式股票代码")
    stock_name: Optional[str] = Field(None, description="显式股票名称")

    @model_validator(mode="after")
    def validate_input_presence(self):
        if not any(
            [
                (self.query or "").strip(),
                (self.stock_code or "").strip(),
                (self.stock_name or "").strip(),
            ]
        ):
            raise ValueError("query、stock_code、stock_name 至少需要提供一个")
        return self


class StockQueryThemeAttributionSchema(BaseModel):
    theme_id: str
    theme_name: str
    relation_type: str
    confidence: str
    reason: str
    matched_boards: List[str] = Field(default_factory=list)


class StockQueryNewsSummarySchema(BaseModel):
    summary: Optional[str] = None
    provider: Optional[str] = None
    headlines: List[str] = Field(default_factory=list)
    catalysts: List[str] = Field(default_factory=list)
    risk_events: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None


class StockQueryTextSupplementSchema(BaseModel):
    summary: Optional[str] = None
    provider: Optional[str] = None
    headlines: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)


class StockQueryConceptAttributionSchema(BaseModel):
    summary: Optional[str] = None
    primary_concept: Optional[str] = None
    concept_names: List[str] = Field(default_factory=list)
    matched_board_names: List[str] = Field(default_factory=list)
    matched_themes: List[StockQueryThemeAttributionSchema] = Field(default_factory=list)


class StockQueryContextSupplementSchema(BaseModel):
    profile: Optional[StockQueryTextSupplementSchema] = None
    announcements: Optional[StockQueryTextSupplementSchema] = None
    lockup: Optional[StockQueryTextSupplementSchema] = None
    concept_attribution: Optional[StockQueryConceptAttributionSchema] = None


class StockQueryFundamentalBlockSchema(BaseModel):
    status: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    source_chain: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class StockQueryFundamentalContextSchema(BaseModel):
    market: Optional[str] = None
    status: Optional[str] = None
    coverage: Dict[str, str] = Field(default_factory=dict)
    source_chain: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    elapsed_ms: Optional[int] = None
    valuation: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)
    growth: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)
    earnings: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)
    institution: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)
    capital_flow: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)
    dragon_tiger: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)
    boards: StockQueryFundamentalBlockSchema = Field(default_factory=StockQueryFundamentalBlockSchema)


class StockQueryAnalyzeResponse(BaseModel):
    query_id: Optional[str] = None
    stock_code: str
    stock_name: str
    instrument_type: Optional[str] = None
    instrument_label: Optional[str] = None
    current_price: Optional[float] = None
    pct_chg: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_ratio: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    total_mv: Optional[float] = None
    circ_mv: Optional[float] = None
    trend_score: Optional[float] = None
    signal: str
    pattern: Optional[str] = None
    support: Optional[float] = None
    pressure: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    bias_ma10: Optional[float] = None
    trend_status: Optional[str] = None
    buy_signal: Optional[str] = None
    selected_reasons: List[str] = Field(default_factory=list)
    excluded_reasons: List[str] = Field(default_factory=list)
    theme_attributions: List[StockQueryThemeAttributionSchema] = Field(default_factory=list)
    themes: List[StockQueryThemeAttributionSchema] = Field(default_factory=list)
    stock_news_summary: Optional[StockQueryNewsSummarySchema] = None
    stock_context_supplement: Optional[StockQueryContextSupplementSchema] = None
    fundamental_context: Optional[StockQueryFundamentalContextSchema] = None
    fundamental_coverage: Dict[str, str] = Field(default_factory=dict)
    fundamental_errors: List[str] = Field(default_factory=list)
    fundamental_details: Dict[str, Any] = Field(default_factory=dict)
    data_sources: Dict[str, Optional[str]] = Field(default_factory=dict)


class StockQueryTaskAcceptedSchema(BaseModel):
    task_id: str
    status: str = Field(default="pending")
    message: str


class StockQueryTaskStatusSchema(BaseModel):
    task_id: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    message: Optional[str] = None
    result: Optional[StockQueryAnalyzeResponse] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class StockQueryHistoryItemSchema(BaseModel):
    query_id: str
    status: str
    query_text: Optional[str] = None
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    instrument_type: Optional[str] = None
    instrument_label: Optional[str] = None
    signal: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[StockQueryAnalyzeResponse] = None


class StockQueryHistoryListResponse(BaseModel):
    items: List[StockQueryHistoryItemSchema] = Field(default_factory=list)


class StockDeepAnalysisCreateRequest(BaseModel):
    force_refresh: bool = Field(default=False, description="是否忽略已有结果并重新生成")


class StockDeepAnalysisMessageSchema(BaseModel):
    id: int
    analysis_id: str
    role: str
    content: str
    created_at: str


class StockDeepAnalysisItemSchema(BaseModel):
    analysis_id: str
    stock_code: str
    stock_name: str
    source_query_id: Optional[str] = None
    status: str
    action: Optional[str] = None
    summary: Optional[str] = None
    trade_plan: Dict[str, Any] = Field(default_factory=dict)
    technical: Dict[str, Any] = Field(default_factory=dict)
    fundamental: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    context_snapshot: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    messages: List[StockDeepAnalysisMessageSchema] = Field(default_factory=list)


class StockDeepAnalysisListResponse(BaseModel):
    items: List[StockDeepAnalysisItemSchema] = Field(default_factory=list)


class StockDeepAnalysisChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000, description="围绕本次深度分析的追问")


class StockDeepAnalysisChatResponse(BaseModel):
    analysis_id: str
    user_message: StockDeepAnalysisMessageSchema
    assistant_message: StockDeepAnalysisMessageSchema


class StockDeepAnalysisAlertRulesRequest(BaseModel):
    scan_interval_minutes: int = Field(default=5, ge=5, description="生成告警规则的扫描间隔，单位分钟")


class StockWatchlistUpsertRequest(BaseModel):
    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(description="股票名称")
    group_name: Optional[str] = Field(default="核心跟踪", description="观察池分组")
    note: Optional[str] = Field(default=None, description="备注")
    latest_signal: Optional[str] = Field(default=None, description="最近一次信号")
    latest_theme: Optional[str] = Field(default=None, description="最近一次辅助题材")
    alert_enabled: bool = Field(default=False, description="是否启用提醒")
    source_query_id: Optional[str] = Field(default=None, description="来源单股查询 ID")


class StockWatchlistItemSchema(BaseModel):
    stock_code: str
    stock_name: str
    group_name: Optional[str] = None
    note: Optional[str] = None
    latest_signal: Optional[str] = None
    latest_theme: Optional[str] = None
    alert_enabled: bool = False
    source_query_id: Optional[str] = None
    created_at: str
    updated_at: str


class StockWatchlistListResponse(BaseModel):
    items: List[StockWatchlistItemSchema] = Field(default_factory=list)


class StockAlertRuleUpsertRequest(BaseModel):
    stock_code: str
    stock_name: str
    rule_type: str
    threshold_value: Optional[float] = None
    scan_interval_minutes: int = Field(default=5, ge=5, description="扫描间隔，单位分钟，最小 5 分钟")
    enabled: bool = True
    note: Optional[str] = None
    source_query_id: Optional[str] = None


class StockAlertRuleUpdateRequest(BaseModel):
    threshold_value: Optional[float] = None
    scan_interval_minutes: Optional[int] = Field(default=None, ge=5, description="扫描间隔，单位分钟，最小 5 分钟")
    enabled: Optional[bool] = None
    note: Optional[str] = None


class StockAlertRuleDefaultsRequest(BaseModel):
    stock_code: str
    stock_name: str
    support_price: Optional[float] = None
    breakout_price: Optional[float] = None
    scan_interval_minutes: int = Field(default=5, ge=5, description="默认规则扫描间隔，单位分钟，最小 5 分钟")
    source_query_id: Optional[str] = None


class StockAlertRuleItemSchema(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    rule_type: str
    threshold_value: Optional[float] = None
    scan_interval_minutes: int = Field(default=5, ge=5)
    enabled: bool = True
    note: Optional[str] = None
    source_query_id: Optional[str] = None
    created_at: str
    updated_at: str


class StockAlertRuleListResponse(BaseModel):
    items: List[StockAlertRuleItemSchema] = Field(default_factory=list)


class StockAlertEventItemSchema(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    rule_id: int
    rule_type: str
    event_type: str
    title: str
    message: str
    dedupe_key: Optional[str] = None
    payload: Optional[dict] = None
    source_query_id: Optional[str] = None
    linked_analysis_id: Optional[str] = None
    created_at: str
    read_at: Optional[str] = None


class StockAlertEventListResponse(BaseModel):
    items: List[StockAlertEventItemSchema] = Field(default_factory=list)


class StockAlertEventMarkAllReadRequest(BaseModel):
    stock_code: Optional[str] = Field(default=None, description="可选股票代码；为空时标记全部为已读")


class StockAlertScanSummarySchema(BaseModel):
    scanned_rules: int = 0
    due_rules: int = 0
    triggered_events: int = 0
    skipped_rules: int = 0


class StockAlertLoopStatusSchema(BaseModel):
    enabled: bool = False
    running: bool = False
    base_tick_seconds: int = 60
    last_started_at: Optional[str] = None
    last_finished_at: Optional[str] = None
    last_error: Optional[str] = None
    last_summary: Optional[StockAlertScanSummarySchema] = None
