from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect per-lead timeline JSONL events.")
    parser.add_argument("--timeline-path", default="state/lead_timeline.jsonl", help="Timeline JSONL path.")
    parser.add_argument("--email", help="Filter by recipient email.")
    parser.add_argument("--campaign-id", help="Filter by campaign id.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum events to print.")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    path = Path(args.timeline_path)
    if not path.exists():
        print("No timeline found.")
        return 0

    events = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            event = json.loads(line)
            if args.email and event.get("email") != args.email:
                continue
            if args.campaign_id and event.get("campaign_id") != args.campaign_id:
                continue
            events.append(event)

    for event in events[-args.limit :]:
        print(
            "\t".join(
                [
                    str(event.get("occurred_at", "")),
                    str(event.get("email", "")),
                    str(event.get("campaign_id", "")),
                    str(event.get("event_type", "")),
                    str(event.get("rule_name", "")),
                    str(event.get("template_name", "")),
                    str(event.get("detail", "")),
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
