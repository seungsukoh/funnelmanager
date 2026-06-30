from __future__ import annotations

import argparse
from pathlib import Path

from automailer.planner import PlanConfig, build_send_queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a send queue CSV without rendering or sending emails.")
    parser.add_argument("--contacts", required=True, help="CSV or XLSX contact file path.")
    parser.add_argument("--funnel-config", required=True, help="Funnel JSON config path.")
    parser.add_argument("--campaign-id", required=True, help="Campaign id used for duplicate checks.")
    parser.add_argument("--output", required=True, help="Queue CSV output path.")
    parser.add_argument("--email-column", help="Recipient email column. Auto-detected if omitted.")
    parser.add_argument("--suppression-list", help="Optional CSV/XLSX list of addresses to exclude.")
    parser.add_argument("--db-path", default="state/send_history.jsonl", help="JSONL send history path.")
    parser.add_argument("--lead-state-path", default="state/lead_state.json", help="Lead state JSON path.")
    parser.add_argument("--limit", type=int, help="Maximum number of rows to plan.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = build_send_queue(
        PlanConfig(
            contacts_path=Path(args.contacts),
            funnel_config_path=Path(args.funnel_config),
            campaign_id=args.campaign_id,
            output_path=Path(args.output),
            suppression_list_path=Path(args.suppression_list) if args.suppression_list else None,
            db_path=Path(args.db_path),
            lead_state_path=Path(args.lead_state_path),
            email_column=args.email_column,
            limit=args.limit,
        )
    )
    print(f"queue={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
