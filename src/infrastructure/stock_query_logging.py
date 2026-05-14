# -*- coding: utf-8 -*-
"""Dedicated file logger for single-stock query traces."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Optional

from theme_picker.infrastructure.runtime import get_theme_picker_config

_LOGGER_NAME = "theme_picker.stock_query"
_DEFAULT_FILENAME = "stock-query.log"
_LOGGER_LOCK = Lock()


def _get_stock_query_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    with _LOGGER_LOCK:
        if logger.handlers:
            return logger

        try:
            config = get_theme_picker_config()
            log_dir = Path(str(getattr(config, "log_dir", "./logs") or "./logs")).expanduser()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / _DEFAULT_FILENAME

            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            logger.addHandler(handler)
        except Exception:
            logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger


def emit_stock_query_log(
    payload: dict,
    *,
    level: str = "info",
    mirror_logger: Optional[logging.Logger] = None,
) -> None:
    try:
        message = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        query_logger = _get_stock_query_logger()
    except Exception:
        return

    if level == "warning":
        query_logger.warning(message)
        if mirror_logger is not None:
            mirror_logger.warning(message)
        return

    query_logger.info(message)
    if mirror_logger is not None:
        mirror_logger.info(message)
