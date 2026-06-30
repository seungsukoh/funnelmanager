from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from automailer.contacts import clean_row
from receive_webhook import append_csv, build_idempotency_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally sync Google Sheets published CSV or local CSV responses into inbox CSV."
    )
    parser.add_argument(
        "--source-csv",
        required=True,
        help="Local CSV path or https://... CSV URL. For Google Sheets, use published/export CSV URL.",
    )
    parser.add_argument("--output", default="inbox/form_responses.csv", help="Output inbox CSV.")
    parser.add_argument("--source-name", default="google_sheets", help="Source name stored in output rows.")
    parser.add_argument(
        "--response-id-column",
        help="Column that uniquely identifies a response. Falls back to row content hash.",
    )
    parser.add_argument(
        "--state-path",
        default="state/sync_state.json",
        help="JSON state file storing synced response keys.",
    )
    return parser.parse_args()


def load_csv_rows(source: str) -> list[dict[str, str]]:
    if _is_url(source):
        with urllib.request.urlopen(source, timeout=30) as response:
            text = response.read().decode("utf-8-sig")
        return _read_csv_text(text)

    path = Path(source)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [clean_row(row) for row in reader]


def sync_rows(
    *,
    rows: list[dict[str, str]],
    output_path: Path,
    state_path: Path,
    source_name: str,
    response_id_column: str | None,
) -> dict[str, int]:
    state = _load_state(state_path)
    seen = set(state.get("synced_keys", []))
    added = 0
    duplicates = 0

    for index, row in enumerate(rows, start=2):
        external_id = _external_id(row, response_id_column, index)
        output_row = {
            "source": source_name,
            "external_response_id": external_id,
            **row,
        }
        output_row["webhook_idempotency_key"] = build_idempotency_key(output_row)
        key = output_row["webhook_idempotency_key"]

        if key in seen:
            duplicates += 1
            continue

        result = append_csv(output_path, output_row)
        seen.add(key)
        if result.appended:
            added += 1
        else:
            duplicates += 1

    _save_state(state_path, {"synced_keys": sorted(seen)})
    return {"read": len(rows), "added": added, "duplicates": duplicates}


def _read_csv_text(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    reader = csv.DictReader(lines)
    return [clean_row(row) for row in reader]


def _external_id(row: dict[str, str], response_id_column: str | None, index: int) -> str:
    if response_id_column and row.get(response_id_column):
        return row[response_id_column]

    for candidate in ("Timestamp", "타임스탬프", "응답 ID", "response_id", "submitted_at"):
        if row.get(candidate):
            return row[candidate]

    comparable = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return f"row-{index}-{build_idempotency_key({'source': 'row', 'external_response_id': comparable})[:16]}"


def _load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"synced_keys": []}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _save_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def main() -> int:
    args = parse_args()
    rows = load_csv_rows(args.source_csv)
    summary = sync_rows(
        rows=rows,
        output_path=Path(args.output),
        state_path=Path(args.state_path),
        source_name=args.source_name,
        response_id_column=args.response_id_column,
    )
    print(f"read={summary['read']}")
    print(f"added={summary['added']}")
    print(f"duplicates={summary['duplicates']}")
    print(f"output={args.output}")
    print(f"state={args.state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
