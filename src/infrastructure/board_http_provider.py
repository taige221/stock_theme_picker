# -*- coding: utf-8 -*-
"""Unified Eastmoney HTTP adapters for board-related data."""

from __future__ import annotations

import logging
import math
import random
from typing import Dict, List, Optional

import pandas as pd
import requests

from theme_picker.data_provider.base import normalize_stock_code

logger = logging.getLogger(__name__)

_BOARD_LIST_URL = "https://79.push2.eastmoney.com/api/qt/clist/get"
_INDUSTRY_BOARD_LIST_URL = "https://17.push2.eastmoney.com/api/qt/clist/get"
_BOARD_CONSTITUENTS_URL = "https://29.push2.eastmoney.com/api/qt/clist/get"
_BELONG_BOARDS_URL = "https://push2.eastmoney.com/api/qt/slist/get"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class BoardHttpProvider:
    """Encapsulate HTTP-based board access against Eastmoney."""

    def get_sector_rankings(
        self,
        n: int = 5,
        *,
        timeout_seconds: float = 10,
    ) -> tuple[list[dict], list[dict]]:
        frame = self.get_industry_board_index(timeout_seconds=timeout_seconds)
        if frame.empty or "涨跌幅" not in frame.columns or "板块名称" not in frame.columns:
            return [], []

        working = frame.copy()
        working["涨跌幅"] = pd.to_numeric(working["涨跌幅"], errors="coerce")
        working = working.dropna(subset=["涨跌幅"])
        if working.empty:
            return [], []

        top = working.nlargest(n, "涨跌幅")
        bottom = working.nsmallest(n, "涨跌幅")
        return (
            [
                {"name": str(row["板块名称"]), "change_pct": float(row["涨跌幅"])}
                for _, row in top.iterrows()
            ],
            [
                {"name": str(row["板块名称"]), "change_pct": float(row["涨跌幅"])}
                for _, row in bottom.iterrows()
            ],
        )

    def get_concept_board_index(self, *, timeout_seconds: float = 10) -> pd.DataFrame:
        frame = self._fetch_paginated_clist(
            _BOARD_LIST_URL,
            {
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f12",
                "fs": "m:90 t:3 f:!50",
                "fields": "f2,f3,f4,f8,f12,f14,f15,f16,f17,f18,f20,f21,f24,f25,f22,f33,f11,f62,f128,f124,f107,f104,f105,f136",
            },
            timeout_seconds=timeout_seconds,
        )
        if frame.empty:
            return pd.DataFrame(columns=["板块名称", "板块代码"])

        column_map = {
            "f12": "板块代码",
            "f14": "板块名称",
            "f2": "最新价",
            "f3": "涨跌幅",
            "f4": "涨跌额",
            "f20": "总市值",
            "f8": "换手率",
            "f104": "上涨家数",
            "f105": "下跌家数",
            "f128": "领涨股票",
            "f136": "领涨股票-涨跌幅",
        }
        working = frame.rename(columns=column_map)
        available = [name for name in column_map.values() if name in working.columns]
        working = working[available].copy()
        for column in ("最新价", "涨跌幅", "涨跌额", "总市值", "换手率", "上涨家数", "下跌家数", "领涨股票-涨跌幅"):
            if column in working.columns:
                working[column] = pd.to_numeric(working[column], errors="coerce")
        if "板块名称" in working.columns:
            working["板块名称"] = working["板块名称"].astype(str).str.strip()
        if "板块代码" in working.columns:
            working["板块代码"] = working["板块代码"].astype(str).str.strip().str.upper()
        return working

    def get_industry_board_index(self, *, timeout_seconds: float = 10) -> pd.DataFrame:
        frame = self._fetch_paginated_clist(
            _INDUSTRY_BOARD_LIST_URL,
            {
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": "m:90 t:2 f:!50",
                "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,f140,f141,f207,f208,f209,f222",
            },
            timeout_seconds=timeout_seconds,
        )
        if frame.empty:
            return pd.DataFrame(columns=["板块名称", "板块代码", "涨跌幅"])

        column_map = {
            "f12": "板块代码",
            "f14": "板块名称",
            "f2": "最新价",
            "f3": "涨跌幅",
            "f4": "涨跌额",
            "f20": "总市值",
            "f8": "换手率",
            "f104": "上涨家数",
            "f105": "下跌家数",
            "f128": "领涨股票",
            "f136": "领涨股票-涨跌幅",
        }
        working = frame.rename(columns=column_map)
        available = [name for name in column_map.values() if name in working.columns]
        working = working[available].copy()
        for column in ("最新价", "涨跌幅", "涨跌额", "总市值", "换手率", "上涨家数", "下跌家数", "领涨股票-涨跌幅"):
            if column in working.columns:
                working[column] = pd.to_numeric(working[column], errors="coerce")
        if "板块名称" in working.columns:
            working["板块名称"] = working["板块名称"].astype(str).str.strip()
        if "板块代码" in working.columns:
            working["板块代码"] = working["板块代码"].astype(str).str.strip().str.upper()
        return working

    def get_concept_board_constituents(
        self,
        board_code: str,
        *,
        timeout_seconds: float = 10,
    ) -> pd.DataFrame:
        normalized_board_code = str(board_code or "").strip().upper()
        if not normalized_board_code:
            return pd.DataFrame(columns=["代码", "名称"])

        frame = self._fetch_paginated_clist(
            _BOARD_CONSTITUENTS_URL,
            {
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f12",
                "fs": f"b:{normalized_board_code} f:!50",
                "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152,f45",
            },
            timeout_seconds=timeout_seconds,
        )
        if frame.empty:
            return pd.DataFrame(columns=["代码", "名称"])

        column_map = {
            "f12": "代码",
            "f14": "名称",
            "f2": "最新价",
            "f3": "涨跌幅",
            "f4": "涨跌额",
            "f5": "成交量",
            "f6": "成交额",
            "f7": "振幅",
            "f8": "换手率",
            "f9": "市盈率-动态",
            "f15": "最高",
            "f16": "最低",
            "f17": "今开",
            "f18": "昨收",
            "f23": "市净率",
        }
        working = frame.rename(columns=column_map)
        available = [name for name in column_map.values() if name in working.columns]
        working = working[available].copy()
        for column in (
            "最新价",
            "涨跌幅",
            "涨跌额",
            "成交量",
            "成交额",
            "振幅",
            "换手率",
            "市盈率-动态",
            "最高",
            "最低",
            "今开",
            "昨收",
            "市净率",
        ):
            if column in working.columns:
                working[column] = pd.to_numeric(working[column], errors="coerce")
        if "代码" in working.columns:
            working["代码"] = working["代码"].astype(str).str.strip()
        if "名称" in working.columns:
            working["名称"] = working["名称"].astype(str).str.strip()
        return working

    def get_belong_boards(self, stock_code: str, *, timeout_seconds: float = 10) -> pd.DataFrame:
        normalized = normalize_stock_code(stock_code)
        if not normalized or not normalized.isdigit() or len(normalized) != 6:
            return pd.DataFrame(columns=["股票代码", "股票名称", "板块代码", "板块名称", "板块涨幅"])

        response = requests.get(
            _BELONG_BOARDS_URL,
            params=(
                ("forcect", "1"),
                ("spt", "3"),
                ("fields", "f1,f12,f152,f3,f14,f128,f136"),
                ("pi", "0"),
                ("pz", "1000"),
                ("po", "1"),
                ("fid", "f3"),
                ("fid0", "f4003"),
                ("invt", "2"),
                ("secid", self._to_stock_secid(normalized)),
            ),
            headers=self._default_headers(referer="https://quote.eastmoney.com/"),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = ((payload.get("data") or {}).get("diff")) or []
        if not data:
            return pd.DataFrame(columns=["股票代码", "股票名称", "板块代码", "板块名称", "板块涨幅"])

        frame = pd.DataFrame(data)
        if frame.empty:
            return pd.DataFrame(columns=["股票代码", "股票名称", "板块代码", "板块名称", "板块涨幅"])

        renamed = frame.rename(columns={"f12": "板块代码", "f14": "板块名称", "f3": "板块涨幅"})
        renamed = renamed[[name for name in ("板块代码", "板块名称", "板块涨幅") if name in renamed.columns]].copy()
        if "板块涨幅" in renamed.columns:
            renamed["板块涨幅"] = pd.to_numeric(renamed["板块涨幅"], errors="coerce") / 100.0
        if "板块代码" in renamed.columns:
            renamed["板块代码"] = renamed["板块代码"].astype(str).str.strip().str.upper()
        if "板块名称" in renamed.columns:
            renamed["板块名称"] = renamed["板块名称"].astype(str).str.strip()
        renamed.insert(0, "股票名称", "")
        renamed.insert(1, "股票代码", normalized)
        return renamed

    def _fetch_paginated_clist(
        self,
        url: str,
        params: Dict[str, str],
        *,
        timeout_seconds: float,
    ) -> pd.DataFrame:
        base_params = dict(params)
        first_page = self._request_json(url, base_params, timeout_seconds=timeout_seconds)
        first_diff = ((first_page.get("data") or {}).get("diff")) or []
        if not first_diff:
            return pd.DataFrame()

        total = int(((first_page.get("data") or {}).get("total")) or len(first_diff))
        per_page = max(1, len(first_diff))
        total_pages = max(1, math.ceil(total / per_page))

        frames: List[pd.DataFrame] = [pd.DataFrame(first_diff)]
        for page in range(2, total_pages + 1):
            page_params = dict(base_params)
            page_params["pn"] = str(page)
            page_json = self._request_json(url, page_params, timeout_seconds=timeout_seconds)
            page_diff = ((page_json.get("data") or {}).get("diff")) or []
            if not page_diff:
                continue
            frames.append(pd.DataFrame(page_diff))

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _request_json(self, url: str, params: Dict[str, str], *, timeout_seconds: float) -> Dict:
        response = requests.get(
            url,
            params=params,
            headers=self._default_headers(referer="https://quote.eastmoney.com/"),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Eastmoney board payload invalid: {type(payload).__name__}")
        return payload

    @staticmethod
    def _to_stock_secid(stock_code: str) -> str:
        if stock_code.startswith(("5", "6", "9")):
            return f"1.{stock_code}"
        return f"0.{stock_code}"

    @staticmethod
    def _default_headers(*, referer: str) -> Dict[str, str]:
        return {
            "Referer": referer,
            "User-Agent": random.choice(_USER_AGENTS),
        }


_BOARD_HTTP_PROVIDER: Optional[BoardHttpProvider] = None


def get_board_http_provider() -> BoardHttpProvider:
    global _BOARD_HTTP_PROVIDER
    if _BOARD_HTTP_PROVIDER is None:
        _BOARD_HTTP_PROVIDER = BoardHttpProvider()
    return _BOARD_HTTP_PROVIDER
