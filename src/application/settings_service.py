# -*- coding: utf-8 -*-
"""Runtime settings service for editable environment-backed configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Dict, List, Optional

from theme_picker.api.schemas import (
    RuntimeSettingFieldSchema,
    RuntimeSettingOptionSchema,
    RuntimeSettingSectionSchema,
    RuntimeSettingsResponseSchema,
    RuntimeSettingsUpdateResponseSchema,
)
from theme_picker.config import Config, REPO_ROOT, get_config, setup_env
from theme_picker.search_service import reset_search_service


@dataclass(frozen=True)
class RuntimeSettingDefinition:
    key: str
    section_id: str
    label: str
    input_type: str
    description: str = ""
    placeholder: str = ""
    secret: bool = False
    requires_restart: bool = False
    options: List[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RuntimeSettingSectionDefinition:
    id: str
    title: str
    description: str


SECTION_DEFINITIONS: List[RuntimeSettingSectionDefinition] = [
    RuntimeSettingSectionDefinition(
        id="runtime",
        title="运行与告警",
        description="适合本地直接调的运行开关和轮询节奏。",
    ),
    RuntimeSettingSectionDefinition(
        id="stock-query",
        title="单股查询",
        description="控制单股查询的超时、代理和缓存回退行为。",
    ),
    RuntimeSettingSectionDefinition(
        id="analysis",
        title="深度分析与搜索",
        description="设置深度分析模型行为，以及新闻搜索窗口。",
    ),
    RuntimeSettingSectionDefinition(
        id="providers",
        title="模型与数据源",
        description="配置常用模型、搜索和行情数据源密钥。",
    ),
]

SETTING_DEFINITIONS: List[RuntimeSettingDefinition] = [
    RuntimeSettingDefinition(
        key="DATABASE_PATH",
        section_id="runtime",
        label="数据库路径",
        input_type="text",
        description="SQLite 数据库文件路径。",
        placeholder="./data/stock_analysis.db",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="SQLITE_WAL_ENABLED",
        section_id="runtime",
        label="启用 SQLite WAL",
        input_type="boolean",
        description="提高并发读写表现，修改后建议重启。",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="SQLITE_BUSY_TIMEOUT_MS",
        section_id="runtime",
        label="SQLite busy timeout（毫秒）",
        input_type="number",
        placeholder="5000",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="STOCK_ALERT_LOOP_ENABLED",
        section_id="runtime",
        label="后台告警循环",
        input_type="boolean",
        description="控制 FastAPI 进程内的告警循环是否启用。",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="STOCK_ALERT_LOOP_BASE_TICK_SECONDS",
        section_id="runtime",
        label="告警轮询基础 Tick（秒）",
        input_type="number",
        description="最小建议 5 秒；改动后建议重启服务使循环参数生效。",
        placeholder="60",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="ENABLE_REALTIME_QUOTE",
        section_id="runtime",
        label="启用实时行情",
        input_type="boolean",
        description="关闭后查询将更依赖缓存或静态信息。",
    ),
    RuntimeSettingDefinition(
        key="PREFETCH_REALTIME_QUOTES",
        section_id="runtime",
        label="预取实时行情",
        input_type="boolean",
        description="在部分查询链路里提前取行情，降低等待感。",
    ),
    RuntimeSettingDefinition(
        key="INFORMATION_WATCH_LOOP_ENABLED",
        section_id="runtime",
        label="信息观察池后台循环",
        input_type="boolean",
        description="控制进程内信息观察池与开放发现池后台循环是否启用。",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="INFORMATION_WATCH_QUERY_TIMEOUT_SECONDS",
        section_id="runtime",
        label="信息观察搜索超时（秒）",
        input_type="number",
        description="信息观察池和开放发现池搜索阶段的单次请求超时。",
        placeholder="8",
    ),
    RuntimeSettingDefinition(
        key="INFORMATION_L1_DIRECT_ENABLED",
        section_id="runtime",
        label="启用 L1 公告直连",
        input_type="boolean",
        description="开启后会优先尝试巨潮公告直连，作为一级硬源确认。",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="INFORMATION_L1_DIRECT_TIMEOUT_SECONDS",
        section_id="runtime",
        label="L1 公告直连超时（秒）",
        input_type="number",
        description="巨潮公告直连单次请求的超时预算。",
        placeholder="10",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="OPEN_DISCOVERY_POOL_ENABLED",
        section_id="runtime",
        label="启用开放发现池",
        input_type="boolean",
        description="允许后台定时全局探索新的产业事件苗头。",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="OPEN_DISCOVERY_SCAN_INTERVAL_MINUTES",
        section_id="runtime",
        label="开放发现扫描间隔（分钟）",
        input_type="number",
        placeholder="120",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="THEME_FACTOR_SCAN_AUTO_ENABLED",
        section_id="runtime",
        label="自动触发主题因子扫描",
        input_type="boolean",
        description="当高质量信息事件出现后自动继续跑主题因子扫描。",
        requires_restart=True,
    ),
    RuntimeSettingDefinition(
        key="REALTIME_SOURCE_PRIORITY",
        section_id="runtime",
        label="实时行情优先级",
        input_type="text",
        description="逗号分隔，例如 tencent,akshare_sina,efinance。",
        placeholder="tencent,akshare_sina,efinance,akshare_em",
    ),
    RuntimeSettingDefinition(
        key="THEME_REALTIME_SOURCE_PRIORITY",
        section_id="runtime",
        label="主题行情优先级",
        input_type="text",
        description="主题选股使用的实时行情源优先级。",
        placeholder="tencent,akshare_sina,efinance,akshare_em,tushare",
    ),
    RuntimeSettingDefinition(
        key="THEME_REALTIME_QUOTE_TIMEOUT",
        section_id="runtime",
        label="主题实时行情超时（秒）",
        input_type="number",
        placeholder="15",
    ),
    RuntimeSettingDefinition(
        key="THEME_TENCENT_QUOTE_TIMEOUT",
        section_id="runtime",
        label="腾讯行情超时（秒）",
        input_type="number",
        placeholder="15",
    ),
    RuntimeSettingDefinition(
        key="THEME_PICKER_TASK_HISTORY_RETENTION_DAYS",
        section_id="runtime",
        label="主题任务历史保留天数",
        input_type="number",
        placeholder="30",
    ),
    RuntimeSettingDefinition(
        key="THEME_PICKER_TASK_HISTORY_CLEANUP_BATCH_SIZE",
        section_id="runtime",
        label="主题任务历史清理批次",
        input_type="number",
        placeholder="200",
    ),
    RuntimeSettingDefinition(
        key="STOCK_LIST",
        section_id="runtime",
        label="默认股票池",
        input_type="text",
        description="逗号分隔股票代码，例如 600519,000001,300750。",
        placeholder="600519,000001,300750",
    ),
    RuntimeSettingDefinition(
        key="STOCK_QUERY_DAILY_FETCH_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="日线抓取超时（秒）",
        input_type="number",
        placeholder="8",
    ),
    RuntimeSettingDefinition(
        key="STOCK_QUERY_DAILY_UNPROXY_ENABLED",
        section_id="stock-query",
        label="日线抓取临时禁用代理",
        input_type="boolean",
        description="避免本地代理误伤国内数据源。",
    ),
    RuntimeSettingDefinition(
        key="STOCK_QUERY_ALLOW_DAILY_CACHE_FALLBACK",
        section_id="stock-query",
        label="允许日线缓存回退",
        input_type="boolean",
        description="在线日线抓取失败后退回本地缓存。",
    ),
    RuntimeSettingDefinition(
        key="STOCK_QUERY_CHIP_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="筹码分布超时（秒）",
        input_type="number",
        placeholder="2.5",
    ),
    RuntimeSettingDefinition(
        key="STOCK_QUERY_TEXT_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="文本情报超时（秒）",
        input_type="number",
        placeholder="10",
    ),
    RuntimeSettingDefinition(
        key="STOCK_QUERY_NEWS_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="新闻摘要超时（秒）",
        input_type="number",
        placeholder="10",
    ),
    RuntimeSettingDefinition(
        key="ETF_DAILY_BAR_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="ETF 日K超时（秒）",
        input_type="number",
        placeholder="8",
    ),
    RuntimeSettingDefinition(
        key="ETF_MOOTDX_QUOTE_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="ETF mootdx 盘口超时（秒）",
        input_type="number",
        placeholder="8",
    ),
    RuntimeSettingDefinition(
        key="ETF_TOP_HOLDINGS_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="ETF 重仓股超时（秒）",
        input_type="number",
        placeholder="12",
    ),
    RuntimeSettingDefinition(
        key="ETF_DAILY_METRICS_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="ETF 日频指标超时（秒）",
        input_type="number",
        placeholder="12",
    ),
    RuntimeSettingDefinition(
        key="ETF_ESTIMATED_IOPV_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="ETF IOPV 估算超时（秒）",
        input_type="number",
        placeholder="8",
    ),
    RuntimeSettingDefinition(
        key="FUNDAMENTAL_STAGE_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="基本面总预算（秒）",
        input_type="number",
        placeholder="25",
    ),
    RuntimeSettingDefinition(
        key="FUNDAMENTAL_FETCH_TIMEOUT_SECONDS",
        section_id="stock-query",
        label="单个基本面块超时（秒）",
        input_type="number",
        placeholder="12",
    ),
    RuntimeSettingDefinition(
        key="ENABLE_EASTMONEY_PATCH",
        section_id="stock-query",
        label="启用东财补丁",
        input_type="boolean",
        description="按现有代码路径启用东财相关兜底行为。",
    ),
    RuntimeSettingDefinition(
        key="DEEP_ANALYSIS_LLM_ENABLED",
        section_id="analysis",
        label="启用深度分析 LLM",
        input_type="boolean",
    ),
    RuntimeSettingDefinition(
        key="DEEP_ANALYSIS_LLM_TIMEOUT_SECONDS",
        section_id="analysis",
        label="深度分析超时（秒）",
        input_type="number",
        placeholder="45",
    ),
    RuntimeSettingDefinition(
        key="DEEP_ANALYSIS_LITELLM_MODEL",
        section_id="analysis",
        label="深度分析专用模型",
        input_type="text",
        placeholder="openai/gpt-5.5",
    ),
    RuntimeSettingDefinition(
        key="DEEP_ANALYSIS_LLM_REASONING_EFFORT",
        section_id="analysis",
        label="深度分析推理强度",
        input_type="select",
        options=[
            ("minimal", "minimal"),
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("xhigh", "xhigh"),
        ],
    ),
    RuntimeSettingDefinition(
        key="DEEP_ANALYSIS_LLM_VERBOSITY",
        section_id="analysis",
        label="深度分析输出密度",
        input_type="select",
        options=[
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
        ],
    ),
    RuntimeSettingDefinition(
        key="NEWS_MAX_AGE_DAYS",
        section_id="analysis",
        label="新闻最大回看天数",
        input_type="number",
        placeholder="3",
    ),
    RuntimeSettingDefinition(
        key="NEWS_STRATEGY_PROFILE",
        section_id="analysis",
        label="新闻分析窗口",
        input_type="select",
        options=[
            ("ultra_short", "ultra_short"),
            ("short", "short"),
            ("medium", "medium"),
            ("long", "long"),
        ],
    ),
    RuntimeSettingDefinition(
        key="NEWS_PROVIDER_PRIORITY",
        section_id="analysis",
        label="新闻检索数据源优先级",
        input_type="text",
        description="逗号分隔，例如 anspire,bocha,tavily,brave,serpapi,minimax,searxng。",
        placeholder="anspire,bocha,tavily,brave,serpapi,minimax,searxng",
    ),
    RuntimeSettingDefinition(
        key="SEARXNG_PUBLIC_INSTANCES_ENABLED",
        section_id="analysis",
        label="启用公开 SearXNG 实例",
        input_type="boolean",
    ),
    RuntimeSettingDefinition(
        key="SEARXNG_BASE_URLS",
        section_id="analysis",
        label="SearXNG Base URLs",
        input_type="text",
        description="逗号分隔多个自建 SearXNG 地址。",
        placeholder="http://127.0.0.1:8080",
    ),
    RuntimeSettingDefinition(
        key="LITELLM_MODEL",
        section_id="providers",
        label="主模型",
        input_type="text",
        placeholder="openai/gpt-5.5",
    ),
    RuntimeSettingDefinition(
        key="LITELLM_FALLBACK_MODELS",
        section_id="providers",
        label="Fallback 模型列表",
        input_type="text",
        description="逗号分隔多个后备模型。",
        placeholder="openai/gpt-5.5-mini,deepseek/deepseek-v4-flash",
    ),
    RuntimeSettingDefinition(
        key="AGENT_LITELLM_MODEL",
        section_id="providers",
        label="Agent 主模型",
        input_type="text",
        placeholder="openai/gpt-5.5",
    ),
    RuntimeSettingDefinition(
        key="OPENAI_BASE_URL",
        section_id="providers",
        label="OpenAI 兼容 Base URL",
        input_type="text",
        placeholder="https://api.openai.com/v1",
    ),
    RuntimeSettingDefinition(
        key="OPENAI_MODEL",
        section_id="providers",
        label="默认 OpenAI 模型名",
        input_type="text",
        placeholder="gpt-5.5",
    ),
    RuntimeSettingDefinition(
        key="AIHUBMIX_KEY",
        section_id="providers",
        label="AIHubMix Key",
        input_type="password",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="OPENAI_API_KEY",
        section_id="providers",
        label="OpenAI API Key",
        input_type="password",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="DEEPSEEK_API_KEY",
        section_id="providers",
        label="DeepSeek API Key",
        input_type="password",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="TAVILY_API_KEYS",
        section_id="providers",
        label="Tavily API Keys",
        input_type="password",
        description="支持逗号分隔多个 Key；运行时会与 TAVILY_API_KEY 合并生效。",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="BOCHA_API_KEYS",
        section_id="providers",
        label="Bocha API Keys",
        input_type="password",
        description="支持逗号分隔多个 Key。",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="BRAVE_API_KEYS",
        section_id="providers",
        label="Brave API Keys",
        input_type="password",
        description="支持逗号分隔多个 Key。",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="SERPAPI_API_KEY",
        section_id="providers",
        label="SerpApi 单值 Key",
        input_type="password",
        description="兼容旧配置；运行时会与 SERPAPI_API_KEYS 合并生效。",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="SERPAPI_API_KEYS",
        section_id="providers",
        label="SerpApi Keys",
        input_type="password",
        description="支持逗号分隔多个 Key；运行时会与 SERPAPI_API_KEY 合并生效。",
        secret=True,
    ),
    RuntimeSettingDefinition(
        key="TUSHARE_TOKEN",
        section_id="providers",
        label="Tushare Token",
        input_type="password",
        secret=True,
    ),
]


class RuntimeSettingsService:
    """Expose a small, validated, env-backed settings surface for the Web UI."""

    def __init__(self) -> None:
        self._definitions = {definition.key: definition for definition in SETTING_DEFINITIONS}
        self._section_definitions = {section.id: section for section in SECTION_DEFINITIONS}

    def get_settings(self) -> RuntimeSettingsResponseSchema:
        config = get_config()
        sections: List[RuntimeSettingSectionSchema] = []

        for section in SECTION_DEFINITIONS:
            fields = [
                self._build_field_schema(definition)
                for definition in SETTING_DEFINITIONS
                if definition.section_id == section.id
            ]
            sections.append(
                RuntimeSettingSectionSchema(
                    id=section.id,
                    title=section.title,
                    description=section.description,
                    fields=fields,
                )
            )

        return RuntimeSettingsResponseSchema(
            env_file=str(self._get_env_path()),
            sections=sections,
            validation_issues=config.validate(),
        )

    def update_settings(self, values: Dict[str, Optional[str]]) -> RuntimeSettingsUpdateResponseSchema:
        if not values:
            return RuntimeSettingsUpdateResponseSchema(message="没有可保存的变更。")

        normalized_values: Dict[str, str] = {}
        updated_keys: List[str] = []
        restart_required_keys: List[str] = []

        for key, raw_value in values.items():
            definition = self._definitions.get(key)
            if definition is None:
                raise ValueError(f"不支持修改环境变量: {key}")

            normalized_value = self._normalize_value(definition, raw_value)
            normalized_values[key] = normalized_value
            updated_keys.append(key)
            if definition.requires_restart:
                restart_required_keys.append(key)

        self._write_env_values(normalized_values)
        Config.reset_instance()
        setup_env(override=True)
        reset_search_service()
        config = get_config()

        message = "设置已保存到 .env"
        if restart_required_keys:
            message += "；部分字段需重启服务后完全生效"

        return RuntimeSettingsUpdateResponseSchema(
            message=message,
            updated_keys=updated_keys,
            restart_required_keys=restart_required_keys,
            validation_issues=config.validate(),
        )

    def _build_field_schema(self, definition: RuntimeSettingDefinition) -> RuntimeSettingFieldSchema:
        value = Config._resolve_env_value(definition.key, default="") or ""
        return RuntimeSettingFieldSchema(
            key=definition.key,
            label=definition.label,
            description=definition.description or None,
            input_type=definition.input_type,
            value=value,
            placeholder=definition.placeholder or None,
            secret=definition.secret,
            requires_restart=definition.requires_restart,
            options=[
                RuntimeSettingOptionSchema(value=option_value, label=option_label)
                for option_value, option_label in definition.options
            ],
        )

    def _normalize_value(self, definition: RuntimeSettingDefinition, value: Optional[str]) -> str:
        normalized = "" if value is None else str(value).strip()

        if definition.input_type == "boolean":
            lowered = normalized.lower()
            truthy_values = {"1", "true", "yes", "on"}
            falsey_values = {"0", "false", "no", "off", ""}
            if lowered in truthy_values:
                return "true"
            if lowered in falsey_values:
                return "false"
            raise ValueError(f"{definition.label} 仅支持 true / false")

        if definition.input_type == "number":
            if not normalized:
                raise ValueError(f"{definition.label} 不能为空")
            if not re.fullmatch(r"-?\d+(\.\d+)?", normalized):
                raise ValueError(f"{definition.label} 必须是数字")
            return normalized

        if definition.input_type == "select":
            allowed_values = {option_value for option_value, _ in definition.options}
            if normalized not in allowed_values:
                raise ValueError(f"{definition.label} 取值不合法")
            return normalized

        return normalized

    def _get_env_path(self) -> Path:
        env_file = Config._resolve_env_value("ENV_FILE")
        return Path(env_file) if env_file else (REPO_ROOT / ".env")

    def _write_env_values(self, values: Dict[str, str]) -> None:
        env_path = self._get_env_path()
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        updated_lines = list(existing_lines)
        remaining = dict(values)

        for index, line in enumerate(updated_lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            key, separator, _ = line.partition("=")
            if not separator:
                continue

            normalized_key = key.strip()
            if normalized_key not in remaining:
                continue

            updated_lines[index] = f"{normalized_key}={remaining.pop(normalized_key)}"

        if remaining:
            if updated_lines and updated_lines[-1].strip():
                updated_lines.append("")
            for key, value in remaining.items():
                updated_lines.append(f"{key}={value}")

        env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
