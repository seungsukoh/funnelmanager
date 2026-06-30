from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from automailer.contacts import EMAIL_COLUMN_CANDIDATES, detect_column, is_valid_email, load_contacts, normalise_email
from automailer.funnel import apply_field_mapping, decide_action, load_funnel_config
from automailer.lead_state import LeadStateStore
from automailer.store import SendHistory


@dataclass(frozen=True)
class PlanConfig:
    contacts_path: Path
    funnel_config_path: Path
    campaign_id: str
    output_path: Path
    suppression_list_path: Path | None
    db_path: Path
    lead_state_path: Path
    email_column: str | None
    limit: int | None


def build_send_queue(config: PlanConfig) -> Path:
    rows = load_contacts(config.contacts_path)
    if config.limit:
        rows = rows[: config.limit]

    funnel = load_funnel_config(config.funnel_config_path)
    rows = [apply_field_mapping(row, funnel.field_mapping) for row in rows]
    email_column = config.email_column or detect_column(rows, EMAIL_COLUMN_CANDIDATES)
    if not email_column:
        raise ValueError("Could not detect recipient email column. Pass --email-column.")

    suppressed = _load_suppressed(config.suppression_list_path)
    history = SendHistory(config.db_path)
    lead_state = LeadStateStore(config.lead_state_path)
    output_rows: list[dict[str, str]] = []

    try:
        for index, row in enumerate(rows, start=2):
            raw_email = row.get(email_column, "")
            email = normalise_email(raw_email)
            lead_row = lead_state.enrich_row(row, email) if email else row

            if not email or not is_valid_email(email):
                output_rows.append(_queue_row(index, raw_email, "skipped", "", "", "invalid email", lead_row))
                continue

            if email in suppressed:
                output_rows.append(_queue_row(index, email, "skipped", "", "", "suppressed", lead_row))
                continue

            if lead_state.is_terminal(email):
                output_rows.append(
                    _queue_row(
                        index,
                        email,
                        "skipped",
                        "lead_state",
                        "",
                        f"terminal status: {lead_row.get('lead_status', '')}",
                        lead_row,
                    )
                )
                continue

            if not lead_state.is_due(email):
                output_rows.append(
                    _queue_row(
                        index,
                        email,
                        "scheduled",
                        "lead_state",
                        "",
                        f"not due until {lead_row.get('next_send_at', '')}",
                        lead_row,
                    )
                )
                continue

            decision = decide_action(funnel, lead_row)
            if decision.action == "skip":
                output_rows.append(
                    _queue_row(
                        index,
                        email,
                        "skipped",
                        decision.rule_name,
                        decision.template_name or "",
                        decision.skip_reason or "rule skipped",
                        lead_row,
                    )
                )
                continue

            if not decision.template_name:
                output_rows.append(
                    _queue_row(index, email, "skipped", decision.rule_name, "", "no template selected", lead_row)
                )
                continue

            key = _idempotency_key(config.campaign_id, decision.template_name, email)
            if history.has_success(key):
                output_rows.append(
                    _queue_row(
                        index,
                        email,
                        "skipped",
                        decision.rule_name,
                        decision.template_name,
                        "duplicate success",
                        lead_row,
                    )
                )
                continue

            output_rows.append(
                _queue_row(index, email, "ready", decision.rule_name, decision.template_name, "ready", lead_row)
            )
    finally:
        history.close()

    return _write_queue(config.output_path, output_rows)


def _queue_row(
    row_number: int,
    email: str,
    status: str,
    rule_name: str,
    template_name: str,
    detail: str,
    lead_row: dict[str, str],
) -> dict[str, str]:
    return {
        "row_number": str(row_number),
        "email": email,
        "status": status,
        "rule": rule_name,
        "template": template_name,
        "detail": detail,
        "lead_status": lead_row.get("lead_status", ""),
        "campaign_step": lead_row.get("campaign_step", ""),
        "next_send_at": lead_row.get("next_send_at", ""),
        "lead_tags": lead_row.get("lead_tags", ""),
    }


def _write_queue(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_number",
        "email",
        "status",
        "rule",
        "template",
        "detail",
        "lead_status",
        "campaign_step",
        "next_send_at",
        "lead_tags",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _load_suppressed(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    rows = load_contacts(path)
    email_column = detect_column(rows, EMAIL_COLUMN_CANDIDATES)
    if not email_column:
        return set()
    return {normalise_email(row.get(email_column, "")) for row in rows if row.get(email_column)}


def _idempotency_key(campaign_id: str, template_name: str, recipient_email: str) -> str:
    value = f"{campaign_id}|{template_name}|{recipient_email}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()
