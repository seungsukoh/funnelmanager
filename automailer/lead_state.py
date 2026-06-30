from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {
    "converted",
    "excluded",
    "unsubscribed",
    "전환됨",
    "제외",
    "수신거부",
}


class LeadStateStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.state = self._load()

    def get(self, email: str) -> dict[str, Any]:
        return dict(self.state.get("contacts", {}).get(email, {}))

    def enrich_row(self, row: dict[str, str], email: str) -> dict[str, str]:
        enriched = dict(row)
        lead = self.get(email)
        if not lead:
            return enriched

        if lead.get("status"):
            enriched["lead_status"] = str(lead["status"])
        if lead.get("campaign_step"):
            enriched["campaign_step"] = str(lead["campaign_step"])
        if lead.get("next_send_at"):
            enriched["next_send_at"] = str(lead["next_send_at"])
        if lead.get("tags"):
            enriched["lead_tags"] = ", ".join(str(tag) for tag in lead["tags"])
        if lead.get("last_sent_at"):
            enriched["last_sent_at"] = str(lead["last_sent_at"])
        return enriched

    def is_terminal(self, email: str) -> bool:
        status = str(self.get(email).get("status", "")).strip()
        return status in TERMINAL_STATUSES

    def is_due(self, email: str, now: datetime | None = None) -> bool:
        raw_next = str(self.get(email).get("next_send_at", "")).strip()
        if not raw_next:
            return True

        now = now or datetime.now(timezone.utc)
        next_send_at = _parse_datetime(raw_next)
        return next_send_at <= now

    def apply_send_success(
        self,
        *,
        email: str,
        campaign_id: str,
        template_name: str,
        rule_name: str,
        updates: dict[str, Any],
    ) -> None:
        contacts = self.state.setdefault("contacts", {})
        lead = dict(contacts.get(email, {}))
        now = datetime.now(timezone.utc)

        if updates.get("set_status"):
            lead["status"] = str(updates["set_status"])
        else:
            lead.setdefault("status", "육성중")

        add_tags = _as_list(updates.get("add_tags"))
        remove_tags = set(str(tag) for tag in _as_list(updates.get("remove_tags")))
        tags = {str(tag) for tag in lead.get("tags", [])}
        tags.update(str(tag) for tag in add_tags)
        tags.difference_update(remove_tags)
        lead["tags"] = sorted(tag for tag in tags if tag)

        if updates.get("set_step"):
            lead["campaign_step"] = str(updates["set_step"])
        elif updates.get("next_step"):
            lead["campaign_step"] = str(updates["next_step"])
        else:
            lead["campaign_step"] = rule_name

        if updates.get("next_send_at"):
            lead["next_send_at"] = str(updates["next_send_at"])
        elif updates.get("next_send_after_days") is not None:
            days = float(updates["next_send_after_days"])
            lead["next_send_at"] = (now + timedelta(days=days)).isoformat()
        else:
            lead.pop("next_send_at", None)

        sent_templates = set(str(value) for value in lead.get("sent_templates", []))
        sent_templates.add(template_name)
        lead["sent_templates"] = sorted(sent_templates)
        lead["last_campaign_id"] = campaign_id
        lead["last_rule_name"] = rule_name
        lead["last_template_name"] = template_name
        lead["last_sent_at"] = now.isoformat()
        lead["updated_at"] = now.isoformat()

        contacts[email] = lead
        self._save()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"contacts": {}}
        with self.path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if "contacts" not in data or not isinstance(data["contacts"], dict):
            data["contacts"] = {}
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(self.state, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")


def should_commit_lead_state(
    *,
    real_send: bool,
    provider: str,
    test_to: str | None,
    outlook_display: bool,
) -> bool:
    return real_send and provider != "dryrun" and not test_to and not outlook_display


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
