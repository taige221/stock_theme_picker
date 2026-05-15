# -*- coding: utf-8 -*-
"""ETF market snapshot service backed by mootdx and Tencent quote."""

from __future__ import annotations

from datetime import datetime
import json
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional

import akshare as ak
from mootdx.quotes import Quotes
import requests

from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.infrastructure.daily_bar_service import get_daily_bar_resolver
from theme_picker.infrastructure.stock_pool_service import canonicalize_stock_code, is_etf_code

logger = logging.getLogger(__name__)

_TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
_TENCENT_USER_AGENT = "Mozilla/5.0"
_ETF_PROFILE_URL = "https://fundf10.eastmoney.com/jbgk_{code}.html"
_ETF_PROFILE_USER_AGENT = "Mozilla/5.0"


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
        profile_payload: Dict[str, Any] = {}
        top_holdings_payload: List[Dict[str, Any]] = []
        daily_bar_source = "wrapped_daily_bar:mootdx"
        quote_source = "tencent"

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

        try:
            profile_payload = self._fetch_etf_profile(base_code)
        except Exception as exc:
            logger.warning("ETF 档案信息失败: code=%s error=%s", base_code, exc)
            errors.append(f"etf profile failed: {exc}")

        try:
            top_holdings_payload = self._fetch_top_holdings(base_code)
        except Exception as exc:
            logger.warning("ETF 重仓股失败: code=%s error=%s", base_code, exc)
            errors.append(f"etf top holdings failed: {exc}")

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

        quote_source = self._resolve_quote_source(quote_payload)

        response: Dict[str, Any] = {
            "stock_code": canonical_code,
            "base_code": base_code,
            "stock_name": quote_payload.get("name") or order_book_payload.get("name") or canonical_code,
            "instrument_type": "etf",
            "instrument_label": "ETF",
            "quote": quote_payload,
            "daily_bars": kline_payload,
            "order_book": order_book_payload,
            "profile": profile_payload,
            "top_holdings": top_holdings_payload,
            "data_sources": {
                "quote": quote_source,
                "daily_bars": daily_bar_source,
                "order_book": "mootdx",
                "profile": "eastmoney_fund_archive",
                "top_holdings": "eastmoney_fund_portfolio",
            },
            "errors": errors,
        }
        return response

    @staticmethod
    def _resolve_quote_source(quote_payload: Dict[str, Any]) -> str:
        raw_source = str((quote_payload or {}).get("raw_source") or "").strip()
        if raw_source:
            return raw_source
        return "unknown"

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

    def _fetch_etf_profile(self, base_code: str) -> Dict[str, Any]:
        response = requests.get(
            _ETF_PROFILE_URL.format(code=base_code),
            headers={"User-Agent": _ETF_PROFILE_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        html = response.text
        text_lines = [
            line.strip()
            for line in re.split(r"[\r\n]+", re.sub(r"<[^>]+>", "\n", html))
            if line and line.strip()
        ]
        if not text_lines:
            return {}

        def _next_value(label: str) -> Optional[str]:
            for idx, item in enumerate(text_lines):
                if item == label:
                    for candidate in text_lines[idx + 1 : idx + 6]:
                        if candidate and candidate != label:
                            return candidate.strip()
            return None

        return {
            "fund_full_name": _next_value("基金全称"),
            "fund_type": _next_value("基金类型"),
            "tracking_target": _next_value("跟踪标的"),
            "performance_benchmark": _next_value("业绩比较基准"),
            "investment_objective": _next_value("投资目标"),
        }

    def _fetch_top_holdings(self, base_code: str) -> List[Dict[str, Any]]:
        current_year = datetime.now().year
        frames = []
        for year in (current_year, current_year - 1, current_year - 2):
            try:
                frame = ak.fund_portfolio_hold_em(symbol=base_code, date=str(year))
            except Exception:
                continue
            if frame is not None and not frame.empty:
                frames.append(frame)
                break

        if not frames:
            return []

        frame = frames[0].copy()
        rows: List[Dict[str, Any]] = []
        for _, row in frame.head(10).iterrows():
            rows.append(
                {
                    "rank": self._safe_int(row.get("序号")),
                    "stock_code": self._safe_text(row.get("股票代码")),
                    "stock_name": self._safe_text(row.get("股票名称")),
                    "weight_pct": self._safe_float(row.get("占净值比例")),
                    "shares_wan": self._safe_float(row.get("持股数")),
                    "market_value_wan": self._safe_float(row.get("持仓市值")),
                    "report_period": self._safe_text(row.get("季度")),
                }
            )
        return rows

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
    def _safe_int(value: Any) -> Optional[int]:
        if value in (None, "", "--"):
            return None
        try:
            return int(float(value))
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
