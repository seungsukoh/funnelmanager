from __future__ import annotations

import argparse
import os
from pathlib import Path

from automailer.campaign import CampaignConfig, run_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send templated emails from a CSV/XLSX contact file through an ESP API."
    )
    parser.add_argument("--contacts", required=True, help="CSV or XLSX contact file path.")
    parser.add_argument(
        "--funnel-config",
        help="JSON file with field mapping, rules, and default template.",
    )
    parser.add_argument("--template-dir", default="email_templates", help="Template directory.")
    parser.add_argument("--template-name", help="Template base name, e.g. event_followup.")
    parser.add_argument(
        "--word-template",
        help="Word .docx file to use as the email body template.",
    )
    parser.add_argument(
        "--subject",
        help="Subject template for --word-template. Defaults to the Word file name.",
    )
    parser.add_argument(
        "--template-column",
        help="Contact file column containing the template base name for each row.",
    )
    parser.add_argument("--campaign-id", required=True, help="Unique campaign id for dedupe.")
    parser.add_argument("--email-column", help="Recipient email column. Auto-detected if omitted.")
    parser.add_argument("--name-column", help="Recipient name column. Auto-detected if omitted.")
    parser.add_argument(
        "--suppression-list",
        help="Optional CSV/XLSX list of addresses to exclude. Auto-detects email column.",
    )
    parser.add_argument(
        "--db-path",
        default="state/send_history.jsonl",
        help="JSONL file path for send history.",
    )
    parser.add_argument(
        "--lead-state-path",
        default="state/lead_state.json",
        help="JSON file storing lead status, tags, campaign step, and next send time.",
    )
    parser.add_argument(
        "--timeline-path",
        default="state/lead_timeline.jsonl",
        help="JSONL timeline file for per-lead processing events.",
    )
    parser.add_argument("--outbox-dir", default="outbox", help="Dry-run output directory.")
    parser.add_argument(
        "--provider",
        choices=("dryrun", "sendgrid", "postmark", "outlook"),
        help="Mail provider. Defaults to MAIL_PROVIDER when --send is used; dryrun otherwise.",
    )
    parser.add_argument(
        "--outlook-display",
        action="store_true",
        help="With --provider outlook, open Outlook compose windows instead of sending.",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of contact rows to process.")
    parser.add_argument(
        "--test-to",
        help="Override every recipient with this address. Useful before real sends.",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Disable send-history duplicate protection.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send email. Omit this for dry-run preview files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.word_template and (args.template_name or args.template_column):
        raise SystemExit("Use either --word-template or --template-name/--template-column, not both.")
    if (
        not args.funnel_config
        and not args.word_template
        and not args.template_name
        and not args.template_column
    ):
        raise SystemExit("Provide --funnel-config, --word-template, --template-name, or --template-column.")

    provider = args.provider or (os.getenv("MAIL_PROVIDER", "dryrun") if args.send else "dryrun")

    config = CampaignConfig(
        contacts_path=Path(args.contacts),
        funnel_config_path=Path(args.funnel_config) if args.funnel_config else None,
        template_dir=Path(args.template_dir),
        template_name=args.template_name,
        word_template_path=Path(args.word_template) if args.word_template else None,
        subject_template=args.subject,
        template_column=args.template_column,
        campaign_id=args.campaign_id,
        email_column=args.email_column,
        name_column=args.name_column,
        suppression_list_path=Path(args.suppression_list) if args.suppression_list else None,
        db_path=Path(args.db_path),
        lead_state_path=Path(args.lead_state_path),
        timeline_path=Path(args.timeline_path),
        outbox_dir=Path(args.outbox_dir),
        limit=args.limit,
        test_to=args.test_to,
        allow_duplicates=args.allow_duplicates,
        provider=provider,
        outlook_display=args.outlook_display,
        real_send=args.send,
    )

    summary = run_campaign(config)
    print(summary.to_text())
    return 0 if summary.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
