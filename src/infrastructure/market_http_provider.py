# -*- coding: utf-8 -*-
"""Unified HTTP adapters for CN realtime quote sources.

This module centralizes A-share / ETF realtime HTTP access so upper layers do
not directly mix request construction, response parsing, and fallback policy.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

import requests

from theme_picker.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote, safe_float, safe_int

logger = logging.getLogger(__name__)

_SINA_REALTIME_URL = "http://hq.sinajs.cn/list="
_TENCENT_REALTIME_URL = "http://qt.gtimg.cn/q="
_EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class MarketHttpProvider:
    """Encapsulate HTTP-based realtime quote providers."""

    def get_quote(
        self,
        stock_code: str,
        *,
        source: str,
        timeout_seconds: float = 10,
    ) -> Optional[UnifiedRealtimeQuote]:
        normalized = self._normalize_stock_code(stock_code)
        if not normalized or not normalized.isdigit() or len(normalized) != 6:
            return None

        source_key = str(source or "").strip().lower()
        if source_key in {"efinance", "akshare_em"}:
            return self.get_eastmoney_quote(
                normalized,
                timeout_seconds=timeout_seconds,
                logical_source=source_key,
            )
        if source_key == "akshare_sina":
            return self.get_sina_quote(normalized, timeout_seconds=timeout_seconds)
        if source_key in {"tencent", "akshare_qq"}:
            return self.get_tencent_quote(normalized, timeout_seconds=timeout_seconds)
        return None

    def get_tencent_quote(self, stock_code: str, *, timeout_seconds: float = 10) -> Optional[UnifiedRealtimeQuote]:
        symbol = self._to_sina_tx_symbol(stock_code)
        response = requests.get(
            f"{_TENCENT_REALTIME_URL}{symbol}",
            headers=self._default_headers(referer="http://finance.qq.com"),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        raw = response.text.strip()
        if "=" not in raw or '"' not in raw:
            raise ValueError(f"腾讯行情返回异常: {raw[:120]}")

        fields = raw.split('"')[1].split("~")
        if len(fields) < 45:
            raise ValueError(f"腾讯行情字段不足: field_count={len(fields)}")

        return UnifiedRealtimeQuote(
            code=stock_code,
            name=fields[1] or "",
            source=RealtimeSource.TENCENT,
            price=safe_float(fields[3]),
            pre_close=safe_float(fields[4]),
            open_price=safe_float(fields[5]),
            change_amount=safe_float(fields[31]),
            change_pct=safe_float(fields[32]),
            high=safe_float(fields[33]),
            low=safe_float(fields[34]),
            volume=safe_int(fields[6]) * 100 if len(fields) > 6 and fields[6] else None,
            amount=safe_float(fields[37]) * 10000 if len(fields) > 37 and fields[37] else None,
            turnover_rate=safe_float(fields[38]) if len(fields) > 38 else None,
            pe_ratio=safe_float(fields[39]) if len(fields) > 39 else None,
            amplitude=safe_float(fields[43]) if len(fields) > 43 else None,
            circ_mv=self._yi_to_yuan(fields[44]) if len(fields) > 44 else None,
            total_mv=self._yi_to_yuan(fields[45]) if len(fields) > 45 else None,
            pb_ratio=safe_float(fields[46]) if len(fields) > 46 else None,
            volume_ratio=safe_float(fields[49]) if len(fields) > 49 else None,
        )

    def get_sina_quote(self, stock_code: str, *, timeout_seconds: float = 10) -> Optional[UnifiedRealtimeQuote]:
        symbol = self._to_sina_tx_symbol(stock_code)
        response = requests.get(
            f"{_SINA_REALTIME_URL}{symbol}",
            headers=self._default_headers(referer="http://finance.sina.com.cn"),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        raw = response.text.strip()
        if "=" not in raw or '"' not in raw:
            raise ValueError(f"新浪行情返回异常: {raw[:120]}")

        fields = raw.split('"')[1].split(",")
        if len(fields) < 32:
            raise ValueError(f"新浪行情字段不足: field_count={len(fields)}")

        price = safe_float(fields[3])
        pre_close = safe_float(fields[2])
        change_amount = None
        change_pct = None
        if price is not None and pre_close not in (None, 0):
            change_amount = price - pre_close
            change_pct = (change_amount / pre_close) * 100

        return UnifiedRealtimeQuote(
            code=stock_code,
            name=fields[0] or "",
            source=RealtimeSource.SINA,
            price=price,
            pre_close=pre_close,
            open_price=safe_float(fields[1]),
            high=safe_float(fields[4]),
            low=safe_float(fields[5]),
            change_amount=change_amount,
            change_pct=change_pct,
            volume=safe_int(fields[8]),
            amount=safe_float(fields[9]),
        )

    def get_eastmoney_quote(
        self,
        stock_code: str,
        *,
        timeout_seconds: float = 10,
        logical_source: str = "akshare_em",
    ) -> Optional[UnifiedRealtimeQuote]:
        response = requests.get(
            _EASTMONEY_QUOTE_URL,
            params={
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "invt": "2",
                "fltt": "2",
                "fields": ",".join(
                    [
                        "f57",  # code
                        "f58",  # name
                        "f43",  # price
                        "f46",  # open
                        "f44",  # high
                        "f45",  # low
                        "f60",  # pre_close
                        "f47",  # volume
                        "f48",  # amount
                        "f50",  # volume_ratio
                        "f168", # turnover_rate
                        "f169", # change_amount
                        "f170", # change_pct
                        "f171", # amplitude
                        "f162", # pe_ratio
                        "f167", # pb_ratio
                        "f116", # total_mv
                        "f117", # circ_mv
                    ]
                ),
                "secid": self._to_eastmoney_secid(stock_code),
            },
            headers=self._default_headers(referer="https://quote.eastmoney.com/"),
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        if not data:
            raise ValueError(f"东财行情返回为空: {payload}")

        quote = UnifiedRealtimeQuote(
            code=str(data.get("f57") or stock_code),
            name=str(data.get("f58") or ""),
            source=RealtimeSource.EFINANCE if logical_source == "efinance" else RealtimeSource.AKSHARE_EM,
            price=self._scale_price(data.get("f43")),
            pre_close=self._scale_price(data.get("f60")),
            open_price=self._scale_price(data.get("f46")),
            high=self._scale_price(data.get("f44")),
            low=self._scale_price(data.get("f45")),
            volume=safe_int(data.get("f47")),
            amount=safe_float(data.get("f48")),
            volume_ratio=self._scale_pct(data.get("f50")),
            turnover_rate=self._scale_pct(data.get("f168")),
            change_amount=self._scale_price(data.get("f169")),
            change_pct=self._scale_pct(data.get("f170")),
            amplitude=self._scale_pct(data.get("f171")),
            pe_ratio=self._scale_price(data.get("f162")),
            pb_ratio=self._scale_price(data.get("f167")),
            total_mv=safe_float(data.get("f116")),
            circ_mv=safe_float(data.get("f117")),
        )
        if quote.price is None and quote.pre_close not in (None, 0) and quote.change_pct is not None:
            quote.price = quote.pre_close * (1 + quote.change_pct / 100)
        return quote

    @staticmethod
    def _normalize_stock_code(stock_code: str) -> str:
        text = str(stock_code or "").strip().upper()
        if not text:
            return ""
        if "." in text:
            base, _ = text.rsplit(".", 1)
            if base.isdigit():
                return base
        if text.startswith(("SH", "SZ", "BJ")) and len(text) == 8 and text[2:].isdigit():
            return text[2:]
        if text.isdigit():
            return text
        return text

    @staticmethod
    def _to_sina_tx_symbol(stock_code: str) -> str:
        if stock_code.startswith(("6", "9")):
            return f"sh{stock_code}"
        if stock_code.startswith("8"):
            return f"bj{stock_code}"
        return f"sz{stock_code}"

    @staticmethod
    def _to_eastmoney_secid(stock_code: str) -> str:
        if stock_code.startswith(("5", "6", "9")):
            return f"1.{stock_code}"
        return f"0.{stock_code}"

    @staticmethod
    def _default_headers(*, referer: str) -> dict:
        return {
            "Referer": referer,
            "User-Agent": random.choice(_USER_AGENTS),
        }

    @staticmethod
    def _scale_price(value) -> Optional[float]:
        raw = safe_float(value)
        if raw is None:
            return None
        return raw / 100.0

    @staticmethod
    def _scale_pct(value) -> Optional[float]:
        raw = safe_float(value)
        if raw is None:
            return None
        return raw / 100.0

    @staticmethod
    def _yi_to_yuan(value) -> Optional[float]:
        raw = safe_float(value)
        if raw is None:
            return None
        return raw * 100000000.0


_MARKET_HTTP_PROVIDER: Optional[MarketHttpProvider] = None


def get_market_http_provider() -> MarketHttpProvider:
    global _MARKET_HTTP_PROVIDER
    if _MARKET_HTTP_PROVIDER is None:
        _MARKET_HTTP_PROVIDER = MarketHttpProvider()
    return _MARKET_HTTP_PROVIDER
