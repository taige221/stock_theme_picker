# -*- coding: utf-8 -*-
"""
===================================
Theme Expansion Service
===================================
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
from threading import RLock
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from theme_picker.data_provider import DataFetcherManager
from theme_picker.data.stock_mapping import STOCK_NAME_MAP
from theme_picker.data.stock_index_loader import get_stock_name_index_map
from theme_picker.domain.theme_event import ThemeDefinitionSchema, ThemeEventSchema
from theme_picker.search_service import SearchService
from theme_picker.infrastructure.board_resolver_service import ThemeBoardResolverService
from theme_picker.infrastructure.runtime import get_theme_picker_config
from theme_picker.infrastructure.stock_pool_service import ThemeStockPoolService, canonicalize_stock_code

logger = logging.getLogger(__name__)

_A_SHARE_CODE_PATTERN = re.compile(r"(?<!\d)([0-9]{6})(?!\d)")
_DEFAULT_QUERY_TIMEOUT_SECONDS = 8.0
_DEFAULT_ALLOWED_SUFFIXES = (".SH", ".SZ", ".BJ")


class ThemeExpansionService:
    """Expand a triggered theme into a richer candidate pool via online scans."""

    def __init__(
        self,
        search_service: Optional[SearchService] = None,
        board_resolver: Optional[ThemeBoardResolverService] = None,
    ):
        self.search_service = search_service
        self.board_resolver = board_resolver or ThemeBoardResolverService()
        self.fetcher_manager = DataFetcherManager()
        self._stock_universe_lock = RLock()
        self._stock_universe: Optional[List[Dict[str, str]]] = None
        self.query_timeout_seconds = float(
            getattr(get_theme_picker_config(), "theme_expansion_query_timeout", _DEFAULT_QUERY_TIMEOUT_SECONDS)
            or _DEFAULT_QUERY_TIMEOUT_SECONDS
        )

    def expand_theme(
        self,
        theme: ThemeDefinitionSchema,
        event: ThemeEventSchema,
        seed_pool: Sequence[str],
        *,
        days: int = 7,
        max_results_per_query: int = 5,
        max_candidates: int = 30,
    ) -> List[str]:
        candidates = self._filter_allowed_market_codes(
            ThemeStockPoolService.normalize_codes(seed_pool)
        )
        if not event.triggered:
            return candidates[:max_candidates]

        board_candidates = self.board_resolver.resolve_theme_candidates(
            theme,
            max_candidates=max_candidates,
        )
        if board_candidates:
            merged_board_candidates = self._build_ranked_candidates(
                candidates,
                {code: 100 for code in board_candidates},
                {code: index for index, code in enumerate(board_candidates)},
            )
            logger.info(
                "主题扩池使用板块成分股: theme=%s seed=%s board_candidates=%s returned=%s",
                theme.id,
                len(candidates),
                len(board_candidates),
                min(len(merged_board_candidates), max_candidates),
            )
            return merged_board_candidates[:max_candidates]

        query_aliases = self._build_query_aliases(theme, event)
        candidate_scores: Dict[str, int] = {}
        candidate_first_seen: Dict[str, int] = {}
        seen_sequence = 0
        merged = self._build_ranked_candidates(candidates, candidate_scores, candidate_first_seen)
        logger.debug(
            "主题扩池开始: theme=%s aliases=%s seed_pool=%s",
            theme.id,
            query_aliases,
            list(seed_pool),
        )
        for alias in query_aliases:
            for query in self._build_queries(alias):
                if len(merged) >= max_candidates:
                    logger.debug(
                        "主题扩池提前停止: theme=%s current_candidates=%s max_candidates=%s",
                        theme.id,
                        len(merged),
                        max_candidates,
                    )
                    break
                logger.debug("主题扩池搜索: theme=%s query=%s", theme.id, query)
                response = self._search_query(
                    query=query,
                    max_results=max_results_per_query,
                    days=days,
                )
                if response is None or not response.success:
                    logger.debug("主题扩池搜索无结果: theme=%s query=%s", theme.id, query)
                    continue
                logger.debug(
                    "主题扩池搜索完成: theme=%s query=%s provider=%s results=%s",
                    theme.id,
                    query,
                    getattr(response, "provider", ""),
                    len(getattr(response, "results", []) or []),
                )
                for item in response.results:
                    extracted = self._extract_candidate_signals_from_text(
                        f"{item.title or ''}\n{item.snippet or ''}"
                    )
                    if not extracted:
                        continue
                    seen_sequence = self._merge_candidate_signals(
                        candidate_scores,
                        candidate_first_seen,
                        extracted,
                        seen_sequence,
                    )
                    merged = self._build_ranked_candidates(
                        candidates,
                        candidate_scores,
                        candidate_first_seen,
                    )
                    if len(merged) >= max_candidates:
                        break
            if len(merged) >= max_candidates:
                break

        if len(merged) < max_candidates:
            for item in event.news_items:
                extracted = self._extract_candidate_signals_from_text(
                    f"{item.title or ''}\n{item.snippet or ''}"
                )
                if not extracted:
                    continue
                seen_sequence = self._merge_candidate_signals(
                    candidate_scores,
                    candidate_first_seen,
                    extracted,
                    seen_sequence,
                )
                merged = self._build_ranked_candidates(
                    candidates,
                    candidate_scores,
                    candidate_first_seen,
                )
                if len(merged) >= max_candidates:
                    break

        truncated = len(merged) > max_candidates
        returned_candidates = merged[:max_candidates]
        discovered_unique = self._build_ranked_discovered_candidates(
            candidate_scores,
            candidate_first_seen,
        )
        logger.info(
            "主题扩池完成: theme=%s seed=%s discovered=%s merged=%s returned=%s truncated=%s",
            theme.id,
            len(candidates),
            len(discovered_unique),
            len(merged),
            len(returned_candidates),
            truncated,
        )
        return returned_candidates

    def _build_query_aliases(
        self,
        theme: ThemeDefinitionSchema,
        event: ThemeEventSchema,
    ) -> List[str]:
        aliases: List[str] = []
        configured_aliases = theme.expansion_aliases or theme.concept_aliases
        for value in [theme.name, *configured_aliases, *event.matched_keywords]:
            text = str(value or "").strip()
            if text and text not in aliases:
                aliases.append(text)
        return aliases

    @staticmethod
    def _build_queries(alias: str) -> List[str]:
        if "概念股" in alias or "龙头股" in alias:
            return [f"{alias} A股"]
        return [
            f"{alias} 概念股 A股",
            f"{alias} 龙头股 A股",
        ]

    def _search_query(
        self,
        *,
        query: str,
        max_results: int,
        days: int,
    ):
        if self.search_service is None or not self.search_service.is_available:
            return None
        last_response = None
        providers = getattr(self.search_service, "_providers", []) or []
        for provider in providers:
            if not provider.is_available:
                continue
            executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
            try:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = executor.submit(
                    provider.search,
                    query,
                    max_results=max_results,
                    days=days,
                )
                response = future.result(timeout=self.query_timeout_seconds)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "主题扩池搜索超时: provider=%s query=%s timeout=%.1fs",
                    getattr(provider, "name", provider.__class__.__name__),
                    query,
                    self.query_timeout_seconds,
                )
                if executor is not None:
                    executor.shutdown(wait=False, cancel_futures=True)
                continue
            except Exception as exc:
                logger.debug(
                    "主题扩池搜索失败: provider=%s query=%s err=%s",
                    getattr(provider, "name", provider.__class__.__name__),
                    query,
                    exc,
                )
                if executor is not None:
                    executor.shutdown(wait=False, cancel_futures=True)
                continue
            finally:
                if executor is not None:
                    executor.shutdown(wait=False)
            last_response = response
            if response.success and response.results:
                return response
        return last_response

    def _extract_candidate_signals_from_text(self, text: str) -> Dict[str, int]:
        raw_text = str(text or "").strip()
        if not raw_text:
            return {}

        discovered: Dict[str, int] = {}

        for code in _A_SHARE_CODE_PATTERN.findall(raw_text):
            canonical = canonicalize_stock_code(code)
            if not canonical.endswith((".SH", ".SZ", ".BJ")):
                continue
            if not self._is_confirmed_text_candidate(canonical):
                logger.debug("主题扩池忽略未确认文本候选: raw=%s canonical=%s", code, canonical)
                continue
            discovered[canonical] = max(discovered.get(canonical, 0), 2)

        return discovered

    def _is_confirmed_text_candidate(self, canonical_code: str) -> bool:
        if not canonical_code:
            return False

        for item in self._get_stock_universe():
            if canonicalize_stock_code(item.get("code", "")) == canonical_code:
                return True
        return False

    def _merge_candidate_signals(
        self,
        candidate_scores: Dict[str, int],
        candidate_first_seen: Dict[str, int],
        extracted: Dict[str, int],
        seen_sequence: int,
    ) -> int:
        for code, score in extracted.items():
            canonical_code = canonicalize_stock_code(code)
            if not canonical_code or not self._is_allowed_market_code(canonical_code):
                continue
            candidate_scores[canonical_code] = candidate_scores.get(canonical_code, 0) + int(score)
            if canonical_code not in candidate_first_seen:
                candidate_first_seen[canonical_code] = seen_sequence
                seen_sequence += 1
        return seen_sequence

    def _build_ranked_candidates(
        self,
        seed_candidates: Sequence[str],
        candidate_scores: Dict[str, int],
        candidate_first_seen: Dict[str, int],
    ) -> List[str]:
        merged = list(self._filter_allowed_market_codes(seed_candidates))
        merged.extend(
            code for code in self._build_ranked_discovered_candidates(candidate_scores, candidate_first_seen)
            if code not in merged
        )
        return merged

    def _build_ranked_discovered_candidates(
        self,
        candidate_scores: Dict[str, int],
        candidate_first_seen: Dict[str, int],
    ) -> List[str]:
        eligible: List[Tuple[str, int, int]] = []
        for code, score in candidate_scores.items():
            if score < 2:
                continue
            eligible.append((code, score, candidate_first_seen.get(code, 10**9)))
        eligible.sort(key=lambda item: (-item[1], item[2], item[0]))
        return [code for code, _, _ in eligible]

    def _get_stock_universe(self) -> List[Dict[str, str]]:
        with self._stock_universe_lock:
            if self._stock_universe is not None:
                return self._stock_universe

            candidates: List[Dict[str, str]] = []
            stock_index_map = get_stock_name_index_map()
            if stock_index_map:
                for code, name in stock_index_map.items():
                    canonical_code = canonicalize_stock_code(code)
                    if not canonical_code or not name or not self._is_allowed_market_code(canonical_code):
                        continue
                    candidates.append({"code": canonical_code, "name": str(name).strip()})
                if candidates:
                    logger.info("主题扩池股票列表加载成功: source=stock_index count=%s", len(candidates))

            if candidates:
                self._stock_universe = self._dedup_universe(candidates)
                return self._stock_universe

            fetchers = self.fetcher_manager._get_fetchers_snapshot()
            for fetcher in fetchers:
                if not hasattr(fetcher, "get_stock_list"):
                    continue
                try:
                    df = fetcher.get_stock_list()
                except Exception as exc:
                    logger.debug("主题扩池获取股票列表失败: fetcher=%s err=%s", fetcher.name, exc)
                    continue
                normalized = self._normalize_stock_list(df)
                if normalized:
                    candidates = normalized
                    logger.info("主题扩池股票列表加载成功: fetcher=%s count=%s", fetcher.name, len(candidates))
                    break

            if not candidates:
                for code, name in STOCK_NAME_MAP.items():
                    canonical_code = canonicalize_stock_code(code)
                    if not canonical_code or not self._is_allowed_market_code(canonical_code):
                        continue
                    candidates.append({"code": canonical_code, "name": name})

            self._stock_universe = candidates
            return self._stock_universe

    @staticmethod
    def _normalize_stock_list(df: Optional[pd.DataFrame]) -> List[Dict[str, str]]:
        if df is None or df.empty:
            return []

        columns = {str(col): col for col in df.columns}
        code_col = columns.get("code")
        name_col = columns.get("name")
        if code_col is None or name_col is None:
            return []

        result: List[Dict[str, str]] = []
        seen = set()
        for _, row in df.iterrows():
            raw_code = canonicalize_stock_code(str(row.get(code_col, "")).strip())
            raw_name = str(row.get(name_col, "")).strip()
            if not raw_code or not raw_name or raw_code in seen:
                continue
            if not raw_code.endswith(_DEFAULT_ALLOWED_SUFFIXES):
                continue
            seen.add(raw_code)
            result.append({"code": raw_code, "name": raw_name})
        return result

    @staticmethod
    def _dedup_universe(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        deduped: List[Dict[str, str]] = []
        seen = set()
        for item in items:
            code = canonicalize_stock_code(item.get("code", ""))
            name = str(item.get("name", "")).strip()
            if not code or not name or code in seen:
                continue
            if not code.endswith(_DEFAULT_ALLOWED_SUFFIXES):
                continue
            seen.add(code)
            deduped.append({"code": code, "name": name})
        return deduped

    @staticmethod
    def _filter_allowed_market_codes(codes: Sequence[str]) -> List[str]:
        return [
            code for code in codes
            if canonicalize_stock_code(code).endswith(_DEFAULT_ALLOWED_SUFFIXES)
        ]

    @staticmethod
    def _is_allowed_market_code(code: str) -> bool:
        return canonicalize_stock_code(code).endswith(_DEFAULT_ALLOWED_SUFFIXES)
