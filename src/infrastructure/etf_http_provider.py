# -*- coding: utf-8 -*-
"""ETF external HTTP/provider adapters.

This module centralizes ETF-related external data access so application services
do not directly mix request construction, parsing, and business logic.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import re
from typing import Any, Dict, List, Optional

import akshare as ak
import requests

from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.infrastructure.stock_pool_service import canonicalize_stock_code

logger = logging.getLogger(__name__)

_TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
_TENCENT_USER_AGENT = "Mozilla/5.0"
_ETF_PROFILE_URL = "https://fundf10.eastmoney.com/jbgk_{code}.html"
_ETF_PROFILE_USER_AGENT = "Mozilla/5.0"


class EtfHttpProvider:
    """Encapsulate ETF external HTTP/adapter access."""

    def get_tencent_quote(self, base_code: str) -> Dict[str, Any]:
        prefix = self._market_prefix(base_code)
        response = requests.get(
            f"{_TENCENT_QUOTE_URL}{prefix}{base_code}",
            headers={"User-Agent": _TENCENT_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        raw = response.text.strip()
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

    def get_etf_profile(self, base_code: str) -> Dict[str, Any]:
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

        def next_value(label: str) -> Optional[str]:
            for idx, item in enumerate(text_lines):
                if item == label:
                    for candidate in text_lines[idx + 1 : idx + 6]:
                        if candidate and candidate != label:
                            return candidate.strip()
            return None

        return {
            "fund_full_name": next_value("基金全称"),
            "fund_type": next_value("基金类型"),
            "tracking_target": next_value("跟踪标的"),
            "performance_benchmark": next_value("业绩比较基准"),
            "investment_objective": next_value("投资目标"),
        }

    def get_etf_top_holdings(self, base_code: str) -> List[Dict[str, Any]]:
        current_year = datetime.now().year
        for year in (current_year, current_year - 1, current_year - 2):
            try:
                frame = ak.fund_portfolio_hold_em(symbol=base_code, date=str(year))
            except Exception as exc:
                logger.debug("ETF 重仓股拉取失败: code=%s year=%s error=%s", base_code, year, exc)
                continue
            if frame is None or frame.empty:
                continue

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
        return []

    def get_sse_etf_daily_metrics(self, trade_date: date | datetime | str) -> List[Dict[str, Any]]:
        normalized_date = self._normalize_trade_date(trade_date)
        frame = ak.fund_etf_scale_sse(date=normalized_date)
        if frame is None or frame.empty:
            return []

        rows: List[Dict[str, Any]] = []
        for _, row in frame.iterrows():
            canonical_code = canonicalize_stock_code(self._safe_text(row.get("基金代码")) or self._safe_text(row.get("证券代码")) or "")
            if not canonical_code:
                continue
            rows.append(
                {
                    "stock_code": canonical_code,
                    "trade_date": self._normalize_trade_date(row.get("截止日期") or normalized_date, compact=False),
                    "fund_shares": self._safe_float(row.get("基金份额")),
                    "nav": self._safe_float(row.get("单位净值")),
                    "derived_fund_size_yi": self._derive_fund_size_yi(
                        shares=self._safe_float(row.get("基金份额")),
                        nav=self._safe_float(row.get("单位净值")),
                    ),
                    "exchange": "SSE",
                    "data_source": "sse_etf_scale",
                }
            )
        return rows

    def get_szse_etf_daily_metrics(
        self,
        trade_date: date | datetime | str | None = None,
        *,
        start_date: date | datetime | str | None = None,
        end_date: date | datetime | str | None = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if start_date or end_date:
            frame = ak.fund_scale_daily_szse(
                start_date=self._normalize_trade_date(start_date or trade_date or datetime.now(), compact=False),
                end_date=self._normalize_trade_date(end_date or trade_date or datetime.now(), compact=False),
                symbol="ETF",
            )
        else:
            frame = ak.fund_etf_scale_szse()
        if frame is None or frame.empty:
            return rows

        fallback_trade_date = self._normalize_trade_date(trade_date or datetime.now(), compact=False)
        for _, row in frame.iterrows():
            canonical_code = canonicalize_stock_code(
                self._safe_text(row.get("基金代码"))
                or self._safe_text(row.get("证券代码"))
                or self._safe_text(row.get("基金简称"))
                or ""
            )
            if not canonical_code:
                continue
            nav = self._safe_float(row.get("单位净值") or row.get("最新净值"))
            shares = self._safe_float(row.get("基金份额") or row.get("份额"))
            rows.append(
                {
                    "stock_code": canonical_code,
                    "trade_date": self._normalize_trade_date(row.get("截止日期") or row.get("交易日期") or fallback_trade_date, compact=False),
                    "fund_shares": shares,
                    "nav": nav,
                    "derived_fund_size_yi": self._derive_fund_size_yi(shares=shares, nav=nav),
                    "exchange": "SZSE",
                    "data_source": "szse_etf_scale",
                }
            )
        return rows

    @staticmethod
    def _derive_fund_size_yi(*, shares: Optional[float], nav: Optional[float]) -> Optional[float]:
        if shares is None or nav is None:
            return None
        return shares * nav / 100000000.0

    @staticmethod
    def _normalize_trade_date(value: Any, *, compact: bool = True) -> str:
        if isinstance(value, datetime):
            dt_value = value.date()
        elif isinstance(value, date):
            dt_value = value
        else:
            text = str(value or "").strip()
            if not text:
                dt_value = datetime.now().date()
            elif re.fullmatch(r"\d{8}", text):
                dt_value = datetime.strptime(text, "%Y%m%d").date()
            else:
                cleaned = re.sub(r"[./]", "-", text)
                dt_value = datetime.strptime(cleaned[:10], "%Y-%m-%d").date()
        return dt_value.strftime("%Y%m%d" if compact else "%Y-%m-%d")

    @staticmethod
    def _market_prefix(base_code: str) -> str:
        normalized = normalize_stock_code(base_code)
        if normalized.startswith(("5", "6", "9")):
            return "sh"
        if normalized.startswith("8"):
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
        return str(value).replace("\x00", "").strip()


_ETF_HTTP_PROVIDER: Optional[EtfHttpProvider] = None


def get_etf_http_provider() -> EtfHttpProvider:
    global _ETF_HTTP_PROVIDER
    if _ETF_HTTP_PROVIDER is None:
        _ETF_HTTP_PROVIDER = EtfHttpProvider()
    return _ETF_HTTP_PROVIDER
