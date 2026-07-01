from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from automailer.contacts import (
    EMAIL_COLUMN_CANDIDATES,
    NAME_COLUMN_CANDIDATES,
    detect_column,
    is_valid_email,
    load_contacts,
    normalise_email,
)
from automailer.funnel import apply_field_mapping, decide_action, load_funnel_config
from automailer.lead_state import LeadStateStore
from automailer.rendering import enrich_variables, load_template, render_template
from automailer.store import SendHistory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export approved due emails for Gmail Apps Script sending.")
    parser.add_argument("--contacts", required=True, help="CSV or XLSX contact file path.")
    parser.add_argument("--funnel-config", required=True, help="Funnel config JSON path.")
    parser.add_argument("--campaign-id", required=True, help="Campaign id for dedupe.")
    parser.add_argument("--approval-path", help="Approval CSV. Only approved=yes rows are exported.")
    parser.add_argument("--output", default="outbox/gmail_send_queue.csv", help="Google Sheets-ready CSV output.")
    parser.add_argument("--template-dir", default="email_templates")
    parser.add_argument("--lead-state-path", default="state/lead_state.json")
    parser.add_argument("--db-path", default="state/send_history.jsonl")
    parser.add_argument("--email-column", help="Recipient email column. Auto-detected if omitted.")
    parser.add_argument("--name-column", help="Recipient name column. Auto-detected if omitted.")
    parser.add_argument("--limit", type=int, help="Maximum number of contact rows to inspect.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_contacts(Path(args.contacts))
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("No contact rows found.")

    funnel = load_funnel_config(Path(args.funnel_config))
    rows = [apply_field_mapping(row, funnel.field_mapping) for row in rows]
    email_column = args.email_column or detect_column(rows, EMAIL_COLUMN_CANDIDATES)
    if not email_column:
        raise SystemExit("Could not detect recipient email column.")
    name_column = args.name_column or detect_column(rows, NAME_COLUMN_CANDIDATES)

    approved_keys = _approved_keys(Path(args.approval_path)) if args.approval_path else None
    lead_state = LeadStateStore(Path(args.lead_state_path))
    history = SendHistory(Path(args.db_path))
    template_cache = {}
    output_rows: list[dict[str, str]] = []

    try:
        for source_row in rows:
            raw_email = source_row.get(email_column, "")
            email = normalise_email(raw_email)
            if not email or not is_valid_email(email):
                continue
            row = lead_state.enrich_row(source_row, email)
            if lead_state.is_terminal(email) or not lead_state.is_due(email):
                continue

            decision = decide_action(funnel, row)
            if decision.action != "send" or not decision.template_name:
                continue
            if approved_keys is not None and _approval_key(email, decision.template_name) not in approved_keys:
                continue

            idempotency_key = _idempotency_key(args.campaign_id, decision.template_name, email)
            if history.has_success(idempotency_key):
                continue

            template = template_cache.get(decision.template_name)
            if template is None:
                template = load_template(Path(args.template_dir), decision.template_name)
                template_cache[decision.template_name] = template

            name = row.get(name_column, "") if name_column else ""
            rendered = render_template(template, enrich_variables(row, email=email, name=name))
            output_rows.append(
                {
                    "approved": "yes",
                    "status": "pending",
                    "email": email,
                    "name": name,
                    "campaign_id": args.campaign_id,
                    "template": decision.template_name,
                    "rule": decision.rule_name,
                    "subject": rendered.subject,
                    "text_body": rendered.text_body,
                    "html_body": rendered.html_body,
                    "dedupe_key": idempotency_key,
                    "sent_at": "",
                    "error": "" if not rendered.missing_variables else "missing: " + ", ".join(rendered.missing_variables),
                }
            )
    finally:
        history.close()

    output_path = Path(args.output)
    _write_queue(output_path, output_rows)
    print(f"gmail_queue={output_path}")
    print(f"pending={len(output_rows)}")
    return 0


def _approved_keys(path: Path) -> set[str]:
    if not path.exists():
        raise SystemExit(f"Approval file not found: {path}")
    keys = set()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if str(row.get("approved") or "").strip().lower() in {"yes", "true", "1", "on"}:
                keys.add(_approval_key(normalise_email(row.get("email", "")), row.get("template", "")))
    return keys


def _approval_key(email: str, template: str) -> str:
    return f"{email}|{template.strip()}"


def _idempotency_key(campaign_id: str, template_name: str, recipient_email: str) -> str:
    value = f"{campaign_id}|{template_name}|{recipient_email}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _write_queue(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "approved",
        "status",
        "email",
        "name",
        "campaign_id",
        "template",
        "rule",
        "subject",
        "text_body",
        "html_body",
        "dedupe_key",
        "sent_at",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
