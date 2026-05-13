# -*- coding: utf-8 -*-
"""Single-stock deep analysis service.

The first implementation is deterministic on purpose: it stabilizes the API,
storage contract, and UI payload before wiring a real LLM provider.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from theme_picker.application.deep_analysis_llm_adapter import DeepAnalysisLLMAdapter
from theme_picker.infrastructure.persistence import (
    create_stock_deep_analysis_message,
    get_stock_deep_analysis_record,
    get_stock_query_record,
    get_theme_picker_db,
    list_stock_deep_analysis_messages,
    list_stock_deep_analysis_records,
    save_stock_deep_analysis_record,
    upsert_stock_alert_rule,
    upsert_stock_watchlist_item,
)


class StockDeepAnalysisService:
    """Build a structured deep-analysis record from an existing stock query."""

    def __init__(self, *, db=None, llm_adapter: Optional[DeepAnalysisLLMAdapter] = None):
        self.db = db or get_theme_picker_db()
        self.llm_adapter = llm_adapter or DeepAnalysisLLMAdapter()

    def create_from_query(
        self,
        query_id: str,
        *,
        force_refresh: bool = False,
        analysis_id: Optional[str] = None,
    ) -> Any:
        query_id = str(query_id or "").strip()
        if not query_id:
            raise ValueError("query_id 不能为空")

        if not force_refresh and not analysis_id:
            existing = self._find_latest_by_query_id(query_id)
            if existing is not None:
                return existing

        query_record = get_stock_query_record(self.db, query_id)
        if query_record is None:
            raise LookupError(f"未找到单股查询历史: {query_id}")

        result_payload = self.db._safe_json_loads(query_record.result_payload)
        if not isinstance(result_payload, dict):
            raise ValueError(f"单股查询历史缺少可用于深度分析的结果: {query_id}")

        analysis_payload = self._build_analysis_payload(result_payload, query_id=query_id)
        return save_stock_deep_analysis_record(
            self.db,
            analysis_id=analysis_id or uuid.uuid4().hex,
            stock_code=analysis_payload["stock_code"],
            stock_name=analysis_payload["stock_name"],
            source_query_id=query_id,
            status="completed",
            action=analysis_payload["action"],
            summary=analysis_payload["summary"],
            trade_plan=analysis_payload["trade_plan"],
            technical=analysis_payload["technical"],
            fundamental=analysis_payload["fundamental"],
            risk=analysis_payload["risk"],
            context_snapshot={
                "source": "stock_query_history",
                "query_id": query_id,
                "stock_query_result": result_payload,
                "generation_mode": analysis_payload.get("generation_mode", "deterministic"),
                "generation_model": analysis_payload.get("generation_model"),
            },
        )

    def get_analysis(self, analysis_id: str) -> Any:
        record = get_stock_deep_analysis_record(self.db, str(analysis_id or "").strip())
        if record is None:
            raise LookupError(f"未找到深度分析: {analysis_id}")
        return record

    def list_history(self, *, stock_code: Optional[str] = None, limit: int = 20) -> List[Any]:
        normalized_stock_code = str(stock_code or "").strip().upper() or None
        return list_stock_deep_analysis_records(
            self.db,
            stock_code=normalized_stock_code,
            limit=max(1, min(int(limit or 20), 100)),
        )

    def chat(self, analysis_id: str, message: str) -> tuple[Any, Any]:
        record = self.get_analysis(analysis_id)
        user_text = str(message or "").strip()
        if not user_text:
            raise ValueError("message 不能为空")

        user_message = create_stock_deep_analysis_message(
            self.db,
            analysis_id=record.analysis_id,
            role="user",
            content=user_text,
        )
        llm_answer = self._answer_follow_up_with_llm(record, user_text)
        assistant_message = create_stock_deep_analysis_message(
            self.db,
            analysis_id=record.analysis_id,
            role="assistant",
            content=llm_answer or self._answer_follow_up(record, user_text),
        )
        return user_message, assistant_message

    def list_messages(self, analysis_id: str, *, limit: int = 50) -> List[Any]:
        return list_stock_deep_analysis_messages(
            self.db,
            analysis_id=str(analysis_id or "").strip(),
            limit=max(1, min(int(limit or 50), 200)),
        )

    def create_alert_rules(self, analysis_id: str, *, scan_interval_minutes: int = 5) -> List[Any]:
        record = self.get_analysis(analysis_id)
        trade_plan = self.db._safe_json_loads(record.trade_plan_json) or {}
        levels = trade_plan.get("levels") if isinstance(trade_plan, dict) else {}
        if not isinstance(levels, dict):
            levels = {}

        stock_code = record.stock_code.strip().upper()
        stock_name = record.stock_name.strip()
        interval = max(5, int(scan_interval_minutes or 5))
        upsert_stock_watchlist_item(
            self.db,
            stock_code=stock_code,
            stock_name=stock_name,
            alert_enabled=True,
            source_query_id=record.source_query_id,
        )

        created = []
        trial_price = self._safe_float(levels.get("trial_price"))
        confirm_price = self._safe_float(levels.get("confirm_price"))
        stop_loss = self._safe_float(levels.get("stop_loss"))

        if trial_price is not None:
            created.append(
                upsert_stock_alert_rule(
                    self.db,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    rule_type="support_retest",
                    threshold_value=trial_price,
                    scan_interval_minutes=interval,
                    enabled=True,
                    note="深度分析生成：回踩试仓条件",
                    source_query_id=record.source_query_id,
                )
            )
        if confirm_price is not None:
            created.append(
                upsert_stock_alert_rule(
                    self.db,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    rule_type="breakout_confirm",
                    threshold_value=confirm_price,
                    scan_interval_minutes=interval,
                    enabled=True,
                    note="深度分析生成：突破确认条件",
                    source_query_id=record.source_query_id,
                )
            )
        created.append(
            upsert_stock_alert_rule(
                self.db,
                stock_code=stock_code,
                stock_name=stock_name,
                rule_type="risk_event",
                threshold_value=None,
                scan_interval_minutes=interval,
                enabled=True,
                note=f"深度分析生成：风险事件提醒；止损位 {stop_loss:.2f} 用于人工风控" if stop_loss else "深度分析生成：风险事件提醒",
                source_query_id=record.source_query_id,
            )
        )
        return created

    def _find_latest_by_query_id(self, query_id: str) -> Optional[Any]:
        records = list_stock_deep_analysis_records(self.db, limit=500)
        for record in records:
            if record.source_query_id == query_id and record.status == "completed":
                return record
        return None

    def _build_analysis_payload(self, result: Dict[str, Any], *, query_id: str) -> Dict[str, Any]:
        stock_code = str(result.get("stock_code") or "").strip().upper()
        stock_name = str(result.get("stock_name") or stock_code).strip()
        current = self._safe_float(result.get("current_price"))
        support = self._safe_float(result.get("support"))
        pressure = self._safe_float(result.get("pressure"))
        trend_score = self._safe_float(result.get("trend_score")) or 50.0
        pct_chg = self._safe_float(result.get("pct_chg"))

        levels = self._build_levels(current=current, support=support, pressure=pressure)
        action, action_label = self._resolve_action(
            current=current,
            trial_price=levels["trial_price"],
            confirm_price=levels["confirm_price"],
            pct_chg=pct_chg,
            signal=str(result.get("signal") or ""),
        )
        confidence = self._build_confidence(result, trend_score=trend_score)
        risks = self._build_risk_items(result, current=current, levels=levels, pct_chg=pct_chg)

        summary = (
            f"{stock_name} 当前深度分析结论为「{action_label}」。"
            f"试仓位 {levels['trial_price']:.2f}，确认位 {levels['confirm_price']:.2f}，"
            f"止损位 {levels['stop_loss']:.2f}，目标位 {levels['target_price']:.2f}。"
        )
        trade_plan = {
            "action": action,
            "action_label": action_label,
            "confidence": confidence,
            "levels": levels,
            "position_plan": self._build_position_plan(action),
            "triggers": [
                f"回踩接近 {levels['trial_price']:.2f} 且没有跌破关键支撑时可小仓验证",
                f"放量站上 {levels['confirm_price']:.2f} 后再考虑加仓",
                f"跌破 {levels['stop_loss']:.2f} 或出现明确风险事件时退出观察",
            ],
        }
        technical = {
            "trend_score": trend_score,
            "trend_status": result.get("trend_status"),
            "buy_signal": result.get("buy_signal"),
            "pattern": result.get("pattern"),
            "support": support,
            "pressure": pressure,
            "ma10": result.get("ma10"),
            "ma20": result.get("ma20"),
            "bias_ma10": result.get("bias_ma10"),
            "assessment": self._technical_assessment(action_label, result),
        }
        fundamental = {
            "context": result.get("fundamental_context") or {},
            "coverage": result.get("fundamental_coverage") or (result.get("fundamental_context") or {}).get("coverage") or {},
            "details": result.get("fundamental_details") or self._extract_fundamental_details_from_context(result.get("fundamental_context")) or {},
            "errors": result.get("fundamental_errors") or (result.get("fundamental_context") or {}).get("errors") or [],
            "assessment": self._fundamental_assessment(result),
        }
        risk = {
            "items": risks,
            "news_summary": result.get("stock_news_summary"),
            "risk_level": "high" if len(risks) >= 3 else "medium" if risks else "low",
        }
        payload = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "action": action,
            "summary": summary,
            "trade_plan": trade_plan,
            "technical": technical,
            "fundamental": fundamental,
            "risk": risk,
            "query_id": query_id,
            "generation_mode": "deterministic",
            "generation_model": None,
        }
        llm_overlay = self._generate_with_llm(
            stock_code=stock_code,
            stock_name=stock_name,
            result=result,
            base_payload=payload,
        )
        if llm_overlay is not None:
            payload = self._apply_llm_overlay(payload, llm_overlay)
        return payload

    def _generate_with_llm(
        self,
        *,
        stock_code: str,
        stock_name: str,
        result: Dict[str, Any],
        base_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        try:
            overlay = self.llm_adapter.generate(
                stock_code=stock_code,
                stock_name=stock_name,
                result=result,
                base_payload=base_payload,
            )
            if overlay:
                overlay["generation_mode"] = "llm"
            return overlay
        except Exception:
            return None

    def _apply_llm_overlay(self, payload: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        next_payload = dict(payload)
        action = str(overlay.get("action") or "").strip()
        if action:
            next_payload["action"] = action
            next_payload["trade_plan"] = {
                **(next_payload.get("trade_plan") or {}),
                "action": action,
            }
        action_label = str(overlay.get("action_label") or "").strip()
        if action_label:
            next_payload["trade_plan"] = {
                **(next_payload.get("trade_plan") or {}),
                "action_label": action_label,
            }
        summary = str(overlay.get("summary") or "").strip()
        if summary:
            next_payload["summary"] = summary
        confidence = self._safe_float(overlay.get("confidence"))
        if confidence is not None:
            next_payload["trade_plan"] = {
                **(next_payload.get("trade_plan") or {}),
                "confidence": int(round(confidence)),
            }
        position_plan = overlay.get("position_plan")
        if isinstance(position_plan, dict) and position_plan:
            next_payload["trade_plan"] = {
                **(next_payload.get("trade_plan") or {}),
                "position_plan": {
                    **((next_payload.get("trade_plan") or {}).get("position_plan") or {}),
                    **{str(key): str(value) for key, value in position_plan.items() if value},
                },
            }
        triggers = overlay.get("triggers")
        if isinstance(triggers, list) and triggers:
            next_payload["trade_plan"] = {
                **(next_payload.get("trade_plan") or {}),
                "triggers": [str(item) for item in triggers[:4] if str(item).strip()],
            }
        technical_assessment = str(overlay.get("technical_assessment") or "").strip()
        if technical_assessment:
            next_payload["technical"] = {
                **(next_payload.get("technical") or {}),
                "assessment": technical_assessment,
            }
        fundamental_assessment = str(overlay.get("fundamental_assessment") or "").strip()
        if fundamental_assessment:
            next_payload["fundamental"] = {
                **(next_payload.get("fundamental") or {}),
                "assessment": fundamental_assessment,
            }
        risk_items = overlay.get("risk_items")
        if isinstance(risk_items, list) and risk_items:
            next_payload["risk"] = {
                **(next_payload.get("risk") or {}),
                "items": [str(item) for item in risk_items[:6] if str(item).strip()],
            }
        risk_level = str(overlay.get("risk_level") or "").strip()
        if risk_level:
            next_payload["risk"] = {
                **(next_payload.get("risk") or {}),
                "risk_level": risk_level,
            }
        next_payload["generation_mode"] = overlay.get("generation_mode", "llm")
        next_payload["generation_model"] = overlay.get("generation_model")
        return next_payload

    def _answer_follow_up_with_llm(self, record: Any, user_text: str) -> Optional[str]:
        try:
            analysis = {
                "analysis_id": record.analysis_id,
                "stock_code": record.stock_code,
                "stock_name": record.stock_name,
                "action": record.action,
                "summary": record.summary,
                "trade_plan": self.db._safe_json_loads(record.trade_plan_json) or {},
                "technical": self.db._safe_json_loads(record.technical_json) or {},
                "fundamental": self.db._safe_json_loads(record.fundamental_json) or {},
                "risk": self.db._safe_json_loads(record.risk_json) or {},
                "context_snapshot": self.db._safe_json_loads(record.context_snapshot_json) or {},
            }
            recent_messages = [
                {"role": message.role, "content": message.content}
                for message in self.list_messages(record.analysis_id, limit=8)
            ]
            answer = self.llm_adapter.chat(
                analysis=analysis,
                user_message=user_text,
                recent_messages=recent_messages,
            )
            normalized = str(answer or "").strip()
            return normalized or None
        except Exception:
            return None

    def _build_levels(
        self,
        *,
        current: Optional[float],
        support: Optional[float],
        pressure: Optional[float],
    ) -> Dict[str, float]:
        anchor = current or support or pressure or 0.0
        trial = support or (anchor * 0.97)
        confirm = pressure or (anchor * 1.03)
        if confirm <= trial:
            confirm = trial * 1.04
        stop = trial * 0.97
        target = max(confirm * 1.08, anchor * 1.1)
        return {
            "current_price": round(anchor, 2),
            "trial_price": round(trial, 2),
            "confirm_price": round(confirm, 2),
            "stop_loss": round(stop, 2),
            "target_price": round(target, 2),
        }

    def _resolve_action(
        self,
        *,
        current: Optional[float],
        trial_price: float,
        confirm_price: float,
        pct_chg: Optional[float],
        signal: str,
    ) -> tuple[str, str]:
        normalized_signal = signal.lower()
        if "risk" in normalized_signal or "avoid" in normalized_signal:
            return "avoid", "放弃观察"
        if current is None:
            return "observe", "继续观察"
        if pct_chg is not None and pct_chg >= 7:
            return "wait_retest", "等待回踩"
        if current <= trial_price * 1.015:
            return "trial_buy", "可试仓"
        if current >= confirm_price:
            return "breakout_confirm", "突破确认"
        return "wait_retest", "等待回踩"

    def _build_confidence(self, result: Dict[str, Any], *, trend_score: float) -> int:
        coverage = result.get("fundamental_coverage") or {}
        data_sources = result.get("data_sources") or {}
        coverage_bonus = sum(1 for value in coverage.values() if value and value != "missing") * 2
        source_bonus = sum(1 for value in data_sources.values() if value) * 2
        risk_penalty = len((result.get("stock_news_summary") or {}).get("risk_events") or []) * 5
        return max(35, min(92, int(trend_score * 0.7 + coverage_bonus + source_bonus - risk_penalty)))

    def _build_risk_items(
        self,
        result: Dict[str, Any],
        *,
        current: Optional[float],
        levels: Dict[str, float],
        pct_chg: Optional[float],
    ) -> List[str]:
        items = list(result.get("excluded_reasons") or [])
        news = result.get("stock_news_summary") or {}
        items.extend(news.get("risk_events") or [])
        if pct_chg is not None and pct_chg >= 7:
            items.append("短线涨幅偏大，当前位置追高的盈亏比不足")
        if current is not None and current > levels["trial_price"] * 1.05:
            items.append("当前价格距离试仓价带较远，需要等待回踩确认")
        if not items:
            items.append("暂无明确负面事件，但仍需跟踪主题热度和量价变化")
        return items[:6]

    @staticmethod
    def _build_position_plan(action: str) -> Dict[str, Any]:
        if action == "trial_buy":
            return {"initial": "20%", "add": "突破确认后加至 40%-50%", "max": "50%"}
        if action == "breakout_confirm":
            return {"initial": "20%-30%", "add": "回踩不破确认位后加仓", "max": "50%"}
        if action == "avoid":
            return {"initial": "0%", "add": "风险解除前不加仓", "max": "0%"}
        return {"initial": "0%-10%", "add": "回踩到试仓价带后再验证", "max": "30%"}

    @staticmethod
    def _technical_assessment(action_label: str, result: Dict[str, Any]) -> str:
        reasons = result.get("selected_reasons") or []
        prefix = "；".join(str(item) for item in reasons[:2]) if reasons else "技术面需要等待价格行为确认"
        return f"{prefix}。当前动作建议：{action_label}。"

    @staticmethod
    def _fundamental_assessment(result: Dict[str, Any]) -> str:
        coverage = result.get("fundamental_coverage") or (result.get("fundamental_context") or {}).get("coverage") or {}
        available = [key for key, value in coverage.items() if value and value != "missing"]
        if available:
            return f"已覆盖 {len(available)} 个基本面模块，适合作为交易计划的辅助验证。"
        return "当前基本面结构化覆盖不足，深度分析不应把基本面作为重仓依据。"

    @staticmethod
    def _extract_fundamental_details_from_context(fundamental_context: Any) -> Dict[str, Any]:
        if not isinstance(fundamental_context, dict):
            return {}
        details: Dict[str, Any] = {}
        for key in ("valuation", "growth", "earnings", "institution", "capital_flow", "dragon_tiger", "boards"):
            block = fundamental_context.get(key)
            if not isinstance(block, dict):
                continue
            data = block.get("data")
            if isinstance(data, dict) and data:
                details[key] = data
        return details

    def _answer_follow_up(self, record: Any, message: str) -> str:
        trade_plan = self.db._safe_json_loads(record.trade_plan_json) or {}
        levels = trade_plan.get("levels") if isinstance(trade_plan, dict) else {}
        if not isinstance(levels, dict):
            levels = {}
        action_label = trade_plan.get("action_label") or record.action or "继续观察"
        trial = levels.get("trial_price", "-")
        confirm = levels.get("confirm_price", "-")
        stop = levels.get("stop_loss", "-")
        text = message.lower()
        if "现在" in message or "为什么" in message or "买" in message:
            return f"当前结论是「{action_label}」。如果价格没有接近试仓位 {trial}，直接买入的盈亏比不够好；更稳妥的是等回踩确认，或站上确认位 {confirm} 后再小仓验证。"
        if "跌破" in message or "止损" in message or "放弃" in message:
            return f"本次计划的硬风控位是 {stop}。跌破后不应继续按原计划持有，需要重新评估趋势、新闻风险和主题热度。"
        if "告警" in message or "规则" in message:
            return f"可以生成三类规则：接近试仓位 {trial}、突破确认位 {confirm}、跌破止损位 {stop} 或出现明确风险事件。"
        return f"基于本次深度分析上下文，核心还是「{action_label}」：试仓看 {trial}，确认看 {confirm}，风控看 {stop}。"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
