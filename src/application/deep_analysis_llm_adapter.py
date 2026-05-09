# -*- coding: utf-8 -*-
"""LLM adapter for stock deep analysis and constrained follow-up chat."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from theme_picker.config import (
    extra_litellm_params,
    get_api_keys_for_model,
    get_config,
    get_effective_agent_models_to_try,
    normalize_agent_litellm_model,
)

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "default"}
_VALID_VERBOSITY = {"low", "medium", "high"}


class DeepAnalysisLLMOutput(BaseModel):
    action: Optional[str] = None
    action_label: Optional[str] = None
    summary: Optional[str] = None
    confidence: Optional[int] = Field(default=None, ge=0, le=100)
    position_plan: Dict[str, str] = Field(default_factory=dict)
    triggers: List[str] = Field(default_factory=list)
    technical_assessment: Optional[str] = None
    fundamental_assessment: Optional[str] = None
    risk_items: List[str] = Field(default_factory=list)
    risk_level: Optional[str] = None


class DeepAnalysisLLMAdapter:
    def __init__(self, *, config=None):
        self.config = config or get_config()
        self._router = None

    def enabled(self) -> bool:
        if not bool(getattr(self.config, "deep_analysis_llm_enabled", True)):
            return False
        return len(self._candidate_models()) > 0

    def generate(self, *, stock_code: str, stock_name: str, result: Dict[str, Any], base_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.enabled():
            return None

        facts = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "signal": result.get("signal"),
            "pattern": result.get("pattern"),
            "trend_status": result.get("trend_status"),
            "buy_signal": result.get("buy_signal"),
            "current_price": result.get("current_price"),
            "pct_chg": result.get("pct_chg"),
            "support": result.get("support"),
            "pressure": result.get("pressure"),
            "ma10": result.get("ma10"),
            "ma20": result.get("ma20"),
            "bias_ma10": result.get("bias_ma10"),
            "selected_reasons": result.get("selected_reasons") or [],
            "excluded_reasons": result.get("excluded_reasons") or [],
            "theme_attributions": result.get("theme_attributions") or [],
            "fundamental_coverage": result.get("fundamental_coverage") or {},
            "fundamental_errors": result.get("fundamental_errors") or [],
            "fundamental_details": result.get("fundamental_details") or {},
            "stock_news_summary": result.get("stock_news_summary") or {},
            "data_sources": result.get("data_sources") or {},
            "deterministic_trade_levels": (base_payload.get("trade_plan") or {}).get("levels") or {},
            "deterministic_risk_items": (base_payload.get("risk") or {}).get("items") or [],
        }
        prompt = (
            "你是A股短线交易分析助手。"
            "请基于提供的事实，输出一份可执行但保守的单股深度分析。"
            "不要发明不存在的数据，不要改变给定的关键价位，只能围绕给定价位解释策略。"
            "如果当前不适合买，就明确写出来。"
            "只返回 JSON，不要包含 markdown。"
        )
        schema_note = {
            "action": "wait_retest|trial_buy|breakout_confirm|avoid|observe",
            "action_label": "中文动作标题",
            "summary": "2-4句中文摘要",
            "confidence": "0-100整数",
            "position_plan": {
                "initial": "初始仓位建议",
                "add": "加仓条件",
                "max": "最大仓位建议",
            },
            "triggers": ["3条以内执行条件"],
            "technical_assessment": "技术面中文说明",
            "fundamental_assessment": "基本面中文说明",
            "risk_items": ["最多6条风险"],
            "risk_level": "low|medium|high",
        }
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema": schema_note,
                        "facts": facts,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        parsed, used_model = self._run_json_completion(messages=messages)
        if parsed is None:
            return None
        return {
            "action": parsed.action,
            "action_label": parsed.action_label,
            "summary": parsed.summary,
            "confidence": parsed.confidence,
            "position_plan": parsed.position_plan,
            "triggers": parsed.triggers,
            "technical_assessment": parsed.technical_assessment,
            "fundamental_assessment": parsed.fundamental_assessment,
            "risk_items": parsed.risk_items,
            "risk_level": parsed.risk_level,
            "generation_model": used_model,
        }

    def chat(self, *, analysis: Dict[str, Any], user_message: str, recent_messages: List[Dict[str, str]]) -> Optional[str]:
        if not self.enabled():
            return None
        messages: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "你是单股深度分析页面里的受控追问助手。"
                    "只能基于当前分析上下文回答，不要假装重新联网搜索，不要发明新的行情或公告。"
                    "回答要直接、中文、交易导向，长度控制在 3-6 句。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "analysis": analysis,
                        "recent_messages": recent_messages[-6:],
                        "question": user_message,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        content, _ = self._run_text_completion(messages=messages)
        return content

    def _run_json_completion(self, *, messages: List[Dict[str, str]]) -> tuple[Optional[DeepAnalysisLLMOutput], Optional[str]]:
        raw_text, used_model = self._run_text_completion(messages=messages)
        if not raw_text:
            return None, used_model
        payload = self._extract_json(raw_text)
        if not isinstance(payload, dict):
            logger.warning("Deep-analysis LLM returned non-JSON payload: %s", raw_text[:400])
            return None, used_model
        try:
            return DeepAnalysisLLMOutput.model_validate(payload), used_model
        except ValidationError as exc:
            logger.warning("Deep-analysis LLM JSON validation failed: %s", exc)
            return None, used_model

    def _run_text_completion(self, *, messages: List[Dict[str, str]]) -> tuple[Optional[str], Optional[str]]:
        try:
            import litellm
        except Exception as exc:
            logger.warning("litellm import failed, skip LLM deep analysis: %s", exc)
            return None, None

        errors: List[str] = []
        for model in self._candidate_models():
            try:
                response = self._completion_with_model(litellm=litellm, model=model, messages=messages)
                content = self._extract_text(response)
                if content:
                    return content, model
            except Exception as exc:
                errors.append(f"{model}: {exc}")
                logger.warning("Deep-analysis LLM call failed for model %s: %s", model, exc)
        if errors:
            logger.warning("Deep-analysis LLM fallback exhausted: %s", " | ".join(errors[:4]))
        return None, None

    def _completion_with_model(self, *, litellm, model: str, messages: List[Dict[str, str]]):
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "timeout": int(getattr(self.config, "deep_analysis_llm_timeout_seconds", 45) or 45),
            "temperature": float(getattr(self.config, "llm_temperature", 0.7) or 0.7),
            "max_tokens": int(getattr(self.config, "deep_analysis_llm_max_tokens", 2200) or 2200),
        }
        reasoning_effort = str(getattr(self.config, "deep_analysis_llm_reasoning_effort", "medium") or "medium").strip().lower()
        verbosity = str(getattr(self.config, "deep_analysis_llm_verbosity", "low") or "low").strip().lower()
        if reasoning_effort in _VALID_REASONING_EFFORTS:
            kwargs["reasoning_effort"] = reasoning_effort
        if verbosity in _VALID_VERBOSITY:
            kwargs["verbosity"] = verbosity

        model_list = getattr(self.config, "llm_model_list", []) or []
        model_list_source = str(getattr(self.config, "llm_models_source", "") or "").strip().lower()
        if model_list and model_list_source != "legacy_env":
            router = self._get_router(litellm=litellm)
            return router.completion(**kwargs)

        api_keys = get_api_keys_for_model(model, self.config)
        if api_keys:
            kwargs["api_key"] = api_keys[0]
        kwargs.update(extra_litellm_params(model, self.config))
        return litellm.completion(**kwargs)

    def _get_router(self, *, litellm):
        if self._router is not None:
            return self._router
        self._router = litellm.Router(
            model_list=(getattr(self.config, "llm_model_list", []) or []),
            timeout=int(getattr(self.config, "deep_analysis_llm_timeout_seconds", 45) or 45),
            num_retries=1,
        )
        return self._router

    def _candidate_models(self) -> List[str]:
        configured_models = set()
        for item in (getattr(self.config, "llm_model_list", []) or []):
            model_name = str(item.get("model_name") or "").strip()
            if model_name:
                configured_models.add(model_name)
        override_model = normalize_agent_litellm_model(
            str(getattr(self.config, "deep_analysis_litellm_model", "") or "").strip(),
            configured_models=configured_models or None,
        )
        ordered = []
        seen = set()
        raw_models = ([override_model] if override_model else []) + get_effective_agent_models_to_try(self.config)
        for model in raw_models:
            normalized = str(model or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    @staticmethod
    def _extract_text(response: Any) -> Optional[str]:
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip() or None
        if isinstance(content, list):
            texts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
            joined = "\n".join(texts).strip()
            return joined or None
        return None

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        candidate = text.strip()
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            match = _JSON_BLOCK_RE.search(candidate)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
