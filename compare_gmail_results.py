from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from import_gmail_results import FAILED_STATUSES, SUCCESS_STATUSES


PENDING_STATUSES = {"", "pending", "queued", "approved", "ready"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Gmail Apps Script results with local customer state.")
    parser.add_argument("--results", required=True, help="CSV exported from the GmailQueue Google Sheet.")
    parser.add_argument("--lead-state-path", default="state/lead_state.json")
    parser.add_argument("--campaign-id", help="Only compare rows for this campaign when campaign_id is present.")
    parser.add_argument("--output", help="Optional comparison CSV output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = compare_results(
        results_path=Path(args.results),
        lead_state_path=Path(args.lead_state_path),
        campaign_id=args.campaign_id,
    )
    if args.output:
        _write_csv(Path(args.output), result["rows"])
        print(f"output={args.output}")
    counts = result["counts"]
    print(f"processed={result['processed']}")
    print(f"matched={counts['matched']}")
    print(f"needs_review={counts['needs_review']}")
    print(f"pending={counts['pending']}")
    print(f"ignored={counts['ignored']}")
    return 0


def compare_results(
    *,
    results_path: Path,
    lead_state_path: Path,
    campaign_id: str | None = None,
) -> dict[str, object]:
    rows = _read_csv(results_path)
    state = _read_json(lead_state_path)
    contacts = state.get("contacts", {}) if isinstance(state.get("contacts"), dict) else {}

    compared: list[dict[str, str]] = []
    counts = {"matched": 0, "needs_review": 0, "pending": 0, "ignored": 0}
    requested_campaign = (campaign_id or "").strip()

    for row in rows:
        item = _compare_row(row, contacts, requested_campaign)
        counts[item["status"]] += 1
        compared.append(item)

    return {"processed": len(rows), "counts": counts, "rows": compared}


def _compare_row(row: dict[str, str], contacts: dict[str, object], requested_campaign: str) -> dict[str, str]:
    email = str(row.get("email") or "").strip().lower()
    template = str(row.get("template") or "").strip()
    gmail_status = str(row.get("status") or "").strip().lower()
    row_campaign = str(row.get("campaign_id") or "").strip()
    sent_at = str(row.get("sent_at") or "").strip()

    base = {
        "email": email,
        "template": template,
        "gmail_status": gmail_status or "pending",
        "campaign_id": row_campaign,
        "sent_at": sent_at,
        "customer_step": "",
        "status": "needs_review",
        "detail": "",
    }

    if requested_campaign and row_campaign and row_campaign != requested_campaign:
        base["status"] = "ignored"
        base["detail"] = "다른 발송 이름입니다."
        return base

    if not email or not template:
        base["detail"] = "이메일 또는 메일 이름이 비어 있습니다."
        return base

    lead = contacts.get(email)
    if isinstance(lead, dict):
        base["customer_step"] = str(lead.get("campaign_step") or "")
        sent_templates = {str(value) for value in lead.get("sent_templates", [])}
    else:
        sent_templates = set()

    if gmail_status in SUCCESS_STATUSES:
        if not isinstance(lead, dict):
            base["detail"] = "Gmail은 발송 완료지만 앱 고객 상태에 고객이 없습니다."
            return base
        if template not in sent_templates:
            base["detail"] = "Gmail은 발송 완료지만 앱 고객 상태에 이 메일 기록이 없습니다."
            return base
        base["status"] = "matched"
        base["detail"] = "Gmail 결과와 앱 고객 상태가 같습니다."
        return base

    if gmail_status in FAILED_STATUSES:
        if template in sent_templates:
            base["detail"] = "Gmail은 실패인데 앱 고객 상태에는 발송 완료로 보입니다."
            return base
        base["status"] = "matched"
        base["detail"] = "실패 결과와 앱 고객 상태가 충돌하지 않습니다."
        return base

    if gmail_status in PENDING_STATUSES:
        base["status"] = "pending"
        base["detail"] = "Gmail에서 아직 발송 전입니다."
        return base

    base["status"] = "ignored"
    base["detail"] = f"알 수 없는 Gmail 상태입니다: {gmail_status}"
    return base


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"contacts": {}}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {"contacts": {}}


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["status", "email", "gmail_status", "template", "campaign_id", "customer_step", "sent_at", "detail"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
