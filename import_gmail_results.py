from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from automailer.funnel import FunnelRule, load_funnel_config
from automailer.lead_state import LeadStateStore
from automailer.store import SendHistory
from automailer.timeline import TimelineStore


SUCCESS_STATUSES = {"sent", "delivered", "success"}
FAILED_STATUSES = {"failed", "error", "bounced"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Gmail Apps Script send results into local funnel state.")
    parser.add_argument("--results", required=True, help="CSV exported from the GmailQueue Google Sheet.")
    parser.add_argument("--funnel-config", required=True, help="Funnel config JSON path.")
    parser.add_argument("--lead-state-path", default="state/lead_state.json")
    parser.add_argument("--db-path", default="state/send_history.jsonl")
    parser.add_argument("--timeline-path", default="state/lead_timeline.jsonl")
    parser.add_argument("--default-campaign-id", help="Used when a result row has no campaign_id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = import_results(
        results_path=Path(args.results),
        funnel_config_path=Path(args.funnel_config),
        lead_state_path=Path(args.lead_state_path),
        db_path=Path(args.db_path),
        timeline_path=Path(args.timeline_path),
        default_campaign_id=args.default_campaign_id,
    )
    print(f"processed={summary['processed']}")
    print(f"imported={summary['imported']}")
    print(f"failed={summary['failed']}")
    print(f"skipped={summary['skipped']}")
    return 0


def import_results(
    *,
    results_path: Path,
    funnel_config_path: Path,
    lead_state_path: Path,
    db_path: Path,
    timeline_path: Path,
    default_campaign_id: str | None = None,
) -> dict[str, int]:
    rows = _read_csv(results_path)
    if not rows:
        return {"processed": 0, "imported": 0, "failed": 0, "skipped": 0}

    funnel = load_funnel_config(funnel_config_path)
    rules_by_name = {rule.name: rule for rule in funnel.rules}
    lead_state = LeadStateStore(lead_state_path)
    history = SendHistory(db_path)
    timeline = TimelineStore(timeline_path)

    processed = 0
    imported = 0
    failed = 0
    skipped = 0
    try:
        for row in rows:
            processed += 1
            email = str(row.get("email") or "").strip().lower()
            template = str(row.get("template") or "").strip()
            campaign_id = str(row.get("campaign_id") or default_campaign_id or "").strip()
            status = str(row.get("status") or "").strip().lower()
            rule_name = str(row.get("rule") or "").strip()
            detail = str(row.get("error") or row.get("sent_at") or "").strip()

            if not email or not template or not campaign_id:
                skipped += 1
                continue
            if status not in SUCCESS_STATUSES and status not in FAILED_STATUSES:
                skipped += 1
                continue

            dedupe_key = str(row.get("dedupe_key") or "").strip()
            if not dedupe_key:
                dedupe_key = _idempotency_key(campaign_id, template, email)

            if status in SUCCESS_STATUSES:
                if history.has_success(dedupe_key):
                    skipped += 1
                    continue
                rule = _rule_for_result(rules_by_name, rule_name, template)
                sent_at = _parse_datetime(str(row.get("sent_at") or ""))
                lead_state.apply_send_success(
                    email=email,
                    campaign_id=campaign_id,
                    template_name=template,
                    rule_name=rule.name if rule else rule_name or template,
                    updates=rule.updates if rule else {},
                    occurred_at=sent_at,
                )
                history.finish(
                    idempotency_key=dedupe_key,
                    status="sent",
                    provider="gmail_apps_script",
                    provider_message_id=str(row.get("sent_at") or ""),
                    error=None,
                )
                timeline.record(
                    email=email,
                    event_type="sent",
                    campaign_id=campaign_id,
                    status="sent",
                    rule_name=rule.name if rule else rule_name,
                    template_name=template,
                    detail="gmail_apps_script",
                    dry_run=False,
                    metadata={"source": "gmail_apps_script", "sent_at": row.get("sent_at", "")},
                )
                imported += 1
                continue

            history.finish(
                idempotency_key=dedupe_key,
                status="failed",
                provider="gmail_apps_script",
                provider_message_id=None,
                error=detail or "gmail_apps_script failed",
            )
            timeline.record(
                email=email,
                event_type="failed",
                campaign_id=campaign_id,
                status="failed",
                rule_name=rule_name,
                template_name=template,
                detail=detail or "gmail_apps_script failed",
                dry_run=False,
                metadata={"source": "gmail_apps_script"},
            )
            failed += 1
    finally:
        history.close()

    return {"processed": processed, "imported": imported, "failed": failed, "skipped": skipped}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _rule_for_result(rules_by_name: dict[str, FunnelRule], rule_name: str, template: str) -> FunnelRule | None:
    if rule_name in rules_by_name:
        return rules_by_name[rule_name]
    for rule in rules_by_name.values():
        if rule.template_name == template:
            return rule
    return None


def _idempotency_key(campaign_id: str, template_name: str, recipient_email: str) -> str:
    value = f"{campaign_id}|{template_name}|{recipient_email}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _parse_datetime(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
