# -*- coding: utf-8 -*-
"""Dedicated file logger for theme search fallback events."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Optional

from theme_picker.infrastructure.runtime import get_theme_picker_config

_LOGGER_NAME = "theme_picker.search_fallback"
_DEFAULT_FILENAME = "theme-search-fallback.log"
_LOGGER_LOCK = Lock()


def _get_fallback_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    with _LOGGER_LOCK:
        if logger.handlers:
            return logger

        config = get_theme_picker_config()
        log_dir = Path(str(getattr(config, "log_dir", "./logs") or "./logs")).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _DEFAULT_FILENAME

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger


def emit_search_fallback_log(
    payload: dict,
    *,
    level: str = "info",
    mirror_logger: Optional[logging.Logger] = None,
) -> None:
    message = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    fallback_logger = _get_fallback_logger()

    if level == "warning":
        fallback_logger.warning(message)
        if mirror_logger is not None:
            mirror_logger.warning(message)
        return

    fallback_logger.info(message)
    if mirror_logger is not None:
        mirror_logger.info(message)
