# -*- coding: utf-8 -*-
"""Read-only backtest data feed backed by cached daily bars."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from theme_picker.infrastructure.persistence import get_theme_picker_db
from theme_picker.infrastructure.stock_pool_service import build_stock_code_variants
from theme_picker.infrastructure.daily_bar_service import WrappedDailyBarProvider, get_daily_bar_resolver


class DailyBarDataFeed:
    """Load cached daily bars without triggering online补数."""

    def __init__(self) -> None:
        self.db = get_theme_picker_db()
        self.provider = WrappedDailyBarProvider()
        self.resolver = get_daily_bar_resolver()

    def load(
        self,
        stock_code: str,
        *,
        start_date: date,
        end_date: date,
        minimum_rows: int = 60,
        price_adjustment: str = "raw",
    ) -> pd.DataFrame:
        frame = self._load_cached_frame(
            stock_code,
            start_date=start_date,
            end_date=end_date,
            price_adjustment=price_adjustment,
        )
        if frame.empty:
            sync_hint = "scripts/sync_tushare_history.py" if str(price_adjustment or "raw").strip().lower() == "qfq" else "scripts/sync_tushare_history.py 或 scripts/sync_daily_bars.py"
            raise ValueError(
                f"{stock_code} 在历史缓存中没有 {start_date.isoformat()} ~ {end_date.isoformat()} 的 {price_adjustment} 日K，请先运行 {sync_hint}"
            )

        earliest = frame["date"].min().date()
        latest = frame["date"].max().date()
        expected_latest = self.resolver.resolve_expected_latest_date(end_date)
        allowed_earliest = start_date + timedelta(days=10)
        if len(frame) < int(minimum_rows):
            raise ValueError(
                f"{stock_code} 的缓存日K不足，当前只有 {len(frame)} 行，至少需要 {minimum_rows} 行，请先补齐历史数据缓存"
            )
        if earliest > allowed_earliest:
            raise ValueError(
                f"{stock_code} 的缓存起始日期为 {earliest.isoformat()}，晚于请求起点 {start_date.isoformat()}，请先补齐历史数据缓存"
            )
        if latest < expected_latest:
            raise ValueError(
                f"{stock_code} 的缓存截止日期为 {latest.isoformat()}，早于所需最新交易日 {expected_latest.isoformat()}，请先补齐历史数据缓存"
            )

        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values("date").reset_index(drop=True)
        return frame

    def resolve_available_start_date(
        self,
        stock_code: str,
        *,
        start_date: date,
        end_date: date,
        price_adjustment: str = "raw",
    ) -> date | None:
        frame = self._load_cached_frame(
            stock_code,
            start_date=start_date,
            end_date=end_date,
            price_adjustment=price_adjustment,
        )
        if frame.empty:
            return None
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if frame.empty:
            return None
        return frame["date"].min().date()

    def _load_cached_frame(
        self,
        stock_code: str,
        *,
        start_date: date,
        end_date: date,
        price_adjustment: str,
    ) -> pd.DataFrame:
        tushare_frame = self._load_tushare_frame(
            stock_code,
            start_date=start_date,
            end_date=end_date,
            price_adjustment=price_adjustment,
        )
        if not tushare_frame.empty:
            return tushare_frame

        if str(price_adjustment or "raw").strip().lower() != "raw":
            return pd.DataFrame(columns=self.provider.standard_columns())

        best_rows = []
        for candidate in build_stock_code_variants(stock_code):
            rows = self.db.get_data_range(candidate, start_date, end_date)
            if len(rows) > len(best_rows):
                best_rows = rows
        if not best_rows:
            return pd.DataFrame(columns=self.provider.standard_columns())
        frame = pd.DataFrame([row.to_dict() for row in best_rows])
        return self.provider.prepare_daily_frame(frame)

    def _load_tushare_frame(
        self,
        stock_code: str,
        *,
        start_date: date,
        end_date: date,
        price_adjustment: str,
    ) -> pd.DataFrame:
        normalized_adjustment = str(price_adjustment or "raw").strip().lower()
        best_raw_rows = []
        best_aux_rows = []
        best_match_size = 0

        for candidate in build_stock_code_variants(stock_code):
            raw_rows = self.db.get_stock_daily_raw_range(candidate, start_date, end_date)
            aux_rows = self.db.get_stock_daily_aux_range(candidate, start_date, end_date)
            match_size = max(len(raw_rows), len(aux_rows))
            if match_size > best_match_size:
                best_match_size = match_size
                best_raw_rows = raw_rows
                best_aux_rows = aux_rows

        if not best_raw_rows:
            return pd.DataFrame(columns=self.provider.standard_columns())

        raw_frame = pd.DataFrame([row.to_dict() for row in best_raw_rows])
        if normalized_adjustment == "qfq":
            required_columns = ["open_qfq", "high_qfq", "low_qfq", "close_qfq"]
            if any(column not in raw_frame.columns for column in required_columns):
                return pd.DataFrame(columns=self.provider.standard_columns())
            if raw_frame[required_columns].notna().sum().sum() == 0:
                return pd.DataFrame(columns=self.provider.standard_columns())
            selected_frame = pd.DataFrame(
                {
                    "date": raw_frame.get("trade_date"),
                    "open": raw_frame.get("open_qfq"),
                    "high": raw_frame.get("high_qfq"),
                    "low": raw_frame.get("low_qfq"),
                    "close": raw_frame.get("close_qfq"),
                    "volume": raw_frame.get("vol"),
                    "amount": raw_frame.get("amount"),
                    "pre_close": raw_frame.get("pre_close"),
                }
            )
        else:
            selected_frame = pd.DataFrame(
                {
                    "date": raw_frame.get("trade_date"),
                    "open": raw_frame.get("open"),
                    "high": raw_frame.get("high"),
                    "low": raw_frame.get("low"),
                    "close": raw_frame.get("close"),
                    "volume": raw_frame.get("vol"),
                    "amount": raw_frame.get("amount"),
                    "pre_close": raw_frame.get("pre_close"),
                }
            )
        if best_aux_rows:
            aux_frame = pd.DataFrame([row.to_dict() for row in best_aux_rows]).rename(columns={"trade_date": "date"})
            keep_columns = [
                "date",
                "volume_ratio",
                "turnover_rate",
                "turnover_rate_f",
                "turnover_rate_median_20",
                "atr_pct_20",
                "style_bucket",
                "up_limit",
                "down_limit",
                "is_suspended",
                "suspend_type",
            ]
            merged = selected_frame.merge(
                aux_frame[[column for column in keep_columns if column in aux_frame.columns]],
                on="date",
                how="left",
            )
        else:
            merged = selected_frame

        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        merged["open"] = pd.to_numeric(merged.get("open"), errors="coerce")
        merged["high"] = pd.to_numeric(merged.get("high"), errors="coerce")
        merged["low"] = pd.to_numeric(merged.get("low"), errors="coerce")
        merged["close"] = pd.to_numeric(merged.get("close"), errors="coerce")
        merged["volume"] = pd.to_numeric(merged.get("volume"), errors="coerce")
        merged["amount"] = pd.to_numeric(merged.get("amount"), errors="coerce")
        merged["pre_close"] = pd.to_numeric(merged.get("pre_close"), errors="coerce")
        if "turnover_rate" in merged.columns:
            merged["turnover_rate"] = pd.to_numeric(merged.get("turnover_rate"), errors="coerce")
        if "turnover_rate_f" in merged.columns:
            merged["turnover_rate_f"] = pd.to_numeric(merged.get("turnover_rate_f"), errors="coerce")
        if "turnover_rate_median_20" in merged.columns:
            merged["turnover_rate_median_20"] = pd.to_numeric(merged.get("turnover_rate_median_20"), errors="coerce")
        if "atr_pct_20" in merged.columns:
            merged["atr_pct_20"] = pd.to_numeric(merged.get("atr_pct_20"), errors="coerce")
        raw_frame = raw_frame.rename(columns={"trade_date": "date", "vol": "raw_volume"})
        raw_frame["date"] = pd.to_datetime(raw_frame["date"], errors="coerce")
        raw_frame["raw_close"] = pd.to_numeric(raw_frame.get("close"), errors="coerce")
        raw_frame["pre_close"] = pd.to_numeric(raw_frame.get("pre_close"), errors="coerce")
        raw_frame["raw_pct_chg"] = ((raw_frame["raw_close"] - raw_frame["pre_close"]) / raw_frame["pre_close"] * 100.0).round(2)
        raw_frame["raw_pct_chg"] = raw_frame["raw_pct_chg"].replace([float("inf"), float("-inf")], pd.NA).fillna(0.0)
        merged = merged.merge(
            raw_frame[["date", "raw_close", "pre_close", "raw_pct_chg"]].drop_duplicates(subset=["date"], keep="last"),
            on="date",
            how="left",
            suffixes=("", "_rawbase"),
        )

        if normalized_adjustment == "raw":
            merged["pct_chg"] = merged["raw_pct_chg"]

        prepared = self.provider.prepare_daily_frame(merged)
        passthrough_columns = [
            "date",
            "raw_close",
            "pre_close",
            "raw_pct_chg",
            "turnover_rate",
            "turnover_rate_f",
            "turnover_rate_median_20",
            "atr_pct_20",
            "style_bucket",
            "up_limit",
            "down_limit",
            "is_suspended",
            "suspend_type",
        ]
        available_columns = [column for column in passthrough_columns if column in merged.columns]
        if available_columns:
            prepared = prepared.merge(
                merged[available_columns].drop_duplicates(subset=["date"], keep="last"),
                on="date",
                how="left",
                suffixes=("", "_passthrough"),
            )
        return prepared
