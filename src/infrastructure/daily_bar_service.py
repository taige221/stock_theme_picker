# -*- coding: utf-8 -*-
"""Unified daily bar cache resolver and wrapped online provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import logging
import os
from threading import Lock
from typing import Any, Dict, List, Optional

import pandas as pd
from mootdx.quotes import Quotes

from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.infrastructure.persistence import get_theme_picker_db
from theme_picker.infrastructure.stock_pool_service import (
    build_stock_code_variants,
    canonicalize_stock_code,
    is_etf_code,
)

logger = logging.getLogger(__name__)

DEFAULT_ONLINE_DAILY_BAR_COUNT = 240
MAX_ONLINE_DAILY_BAR_COUNT = 2000
DEFAULT_MIN_ROWS = 30
MARKET_CLOSE_CUTOFF = time(hour=15, minute=0)
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_NO_PROXY_ENV_KEYS = ("NO_PROXY", "no_proxy")
_PROXY_ENV_LOCK = Lock()


@dataclass
class DailyBarResolveResult:
    stock_code: str
    base_code: str
    instrument_type: str
    instrument_label: str
    frame: pd.DataFrame
    data_source: str
    cache_status: str
    latest_trade_date: Optional[date] = None
    errors: List[str] = field(default_factory=list)


class WrappedDailyBarProvider:
    """Stable online daily-bar provider for CN A-shares and ETFs."""

    def __init__(self, *, default_fetch_bars: int = DEFAULT_ONLINE_DAILY_BAR_COUNT):
        self.default_fetch_bars = max(1, int(default_fetch_bars or DEFAULT_ONLINE_DAILY_BAR_COUNT))
        self._fetcher_manager = None

    def fetch_online_daily_bars(
        self,
        stock_code: str,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bars: int = DEFAULT_ONLINE_DAILY_BAR_COUNT,
    ) -> tuple[pd.DataFrame, str]:
        canonical_code = canonicalize_stock_code(stock_code)
        base_code = normalize_stock_code(canonical_code)
        if not self._supports_symbol(base_code):
            raise ValueError(f"暂不支持该标的的统一日K获取: {stock_code}")

        fetch_count = self._resolve_fetch_count(bars=bars, start_date=start_date, end_date=end_date)
        errors: List[str] = []
        for source in self._resolve_source_priority():
            try:
                if source == "mootdx":
                    frame, source_label = self._fetch_mootdx_daily_bars(
                        base_code,
                        start_date=start_date,
                        end_date=end_date,
                        fetch_count=fetch_count,
                    )
                else:
                    frame, source_label = self._fetch_manager_daily_bars(
                        canonical_code,
                        source=source,
                        start_date=start_date,
                        end_date=end_date,
                        fetch_count=fetch_count,
                    )
                if frame is not None and not frame.empty:
                    return frame, source_label
                errors.append(f"{source}: empty result")
                logger.debug("统一日K数据源返回空数据: code=%s source=%s", canonical_code, source)
            except Exception as exc:
                errors.append(f"{source}: {exc}")
                logger.debug("统一日K数据源失败: code=%s source=%s error=%s", canonical_code, source, exc)
                continue

        raise ValueError(f"统一日K在线数据源全部失败: {canonical_code}; " + "; ".join(errors))

    def _fetch_mootdx_daily_bars(
        self,
        base_code: str,
        *,
        start_date: Optional[date],
        end_date: Optional[date],
        fetch_count: int,
    ) -> tuple[pd.DataFrame, str]:
        client = Quotes.factory(market="std")
        raw_df = client.bars(symbol=base_code, category=4, offset=fetch_count)
        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=self._standard_columns()), "wrapped_daily_bar:mootdx"

        frame = raw_df.copy()
        if "datetime" in frame.columns:
            frame["date"] = frame["datetime"]
        else:
            index_series = frame.index.to_series(index=frame.index)
            frame["date"] = index_series.values

        normalized = pd.DataFrame(
            {
                "date": frame["date"],
                "open": frame.get("open"),
                "high": frame.get("high"),
                "low": frame.get("low"),
                "close": frame.get("close"),
                "volume": frame.get("vol", frame.get("volume")),
                "amount": frame.get("amount"),
            }
        )
        prepared = self._prepare_daily_frame(normalized)
        filtered = self._filter_frame(prepared, start_date=start_date, end_date=end_date)
        return filtered.reset_index(drop=True), "wrapped_daily_bar:mootdx"

    def _fetch_manager_daily_bars(
        self,
        stock_code: str,
        *,
        source: str,
        start_date: Optional[date],
        end_date: Optional[date],
        fetch_count: int,
    ) -> tuple[pd.DataFrame, str]:
        fetcher_name = self._source_to_fetcher_name(source)
        manager = self._get_fetcher_manager()
        fetcher = next(
            (item for item in manager._get_fetchers_snapshot() if item.name == fetcher_name),
            None,
        )
        if fetcher is None or not hasattr(fetcher, "get_daily_data"):
            raise ValueError(f"不支持的统一日K数据源: {source}")

        start_text = start_date.strftime("%Y-%m-%d") if start_date else None
        end_text = end_date.strftime("%Y-%m-%d") if end_date else None
        frame = manager._call_fetcher_method(
            fetcher,
            "get_daily_data",
            stock_code=stock_code,
            start_date=start_text,
            end_date=end_text,
            days=fetch_count,
        )
        prepared = self._prepare_daily_frame(frame)
        filtered = self._filter_frame(prepared, start_date=start_date, end_date=end_date)
        return filtered.reset_index(drop=True), f"wrapped_daily_bar:{source}"

    def _get_fetcher_manager(self):
        if self._fetcher_manager is None:
            from theme_picker.data_provider import DataFetcherManager

            self._fetcher_manager = DataFetcherManager()
        return self._fetcher_manager

    @staticmethod
    def _source_to_fetcher_name(source: str) -> str:
        source_map = {
            "tushare": "TushareFetcher",
            "efinance": "EfinanceFetcher",
            "akshare": "AkshareFetcher",
            "akshare_em": "AkshareFetcher",
            "pytdx": "PytdxFetcher",
            "baostock": "BaostockFetcher",
        }
        normalized = str(source or "").strip().lower()
        if normalized not in source_map:
            raise ValueError(f"不支持的统一日K数据源: {source}")
        return source_map[normalized]

    @staticmethod
    def _resolve_source_priority() -> List[str]:
        from theme_picker.infrastructure.runtime import get_theme_picker_config

        priority = getattr(get_theme_picker_config(), "daily_bar_source_priority", "mootdx") or "mootdx"
        sources = [
            item.strip().lower()
            for item in str(priority).split(",")
            if item.strip()
        ]
        return sources or ["mootdx"]

    def _resolve_fetch_count(
        self,
        *,
        bars: int,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> int:
        requested = max(1, int(bars or self.default_fetch_bars))
        fetch_count = max(requested, self.default_fetch_bars)
        if start_date and end_date and end_date >= start_date:
            span_days = (end_date - start_date).days + 1
            estimated_trade_bars = int(span_days * 0.8) + 10
            fetch_count = max(fetch_count, estimated_trade_bars)
        return min(fetch_count, MAX_ONLINE_DAILY_BAR_COUNT)

    @staticmethod
    def _supports_symbol(base_code: str) -> bool:
        return bool(base_code and base_code.isdigit() and len(base_code) == 6)

    @staticmethod
    def _standard_columns() -> List[str]:
        return [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pct_chg",
            "ma5",
            "ma10",
            "ma20",
            "volume_ratio",
        ]

    def standard_columns(self) -> List[str]:
        return self._standard_columns()

    @staticmethod
    def _prepare_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=WrappedDailyBarProvider._standard_columns())

        frame = df.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg"]
        for col in numeric_cols:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")

        frame = frame.dropna(subset=["date", "close", "volume"])
        frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        frame["pct_chg"] = frame["close"].pct_change() * 100
        frame["pct_chg"] = frame["pct_chg"].fillna(0.0).round(2)
        frame["ma5"] = frame["close"].rolling(window=5, min_periods=1).mean().round(2)
        frame["ma10"] = frame["close"].rolling(window=10, min_periods=1).mean().round(2)
        frame["ma20"] = frame["close"].rolling(window=20, min_periods=1).mean().round(2)

        avg_volume_5 = frame["volume"].rolling(window=5, min_periods=1).mean()
        frame["volume_ratio"] = frame["volume"] / avg_volume_5.shift(1)
        frame["volume_ratio"] = frame["volume_ratio"].replace([float("inf"), float("-inf")], pd.NA)
        frame["volume_ratio"] = frame["volume_ratio"].fillna(1.0).round(2)
        return frame

    def prepare_daily_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._prepare_daily_frame(df)

    @staticmethod
    def _filter_frame(
        frame: pd.DataFrame,
        *,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame(columns=WrappedDailyBarProvider._standard_columns())

        result = frame.copy()
        if start_date is not None:
            result = result[result["date"].dt.date >= start_date]
        if end_date is not None:
            result = result[result["date"].dt.date <= end_date]
        return result.sort_values("date").reset_index(drop=True)


class DailyBarResolver:
    """Resolve daily bars with cache-first and online-merge strategy."""

    def __init__(
        self,
        *,
        provider: Optional[WrappedDailyBarProvider] = None,
        db=None,
        default_fetch_bars: int = DEFAULT_ONLINE_DAILY_BAR_COUNT,
    ):
        self.provider = provider or WrappedDailyBarProvider(default_fetch_bars=default_fetch_bars)
        self.db = db or get_theme_picker_db()
        self.default_fetch_bars = max(1, int(default_fetch_bars or DEFAULT_ONLINE_DAILY_BAR_COUNT))

    def resolve_daily_bars(
        self,
        stock_code: str,
        *,
        bars: int = DEFAULT_ONLINE_DAILY_BAR_COUNT,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        minimum_rows: int = DEFAULT_MIN_ROWS,
        allow_stale_fallback: bool = True,
        without_proxy: bool = False,
    ) -> DailyBarResolveResult:
        canonical_code = canonicalize_stock_code(stock_code)
        base_code = normalize_stock_code(canonical_code)
        if not self._supports_symbol(base_code):
            raise ValueError(f"暂不支持该标的的统一日K获取: {stock_code}")

        requested_bars = max(1, int(bars or self.default_fetch_bars))
        target_end_date = self._normalize_end_date(end_date)
        explicit_start_date = start_date is not None
        target_start_date = start_date or self._estimate_start_date(target_end_date, requested_bars)
        expected_latest_date = self._resolve_expected_latest_date(target_end_date)
        instrument_type = "etf" if is_etf_code(base_code) else "stock"
        instrument_label = "ETF" if instrument_type == "etf" else "股票"
        errors: List[str] = []

        cached_frame = self._load_cached_frame(canonical_code, start_date=target_start_date, end_date=target_end_date)
        if self._is_cache_complete(
            cached_frame,
            requested_bars=requested_bars,
            expected_latest_date=expected_latest_date,
            minimum_rows=minimum_rows,
            explicit_start_date=explicit_start_date,
            requested_start_date=target_start_date,
        ):
            final_frame = self._finalize_frame(
                cached_frame,
                requested_bars=requested_bars,
                start_date=target_start_date,
                end_date=target_end_date,
            )
            latest_trade_date = self._frame_latest_date(final_frame)
            return DailyBarResolveResult(
                stock_code=canonical_code,
                base_code=base_code,
                instrument_type=instrument_type,
                instrument_label=instrument_label,
                frame=final_frame,
                data_source="stock_daily_cache",
                cache_status="hit",
                latest_trade_date=latest_trade_date,
            )

        try:
            online_frame, online_source = self._fetch_online_frame(
                canonical_code,
                start_date=target_start_date,
                end_date=target_end_date,
                bars=max(requested_bars, self.default_fetch_bars),
                without_proxy=without_proxy,
            )
        except Exception as exc:
            logger.warning("统一日K在线补数失败: code=%s error=%s", canonical_code, exc)
            errors.append(str(exc))
            online_frame = pd.DataFrame(columns=self.provider._standard_columns())
            online_source = "wrapped_daily_bar:mootdx"

        merged_frame = self._merge_frames(cached_frame, online_frame)
        online_has_rows = online_frame is not None and not online_frame.empty
        merged_complete = (
            not merged_frame.empty
            and self._is_cache_complete(
                merged_frame,
                requested_bars=requested_bars,
                expected_latest_date=expected_latest_date,
                minimum_rows=minimum_rows,
                explicit_start_date=explicit_start_date,
                requested_start_date=target_start_date,
            )
        )
        if not merged_frame.empty:
            self._save_merged_frame(merged_frame, canonical_code, data_source=online_source)
            final_frame = self._finalize_frame(
                merged_frame,
                requested_bars=requested_bars,
                start_date=target_start_date,
                end_date=target_end_date,
            )
            latest_trade_date = self._frame_latest_date(final_frame)
            if cached_frame.empty:
                cache_status = "seeded" if merged_complete else "seeded_partial"
                return DailyBarResolveResult(
                    stock_code=canonical_code,
                    base_code=base_code,
                    instrument_type=instrument_type,
                    instrument_label=instrument_label,
                    frame=final_frame,
                    data_source=online_source,
                    cache_status=cache_status,
                    latest_trade_date=latest_trade_date,
                    errors=errors,
                )
            if online_has_rows:
                cache_status = "merged" if merged_complete else "merged_partial"
                return DailyBarResolveResult(
                    stock_code=canonical_code,
                    base_code=base_code,
                    instrument_type=instrument_type,
                    instrument_label=instrument_label,
                    frame=final_frame,
                    data_source=online_source,
                    cache_status=cache_status,
                    latest_trade_date=latest_trade_date,
                    errors=errors,
                )

        if not cached_frame.empty and allow_stale_fallback:
            final_frame = self._finalize_frame(
                cached_frame,
                requested_bars=requested_bars,
                start_date=target_start_date,
                end_date=target_end_date,
            )
            latest_trade_date = self._frame_latest_date(final_frame)
            return DailyBarResolveResult(
                stock_code=canonical_code,
                base_code=base_code,
                instrument_type=instrument_type,
                instrument_label=instrument_label,
                frame=final_frame,
                data_source="stock_daily_cache",
                cache_status="stale_fallback",
                latest_trade_date=latest_trade_date,
                errors=errors,
            )

        raise ValueError(f"未获取到 {canonical_code} 的日线数据")

    def _fetch_online_frame(
        self,
        stock_code: str,
        *,
        start_date: Optional[date],
        end_date: Optional[date],
        bars: int,
        without_proxy: bool,
    ) -> tuple[pd.DataFrame, str]:
        env_snapshot: Dict[str, Optional[str]] = {}
        lock = _PROXY_ENV_LOCK if without_proxy else None
        if lock is not None:
            lock.acquire()
        try:
            if without_proxy:
                env_snapshot = self._disable_proxy_env_for_attempt()
            return self.provider.fetch_online_daily_bars(
                stock_code,
                start_date=start_date,
                end_date=end_date,
                bars=bars,
            )
        finally:
            if without_proxy:
                self._restore_proxy_env_after_attempt(env_snapshot)
            if lock is not None:
                lock.release()

    @staticmethod
    def _supports_symbol(base_code: str) -> bool:
        return bool(base_code and base_code.isdigit() and len(base_code) == 6)

    @staticmethod
    def _normalize_end_date(end_date: Optional[date]) -> date:
        if isinstance(end_date, datetime):
            return end_date.date()
        if isinstance(end_date, date):
            return end_date
        return datetime.now().date()

    @staticmethod
    def _estimate_start_date(target_end_date: date, requested_bars: int) -> date:
        day_span = max(requested_bars * 2, DEFAULT_ONLINE_DAILY_BAR_COUNT)
        return target_end_date - timedelta(days=day_span)

    def _resolve_expected_latest_date(self, target_end_date: date) -> date:
        now = datetime.now()
        today = now.date()
        if target_end_date != today:
            return self._previous_weekday_if_needed(target_end_date)
        if now.time() < MARKET_CLOSE_CUTOFF:
            return self._previous_trading_day(today)
        return self._previous_weekday_if_needed(today)

    def resolve_expected_latest_date(self, target_end_date: date) -> date:
        return self._resolve_expected_latest_date(target_end_date)

    @staticmethod
    def _previous_weekday_if_needed(value: date) -> date:
        result = value
        while result.weekday() >= 5:
            result -= timedelta(days=1)
        return result

    def _previous_trading_day(self, value: date) -> date:
        result = value - timedelta(days=1)
        return self._previous_weekday_if_needed(result)

    def _load_cached_frame(
        self,
        stock_code: str,
        *,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        best_rows: List[Any] = []
        for candidate in build_stock_code_variants(stock_code):
            try:
                rows = self.db.get_data_range(candidate, start_date, end_date)
            except Exception:
                continue
            if len(rows) > len(best_rows):
                best_rows = rows

        if not best_rows:
            return pd.DataFrame(columns=self.provider._standard_columns())
        frame = pd.DataFrame([row.to_dict() for row in best_rows])
        return self.provider._prepare_daily_frame(frame)

    @staticmethod
    def _is_cache_complete(
        frame: pd.DataFrame,
        *,
        requested_bars: int,
        expected_latest_date: date,
        minimum_rows: int,
        explicit_start_date: bool,
        requested_start_date: Optional[date],
    ) -> bool:
        if frame is None or frame.empty:
            return False
        latest_trade_date = DailyBarResolver._frame_latest_date(frame)
        if latest_trade_date is None or latest_trade_date < expected_latest_date:
            return False
        if explicit_start_date:
            earliest_trade_date = DailyBarResolver._frame_earliest_date(frame)
            if requested_start_date is not None and (
                earliest_trade_date is None or earliest_trade_date > requested_start_date
            ):
                return False
            return len(frame) >= max(1, minimum_rows)
        return len(frame) >= max(1, requested_bars, minimum_rows)

    def _merge_frames(self, cached_frame: pd.DataFrame, online_frame: pd.DataFrame) -> pd.DataFrame:
        if (cached_frame is None or cached_frame.empty) and (online_frame is None or online_frame.empty):
            return pd.DataFrame(columns=self.provider._standard_columns())
        if cached_frame is None or cached_frame.empty:
            return self.provider._prepare_daily_frame(online_frame)
        if online_frame is None or online_frame.empty:
            return self.provider._prepare_daily_frame(cached_frame)
        merged = pd.concat([cached_frame, online_frame], ignore_index=True)
        return self.provider._prepare_daily_frame(merged)

    def _save_merged_frame(self, frame: pd.DataFrame, stock_code: str, *, data_source: str) -> None:
        if frame is None or frame.empty:
            return
        try:
            self.db.save_daily_data(frame, code=stock_code, data_source=data_source)
        except Exception as exc:
            logger.warning("统一日K写入缓存失败: code=%s error=%s", stock_code, exc)

    def _finalize_frame(
        self,
        frame: pd.DataFrame,
        *,
        requested_bars: int,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        filtered = self.provider._filter_frame(frame, start_date=start_date, end_date=end_date)
        if filtered.empty:
            return filtered
        return filtered.tail(max(1, requested_bars)).reset_index(drop=True)

    @staticmethod
    def _frame_latest_date(frame: pd.DataFrame) -> Optional[date]:
        if frame is None or frame.empty or "date" not in frame.columns:
            return None
        latest = pd.to_datetime(frame["date"], errors="coerce").dropna()
        if latest.empty:
            return None
        return latest.iloc[-1].date()

    @staticmethod
    def _frame_earliest_date(frame: pd.DataFrame) -> Optional[date]:
        if frame is None or frame.empty or "date" not in frame.columns:
            return None
        values = pd.to_datetime(frame["date"], errors="coerce").dropna()
        if values.empty:
            return None
        return values.iloc[0].date()

    @staticmethod
    def serialize_frame(frame: pd.DataFrame) -> List[Dict[str, Any]]:
        if frame is None or frame.empty:
            return []
        rows: List[Dict[str, Any]] = []
        for _, row in frame.iterrows():
            dt_value = pd.to_datetime(row.get("date"), errors="coerce")
            rows.append(
                {
                    "date": dt_value.strftime("%Y-%m-%d") if not pd.isna(dt_value) else None,
                    "datetime": dt_value.strftime("%Y-%m-%d 00:00:00") if not pd.isna(dt_value) else None,
                    "open": DailyBarResolver._safe_float(row.get("open")),
                    "high": DailyBarResolver._safe_float(row.get("high")),
                    "low": DailyBarResolver._safe_float(row.get("low")),
                    "close": DailyBarResolver._safe_float(row.get("close")),
                    "volume": DailyBarResolver._safe_float(row.get("volume")),
                    "amount": DailyBarResolver._safe_float(row.get("amount")),
                    "pct_chg": DailyBarResolver._safe_float(row.get("pct_chg")),
                    "ma5": DailyBarResolver._safe_float(row.get("ma5")),
                    "ma10": DailyBarResolver._safe_float(row.get("ma10")),
                    "ma20": DailyBarResolver._safe_float(row.get("ma20")),
                    "volume_ratio": DailyBarResolver._safe_float(row.get("volume_ratio")),
                }
            )
        return rows

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value in (None, "", "--"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _disable_proxy_env_for_attempt() -> Dict[str, Optional[str]]:
        snapshot: Dict[str, Optional[str]] = {}
        for key in (*_PROXY_ENV_KEYS, *_NO_PROXY_ENV_KEYS):
            snapshot[key] = os.environ.get(key)
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        return snapshot

    @staticmethod
    def _restore_proxy_env_after_attempt(snapshot: Dict[str, Optional[str]]) -> None:
        for key, value in snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


_DAILY_BAR_RESOLVER: Optional[DailyBarResolver] = None


def get_daily_bar_resolver() -> DailyBarResolver:
    global _DAILY_BAR_RESOLVER
    if _DAILY_BAR_RESOLVER is None:
        _DAILY_BAR_RESOLVER = DailyBarResolver()
    return _DAILY_BAR_RESOLVER
