from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path

from automailer.campaign import CampaignConfig, run_campaign
from automailer.contacts import EMAIL_COLUMN_CANDIDATES, detect_column, load_contacts, normalise_email
from automailer.planner import PlanConfig, build_send_queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or send due funnel emails with approval control.")
    parser.add_argument("--contacts", required=True, help="CSV or XLSX contact file path.")
    parser.add_argument("--funnel-config", required=True, help="Funnel config JSON path.")
    parser.add_argument("--campaign-id", required=True, help="Campaign id for dedupe.")
    parser.add_argument("--lead-state-path", default="state/lead_state.json")
    parser.add_argument("--db-path", default="state/send_history.jsonl")
    parser.add_argument("--timeline-path", default="state/lead_timeline.jsonl")
    parser.add_argument("--queue-output", default="outbox/due_queue.csv")
    parser.add_argument("--approval-output", default="outbox/due_approval.csv")
    parser.add_argument("--outbox-dir", default="outbox")
    parser.add_argument("--email-column", help="Recipient email column. Auto-detected if omitted.")
    parser.add_argument("--provider", choices=("dryrun", "sendgrid", "postmark", "outlook"))
    parser.add_argument("--test-to", help="Send every approved email to this address.")
    parser.add_argument("--outlook-display", action="store_true", help="Open Outlook compose windows instead of sending.")
    parser.add_argument("--send-approved", action="store_true", help="Process only rows marked approved=yes.")
    parser.add_argument("--send", action="store_true", help="Actually send approved emails. Omit for dry-run preview.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue_path = build_send_queue(
        PlanConfig(
            contacts_path=Path(args.contacts),
            funnel_config_path=Path(args.funnel_config),
            campaign_id=args.campaign_id,
            output_path=Path(args.queue_output),
            suppression_list_path=None,
            db_path=Path(args.db_path),
            lead_state_path=Path(args.lead_state_path),
            email_column=args.email_column,
            limit=None,
        )
    )
    queue_rows = _read_csv(queue_path)
    ready_rows = [row for row in queue_rows if row.get("status") == "ready"]
    approval_path = Path(args.approval_output)
    _write_approval_file(approval_path, ready_rows)

    print(f"queue={queue_path}")
    print(f"approval={approval_path}")
    print(f"ready={len(ready_rows)}")
    print(f"scheduled={sum(1 for row in queue_rows if row.get('status') == 'scheduled')}")
    print(f"skipped={sum(1 for row in queue_rows if row.get('status') == 'skipped')}")

    if not args.send_approved:
        print("mode=approval")
        print("next=mark approved=yes in the approval file, then rerun with --send-approved")
        return 0

    approved_emails = _approved_emails(approval_path)
    if not approved_emails:
        print("mode=send-approved")
        print("approved=0")
        return 0

    approved_contacts = _write_approved_contacts(
        contacts_path=Path(args.contacts),
        approved_emails=approved_emails,
        email_column=args.email_column,
        outbox_dir=Path(args.outbox_dir),
        campaign_id=args.campaign_id,
    )
    provider = args.provider or (os.getenv("MAIL_PROVIDER", "dryrun") if args.send else "dryrun")
    summary = run_campaign(
        CampaignConfig(
            contacts_path=approved_contacts,
            funnel_config_path=Path(args.funnel_config),
            template_dir=Path("email_templates"),
            template_name=None,
            word_template_path=None,
            subject_template=None,
            template_column=None,
            campaign_id=args.campaign_id,
            email_column=args.email_column,
            name_column=None,
            suppression_list_path=None,
            db_path=Path(args.db_path),
            lead_state_path=Path(args.lead_state_path),
            timeline_path=Path(args.timeline_path),
            outbox_dir=Path(args.outbox_dir),
            limit=None,
            test_to=args.test_to,
            allow_duplicates=False,
            provider=provider,
            outlook_display=args.outlook_display,
            real_send=args.send,
        )
    )
    print(summary.to_text())
    return 0 if summary.failed == 0 else 2


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _write_approval_file(path: Path, ready_rows: list[dict[str, str]]) -> None:
    previous = {
        _approval_key(row): str(row.get("approved") or "").strip().lower()
        for row in _read_csv(path)
    }
    rows = []
    for row in ready_rows:
        approved = previous.get(_approval_key(row), "no")
        rows.append(
            {
                "approved": "yes" if approved in {"yes", "true", "1", "on"} else "no",
                "email": row.get("email", ""),
                "template": row.get("template", ""),
                "rule": row.get("rule", ""),
                "campaign_step": row.get("campaign_step", ""),
                "next_send_at": row.get("next_send_at", ""),
                "detail": row.get("detail", ""),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        fieldnames = ["approved", "email", "template", "rule", "campaign_step", "next_send_at", "detail"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _approval_key(row: dict[str, str]) -> str:
    return f"{normalise_email(row.get('email', ''))}|{row.get('template', '').strip()}"


def _approved_emails(path: Path) -> set[str]:
    return {
        normalise_email(row.get("email", ""))
        for row in _read_csv(path)
        if str(row.get("approved") or "").strip().lower() in {"yes", "true", "1", "on"}
    }


def _write_approved_contacts(
    *,
    contacts_path: Path,
    approved_emails: set[str],
    email_column: str | None,
    outbox_dir: Path,
    campaign_id: str,
) -> Path:
    rows = load_contacts(contacts_path)
    if not rows:
        raise ValueError("No contact rows found.")
    detected_email_column = email_column or detect_column(rows, EMAIL_COLUMN_CANDIDATES)
    if not detected_email_column:
        raise ValueError("Could not detect recipient email column.")

    approved_rows = [
        row
        for row in rows
        if normalise_email(row.get(detected_email_column, "")) in approved_emails
    ]
    outbox_dir.mkdir(parents=True, exist_ok=True)
    safe_campaign = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in campaign_id)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8-sig",
        newline="",
        suffix=f"_{safe_campaign}_approved_contacts.csv",
        dir=outbox_dir,
        delete=False,
    ) as file:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(approved_rows)
        return Path(file.name)


if __name__ == "__main__":
    raise SystemExit(main())
