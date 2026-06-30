from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TimelineStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        email: str,
        event_type: str,
        campaign_id: str,
        status: str,
        rule_name: str = "",
        template_name: str = "",
        detail: str = "",
        dry_run: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "email": email,
            "event_type": event_type,
            "campaign_id": campaign_id,
            "status": status,
            "rule_name": rule_name,
            "template_name": template_name,
            "detail": detail,
            "dry_run": dry_run,
            "metadata": metadata or {},
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
