from __future__ import annotations

import hashlib
import csv
from dataclasses import dataclass, field
from pathlib import Path

from automailer.contacts import (
    EMAIL_COLUMN_CANDIDATES,
    NAME_COLUMN_CANDIDATES,
    detect_column,
    is_valid_email,
    load_contacts,
    normalise_email,
)
from automailer.funnel import (
    RuleDecision,
    apply_field_mapping,
    decide_action,
    load_funnel_config,
)
from automailer.lead_state import LeadStateStore, should_commit_lead_state
from automailer.providers import SendRequest, create_provider
from automailer.rendering import enrich_variables, load_template, render_template
from automailer.word_template import load_word_template
from automailer.store import SendHistory
from automailer.timeline import TimelineStore


@dataclass(frozen=True)
class CampaignConfig:
    contacts_path: Path
    funnel_config_path: Path | None
    template_dir: Path
    template_name: str | None
    word_template_path: Path | None
    subject_template: str | None
    template_column: str | None
    campaign_id: str
    email_column: str | None
    name_column: str | None
    suppression_list_path: Path | None
    db_path: Path
    lead_state_path: Path
    timeline_path: Path
    outbox_dir: Path
    limit: int | None
    test_to: str | None
    allow_duplicates: bool
    provider: str
    outlook_display: bool
    real_send: bool


@dataclass
class CampaignSummary:
    processed: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = True
    provider: str = "dryrun"
    report_path: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            f"provider={self.provider}",
            f"mode={'dry-run' if self.dry_run else 'send'}",
            f"processed={self.processed}",
            f"sent={self.sent}",
            f"skipped={self.skipped}",
            f"failed={self.failed}",
        ]
        if self.report_path:
            lines.append(f"report={self.report_path}")
        if self.errors:
            lines.append("errors:")
            lines.extend(f"- {error}" for error in self.errors[:20])
            if len(self.errors) > 20:
                lines.append(f"- ... and {len(self.errors) - 20} more")
        return "\n".join(lines)


def run_campaign(config: CampaignConfig) -> CampaignSummary:
    rows = load_contacts(config.contacts_path)
    if config.limit:
        rows = rows[: config.limit]

    summary = CampaignSummary(dry_run=not config.real_send, provider=config.provider)
    if not rows:
        summary.errors.append("No contact rows found.")
        return summary

    funnel = load_funnel_config(config.funnel_config_path) if config.funnel_config_path else None
    if funnel:
        rows = [apply_field_mapping(row, funnel.field_mapping) for row in rows]

    email_column = config.email_column or detect_column(rows, EMAIL_COLUMN_CANDIDATES)
    if not email_column:
        raise ValueError("Could not detect recipient email column. Pass --email-column.")

    name_column = config.name_column or detect_column(rows, NAME_COLUMN_CANDIDATES)
    suppressed = _load_suppressed(config.suppression_list_path)
    provider = create_provider(
        config.provider,
        config.outbox_dir,
        outlook_display=config.outlook_display,
    )
    history = SendHistory(config.db_path)
    lead_state = LeadStateStore(config.lead_state_path)
    timeline = TimelineStore(config.timeline_path)
    commit_lead_state = should_commit_lead_state(
        real_send=config.real_send,
        provider=config.provider,
        test_to=config.test_to,
        outlook_display=config.outlook_display,
    )

    template_cache = {}
    report_rows: list[dict[str, str]] = []
    try:
        for index, row in enumerate(rows, start=2):
            summary.processed += 1
            raw_email = row.get(email_column, "")
            recipient_email = normalise_email(config.test_to or raw_email)
            original_email = normalise_email(raw_email)

            if not original_email or not is_valid_email(original_email):
                summary.skipped += 1
                summary.errors.append(f"row {index}: invalid email '{raw_email}'")
                report_rows.append(
                    _report_row(index, raw_email, recipient_email, "skipped", "", "", "invalid email")
                )
                timeline.record(
                    email=raw_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    detail="invalid email",
                    dry_run=not config.real_send,
                )
                continue
            if not is_valid_email(recipient_email):
                summary.failed += 1
                summary.errors.append(f"row {index}: invalid test recipient '{recipient_email}'")
                report_rows.append(
                    _report_row(index, original_email, recipient_email, "failed", "", "", "invalid test recipient")
                )
                timeline.record(
                    email=original_email,
                    event_type="failed",
                    campaign_id=config.campaign_id,
                    status="failed",
                    detail="invalid test recipient",
                    dry_run=not config.real_send,
                )
                continue
            if original_email in suppressed:
                summary.skipped += 1
                report_rows.append(
                    _report_row(index, original_email, recipient_email, "skipped", "", "", "suppressed")
                )
                timeline.record(
                    email=original_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    detail="suppressed",
                    dry_run=not config.real_send,
                )
                continue

            row = lead_state.enrich_row(row, original_email)
            if lead_state.is_terminal(original_email):
                summary.skipped += 1
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "skipped",
                        "lead_state",
                        "",
                        f"terminal status: {row.get('lead_status', '')}",
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    rule_name="lead_state",
                    detail=f"terminal status: {row.get('lead_status', '')}",
                    dry_run=not config.real_send,
                )
                continue
            if not lead_state.is_due(original_email):
                summary.skipped += 1
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "skipped",
                        "lead_state",
                        "",
                        f"not due until {row.get('next_send_at', '')}",
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    rule_name="lead_state",
                    detail=f"not due until {row.get('next_send_at', '')}",
                    dry_run=not config.real_send,
                )
                continue

            decision = decide_action(funnel, row) if funnel else _legacy_decision(config, row, index)
            if decision.action == "skip":
                summary.skipped += 1
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "skipped",
                        decision.rule_name,
                        decision.template_name or "",
                        decision.skip_reason or "rule skipped",
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    rule_name=decision.rule_name,
                    template_name=decision.template_name or "",
                    detail=decision.skip_reason or "rule skipped",
                    dry_run=not config.real_send,
                )
                continue

            if not decision.template_name:
                summary.skipped += 1
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "skipped",
                        decision.rule_name,
                        "",
                        "no template selected",
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    rule_name=decision.rule_name,
                    detail="no template selected",
                    dry_run=not config.real_send,
                )
                continue

            template_name = decision.template_name
            template = template_cache.get(template_name)
            if template is None:
                if config.word_template_path:
                    template = load_word_template(
                        config.word_template_path,
                        subject_template=config.subject_template,
                    )
                else:
                    template = load_template(config.template_dir, template_name)
                template_cache[template_name] = template

            to_name = row.get(name_column, "") if name_column else ""
            variables = enrich_variables(row, email=original_email, name=to_name)
            rendered = render_template(template, variables)
            if rendered.missing_variables:
                summary.errors.append(
                    f"row {index}: missing variables for {original_email}: "
                    + ", ".join(rendered.missing_variables)
                )

            key = _idempotency_key(config.campaign_id, template_name, original_email)
            if not config.allow_duplicates and history.has_success(key):
                summary.skipped += 1
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "skipped",
                        decision.rule_name,
                        template_name,
                        "duplicate success",
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="skipped",
                    campaign_id=config.campaign_id,
                    status="skipped",
                    rule_name=decision.rule_name,
                    template_name=template_name,
                    detail="duplicate success",
                    dry_run=not config.real_send,
                )
                continue

            request = SendRequest(
                to_email=recipient_email,
                to_name=to_name or None,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                template_name=template_name,
                campaign_id=config.campaign_id,
            )

            if config.real_send:
                history.start(
                    idempotency_key=key,
                    campaign_id=config.campaign_id,
                    recipient_email=original_email,
                    template_name=template_name,
                )
            result = provider.send(request)
            if result.ok:
                summary.sent += 1
                if commit_lead_state:
                    lead_state.apply_send_success(
                        email=original_email,
                        campaign_id=config.campaign_id,
                        template_name=template_name,
                        rule_name=decision.rule_name,
                        updates=decision.updates,
                    )
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "sent",
                        decision.rule_name,
                        template_name,
                        result.message_id or "",
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="sent" if config.real_send else "dry_run_sent",
                    campaign_id=config.campaign_id,
                    status="sent",
                    rule_name=decision.rule_name,
                    template_name=template_name,
                    detail=result.message_id or "",
                    dry_run=not config.real_send,
                    metadata={"lead_updates": decision.updates},
                )
                if config.real_send:
                    history.finish(
                        idempotency_key=key,
                        status="sent",
                        provider=result.provider,
                        provider_message_id=result.message_id,
                        error=None,
                    )
            else:
                summary.failed += 1
                error = result.error or f"status={result.status_code}"
                summary.errors.append(f"row {index}: provider error for {original_email}: {error}")
                report_rows.append(
                    _report_row(
                        index,
                        original_email,
                        recipient_email,
                        "failed",
                        decision.rule_name,
                        template_name,
                        error,
                    )
                )
                timeline.record(
                    email=original_email,
                    event_type="failed",
                    campaign_id=config.campaign_id,
                    status="failed",
                    rule_name=decision.rule_name,
                    template_name=template_name,
                    detail=error,
                    dry_run=not config.real_send,
                )
                if config.real_send:
                    history.finish(
                        idempotency_key=key,
                        status="failed",
                        provider=result.provider,
                        provider_message_id=result.message_id,
                        error=error,
                    )
    finally:
        history.close()

    if report_rows:
        summary.report_path = str(_write_report(config.outbox_dir, config.campaign_id, report_rows))

    return summary


def _load_suppressed(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    rows = load_contacts(path)
    email_column = detect_column(rows, EMAIL_COLUMN_CANDIDATES)
    if not email_column:
        return set()
    return {normalise_email(row.get(email_column, "")) for row in rows if row.get(email_column)}


def _legacy_decision(config: CampaignConfig, row: dict[str, str], index: int) -> RuleDecision:
    return RuleDecision(
        action="send",
        template_name=_template_name_for_row(config, row, index),
        rule_name="legacy",
        skip_reason=None,
        updates={},
    )


def _template_name_for_row(config: CampaignConfig, row: dict[str, str], index: int) -> str:
    if config.word_template_path:
        return config.word_template_path.stem
    if config.template_column:
        value = row.get(config.template_column, "").strip()
        if not value:
            raise ValueError(f"row {index}: template column '{config.template_column}' is empty.")
        return value
    if not config.template_name:
        raise ValueError("No template name configured.")
    return config.template_name


def _idempotency_key(campaign_id: str, template_name: str, recipient_email: str) -> str:
    value = f"{campaign_id}|{template_name}|{recipient_email}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _report_row(
    row_number: int,
    original_email: str,
    recipient_email: str,
    status: str,
    rule_name: str,
    template_name: str,
    detail: str,
) -> dict[str, str]:
    return {
        "row_number": str(row_number),
        "original_email": original_email,
        "recipient_email": recipient_email,
        "status": status,
        "rule": rule_name,
        "template": template_name,
        "detail": detail,
    }


def _write_report(outbox_dir: Path, campaign_id: str, rows: list[dict[str, str]]) -> Path:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    safe_campaign = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in campaign_id)
    path = outbox_dir / f"{safe_campaign}_report.csv"
    fieldnames = ["row_number", "original_email", "recipient_email", "status", "rule", "template", "detail"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
