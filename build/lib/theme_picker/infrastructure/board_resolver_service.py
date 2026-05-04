# -*- coding: utf-8 -*-
"""
===================================
Theme Board Resolver Service
===================================
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional, Sequence

import pandas as pd

from theme_picker.data_provider.tushare_fetcher import _TushareHttpClient
from theme_picker.domain.theme_event import ThemeDefinitionSchema
from theme_picker.infrastructure.runtime import get_theme_picker_config
from theme_picker.infrastructure.stock_pool_service import ThemeStockPoolService, canonicalize_stock_code

logger = logging.getLogger(__name__)

_BOARD_CODE_PATTERN = re.compile(r"^BK\d+$", re.IGNORECASE)
_DC_THEME_CODE_PATTERN = re.compile(r"^\d{6}\.DC$", re.IGNORECASE)


class ThemeBoardResolverService:
    """Resolve concept-board definitions into A-share constituent stock codes."""

    def __init__(self):
        package_root = Path(__file__).resolve().parents[1]
        data_dir = package_root / "data"
        self.cache_path = data_dir / "theme_board_cache.json"
        self.global_mapping_path = data_dir / "theme_board_mappings.json"
        self.example_global_mapping_path = data_dir / "theme_board_mappings.example.json"
        self._cache_lock = RLock()
        self._global_mapping_lock = RLock()
        self._board_index_lock = RLock()
        self._board_index_df: Optional[pd.DataFrame] = None
        self._board_name_to_code: Dict[str, str] = {}
        self._normalized_board_name_to_code: Dict[str, str] = {}
        self._dc_theme_index_lock = RLock()
        self._dc_theme_index_df: Optional[pd.DataFrame] = None
        self._dc_theme_name_to_code: Dict[str, str] = {}
        self._normalized_dc_theme_name_to_code: Dict[str, str] = {}
        self._dc_theme_trade_dates: Dict[str, str] = {}
        self._global_board_to_dc_mappings: Optional[Dict[str, str]] = None
        self._tushare_client: Optional[_TushareHttpClient] = None

    def resolve_theme_candidates(
        self,
        theme: ThemeDefinitionSchema,
        *,
        max_candidates: int = 30,
    ) -> List[str]:
        candidates: List[str] = []
        seen = set()
        em_board_codes = self._resolve_theme_board_codes(theme)
        for board_code in em_board_codes:
            for stock_code in self._fetch_board_constituent_codes(board_code):
                canonical = canonicalize_stock_code(stock_code)
                if not canonical.endswith((".SH", ".SZ", ".BJ")) or canonical in seen:
                    continue
                seen.add(canonical)
                candidates.append(canonical)
                if len(candidates) >= max_candidates:
                    logger.info(
                        "主题板块扩池达到上限: theme=%s source=eastmoney board_codes=%s returned=%s",
                        theme.id,
                        em_board_codes,
                        len(candidates),
                    )
                    return candidates

        if candidates:
            logger.info(
                "主题板块扩池完成: theme=%s source=eastmoney board_codes=%s returned=%s",
                theme.id,
                em_board_codes,
                len(candidates),
            )
            return candidates

        dc_theme_codes = self._resolve_theme_dc_codes(theme)
        for theme_code in dc_theme_codes:
            for stock_code in self._fetch_dc_theme_constituent_codes(theme_code):
                canonical = canonicalize_stock_code(stock_code)
                if not canonical.endswith((".SH", ".SZ", ".BJ")) or canonical in seen:
                    continue
                seen.add(canonical)
                candidates.append(canonical)
                if len(candidates) >= max_candidates:
                    logger.info(
                        "主题板块扩池达到上限: theme=%s source=tushare_dc theme_codes=%s returned=%s",
                        theme.id,
                        dc_theme_codes,
                        len(candidates),
                    )
                    return candidates

        if candidates:
            logger.info(
                "主题板块扩池完成: theme=%s source=tushare_dc theme_codes=%s returned=%s",
                theme.id,
                dc_theme_codes,
                len(candidates),
            )
            return candidates

        logger.info(
            "主题板块扩池未命中结构化成分股: theme=%s em_codes=%s dc_codes=%s",
            theme.id,
            em_board_codes,
            dc_theme_codes,
        )
        return []

    def _resolve_theme_board_codes(self, theme: ThemeDefinitionSchema) -> List[str]:
        resolved: List[str] = []
        seen = set()

        direct_codes = [
            str(code or "").strip().upper()
            for code in theme.concept_board_codes
            if _BOARD_CODE_PATTERN.match(str(code or "").strip().upper())
        ]
        for code in direct_codes:
            if not _BOARD_CODE_PATTERN.match(code) or code in seen:
                continue
            seen.add(code)
            resolved.append(code)

        board_name_inputs: Sequence[str] = theme.concept_board_names or (
            [] if direct_codes else theme.concept_aliases
        )
        board_names = [
            str(name or "").strip()
            for name in board_name_inputs
            if str(name or "").strip()
        ]
        for board_name in board_names:
            board_code = self._match_board_code_by_name(board_name)
            if not board_code or board_code in seen:
                continue
            seen.add(board_code)
            resolved.append(board_code)

        return resolved

    def _resolve_theme_dc_codes(self, theme: ThemeDefinitionSchema) -> List[str]:
        resolved: List[str] = []
        seen = set()

        direct_codes = [
            str(code or "").strip().upper()
            for code in theme.concept_board_codes
            if _DC_THEME_CODE_PATTERN.match(str(code or "").strip().upper())
        ]
        for code in direct_codes:
            if code in seen:
                continue
            seen.add(code)
            resolved.append(code)

        for em_code in self._resolve_theme_board_codes(theme):
            mapped_dc_code = self._lookup_mapped_dc_code(theme, em_code)
            if not mapped_dc_code or mapped_dc_code in seen:
                continue
            seen.add(mapped_dc_code)
            resolved.append(mapped_dc_code)

        theme_name_inputs: Sequence[str] = theme.concept_board_names or theme.concept_aliases or [theme.name]
        theme_names = [
            str(name or "").strip()
            for name in theme_name_inputs
            if str(name or "").strip()
        ]
        for theme_name in theme_names:
            theme_code = self._match_dc_theme_code_by_name(theme_name)
            if not theme_code or theme_code in seen:
                continue
            seen.add(theme_code)
            resolved.append(theme_code)

        return resolved

    def _match_board_code_by_name(self, board_name: str) -> Optional[str]:
        board_name = str(board_name or "").strip()
        if not board_name:
            return None
        if _BOARD_CODE_PATTERN.match(board_name.upper()):
            return board_name.upper()

        index_df = self._load_board_index()
        if index_df is None or index_df.empty:
            return None

        exact = self._board_name_to_code.get(board_name)
        if exact:
            logger.info("主题板块名称精确匹配成功: %s -> %s", board_name, exact)
            return exact

        normalized_name = self._normalize_board_name(board_name)
        normalized = self._normalized_board_name_to_code.get(normalized_name)
        if normalized:
            logger.info("主题板块名称规范化匹配成功: %s -> %s", board_name, normalized)
            return normalized

        contains_matches = []
        for _, row in index_df.iterrows():
            candidate_name = str(row.get("板块名称") or "").strip()
            candidate_code = str(row.get("板块代码") or "").strip().upper()
            if not candidate_name or not candidate_code:
                continue
            normalized_candidate_name = self._normalize_board_name(candidate_name)
            if normalized_name and normalized_name in normalized_candidate_name:
                contains_matches.append((candidate_name, candidate_code))

        if len(contains_matches) == 1:
            matched_name, matched_code = contains_matches[0]
            logger.info(
                "主题板块名称包含匹配成功: %s -> %s (%s)",
                board_name,
                matched_name,
                matched_code,
            )
            return matched_code

        if len(contains_matches) > 1:
            logger.warning(
                "主题板块名称匹配歧义: name=%s matches=%s",
                board_name,
                [name for name, _ in contains_matches[:5]],
            )
        else:
            logger.warning("主题板块名称未匹配到东方财富概念板块: %s", board_name)
        return None

    def _match_dc_theme_code_by_name(self, theme_name: str) -> Optional[str]:
        theme_name = str(theme_name or "").strip()
        if not theme_name:
            return None
        if _DC_THEME_CODE_PATTERN.match(theme_name.upper()):
            return theme_name.upper()

        index_df = self._load_dc_theme_index()
        if index_df is None or index_df.empty:
            return None

        exact = self._dc_theme_name_to_code.get(theme_name)
        if exact:
            logger.info("Tushare 题材名称精确匹配成功: %s -> %s", theme_name, exact)
            return exact

        normalized_name = self._normalize_board_name(theme_name)
        normalized = self._normalized_dc_theme_name_to_code.get(normalized_name)
        if normalized:
            logger.info("Tushare 题材名称规范化匹配成功: %s -> %s", theme_name, normalized)
            return normalized

        contains_matches = []
        for _, row in index_df.iterrows():
            candidate_name = str(row.get("题材名称") or "").strip()
            candidate_code = str(row.get("题材代码") or "").strip().upper()
            if not candidate_name or not candidate_code:
                continue
            normalized_candidate_name = self._normalize_board_name(candidate_name)
            if normalized_name and normalized_name in normalized_candidate_name:
                contains_matches.append((candidate_name, candidate_code))

        if len(contains_matches) == 1:
            matched_name, matched_code = contains_matches[0]
            logger.info(
                "Tushare 题材名称包含匹配成功: %s -> %s (%s)",
                theme_name,
                matched_name,
                matched_code,
            )
            return matched_code

        if len(contains_matches) > 1:
            logger.warning(
                "Tushare 题材名称匹配歧义: name=%s matches=%s",
                theme_name,
                [name for name, _ in contains_matches[:5]],
            )
        else:
            logger.warning("主题名称未匹配到 Tushare 东财题材: %s", theme_name)
        return None

    def _load_board_index(self) -> Optional[pd.DataFrame]:
        with self._board_index_lock:
            if self._board_index_df is not None:
                return self._board_index_df

            try:
                import akshare as ak

                df = ak.stock_board_concept_name_em()
            except Exception as exc:
                logger.warning("加载东方财富概念板块列表失败: %s", exc)
                cached_df = self._load_cached_board_index()
                if cached_df is not None and not cached_df.empty:
                    logger.info("回退使用缓存的东方财富概念板块列表: count=%s", len(cached_df))
                    self._apply_board_index(cached_df)
                    return self._board_index_df
                return None

            if df is None or df.empty:
                logger.warning("东方财富概念板块列表为空")
                cached_df = self._load_cached_board_index()
                if cached_df is not None and not cached_df.empty:
                    logger.info("东方财富概念板块列表为空，回退使用缓存: count=%s", len(cached_df))
                    self._apply_board_index(cached_df)
                    return self._board_index_df
                return None

            name_col = "板块名称" if "板块名称" in df.columns else next(
                (col for col in df.columns if "名称" in str(col)),
                None,
            )
            code_col = "板块代码" if "板块代码" in df.columns else next(
                (col for col in df.columns if "代码" in str(col)),
                None,
            )
            if name_col is None or code_col is None:
                logger.warning("东方财富概念板块列表缺少名称/代码字段: columns=%s", list(df.columns))
                return None

            normalized_df = df[[name_col, code_col]].copy()
            normalized_df.columns = ["板块名称", "板块代码"]
            normalized_df["板块名称"] = normalized_df["板块名称"].astype(str).str.strip()
            normalized_df["板块代码"] = normalized_df["板块代码"].astype(str).str.strip().str.upper()
            normalized_df = normalized_df[
                normalized_df["板块名称"].astype(bool) & normalized_df["板块代码"].astype(bool)
            ].drop_duplicates(subset=["板块代码"])

            self._apply_board_index(normalized_df)
            self._save_cached_board_index(normalized_df)
            logger.info("东方财富概念板块列表加载成功: count=%s", len(normalized_df))
            return self._board_index_df

    def _load_dc_theme_index(self) -> Optional[pd.DataFrame]:
        with self._dc_theme_index_lock:
            if self._dc_theme_index_df is not None:
                return self._dc_theme_index_df

            try:
                client = self._get_tushare_client()
                if client is None:
                    raise RuntimeError("Tushare Token 未配置")
                df = client.query("dc_concept", fields="theme_code,trade_date,name")
            except Exception as exc:
                logger.warning("加载 Tushare 东财题材列表失败: %s", exc)
                cached_df = self._load_cached_dc_theme_index()
                if cached_df is not None and not cached_df.empty:
                    logger.info("回退使用缓存的 Tushare 东财题材列表: count=%s", len(cached_df))
                    self._apply_dc_theme_index(cached_df)
                    return self._dc_theme_index_df
                return None

            if df is None or df.empty:
                logger.warning("Tushare 东财题材列表为空")
                cached_df = self._load_cached_dc_theme_index()
                if cached_df is not None and not cached_df.empty:
                    logger.info("Tushare 东财题材列表为空，回退使用缓存: count=%s", len(cached_df))
                    self._apply_dc_theme_index(cached_df)
                    return self._dc_theme_index_df
                return None

            normalized_df = df.rename(
                columns={
                    "theme_code": "题材代码",
                    "trade_date": "交易日期",
                    "name": "题材名称",
                }
            )[["题材代码", "交易日期", "题材名称"]].copy()
            normalized_df["题材代码"] = normalized_df["题材代码"].astype(str).str.strip().str.upper()
            normalized_df["交易日期"] = normalized_df["交易日期"].astype(str).str.strip()
            normalized_df["题材名称"] = normalized_df["题材名称"].astype(str).str.strip()
            normalized_df = normalized_df[
                normalized_df["题材代码"].astype(bool) & normalized_df["题材名称"].astype(bool)
            ]
            if normalized_df.empty:
                return None
            normalized_df = (
                normalized_df.sort_values(by=["交易日期", "题材代码"], ascending=[False, True])
                .drop_duplicates(subset=["题材代码"], keep="first")
                .reset_index(drop=True)
            )

            self._apply_dc_theme_index(normalized_df)
            self._save_cached_dc_theme_index(normalized_df)
            logger.info("Tushare 东财题材列表加载成功: count=%s", len(normalized_df))
            return self._dc_theme_index_df

    def _fetch_board_constituent_codes(self, board_code: str) -> List[str]:
        try:
            import akshare as ak

            df = ak.stock_board_concept_cons_em(symbol=board_code)
        except Exception as exc:
            logger.warning("获取概念板块成分股失败: board=%s err=%s", board_code, exc)
            cached_codes = self._load_cached_board_constituents(board_code)
            if cached_codes:
                logger.info("回退使用缓存的概念板块成分股: board=%s count=%s", board_code, len(cached_codes))
                return cached_codes
            return []

        if df is None or df.empty:
            logger.warning("概念板块成分股为空: board=%s", board_code)
            cached_codes = self._load_cached_board_constituents(board_code)
            if cached_codes:
                logger.info("概念板块成分股为空，回退使用缓存: board=%s count=%s", board_code, len(cached_codes))
                return cached_codes
            return []

        code_col = "代码" if "代码" in df.columns else next(
            (col for col in df.columns if "代码" in str(col)),
            None,
        )
        if code_col is None:
            logger.warning("概念板块成分股缺少代码字段: board=%s columns=%s", board_code, list(df.columns))
            cached_codes = self._load_cached_board_constituents(board_code)
            if cached_codes:
                logger.info("概念板块成分股字段缺失，回退使用缓存: board=%s count=%s", board_code, len(cached_codes))
                return cached_codes
            return []

        resolved = ThemeStockPoolService.normalize_codes(
            [str(value).strip() for value in df[code_col].tolist()]
        )
        self._save_cached_board_constituents(board_code, resolved)
        logger.info("概念板块成分股获取成功: board=%s count=%s", board_code, len(resolved))
        return resolved

    def _fetch_dc_theme_constituent_codes(self, theme_code: str) -> List[str]:
        trade_date = self._dc_theme_trade_dates.get(str(theme_code or "").upper(), "")
        try:
            client = self._get_tushare_client()
            if client is None:
                raise RuntimeError("Tushare Token 未配置")
            kwargs = {"theme_code": str(theme_code or "").upper()}
            if trade_date:
                kwargs["trade_date"] = trade_date
            df = client.query(
                "dc_concept_cons",
                fields="ts_code,trade_date,name",
                **kwargs,
            )
        except Exception as exc:
            logger.warning("获取 Tushare 东财题材成分股失败: theme=%s err=%s", theme_code, exc)
            cached_codes = self._load_cached_dc_theme_constituents(theme_code)
            if cached_codes:
                logger.info(
                    "回退使用缓存的 Tushare 东财题材成分股: theme=%s count=%s",
                    theme_code,
                    len(cached_codes),
                )
                return cached_codes
            return []

        if df is None or df.empty:
            logger.warning("Tushare 东财题材成分股为空: theme=%s", theme_code)
            cached_codes = self._load_cached_dc_theme_constituents(theme_code)
            if cached_codes:
                logger.info(
                    "Tushare 东财题材成分股为空，回退使用缓存: theme=%s count=%s",
                    theme_code,
                    len(cached_codes),
                )
                return cached_codes
            return []

        working_df = df.copy()
        if "trade_date" in working_df.columns:
            working_df["trade_date"] = working_df["trade_date"].astype(str).str.strip()
            working_df = (
                working_df.sort_values(by=["trade_date", "ts_code"], ascending=[False, True])
                .drop_duplicates(subset=["ts_code"], keep="first")
                .reset_index(drop=True)
            )
        resolved = ThemeStockPoolService.normalize_codes(
            [str(value).strip() for value in working_df["ts_code"].tolist()]
        )
        self._save_cached_dc_theme_constituents(str(theme_code or "").upper(), resolved)
        logger.info("Tushare 东财题材成分股获取成功: theme=%s count=%s", theme_code, len(resolved))
        return resolved

    def _lookup_mapped_dc_code(self, theme: ThemeDefinitionSchema, em_code: str) -> Optional[str]:
        mappings = getattr(theme, "board_code_mappings", {}) or {}
        if not isinstance(mappings, dict):
            mappings = {}
        mapped = str(mappings.get(str(em_code or "").upper()) or "").strip().upper()
        if _DC_THEME_CODE_PATTERN.match(mapped):
            logger.info("主题板块局部映射命中: %s -> %s", em_code, mapped)
            return mapped

        global_mappings = self._load_global_board_mappings()
        mapped = str(global_mappings.get(str(em_code or "").upper()) or "").strip().upper()
        if _DC_THEME_CODE_PATTERN.match(mapped):
            logger.info("主题板块全局映射命中: %s -> %s", em_code, mapped)
            return mapped
        return None

    def _apply_board_index(self, normalized_df: pd.DataFrame) -> None:
        self._board_index_df = normalized_df
        self._board_name_to_code = {
            row["板块名称"]: row["板块代码"] for _, row in normalized_df.iterrows()
        }
        self._normalized_board_name_to_code = {}
        for _, row in normalized_df.iterrows():
            normalized_name = self._normalize_board_name(row["板块名称"])
            if normalized_name and normalized_name not in self._normalized_board_name_to_code:
                self._normalized_board_name_to_code[normalized_name] = row["板块代码"]

    def _apply_dc_theme_index(self, normalized_df: pd.DataFrame) -> None:
        self._dc_theme_index_df = normalized_df
        self._dc_theme_name_to_code = {
            row["题材名称"]: row["题材代码"] for _, row in normalized_df.iterrows()
        }
        self._normalized_dc_theme_name_to_code = {}
        self._dc_theme_trade_dates = {}
        for _, row in normalized_df.iterrows():
            normalized_name = self._normalize_board_name(row["题材名称"])
            if normalized_name and normalized_name not in self._normalized_dc_theme_name_to_code:
                self._normalized_dc_theme_name_to_code[normalized_name] = row["题材代码"]
            self._dc_theme_trade_dates[str(row["题材代码"]).upper()] = str(row["交易日期"])

    def _load_cached_board_index(self) -> Optional[pd.DataFrame]:
        payload = self._load_cache_payload()
        board_index_payload = payload.get("board_index") or []
        items = self._extract_cached_items(board_index_payload)
        if not self._is_cache_usable(board_index_payload):
            return None
        if not items:
            return None
        try:
            df = pd.DataFrame(items)
        except Exception:
            return None
        if df.empty or "板块名称" not in df.columns or "板块代码" not in df.columns:
            return None
        df["板块名称"] = df["板块名称"].astype(str).str.strip()
        df["板块代码"] = df["板块代码"].astype(str).str.strip().str.upper()
        df = df[df["板块名称"].astype(bool) & df["板块代码"].astype(bool)].drop_duplicates(subset=["板块代码"])
        return df if not df.empty else None

    def _save_cached_board_index(self, normalized_df: pd.DataFrame) -> None:
        payload = self._load_cache_payload()
        payload["board_index"] = {
            "items": normalized_df.to_dict("records"),
            "cached_at": int(time.time()),
        }
        self._save_cache_payload(payload)

    def _load_cached_dc_theme_index(self) -> Optional[pd.DataFrame]:
        payload = self._load_cache_payload()
        dc_theme_index_payload = payload.get("dc_theme_index") or []
        items = self._extract_cached_items(dc_theme_index_payload)
        if not self._is_cache_usable(dc_theme_index_payload):
            return None
        if not items:
            return None
        try:
            df = pd.DataFrame(items)
        except Exception:
            return None
        if df.empty or "题材名称" not in df.columns or "题材代码" not in df.columns:
            return None
        df["题材名称"] = df["题材名称"].astype(str).str.strip()
        df["题材代码"] = df["题材代码"].astype(str).str.strip().str.upper()
        df["交易日期"] = df.get("交易日期", "").astype(str).str.strip()
        df = df[df["题材名称"].astype(bool) & df["题材代码"].astype(bool)].drop_duplicates(subset=["题材代码"])
        return df if not df.empty else None

    def _save_cached_dc_theme_index(self, normalized_df: pd.DataFrame) -> None:
        payload = self._load_cache_payload()
        payload["dc_theme_index"] = {
            "items": normalized_df.to_dict("records"),
            "cached_at": int(time.time()),
        }
        self._save_cache_payload(payload)

    def _load_cached_board_constituents(self, board_code: str) -> List[str]:
        payload = self._load_cache_payload()
        boards = payload.get("board_constituents") or {}
        board_payload = boards.get(str(board_code or "").upper()) or {}
        if not self._is_cache_usable(board_payload):
            return []
        raw_codes = self._extract_cached_codes(board_payload)
        if not isinstance(raw_codes, list):
            return []
        return ThemeStockPoolService.normalize_codes(raw_codes)

    def _save_cached_board_constituents(self, board_code: str, codes: List[str]) -> None:
        normalized_codes = ThemeStockPoolService.normalize_codes(codes)
        if not normalized_codes:
            return
        payload = self._load_cache_payload()
        boards = payload.setdefault("board_constituents", {})
        boards[str(board_code or "").upper()] = {
            "codes": normalized_codes,
            "cached_at": int(time.time()),
        }
        self._save_cache_payload(payload)

    def _load_cached_dc_theme_constituents(self, theme_code: str) -> List[str]:
        payload = self._load_cache_payload()
        themes = payload.get("dc_theme_constituents") or {}
        theme_payload = themes.get(str(theme_code or "").upper()) or {}
        if not self._is_cache_usable(theme_payload):
            return []
        raw_codes = self._extract_cached_codes(theme_payload)
        if not isinstance(raw_codes, list):
            return []
        return ThemeStockPoolService.normalize_codes(raw_codes)

    def _save_cached_dc_theme_constituents(self, theme_code: str, codes: List[str]) -> None:
        normalized_codes = ThemeStockPoolService.normalize_codes(codes)
        if not normalized_codes:
            return
        payload = self._load_cache_payload()
        themes = payload.setdefault("dc_theme_constituents", {})
        themes[str(theme_code or "").upper()] = {
            "codes": normalized_codes,
            "cached_at": int(time.time()),
        }
        self._save_cache_payload(payload)

    def _get_tushare_client(self) -> Optional[_TushareHttpClient]:
        if self._tushare_client is not None:
            return self._tushare_client

        token = str(get_theme_picker_config().tushare_token or "").strip()
        if not token:
            return None

        self._tushare_client = _TushareHttpClient(token=token, api_url="https://api.tushare.pro")
        return self._tushare_client

    def _load_global_board_mappings(self) -> Dict[str, str]:
        with self._global_mapping_lock:
            if self._global_board_to_dc_mappings is not None:
                return self._global_board_to_dc_mappings

            target_path = self.global_mapping_path
            if not target_path.exists():
                if self.example_global_mapping_path.exists():
                    target_path = self.example_global_mapping_path
                else:
                    self._global_board_to_dc_mappings = {}
                    return self._global_board_to_dc_mappings

            try:
                raw = json.loads(target_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("读取主题板块全局映射失败: %s", exc)
                self._global_board_to_dc_mappings = {}
                return self._global_board_to_dc_mappings

            if isinstance(raw, dict) and isinstance(raw.get("mappings"), dict):
                raw = raw.get("mappings")

            if not isinstance(raw, dict):
                self._global_board_to_dc_mappings = {}
                return self._global_board_to_dc_mappings

            normalized: Dict[str, str] = {}
            for raw_board_code, raw_theme_code in raw.items():
                board_code = str(raw_board_code or "").strip().upper()
                theme_code = str(raw_theme_code or "").strip().upper()
                if not _BOARD_CODE_PATTERN.match(board_code):
                    continue
                if not _DC_THEME_CODE_PATTERN.match(theme_code):
                    continue
                normalized[board_code] = theme_code

            self._global_board_to_dc_mappings = normalized
            return self._global_board_to_dc_mappings

    def _load_cache_payload(self) -> Dict[str, object]:
        with self._cache_lock:
            if not self.cache_path.exists():
                return {}
            try:
                raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.debug("读取主题板块缓存失败: %s", exc)
                return {}
            return raw if isinstance(raw, dict) else {}

    def _save_cache_payload(self, payload: Dict[str, object]) -> None:
        with self._cache_lock:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _is_cache_usable(self, cache_payload: object) -> bool:
        ttl = int(get_theme_picker_config().theme_board_cache_ttl_seconds)
        if ttl <= 0:
            return False
        if not isinstance(cache_payload, dict):
            return True
        cached_at = cache_payload.get("cached_at")
        if cached_at in (None, ""):
            return True
        try:
            cached_ts = float(cached_at)
        except (TypeError, ValueError):
            return True
        return (time.time() - cached_ts) <= ttl

    @staticmethod
    def _extract_cached_items(cache_payload: object) -> List[dict]:
        if isinstance(cache_payload, list):
            return cache_payload
        if isinstance(cache_payload, dict):
            items = cache_payload.get("items") or []
            return items if isinstance(items, list) else []
        return []

    @staticmethod
    def _extract_cached_codes(cache_payload: object) -> List[str]:
        if isinstance(cache_payload, list):
            return [str(item).strip() for item in cache_payload]
        if isinstance(cache_payload, dict):
            codes = cache_payload.get("codes") or []
            return [str(item).strip() for item in codes] if isinstance(codes, list) else []
        return []

    @staticmethod
    def _normalize_board_name(raw_name: str) -> str:
        normalized = str(raw_name or "").strip().lower()
        normalized = normalized.replace(" ", "")
        normalized = normalized.replace("概念板块", "")
        normalized = normalized.replace("概念题材", "")
        normalized = normalized.replace("概念股", "")
        normalized = normalized.replace("板块", "")
        normalized = normalized.replace("概念", "")
        normalized = normalized.replace("题材", "")
        normalized = normalized.replace("（", "(").replace("）", ")")
        normalized = normalized.replace("aigc", "ai")
        normalized = normalized.replace("人工智能", "ai")
        normalized = normalized.replace("智能应用", "ai应用")
        return normalized
