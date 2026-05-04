# -*- coding: utf-8 -*-
"""
===================================
Theme Stock Pool Service
===================================
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from theme_picker.domain.theme_event import ThemeDefinitionSchema


def infer_exchange_suffix(base_code: str) -> Optional[str]:
    """Infer a CN exchange suffix from a 6-digit base code."""
    if not base_code or not base_code.isdigit():
        return None

    if base_code.startswith(("600", "601", "603", "605", "688", "689", "900")):
        return ".SH"
    if base_code.startswith(("000", "001", "002", "003", "300", "301", "302", "200")):
        return ".SZ"
    if base_code.startswith(("430", "800", "830", "831", "832", "833", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "877", "878", "879", "880", "881", "882", "883", "884", "885", "886", "887", "888", "889", "920")):
        return ".BJ"
    return None


def canonicalize_stock_code(raw_code: str) -> str:
    """Normalize stock codes while preserving exchange information for CN equities."""
    text = str(raw_code or "").strip().upper()
    if not text:
        return ""

    if text.startswith(("SH", "SZ", "BJ")) and len(text) == 8 and text[2:].isdigit():
        return f"{text[2:]}.{text[:2]}"
    if text.startswith("HK") and len(text) >= 3 and text[2:].isdigit():
        return f"{text[2:].zfill(5)}.HK"

    if "." in text:
        base, suffix = text.rsplit(".", 1)
        if base.isdigit() and suffix in {"SH", "SZ", "SS", "BJ"}:
            return f"{base}.{ 'SH' if suffix == 'SS' else suffix }"
        if base.isdigit() and suffix == "HK":
            return f"{base.zfill(5)}.HK"
        return text

    if text.isdigit() and len(text) == 6:
        suffix = infer_exchange_suffix(text)
        return f"{text}{suffix}" if suffix else text
    if text.isdigit() and len(text) == 5:
        return f"{text}.HK"
    return text


def build_stock_code_variants(raw_code: str) -> List[str]:
    """Build ordered lookup variants for one stock code."""
    canonical = canonicalize_stock_code(raw_code)
    variants: List[str] = []

    def _append(value: str) -> None:
        if value and value not in variants:
            variants.append(value)

    _append(canonical)
    _append(str(raw_code or "").strip().upper())

    if "." in canonical:
        base, suffix = canonical.rsplit(".", 1)
        _append(base)
        if suffix == "HK" and base.isdigit():
            _append(f"HK{base}")
    elif canonical.isdigit():
        suffix = infer_exchange_suffix(canonical)
        if suffix:
            _append(f"{canonical}{suffix}")

    return variants


class ThemeStockPoolService:
    """Resolve and normalize stock pools from theme definitions."""

    @staticmethod
    def get_stock_pool(theme: ThemeDefinitionSchema) -> List[str]:
        return ThemeStockPoolService.normalize_codes(theme.stock_pool)

    @staticmethod
    def normalize_codes(raw_codes: Iterable[str]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for raw_code in raw_codes:
            code = canonicalize_stock_code(str(raw_code or "").strip())
            if not code or code in seen:
                continue
            seen.add(code)
            normalized.append(code)
        return normalized
