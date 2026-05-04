# -*- coding: utf-8 -*-
"""
===================================
主题选股聚合服务
===================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from theme_picker.core.theme_alert_pipeline import ThemeAlertPipeline
from theme_picker.domain.theme_event import ThemeAlertResultSchema, ThemeDefinitionSchema, ThemeEventSchema
from theme_picker.search_service import SearchService
from theme_picker.application.registry_service import ThemeRegistryService
from theme_picker.infrastructure.event_scanner import ThemeEventScanner
from theme_picker.infrastructure.expansion_service import ThemeExpansionService
from theme_picker.infrastructure.runtime import get_theme_picker_config


@dataclass
class ThemePickerQueryPayload:
    theme_id: Optional[str]
    theme_name: Optional[str]
    board_code: Optional[str]
    board_name: Optional[str]
    strategy_mode: str
    max_candidates: int


@dataclass
class ThemeInsightPayload:
    theme_name: str
    event_status: str
    event_score: Optional[float] = None
    matched_keywords: List[str] = field(default_factory=list)
    news_count: int = 0
    heat_level: Optional[str] = None
    board_mapping_path: Optional[str] = None
    board_candidate_count: Optional[int] = None
    primary_catalyst: Optional[str] = None


@dataclass
class ThemePickerStockItemPayload:
    rank: int
    stock_code: str
    stock_name: str
    signal_level: str
    current_pattern: Optional[str] = None
    selection_reason: str = ""
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
    mini_reasons: List[str] = field(default_factory=list)


@dataclass
class ThemePickerSelectedStockPayload:
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
    news_summary: List[str] = field(default_factory=list)
    selected_reasons: List[str] = field(default_factory=list)
    risk_reasons: List[str] = field(default_factory=list)
    data_sources: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class ThemePickerSourceInfoPayload:
    board_source: Optional[str] = None
    board_fallback_used: Optional[bool] = None
    cache_hit: Optional[bool] = None
    source_pills: List[str] = field(default_factory=list)
    note: Optional[str] = None
    response_schema_version: int = 2
    history_repaired: Optional[bool] = None
    key_levels_backfilled: Optional[bool] = None
    board_source_confidence: Optional[str] = None
    pricing_source: Optional[str] = None


_DIRECT_BOARD_SOURCE_MAP = {
    "BK": "eastmoney_board",
    ".DC": "tushare_dc",
}

_SIGNAL_LEVEL_LABELS = {
    "持有候选": "持有候选",
    "低吸观察": "低吸观察",
    "主题触发": "主题触发",
    "不宜追高": "不宜追高",
    "可参与": "优先关注",
    "盘中异动": "优先关注",
}

_SIGNAL_LEVEL_RANK = {
    "优先关注": 0,
    "持有候选": 1,
    "低吸观察": 2,
    "主题触发": 3,
    "不宜追高": 4,
}


class ThemePickerService:
    RESPONSE_SCHEMA_VERSION = 2

    def __init__(
        self,
        *,
        registry_service: Optional[ThemeRegistryService] = None,
        pipeline: Optional[ThemeAlertPipeline] = None,
    ):
        self.registry_service = registry_service or ThemeRegistryService()
        self.pipeline = pipeline or self._build_pipeline(self.registry_service)

    @staticmethod
    def _build_pipeline(registry_service: ThemeRegistryService) -> ThemeAlertPipeline:
        config = get_theme_picker_config()
        search_service = SearchService(
            bocha_keys=config.bocha_api_keys,
            tavily_keys=config.tavily_api_keys,
            anspire_keys=config.anspire_api_keys,
            brave_keys=config.brave_api_keys,
            serpapi_keys=config.serpapi_keys,
            minimax_keys=config.minimax_api_keys,
            searxng_base_urls=config.searxng_base_urls,
            searxng_public_instances_enabled=config.searxng_public_instances_enabled,
            news_max_age_days=config.news_max_age_days,
            news_strategy_profile=getattr(config, "news_strategy_profile", "short"),
        )
        event_scanner = ThemeEventScanner(search_service=search_service)
        expansion_service = ThemeExpansionService(search_service=search_service)
        return ThemeAlertPipeline(
            registry_service=registry_service,
            event_scanner=event_scanner,
            expansion_service=expansion_service,
        )

    def list_themes(self) -> Dict[str, Any]:
        items = []
        for theme in self.registry_service.list_themes(enabled_only=True):
            items.append(
                {
                    "id": theme.id,
                    "name": theme.name,
                    "board_codes": list(theme.concept_board_codes or []),
                    "board_names": list(theme.concept_board_names or []),
                    "strategy_mode": theme.signal_rules.strategy_mode,
                    "enabled": theme.enabled,
                }
            )
        return {"items": items}

    def scan(self, request) -> Dict[str, Any]:
        resolved = self._resolve_input_theme(request)
        mode = resolved["mode"]
        themes = resolved["themes"]

        if mode == "direct":
            result = self._run_direct_board_replay(
                themes,
                max_expanded_candidates=request.max_candidates,
            )
        else:
            result = self.pipeline.run(
                theme_ids=[],
                extra_themes=themes,
                max_expanded_candidates=request.max_candidates,
                triggered_only=not request.include_untriggered,
            )

        return self._build_response(request, themes, result)

    @classmethod
    def normalize_response_payload(
        cls,
        payload: Optional[Dict[str, Any]],
        db: Any = None,
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        if not isinstance(payload, dict):
            return payload, False

        normalized = dict(payload)
        changed = False
        repaired = False
        key_levels_backfilled = False
        source_info = cls._ensure_source_info_dict(normalized)
        if source_info.get("response_schema_version") != cls.RESPONSE_SCHEMA_VERSION:
            source_info["response_schema_version"] = cls.RESPONSE_SCHEMA_VERSION
            changed = True
        selected_stock = normalized.get("selected_stock")
        if not isinstance(selected_stock, dict):
            selected_stock = normalized.get("selectedStock")
        selected_stock_code = ""
        if isinstance(selected_stock, dict):
            selected_stock_code = str(
                selected_stock.get("stock_code") or selected_stock.get("stockCode") or ""
            ).strip().upper()

        raw_stocks = normalized.get("stocks")
        if isinstance(raw_stocks, list):
            deduped_stocks: List[Dict[str, Any]] = []
            stock_index: Dict[str, Dict[str, Any]] = {}
            for item in raw_stocks:
                if not isinstance(item, dict):
                    deduped_stocks.append(item)
                    continue
                stock_code = str(item.get("stock_code") or item.get("stockCode") or "").strip().upper()
                if not stock_code:
                    deduped_stocks.append(item)
                    continue
                existing = stock_index.get(stock_code)
                if existing is None:
                    cloned = dict(item)
                    if selected_stock_code and stock_code == selected_stock_code:
                        stock_changed = cls._hydrate_stock_item_from_selected_stock(cloned, selected_stock)
                        changed = changed or stock_changed
                        repaired = repaired or stock_changed
                    stock_index[stock_code] = cloned
                    deduped_stocks.append(cloned)
                    continue

                merged_reasons = list(
                    dict.fromkeys(
                        [
                            *(existing.get("mini_reasons") or existing.get("miniReasons") or []),
                            *(item.get("mini_reasons") or item.get("miniReasons") or []),
                        ]
                    )
                )
                if "mini_reasons" in existing:
                    existing["mini_reasons"] = merged_reasons
                elif "miniReasons" in existing:
                    existing["miniReasons"] = merged_reasons
                changed = True
                repaired = True

            if isinstance(selected_stock, dict) and selected_stock_code:
                for item in deduped_stocks:
                    if not isinstance(item, dict):
                        continue
                    stock_code = str(item.get("stock_code") or item.get("stockCode") or "").strip().upper()
                    if stock_code != selected_stock_code:
                        continue
                    stock_changed = cls._hydrate_stock_item_from_selected_stock(item, selected_stock)
                    changed = changed or stock_changed
                    repaired = repaired or stock_changed
                    break

            if db is not None:
                for item in deduped_stocks:
                    if not isinstance(item, dict):
                        continue
                    stock_changed = cls._hydrate_key_levels_from_daily_data(item, db)
                    changed = changed or stock_changed
                    repaired = repaired or stock_changed
                    key_levels_backfilled = key_levels_backfilled or stock_changed
                if isinstance(selected_stock, dict):
                    selected_changed = cls._hydrate_selected_stock_from_daily_data(selected_stock, db)
                    changed = changed or selected_changed
                    repaired = repaired or selected_changed
                    key_levels_backfilled = key_levels_backfilled or selected_changed

            for idx, item in enumerate(deduped_stocks, start=1):
                if isinstance(item, dict):
                    rank_key = "rank" if "rank" in item else ("Rank" if "Rank" in item else None)
                    if rank_key is not None and item.get(rank_key) != idx:
                        item[rank_key] = idx
                        changed = True

            if len(deduped_stocks) != len(raw_stocks):
                changed = True
                repaired = True
            normalized["stocks"] = deduped_stocks

            theme_insight = normalized.get("theme_insight")
            if isinstance(theme_insight, dict):
                candidate_key = None
                if "board_candidate_count" in theme_insight:
                    candidate_key = "board_candidate_count"
                elif "boardCandidateCount" in theme_insight:
                    candidate_key = "boardCandidateCount"
                if candidate_key is not None and theme_insight.get(candidate_key) != len(deduped_stocks):
                    theme_insight[candidate_key] = len(deduped_stocks)
                    changed = True
                    repaired = True

        source_info["history_repaired"] = repaired or bool(source_info.get("history_repaired"))
        source_info["key_levels_backfilled"] = key_levels_backfilled or bool(source_info.get("key_levels_backfilled"))
        source_info["board_source_confidence"] = source_info.get("board_source_confidence") or cls._derive_board_source_confidence(
            source_info.get("board_source"),
            source_info.get("board_fallback_used"),
        )
        source_info["pricing_source"] = source_info.get("pricing_source") or cls._infer_pricing_source_from_payload(normalized)

        return normalized, changed

    @staticmethod
    def _ensure_source_info_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
        source_info = payload.get("source_info")
        if isinstance(source_info, dict):
            return source_info
        source_info = payload.get("sourceInfo")
        if isinstance(source_info, dict):
            payload["source_info"] = source_info
            return source_info
        source_info = {}
        payload["source_info"] = source_info
        return source_info

    @classmethod
    def _hydrate_key_levels_from_daily_data(
        cls,
        stock_item: Dict[str, Any],
        db: Any,
    ) -> bool:
        stock_code = str(stock_item.get("stock_code") or stock_item.get("stockCode") or "").strip().upper()
        if not stock_code:
            return False
        if all(
            stock_item.get(key) not in (None, "")
            for key in ("current_price", "support_level", "pressure_level")
        ) or all(
            stock_item.get(key) not in (None, "")
            for key in ("currentPrice", "supportLevel", "pressureLevel")
        ):
            return False

        snapshot = cls._build_daily_snapshot(stock_code, db)
        if snapshot is None:
            return False

        changed = False
        for target_key, snapshot_key in (
            ("current_price", "current_price"),
            ("support_level", "support_level"),
            ("pressure_level", "pressure_level"),
        ):
            alt_key = cls._to_camel_key(target_key)
            existing = stock_item.get(target_key, stock_item.get(alt_key))
            if existing not in (None, ""):
                continue
            value = snapshot.get(snapshot_key)
            if value in (None, ""):
                continue
            if target_key in stock_item:
                stock_item[target_key] = value
            elif alt_key in stock_item:
                stock_item[alt_key] = value
            else:
                stock_item[target_key] = value
            changed = True
        return changed

    @classmethod
    def _hydrate_selected_stock_from_daily_data(
        cls,
        selected_stock: Dict[str, Any],
        db: Any,
    ) -> bool:
        stock_code = str(selected_stock.get("stock_code") or selected_stock.get("stockCode") or "").strip().upper()
        if not stock_code:
            return False

        snapshot = cls._build_daily_snapshot(stock_code, db)
        if snapshot is None:
            return False

        changed = False
        field_map = (
            ("current_price", "current_price"),
            ("support_level", "support_level"),
            ("pressure_level", "pressure_level"),
            ("ma10", "ma10"),
            ("ma20", "ma20"),
            ("bias_ma10", "bias_ma10"),
            ("bias_ma20", "bias_ma20"),
            ("recent_strong_days", "recent_strong_days"),
        )
        for target_key, snapshot_key in field_map:
            alt_key = cls._to_camel_key(target_key)
            existing = selected_stock.get(target_key, selected_stock.get(alt_key))
            if existing not in (None, ""):
                continue
            value = snapshot.get(snapshot_key)
            if value in (None, ""):
                continue
            if target_key in selected_stock:
                selected_stock[target_key] = value
            elif alt_key in selected_stock:
                selected_stock[alt_key] = value
            else:
                selected_stock[target_key] = value
            changed = True
        return changed

    @classmethod
    def _build_daily_snapshot(cls, stock_code: str, db: Any) -> Optional[Dict[str, Any]]:
        try:
            records = db.get_latest_data(stock_code, days=21)
        except Exception:
            return None
        if not records:
            return None

        latest = records[0]
        current_price = cls._safe_float(getattr(latest, "close", None))
        ma10 = cls._safe_float(getattr(latest, "ma10", None))
        ma20 = cls._safe_float(getattr(latest, "ma20", None))
        support_level = ma10 or ma20

        lookback_records = [record for record in records[1:11] if getattr(record, "high", None) is not None]
        if not lookback_records:
            lookback_records = [record for record in records[:10] if getattr(record, "high", None) is not None]
        pressure_level = None
        if lookback_records:
            try:
                pressure_level = max(float(getattr(record, "high")) for record in lookback_records)
            except Exception:
                pressure_level = None

        recent_strong_days = 0
        for record in records[:10]:
            pct_chg = cls._safe_float(getattr(record, "pct_chg", None))
            if pct_chg is not None and pct_chg > 5:
                recent_strong_days += 1

        return {
            "current_price": current_price,
            "support_level": support_level,
            "pressure_level": pressure_level,
            "ma10": ma10,
            "ma20": ma20,
            "bias_ma10": cls._calculate_bias(current_price or 0.0, ma10) if current_price is not None else None,
            "bias_ma20": cls._calculate_bias(current_price or 0.0, ma20) if current_price is not None else None,
            "recent_strong_days": recent_strong_days,
        }

    @staticmethod
    def _to_camel_key(snake_key: str) -> str:
        parts = snake_key.split("_")
        return parts[0] + "".join(part.capitalize() for part in parts[1:])

    @staticmethod
    def _calculate_bias(price: float, ma_value: Optional[float]) -> Optional[float]:
        if ma_value in (None, 0):
            return None
        try:
            return (float(price) / float(ma_value) - 1.0) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @classmethod
    def _hydrate_stock_item_from_selected_stock(
        cls,
        stock_item: Dict[str, Any],
        selected_stock: Optional[Dict[str, Any]],
    ) -> bool:
        if not isinstance(stock_item, dict) or not isinstance(selected_stock, dict):
            return False

        changed = False
        field_pairs = [
            (("current_price", "currentPrice"), ("current_price", "currentPrice")),
            (("support_level", "supportLevel"), ("support_level", "supportLevel")),
            (("pressure_level", "pressureLevel"), ("pressure_level", "pressureLevel")),
        ]

        for target_keys, source_keys in field_pairs:
            current_value = None
            current_key = None
            for key in target_keys:
                if key in stock_item:
                    current_key = key
                    current_value = stock_item.get(key)
                    break

            if current_value not in (None, ""):
                continue

            source_value = None
            for key in source_keys:
                if selected_stock.get(key) not in (None, ""):
                    source_value = selected_stock.get(key)
                    break

            if source_value in (None, ""):
                continue

            target_key = current_key or target_keys[0]
            stock_item[target_key] = source_value
            changed = True

        return changed

    def _resolve_input_theme(self, request) -> Dict[str, Any]:
        strategy_mode = request.strategy_mode

        if request.theme_id:
            theme = self.registry_service.get_theme(request.theme_id.strip())
            if theme is None:
                raise ValueError(f"未找到主题: {request.theme_id}")
            copied = theme.model_copy(deep=True)
            copied.signal_rules.strategy_mode = strategy_mode
            return {"mode": "scan", "themes": [copied]}

        board_codes = self._parse_csv_values(request.board_code)
        board_names = self._parse_csv_values(request.board_name)
        if board_codes or board_names:
            direct_themes = self._build_direct_board_themes(
                board_codes,
                board_names,
                strategy_mode=strategy_mode,
            )
            if direct_themes:
                return {"mode": "direct", "themes": direct_themes}

        theme_name = (request.theme_name or "").strip()
        if theme_name:
            matched = self._find_registered_theme_by_name(theme_name)
            if matched is not None:
                copied = matched.model_copy(deep=True)
                copied.signal_rules.strategy_mode = strategy_mode
                return {"mode": "scan", "themes": [copied]}

            temp_theme = ThemeDefinitionSchema(
                id=f"theme_name_{self._slug(theme_name)}",
                name=theme_name,
                enabled=True,
                priority=0,
                keywords=[theme_name],
                stock_pool=[],
                concept_board_codes=[],
                concept_board_names=[theme_name],
            )
            temp_theme.signal_rules.strategy_mode = strategy_mode
            return {"mode": "scan", "themes": [temp_theme]}

        raise ValueError("theme_id、theme_name、board_code、board_name 至少需要提供一个")

    def _build_direct_board_themes(
        self,
        board_codes: List[str],
        board_names: List[str],
        *,
        strategy_mode: str,
    ) -> List[ThemeDefinitionSchema]:
        themes: List[ThemeDefinitionSchema] = []
        registry_themes = self.registry_service.list_themes(enabled_only=False)

        for board_code in board_codes:
            normalized_code = str(board_code or "").strip().upper()
            if not normalized_code:
                continue
            inherited_mappings: Dict[str, str] = {}
            inherited_names: List[str] = []
            for registered_theme in registry_themes:
                registered_codes = {
                    str(code or "").strip().upper()
                    for code in getattr(registered_theme, "concept_board_codes", [])
                }
                if normalized_code not in registered_codes:
                    continue
                inherited_mappings.update(getattr(registered_theme, "board_code_mappings", {}) or {})
                inherited_names.extend(
                    [
                        str(name or "").strip()
                        for name in getattr(registered_theme, "concept_board_names", [])
                        if str(name or "").strip()
                    ]
                )
            theme = ThemeDefinitionSchema(
                id=f"board_{normalized_code.lower()}",
                name=normalized_code,
                enabled=True,
                priority=0,
                keywords=[],
                stock_pool=[],
                concept_board_codes=[normalized_code],
                concept_board_names=list(dict.fromkeys(inherited_names)),
                board_code_mappings=inherited_mappings,
            )
            theme.signal_rules.strategy_mode = strategy_mode
            themes.append(theme)

        for board_name in board_names:
            normalized_name = str(board_name or "").strip()
            if not normalized_name:
                continue
            inherited_codes: List[str] = []
            inherited_mappings: Dict[str, str] = {}
            for registered_theme in registry_themes:
                registered_names = {
                    str(name or "").strip()
                    for name in getattr(registered_theme, "concept_board_names", [])
                }
                if normalized_name not in registered_names:
                    continue
                inherited_codes.extend(
                    [
                        str(code or "").strip().upper()
                        for code in getattr(registered_theme, "concept_board_codes", [])
                        if str(code or "").strip()
                    ]
                )
                inherited_mappings.update(getattr(registered_theme, "board_code_mappings", {}) or {})
            theme = ThemeDefinitionSchema(
                id=f"board_name_{self._slug(normalized_name)}",
                name=normalized_name,
                enabled=True,
                priority=0,
                keywords=[],
                stock_pool=[],
                concept_board_codes=list(dict.fromkeys(inherited_codes)),
                concept_board_names=[normalized_name],
                board_code_mappings=inherited_mappings,
            )
            theme.signal_rules.strategy_mode = strategy_mode
            themes.append(theme)

        return self._dedupe_direct_board_themes(themes)

    def _run_direct_board_replay(
        self,
        direct_themes: List[ThemeDefinitionSchema],
        *,
        max_expanded_candidates: int,
    ) -> ThemeAlertResultSchema:
        result = ThemeAlertResultSchema(scanned_theme_ids=[theme.id for theme in direct_themes])
        for theme in direct_themes:
            if theme.concept_board_codes:
                target = ",".join(theme.concept_board_codes)
                reason = f"用户直接指定板块代码: {target}"
            else:
                target = ",".join(theme.concept_board_names)
                reason = f"用户直接指定板块名称: {target}"
            event = ThemeEventSchema(
                theme_id=theme.id,
                theme_name=theme.name,
                event_score=100,
                triggered=True,
                trigger_reason=reason,
                matched_keywords=[],
                matched_news_count=0,
                news_items=[],
            )
            result.events.append(event)
            stock_pool = self.pipeline.stock_pool_service.get_stock_pool(theme)
            candidate_pool = self.pipeline.expansion_service.expand_theme(
                theme,
                event,
                stock_pool,
                max_candidates=max_expanded_candidates,
            )
            signals = self.pipeline.signal_service.evaluate_theme(theme, event, candidate_pool)
            result.signals.extend(signals)
        return result

    def _build_response(
        self,
        request,
        themes: List[ThemeDefinitionSchema],
        result: ThemeAlertResultSchema,
    ) -> Dict[str, Any]:
        event = result.events[0] if result.events else None
        deduped_signals = self._dedupe_signals_by_stock_code(result.signals)
        stocks = self._build_stock_items(deduped_signals)
        signal_by_code = {
            str(signal.stock_code or "").strip().upper(): signal
            for signal in deduped_signals
            if str(signal.stock_code or "").strip()
        }
        selected_signal = signal_by_code.get(stocks[0].stock_code.upper()) if stocks else None
        selected_stock = (
            self._build_selected_stock(
                stocks[0],
                selected_signal,
                event,
                request,
                themes[0] if themes else None,
            )
            if stocks and selected_signal
            else None
        )
        empty_reason = None if stocks else self._derive_empty_reason(event)

        return {
            "query": asdict(ThemePickerQueryPayload(
                theme_id=themes[0].id if themes else request.theme_id,
                theme_name=themes[0].name if themes else request.theme_name,
                board_code=(themes[0].concept_board_codes[0] if themes and themes[0].concept_board_codes else request.board_code),
                board_name=(themes[0].concept_board_names[0] if themes and themes[0].concept_board_names else request.board_name),
                strategy_mode=request.strategy_mode,
                max_candidates=request.max_candidates,
            )),
            "theme_insight": asdict(
                self._build_theme_insight(
                    event,
                    themes[0] if themes else None,
                    deduped_signal_count=len(deduped_signals),
                )
            ),
            "stocks": [asdict(item) for item in stocks],
            "selected_stock": asdict(selected_stock) if selected_stock else None,
            "source_info": asdict(self._build_source_info(request, themes[0] if themes else None, event, result)),
            "empty_reason": empty_reason,
        }

    def _build_theme_insight(
        self,
        event: Optional[ThemeEventSchema],
        theme: Optional[ThemeDefinitionSchema],
        *,
        deduped_signal_count: int,
    ) -> ThemeInsightPayload:
        if event is None:
            theme_name = theme.name if theme else ""
            return ThemeInsightPayload(
                theme_name=theme_name,
                event_status="unresolved",
                event_score=None,
                matched_keywords=[],
                news_count=0,
                heat_level=None,
                board_mapping_path=self._build_board_mapping_path(theme),
                board_candidate_count=deduped_signal_count or None,
                primary_catalyst=None,
            )

        status = "triggered" if event.triggered else "untriggered"
        catalysts = [item.title for item in event.news_items[:2] if item.title]
        return ThemeInsightPayload(
            theme_name=event.theme_name,
            event_status=status,
            event_score=event.event_score,
            matched_keywords=list(event.matched_keywords or []),
            news_count=event.matched_news_count,
            heat_level=self._derive_heat_level(event.event_score, event.matched_news_count),
            board_mapping_path=self._build_board_mapping_path(theme),
            board_candidate_count=deduped_signal_count or None,
            primary_catalyst=" / ".join(catalysts) if catalysts else None,
        )

    def _build_stock_items(self, signals: List[Any]) -> List[ThemePickerStockItemPayload]:
        sorted_signals = sorted(
            signals,
            key=lambda signal: (
                _SIGNAL_LEVEL_RANK.get(_SIGNAL_LEVEL_LABELS.get(signal.signal_level, signal.signal_level), 9),
                -(float(signal.metrics.get("trend_score") or 0.0)),
                -(float(signal.metrics.get("pct_chg") or 0.0)),
            ),
        )
        items: List[ThemePickerStockItemPayload] = []
        for idx, signal in enumerate(sorted_signals, start=1):
            metrics = signal.metrics or {}
            mapped_level = _SIGNAL_LEVEL_LABELS.get(signal.signal_level, signal.signal_level)
            positive_reasons = self._pick_display_reasons(signal.reasons, prefer_positive=True, limit=3)
            display_reasons = positive_reasons or self._pick_display_reasons(signal.reasons, prefer_positive=False, limit=3)
            risk_reasons = self._derive_risk_reasons(mapped_level, metrics, signal.reasons)
            items.append(
                ThemePickerStockItemPayload(
                    rank=idx,
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name or signal.stock_code,
                    signal_level=mapped_level,
                    current_pattern=self._derive_current_pattern(mapped_level, metrics),
                    selection_reason=self._derive_selection_reason(mapped_level, metrics, signal.reasons),
                    risk_note=risk_reasons[0] if risk_reasons else None,
                    current_price=self._safe_float(metrics.get("current_price")),
                    support_level=self._safe_float(metrics.get("ma10") or metrics.get("ma20")),
                    pressure_level=self._safe_float(metrics.get("recent_high")),
                    trend_score=self._safe_float(metrics.get("trend_score")),
                    pct_chg=self._safe_float(metrics.get("pct_chg")),
                    volume_ratio=self._safe_float(metrics.get("volume_ratio")),
                    turnover_rate=self._safe_float(metrics.get("turnover_rate")),
                    buy_signal=self._safe_string(metrics.get("buy_signal")),
                    data_completeness=self._derive_data_completeness(metrics),
                    mini_reasons=display_reasons,
                )
            )
        return items

    def _dedupe_direct_board_themes(
        self,
        themes: List[ThemeDefinitionSchema],
    ) -> List[ThemeDefinitionSchema]:
        merged: Dict[Tuple[str, Tuple[str, ...]], ThemeDefinitionSchema] = {}
        ordered_keys: List[Tuple[str, Tuple[str, ...]]] = []

        for theme in themes:
            key = self._build_direct_theme_identity(theme)
            existing = merged.get(key)
            if existing is None:
                merged[key] = theme
                ordered_keys.append(key)
                continue

            merged_names = list(
                dict.fromkeys(
                    [
                        *getattr(existing, "concept_board_names", []),
                        *getattr(theme, "concept_board_names", []),
                    ]
                )
            )
            merged_codes = list(
                dict.fromkeys(
                    [
                        *(str(code or "").strip().upper() for code in getattr(existing, "concept_board_codes", [])),
                        *(str(code or "").strip().upper() for code in getattr(theme, "concept_board_codes", [])),
                    ]
                )
            )
            existing.concept_board_names = [name for name in merged_names if str(name or "").strip()]
            existing.concept_board_codes = [code for code in merged_codes if str(code or "").strip()]
            existing.board_code_mappings = {
                **(getattr(existing, "board_code_mappings", {}) or {}),
                **(getattr(theme, "board_code_mappings", {}) or {}),
            }

        return [merged[key] for key in ordered_keys]

    def _build_direct_theme_identity(
        self,
        theme: ThemeDefinitionSchema,
    ) -> Tuple[str, Tuple[str, ...]]:
        codes = tuple(
            sorted(
                {
                    str(code or "").strip().upper()
                    for code in getattr(theme, "concept_board_codes", [])
                    if str(code or "").strip()
                }
            )
        )
        if codes:
            return ("codes", codes)

        names = tuple(
            sorted(
                {
                    str(name or "").strip()
                    for name in getattr(theme, "concept_board_names", [])
                    if str(name or "").strip()
                }
            )
        )
        return ("names", names)

    def _dedupe_signals_by_stock_code(self, signals: List[Any]) -> List[Any]:
        sorted_signals = sorted(
            signals,
            key=lambda signal: (
                _SIGNAL_LEVEL_RANK.get(_SIGNAL_LEVEL_LABELS.get(signal.signal_level, signal.signal_level), 9),
                -(float(signal.metrics.get("trend_score") or 0.0)),
                -(float(signal.metrics.get("pct_chg") or 0.0)),
            ),
        )

        deduped: Dict[str, Any] = {}
        ordered_codes: List[str] = []
        for signal in sorted_signals:
            stock_code = str(getattr(signal, "stock_code", "") or "").strip().upper()
            if not stock_code:
                continue
            existing = deduped.get(stock_code)
            if existing is None:
                deduped[stock_code] = signal
                ordered_codes.append(stock_code)
                continue

            merged_reasons = list(
                dict.fromkeys(
                    [
                        *(getattr(existing, "reasons", []) or []),
                        *(getattr(signal, "reasons", []) or []),
                    ]
                )
            )
            existing.reasons = merged_reasons

        return [deduped[code] for code in ordered_codes]

    def _build_selected_stock(
        self,
        stock_item: ThemePickerStockItemPayload,
        signal: Any,
        event: Optional[ThemeEventSchema],
        request,
        theme: Optional[ThemeDefinitionSchema],
    ) -> ThemePickerSelectedStockPayload:
        metrics: Dict[str, Any] = dict(getattr(signal, "metrics", {}) or {})
        risk_reasons = self._derive_risk_reasons(stock_item.signal_level, metrics, getattr(signal, "reasons", []) or [])
        selected_reasons = self._pick_display_reasons(getattr(signal, "reasons", []) or [], prefer_positive=True, limit=5)
        if not selected_reasons:
            selected_reasons = list(stock_item.mini_reasons)

        theme_relevance = "high"
        resonance_count = self._safe_int(metrics.get("resonance_count"))
        if stock_item.rank > 5 or (resonance_count is not None and resonance_count <= 1):
            theme_relevance = "medium"
        if stock_item.rank > 8 and (resonance_count is None or resonance_count == 0):
            theme_relevance = "low"

        return ThemePickerSelectedStockPayload(
            stock_code=stock_item.stock_code,
            stock_name=stock_item.stock_name,
            theme_relevance=theme_relevance,
            current_price=self._safe_float(metrics.get("current_price")),
            pct_chg=self._safe_float(metrics.get("pct_chg")),
            volume_ratio=self._safe_float(metrics.get("volume_ratio")),
            turnover_rate=self._safe_float(metrics.get("turnover_rate")),
            trend_score=stock_item.trend_score,
            trend_status=self._safe_string(metrics.get("trend_status")),
            buy_signal=stock_item.buy_signal,
            current_pattern=stock_item.current_pattern,
            data_completeness=stock_item.data_completeness,
            resonance_count=resonance_count,
            ma5=self._safe_float(metrics.get("ma5")),
            ma10=self._safe_float(metrics.get("ma10")),
            ma20=self._safe_float(metrics.get("ma20")),
            bias_ma5=self._safe_float(metrics.get("bias_ma5")),
            bias_ma10=self._safe_float(metrics.get("bias_ma10")),
            bias_ma20=self._safe_float(metrics.get("bias_ma20")),
            recent_strong_days=self._safe_int(metrics.get("recent_strong_days")),
            support_level=self._safe_float(metrics.get("ma10") or metrics.get("ma20")),
            pressure_level=self._safe_float(metrics.get("recent_high")),
            news_summary=[item.title for item in (event.news_items if event else [])[:3] if item.title],
            selected_reasons=selected_reasons,
            risk_reasons=risk_reasons,
            data_sources=self._build_data_sources(request, stock_item, theme),
        )

    def _build_source_info(
        self,
        request,
        theme: Optional[ThemeDefinitionSchema],
        event: Optional[ThemeEventSchema],
        result: ThemeAlertResultSchema,
    ) -> ThemePickerSourceInfoPayload:
        board_source = self._infer_board_source(request, theme)
        note = None
        if board_source == "tushare_dc":
            note = "当前板块链路优先使用 Tushare 东财题材成分股"
        elif board_source == "eastmoney_board":
            note = "当前板块链路优先使用东方财富概念板块成分股"
        elif event and event.triggered:
            note = "结果已结合主题触发、板块扩池与技术筛选生成"

        has_realtime = any(self._derive_data_completeness(signal.metrics or {}) != "daily_only" for signal in result.signals)
        pricing_source = self._derive_pricing_source(result)
        source_pills = self._build_source_pills(
            board_source=board_source,
            has_news=bool(event and event.news_items),
            has_realtime=has_realtime,
        )
        return ThemePickerSourceInfoPayload(
            board_source=board_source,
            board_fallback_used=True if board_source == "tushare_dc" and request.board_code and request.board_code.upper().startswith("BK") else None,
            cache_hit=None,
            source_pills=source_pills,
            note=note,
            response_schema_version=self.RESPONSE_SCHEMA_VERSION,
            history_repaired=False,
            key_levels_backfilled=False,
            board_source_confidence=self._derive_board_source_confidence(
                board_source,
                True if board_source == "tushare_dc" and request.board_code and request.board_code.upper().startswith("BK") else None,
            ),
            pricing_source=pricing_source,
        )

    def _find_registered_theme_by_name(self, theme_name: str) -> Optional[ThemeDefinitionSchema]:
        target = (theme_name or "").strip()
        for theme in self.registry_service.list_themes(enabled_only=False):
            if str(theme.name or "").strip() == target:
                return theme
        return None

    def _build_board_mapping_path(self, theme: Optional[ThemeDefinitionSchema]) -> Optional[str]:
        if theme is None:
            return None
        board_codes = list(theme.concept_board_codes or [])
        mapping_segments = []
        for board_code in board_codes:
            mapped = (theme.board_code_mappings or {}).get(board_code)
            if mapped:
                mapping_segments.append(f"{board_code} -> {mapped}")
            else:
                mapping_segments.append(board_code)
        if not mapping_segments and theme.concept_board_names:
            return ", ".join(theme.concept_board_names)
        return " -> ".join(mapping_segments) if mapping_segments else None

    @staticmethod
    def _derive_heat_level(event_score: int, news_count: int) -> Optional[str]:
        if event_score >= 80 or news_count >= 8:
            return "high"
        if event_score >= 50 or news_count >= 3:
            return "medium"
        if event_score > 0 or news_count > 0:
            return "low"
        return None

    @staticmethod
    def _derive_current_pattern(signal_level: str, metrics: Dict[str, Any]) -> Optional[str]:
        pct_chg = float(metrics.get("pct_chg") or 0.0)
        bias_ma10 = float(metrics.get("bias_ma10") or 0.0)
        if signal_level == "持有候选":
            return "趋势延续"
        if signal_level == "低吸观察":
            return "回踩支撑区"
        if signal_level == "不宜追高":
            return "短线加速"
        if bias_ma10 <= 2 and pct_chg >= 0:
            return "平台上沿整理"
        if pct_chg >= 3:
            return "题材异动"
        return "主题跟踪"

    @staticmethod
    def _derive_selection_reason(signal_level: str, metrics: Dict[str, Any], reasons: List[str]) -> str:
        positive_reasons = ThemePickerService._pick_display_reasons(reasons, prefer_positive=True, limit=3)
        if positive_reasons:
            return " + ".join(positive_reasons)
        if not reasons:
            return "主题、板块与技术条件综合后进入候选"
        if signal_level == "不宜追高":
            pct_chg = float(metrics.get("pct_chg") or 0.0)
            return f"题材已被点火，但短线涨幅 {pct_chg:.2f}% 偏快，优先等回踩确认"
        return " + ".join(reasons[:3])

    @staticmethod
    def _derive_risk_note(signal_level: str, metrics: Dict[str, Any], reasons: List[str]) -> Optional[str]:
        risk_reasons = ThemePickerService._derive_risk_reasons(signal_level, metrics, reasons)
        return risk_reasons[0] if risk_reasons else None

    @staticmethod
    def _derive_risk_reasons(signal_level: str, metrics: Dict[str, Any], reasons: List[str]) -> List[str]:
        risk_reasons: List[str] = []
        if signal_level == "不宜追高":
            risk_reasons.append("短线节奏偏快，不宜追高")
        turnover_rate = ThemePickerService._safe_float(metrics.get("turnover_rate"))
        if turnover_rate is not None and turnover_rate >= 20:
            risk_reasons.append(f"换手率 {turnover_rate:.2f}% 偏高，盘中分歧较大")
        volume_ratio = ThemePickerService._safe_float(metrics.get("volume_ratio"))
        if volume_ratio is not None and volume_ratio < 1:
            risk_reasons.append(f"量比 {volume_ratio:.2f} 未明显放大，资金接力仍需确认")
        for reason in reasons:
            if ThemePickerService._is_negative_reason(reason):
                risk_reasons.append(reason)
        return list(dict.fromkeys([reason for reason in risk_reasons if reason]))

    @staticmethod
    def _derive_data_completeness(metrics: Dict[str, Any]) -> Optional[str]:
        has_realtime = any(metrics.get(key) is not None for key in ("pct_chg", "volume_ratio", "turnover_rate"))
        has_full = metrics.get("volume_ratio") is not None and metrics.get("turnover_rate") is not None
        if has_full:
            return "full_realtime"
        if has_realtime:
            return "partial_realtime"
        return "daily_only"

    def _build_data_sources(
        self,
        request,
        stock_item: ThemePickerStockItemPayload,
        theme: Optional[ThemeDefinitionSchema],
    ) -> Dict[str, Optional[str]]:
        completeness = stock_item.data_completeness
        realtime = None
        if completeness == "full_realtime":
            realtime = "tencent"
        elif completeness == "partial_realtime":
            realtime = "mixed"

        return {
            "daily": "multi_source_daily",
            "realtime": realtime,
            "board": self._infer_board_source(request, theme),
            "news": "search_service" if request.theme_id or request.theme_name else None,
        }

    @staticmethod
    def _build_source_pills(
        *,
        board_source: Optional[str],
        has_news: bool,
        has_realtime: bool,
    ) -> List[str]:
        pills: List[str] = []
        if board_source == "tushare_dc":
            pills.append("Tushare 题材")
        elif board_source == "eastmoney_board":
            pills.append("东方财富板块")
        if has_realtime:
            pills.append("实时行情")
        if has_news:
            pills.append("新闻检索")
        return pills

    def _derive_pricing_source(self, result: ThemeAlertResultSchema) -> Optional[str]:
        if not result.signals:
            return None
        completeness_values = {
            self._derive_data_completeness(signal.metrics or {})
            for signal in result.signals
        }
        if completeness_values == {"daily_only"}:
            return "daily_only"
        if "full_realtime" in completeness_values and len(completeness_values) == 1:
            return "realtime_enhanced"
        if "full_realtime" in completeness_values or "partial_realtime" in completeness_values:
            return "mixed"
        return None

    @classmethod
    def _infer_pricing_source_from_payload(cls, payload: Dict[str, Any]) -> Optional[str]:
        source_info = payload.get("source_info") or payload.get("sourceInfo") or {}
        if isinstance(source_info, dict) and source_info.get("pricing_source"):
            return str(source_info.get("pricing_source"))
        stocks = payload.get("stocks") or []
        if not isinstance(stocks, list) or not stocks:
            return None
        completeness_values = set()
        for item in stocks:
            if not isinstance(item, dict):
                continue
            completeness = item.get("data_completeness") or item.get("dataCompleteness")
            if completeness:
                completeness_values.add(str(completeness))
        if completeness_values == {"daily_only"}:
            return "daily_only"
        if completeness_values == {"full_realtime"}:
            return "realtime_enhanced"
        if "full_realtime" in completeness_values or "partial_realtime" in completeness_values:
            return "mixed"
        if isinstance(source_info, dict) and source_info.get("key_levels_backfilled"):
            return "daily_only"
        return None

    @staticmethod
    def _derive_board_source_confidence(
        board_source: Optional[str],
        board_fallback_used: Optional[bool],
    ) -> Optional[str]:
        if board_source == "eastmoney_board":
            return "high"
        if board_source == "tushare_dc":
            return "medium" if board_fallback_used else "high"
        if board_source:
            return "low"
        return None

    @staticmethod
    def _pick_display_reasons(
        reasons: List[str],
        *,
        prefer_positive: bool,
        limit: int,
    ) -> List[str]:
        if not reasons:
            return []
        filtered: List[str] = []
        for reason in reasons:
            if prefer_positive and ThemePickerService._is_negative_reason(reason):
                continue
            if not prefer_positive and ThemePickerService._is_positive_reason(reason):
                continue
            filtered.append(reason)
        if filtered:
            return list(dict.fromkeys(filtered[:limit]))
        return list(dict.fromkeys(reasons[:limit]))

    @staticmethod
    def _is_positive_reason(reason: str) -> bool:
        positive_tokens = (
            "满足",
            "维持向上",
            "站上",
            "可持有",
            "趋势底座完整",
            "适合作为",
            "更适合观察承接后分批介入",
            "达到异动阈值",
            "达到放量阈值",
            "突破近",
            "技术信号为",
            "共振数量达到",
            "回踩至",
        )
        return any(token in reason for token in positive_tokens)

    @staticmethod
    def _is_negative_reason(reason: str) -> bool:
        negative_tokens = (
            "未满足",
            "不足",
            "低于",
            "尚未",
            "仅为",
            "已跌",
            "跌破",
            "偏少",
            "偏高",
            "分歧",
            "超过",
            "加速过快",
            "不宜追高",
            "还不够舒服",
            "等待",
        )
        return any(token in reason for token in negative_tokens)

    @staticmethod
    def _infer_board_source(request, theme: Optional[ThemeDefinitionSchema]) -> Optional[str]:
        code = (request.board_code or "").strip().upper()
        if not code and theme and theme.concept_board_codes:
            code = str(theme.concept_board_codes[0] or "").strip().upper()
        if code.endswith(".DC"):
            return "tushare_dc"
        if code.startswith("BK"):
            return "eastmoney_board"
        return None

    @staticmethod
    def _derive_empty_reason(event: Optional[ThemeEventSchema]) -> Optional[str]:
        if event is None:
            return "未识别到有效主题"
        if not event.triggered:
            return "主题已识别，但未满足当前触发条件"
        return "候选股均未满足当前筛选条件"

    @staticmethod
    def _parse_csv_values(raw: Optional[str]) -> List[str]:
        return [item.strip() for item in str(raw or "").split(",") if item.strip()]

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_string(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "theme"
