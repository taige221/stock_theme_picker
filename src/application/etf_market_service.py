# -*- coding: utf-8 -*-
"""ETF market snapshot service backed by mootdx and Tencent quote."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional

from mootdx.quotes import Quotes

from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.infrastructure.daily_bar_service import get_daily_bar_resolver
from theme_picker.infrastructure.stock_pool_service import canonicalize_stock_code, is_etf_code

logger = logging.getLogger(__name__)

_TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
_TENCENT_USER_AGENT = "Mozilla/5.0"


class EtfMarketService:
    """Expose a small, Eastmoney-free ETF market snapshot."""

    def __init__(self) -> None:
        self.daily_bar_resolver = get_daily_bar_resolver()

    def get_snapshot(self, stock_code: str, *, bars: int = 20) -> Dict[str, Any]:
        base_code = self._normalize_etf_code(stock_code)
        canonical_code = canonicalize_stock_code(base_code)
        errors: List[str] = []

        quote_payload: Dict[str, Any] = {}
        order_book_payload: Dict[str, Any] = {}
        kline_payload: List[Dict[str, Any]] = []
        daily_bar_source = "wrapped_daily_bar:mootdx"

        try:
            quote_payload = self._fetch_tencent_quote(base_code)
        except Exception as exc:
            logger.warning("ETF 腾讯行情失败: code=%s error=%s", base_code, exc)
            errors.append(f"tencent quote failed: {exc}")

        try:
            daily_result = self.daily_bar_resolver.resolve_daily_bars(
                canonical_code,
                bars=bars,
                minimum_rows=1,
            )
            daily_bar_source = daily_result.data_source
            kline_payload = self._serialize_daily_bars(daily_result.frame)
            errors.extend(daily_result.errors)
        except Exception as exc:
            logger.warning("ETF 统一日K失败: code=%s error=%s", base_code, exc)
            errors.append(f"daily bars failed: {exc}")

        try:
            order_book_payload = self._fetch_mootdx_quote(base_code)
        except Exception as exc:
            logger.warning("ETF mootdx 盘口失败: code=%s error=%s", base_code, exc)
            errors.append(f"mootdx quote failed: {exc}")

        if not quote_payload and order_book_payload:
            quote_payload = {
                "name": order_book_payload.get("name"),
                "price": order_book_payload.get("price"),
                "last_close": order_book_payload.get("last_close"),
                "open": order_book_payload.get("open"),
                "high": order_book_payload.get("high"),
                "low": order_book_payload.get("low"),
                "volume": order_book_payload.get("volume"),
                "amount": order_book_payload.get("amount"),
                "server_time": order_book_payload.get("server_time"),
                "raw_source": "mootdx_fallback",
            }

        if not quote_payload and not order_book_payload and not kline_payload:
            raise ValueError(f"未获取到 {canonical_code} 的 ETF 市场数据")

        response: Dict[str, Any] = {
            "stock_code": canonical_code,
            "base_code": base_code,
            "stock_name": quote_payload.get("name") or order_book_payload.get("name") or canonical_code,
            "instrument_type": "etf",
            "instrument_label": "ETF",
            "quote": quote_payload,
            "daily_bars": kline_payload,
            "order_book": order_book_payload,
            "data_sources": {
                "quote": "tencent",
                "daily_bars": daily_bar_source,
                "order_book": "mootdx",
            },
            "errors": errors,
        }
        return response

    def _normalize_etf_code(self, stock_code: str) -> str:
        normalized = normalize_stock_code(stock_code)
        if not is_etf_code(normalized):
            raise ValueError(f"不是可识别的 A 股 ETF 代码: {stock_code}")
        return normalized

    def _fetch_tencent_quote(self, base_code: str) -> Dict[str, Any]:
        prefix = self._market_prefix(base_code)
        request = urllib.request.Request(
            f"{_TENCENT_QUOTE_URL}{prefix}{base_code}",
            headers={"User-Agent": _TENCENT_USER_AGENT},
        )
        payload = urllib.request.urlopen(request, timeout=10).read().decode("gbk", errors="ignore")
        raw = payload.strip()
        if "=" not in raw or '"' not in raw:
            raise ValueError(f"腾讯行情返回异常: {raw[:120]}")

        fields = raw.split('"')[1].split("~")
        if len(fields) < 53:
            raise ValueError(f"腾讯行情字段不足: field_count={len(fields)}")

        return {
            "name": fields[1] or None,
            "price": self._safe_float(fields[3]),
            "last_close": self._safe_float(fields[4]),
            "open": self._safe_float(fields[5]),
            "high": self._safe_float(fields[33]),
            "low": self._safe_float(fields[34]),
            "change_amount": self._safe_float(fields[31]),
            "change_pct": self._safe_float(fields[32]),
            "amount_wan": self._safe_float(fields[37]),
            "turnover_rate": self._safe_float(fields[38]),
            "pe_ttm": self._safe_float(fields[39]),
            "amplitude_pct": self._safe_float(fields[43]),
            "total_market_value_yi": self._safe_float(fields[44]),
            "float_market_value_yi": self._safe_float(fields[45]),
            "pb": self._safe_float(fields[46]),
            "limit_up": self._safe_float(fields[47]),
            "limit_down": self._safe_float(fields[48]),
            "volume_ratio": self._safe_float(fields[49]),
            "pe_static": self._safe_float(fields[52]),
            "trade_time": fields[30] or None,
            "raw_source": "tencent",
        }

    def _fetch_mootdx_quote(self, base_code: str) -> Dict[str, Any]:
        client = Quotes.factory(market="std")
        df = client.quotes(symbol=[base_code])
        if df is None or df.empty:
            return {}

        row = df.iloc[0]
        return {
            "name": self._safe_text(row.get("name")),
            "price": self._safe_float(row.get("price")),
            "last_close": self._safe_float(row.get("last_close")),
            "open": self._safe_float(row.get("open")),
            "high": self._safe_float(row.get("high")),
            "low": self._safe_float(row.get("low")),
            "volume": self._safe_float(row.get("vol") or row.get("volume")),
            "amount": self._safe_float(row.get("amount")),
            "server_time": self._safe_text(row.get("servertime")),
            "bid1": self._safe_float(row.get("bid1")),
            "ask1": self._safe_float(row.get("ask1")),
            "bid_vol1": self._safe_float(row.get("bid_vol1")),
            "ask_vol1": self._safe_float(row.get("ask_vol1")),
            "raw_source": "mootdx",
        }

    @staticmethod
    def _serialize_daily_bars(frame) -> List[Dict[str, Any]]:
        if frame is None or getattr(frame, "empty", True):
            return []
        rows: List[Dict[str, Any]] = []
        for item in get_daily_bar_resolver().serialize_frame(frame):
            rows.append(
                {
                    "datetime": item.get("datetime"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": item.get("volume"),
                    "amount": item.get("amount"),
                }
            )
        return rows

    @staticmethod
    def _market_prefix(base_code: str) -> str:
        if base_code.startswith(("5", "6", "9")):
            return "sh"
        if base_code.startswith("8"):
            return "bj"
        return "sz"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value in (None, "", "--"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_text(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)


_ETF_MARKET_SERVICE: Optional[EtfMarketService] = None


def get_etf_market_service() -> EtfMarketService:
    global _ETF_MARKET_SERVICE
    if _ETF_MARKET_SERVICE is None:
        _ETF_MARKET_SERVICE = EtfMarketService()
    return _ETF_MARKET_SERVICE
