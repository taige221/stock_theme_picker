# -*- coding: utf-8 -*-
"""
===================================
Theme Event Radar - Schema
===================================

Schema definitions for dynamic theme-driven event radar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ThemeEventRuleSchema(BaseModel):
    """Rules for deciding whether a theme event should trigger."""

    min_keyword_hits: int = Field(default=1, ge=1)
    min_news_count: int = Field(default=1, ge=1)
    max_news_items: int = Field(default=10, ge=1)


class ThemeSignalRuleSchema(BaseModel):
    """Rules for technical confirmation after a theme event is detected."""

    strategy_mode: str = "event"
    min_breakout_pct: float = 3.0
    min_volume_ratio: float = 1.5
    max_bias_ma5_pct: float = 6.0
    min_limit_up_warning_pct: float = 9.0
    min_resonance_count: int = Field(default=3, ge=1)
    breakout_lookback_days: int = Field(default=10, ge=3)
    recent_limit_up_days: int = Field(default=10, ge=3)
    min_recent_strong_days: int = Field(default=2, ge=1)
    holding_min_trend_score: float = 50.0
    holding_max_bias_ma10_pct: float = 4.0
    holding_min_recent_strong_days: int = Field(default=1, ge=0)
    holding_support_tolerance_pct: float = 1.5
    holding_ma20_drift_tolerance_pct: float = 0.5


class ThemeDefinitionSchema(BaseModel):
    """Dynamic theme definition from registry."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    enabled: bool = True
    priority: int = 100
    keywords: List[str] = Field(default_factory=list)
    stock_pool: List[str] = Field(default_factory=list)
    concept_board_codes: List[str] = Field(default_factory=list)
    concept_board_names: List[str] = Field(default_factory=list)
    board_code_mappings: Dict[str, str] = Field(default_factory=dict)
    expansion_aliases: List[str] = Field(default_factory=list)
    concept_aliases: List[str] = Field(default_factory=list)
    event_rules: ThemeEventRuleSchema = Field(default_factory=ThemeEventRuleSchema)
    signal_rules: ThemeSignalRuleSchema = Field(default_factory=ThemeSignalRuleSchema)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ThemeRegistrySchema(BaseModel):
    """Top-level theme registry document."""

    version: int = 1
    themes: List[ThemeDefinitionSchema] = Field(default_factory=list)


class ThemeNewsItemSchema(BaseModel):
    """Minimal normalized news item for a theme event."""

    title: str
    snippet: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    published_date: Optional[str] = None
    provider: Optional[str] = None
    matched_keywords: List[str] = Field(default_factory=list)


class ThemeEventSchema(BaseModel):
    """Detected theme event."""

    theme_id: str
    theme_name: str
    event_score: int = Field(default=0, ge=0, le=100)
    triggered: bool = False
    trigger_reason: str = ""
    matched_keywords: List[str] = Field(default_factory=list)
    matched_news_count: int = 0
    news_items: List[ThemeNewsItemSchema] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


class ThemeStockSignalSchema(BaseModel):
    """Technical signal for a stock under a specific theme event."""

    theme_id: str
    theme_name: str
    stock_code: str
    stock_name: Optional[str] = None
    signal_level: str
    triggered: bool = False
    reasons: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ThemeAlertResultSchema(BaseModel):
    """Final output of the theme alert pipeline."""

    generated_at: datetime = Field(default_factory=datetime.now)
    scanned_theme_ids: List[str] = Field(default_factory=list)
    events: List[ThemeEventSchema] = Field(default_factory=list)
    signals: List[ThemeStockSignalSchema] = Field(default_factory=list)
