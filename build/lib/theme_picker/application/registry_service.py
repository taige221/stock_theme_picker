# -*- coding: utf-8 -*-
"""
===================================
Dynamic Theme Registry Service
===================================
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional

from theme_picker.domain.theme_event import ThemeDefinitionSchema, ThemeRegistrySchema

logger = logging.getLogger(__name__)


class ThemeRegistryService:
    """Load and cache dynamic theme definitions from a local JSON registry."""

    def __init__(self, registry_path: Optional[Path | str] = None):
        package_root = Path(__file__).resolve().parents[1]
        data_dir = package_root / "data"
        self.registry_path = Path(registry_path) if registry_path else data_dir / "theme_registry.json"
        self.example_registry_path = data_dir / "theme_registry.example.json"
        self._lock = RLock()
        self._registry: Optional[ThemeRegistrySchema] = None

    def reload(self) -> ThemeRegistrySchema:
        """Reload registry from disk."""
        with self._lock:
            self._registry = self._load_registry()
            return self._registry

    def get_registry(self) -> ThemeRegistrySchema:
        """Return cached registry, loading it on first access."""
        with self._lock:
            if self._registry is None:
                self._registry = self._load_registry()
            return self._registry

    def list_themes(self, *, enabled_only: bool = False) -> List[ThemeDefinitionSchema]:
        """List themes from registry."""
        themes = list(self.get_registry().themes)
        if enabled_only:
            themes = [theme for theme in themes if theme.enabled]
        return sorted(themes, key=lambda item: (item.priority, item.name))

    def get_theme(self, theme_id: str) -> Optional[ThemeDefinitionSchema]:
        """Return one theme by id."""
        target = str(theme_id or "").strip()
        if not target:
            return None
        for theme in self.get_registry().themes:
            if theme.id == target:
                return theme
        return None

    def get_enabled_theme_map(self) -> Dict[str, ThemeDefinitionSchema]:
        """Return enabled themes keyed by id."""
        return {theme.id: theme for theme in self.list_themes(enabled_only=True)}

    def _load_registry(self) -> ThemeRegistrySchema:
        target_path = self.registry_path
        if not target_path.exists():
            if self.example_registry_path.exists():
                target_path = self.example_registry_path
            else:
                logger.warning("主题注册表不存在，使用空配置: %s", self.registry_path)
                return ThemeRegistrySchema()

        try:
            raw = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("读取主题注册表失败: %s", exc)
            return ThemeRegistrySchema()

        if isinstance(raw, list):
            raw = {"version": 1, "themes": raw}

        try:
            registry = ThemeRegistrySchema.model_validate(raw)
        except Exception as exc:
            logger.error("主题注册表格式非法: %s", exc)
            return ThemeRegistrySchema()

        return registry
