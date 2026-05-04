"""Compatibility shim for the standalone ``theme_picker`` source layout."""

from __future__ import annotations

from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
_SRC_PACKAGE_DIR = _CURRENT_DIR / "src"

if _SRC_PACKAGE_DIR.is_dir():
    __path__.append(str(_SRC_PACKAGE_DIR))
