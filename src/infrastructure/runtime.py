# -*- coding: utf-8 -*-
"""Theme picker runtime adapters."""

from __future__ import annotations

from typing import Any

from theme_picker.config import get_config


def get_theme_picker_config() -> Any:
    """Return the shared runtime config used by theme picker."""
    return get_config()
