# -*- coding: utf-8 -*-
"""Run one stock-alert scan cycle manually."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
PARENT_DIR = REPO_ROOT.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.application.stock_alert_service import StockAlertService
from theme_picker.infrastructure.persistence import get_theme_picker_db, list_stock_alert_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one stock alert scan cycle")
    parser.add_argument("--stock-code", help="只扫描某一只股票代码")
    parser.add_argument("--limit", type=int, default=10, help="输出最近事件数量")
    args = parser.parse_args()

    service = StockAlertService()
    summary = service.run_once(stock_code=args.stock_code)

    print(
        json.dumps(
            {
                "scanned_rules": summary.scanned_rules,
                "due_rules": summary.due_rules,
                "skipped_rules": summary.skipped_rules,
                "triggered_events": summary.triggered_events,
                "trigger_records": [
                    {
                        "stock_code": item.stock_code,
                        "stock_name": item.stock_name,
                        "rule_id": item.rule_id,
                        "rule_type": item.rule_type,
                        "title": item.title,
                        "message": item.message,
                        "dedupe_key": item.dedupe_key,
                    }
                    for item in summary.trigger_records
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    db = get_theme_picker_db()
    recent_events = list_stock_alert_events(
        db,
        limit=max(1, int(args.limit)),
        stock_code=args.stock_code.strip().upper() if args.stock_code else None,
    )
    if not recent_events:
        print("recent_events: []")
        return

    print("recent_events:")
    for event in recent_events:
        print(
            json.dumps(
                {
                    "id": event.id,
                    "stock_code": event.stock_code,
                    "stock_name": event.stock_name,
                    "rule_id": event.rule_id,
                    "rule_type": event.rule_type,
                    "event_type": event.event_type,
                    "title": event.title,
                    "message": event.message,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
