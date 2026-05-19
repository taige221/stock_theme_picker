# -*- coding: utf-8 -*-
"""
===================================
Information Review Service
===================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from theme_picker.infrastructure.persistence import get_theme_picker_db, list_information_events, list_theme_factor_scan_records


EVENT_TYPE_LABELS: Dict[str, str] = {
    "order": "订单/采购",
    "capacity_expand": "扩产/投产",
    "mass_production": "量产/交付",
    "price_signal": "涨价/价格",
    "policy_catalyst": "政策/放行",
    "technology_progress": "技术进展",
    "capital_expenditure": "资本开支",
    "risk_signal": "风险事件",
    "opinion_only": "观点解读",
}


class InformationReviewService:
    def __init__(self) -> None:
        self.db = get_theme_picker_db()

    def build_summary(self, *, days: int = 7) -> Dict[str, Any]:
        safe_days = max(1, min(int(days or 7), 90))
        cutoff = datetime.now() - timedelta(days=safe_days)
        events = [event for event in list_information_events(self.db, limit=600) if (event.created_at or event.updated_at or datetime.min) >= cutoff]
        scans = [scan for scan in list_theme_factor_scan_records(self.db, limit=400) if (scan.created_at or scan.updated_at or datetime.min) >= cutoff]

        event_by_id = {str(getattr(event, "event_id", "") or ""): event for event in events}
        total_events = len(events)
        promoted_events = sum(1 for event in events if str(getattr(event, "status", "") or "") == "promoted")
        discovery_events = sum(1 for event in events if str(getattr(event, "source_mode", "") or "") == "discovery")
        scan_count = len(scans)
        high_score_scan_count = sum(1 for scan in scans if float(getattr(scan, "theme_factor_score", 0.0) or 0.0) >= 75.0)

        confirmed_etf_scan_count = 0
        theme_counter: Counter[str] = Counter()
        host_counter: Counter[str] = Counter()
        breakdown: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "event_count": 0,
                "promoted_count": 0,
                "scan_count": 0,
                "high_score_count": 0,
                "signal_sum": 0.0,
                "theme_factor_sum": 0.0,
            }
        )

        for event in events:
            metadata = self.db._safe_json_loads(getattr(event, "metadata_json", None)) or {}
            event_type = str(getattr(event, "event_type", "") or "")
            bucket = breakdown[event_type]
            bucket["event_count"] += 1
            bucket["signal_sum"] += float(getattr(event, "signal_strength", 0.0) or 0.0)
            if str(getattr(event, "status", "") or "") == "promoted":
                bucket["promoted_count"] += 1
            for theme in self.db._safe_json_loads(getattr(event, "themes_json", None)) or []:
                theme_counter[str(theme)] += 1
            source_host = str(metadata.get("source_host") or "").strip()
            if source_host:
                host_counter[source_host] += 1

        for scan in scans:
            result = self.db._safe_json_loads(getattr(scan, "result_payload", None)) or {}
            etf_confirmation = dict((result or {}).get("etf_confirmation") or {})
            if bool(etf_confirmation.get("confirmed")):
                confirmed_etf_scan_count += 1
            event = event_by_id.get(str(getattr(scan, "event_id", "") or ""))
            if event is None:
                continue
            event_type = str(getattr(event, "event_type", "") or "")
            bucket = breakdown[event_type]
            bucket["scan_count"] += 1
            theme_factor_score = float(getattr(scan, "theme_factor_score", 0.0) or 0.0)
            bucket["theme_factor_sum"] += theme_factor_score
            if theme_factor_score >= 75.0:
                bucket["high_score_count"] += 1

        summary_breakdown: List[Dict[str, Any]] = []
        for event_type, bucket in breakdown.items():
            event_count = max(1, int(bucket["event_count"]))
            scan_count_for_type = max(1, int(bucket["scan_count"])) if int(bucket["scan_count"]) > 0 else 0
            summary_breakdown.append(
                {
                    "key": event_type,
                    "label": EVENT_TYPE_LABELS.get(event_type, event_type),
                    "event_count": int(bucket["event_count"]),
                    "promoted_count": int(bucket["promoted_count"]),
                    "scan_count": int(bucket["scan_count"]),
                    "high_score_count": int(bucket["high_score_count"]),
                    "avg_signal_strength": round(float(bucket["signal_sum"]) / event_count, 2),
                    "avg_theme_factor_score": round(
                        float(bucket["theme_factor_sum"]) / scan_count_for_type,
                        2,
                    )
                    if scan_count_for_type
                    else 0.0,
                }
            )

        summary_breakdown.sort(
            key=lambda item: (
                int(item.get("high_score_count") or 0),
                int(item.get("scan_count") or 0),
                float(item.get("avg_signal_strength") or 0.0),
            ),
            reverse=True,
        )

        promoted_rate = round((promoted_events / total_events) * 100.0, 2) if total_events else 0.0
        scan_conversion_rate = round((scan_count / promoted_events) * 100.0, 2) if promoted_events else 0.0
        high_score_rate = round((high_score_scan_count / scan_count) * 100.0, 2) if scan_count else 0.0
        confirmed_etf_rate = round((confirmed_etf_scan_count / scan_count) * 100.0, 2) if scan_count else 0.0

        return {
            "days": safe_days,
            "total_events": total_events,
            "promoted_events": promoted_events,
            "discovery_events": discovery_events,
            "scan_count": scan_count,
            "high_score_scan_count": high_score_scan_count,
            "confirmed_etf_scan_count": confirmed_etf_scan_count,
            "promoted_rate": promoted_rate,
            "scan_conversion_rate": scan_conversion_rate,
            "high_score_rate": high_score_rate,
            "confirmed_etf_rate": confirmed_etf_rate,
            "top_themes": [{"label": label, "count": count} for label, count in theme_counter.most_common(8)],
            "top_source_hosts": [{"label": label, "count": count} for label, count in host_counter.most_common(8)],
            "event_type_breakdown": summary_breakdown[:8],
        }
