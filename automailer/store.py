from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SendRecord:
    idempotency_key: str
    recipient_email: str
    template_name: str
    status: str


class SendHistory:
    def __init__(self, db_path: Path):
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.statuses = self._load_statuses()

    def has_success(self, idempotency_key: str) -> bool:
        return self.statuses.get(idempotency_key) == "sent"

    def start(
        self,
        *,
        idempotency_key: str,
        campaign_id: str,
        recipient_email: str,
        template_name: str,
    ) -> None:
        now = _now()
        self.statuses[idempotency_key] = "sending"
        self._append(
            {
                "event": "start",
                "idempotency_key": idempotency_key,
                "campaign_id": campaign_id,
                "recipient_email": recipient_email,
                "template_name": template_name,
                "status": "sending",
                "created_at": now,
                "updated_at": now,
            }
        )

    def finish(
        self,
        *,
        idempotency_key: str,
        status: str,
        provider: str,
        provider_message_id: str | None,
        error: str | None,
    ) -> None:
        self.statuses[idempotency_key] = status
        self._append(
            {
                "event": "finish",
                "idempotency_key": idempotency_key,
                "status": status,
                "provider": provider,
                "provider_message_id": provider_message_id,
                "error": error,
                "updated_at": _now(),
            }
        )

    def close(self) -> None:
        return None

    def _load_statuses(self) -> dict[str, str]:
        if not self.db_path.exists():
            return {}

        statuses: dict[str, str] = {}
        with self.db_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = record.get("idempotency_key")
                status = record.get("status")
                if key and status:
                    statuses[str(key)] = str(status)
        return statuses

    def _append(self, record: dict[str, object]) -> None:
        with self.db_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
