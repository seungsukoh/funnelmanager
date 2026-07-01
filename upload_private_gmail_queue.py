from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from pathlib import Path
from urllib.parse import quote

from fetch_private_gmail_results import (
    DEFAULT_SHEET_NAME,
    _count_rows,
    _ensure_gmail_results_csv,
    _quote_sheet_name,
    _read_json_response,
    _valid_access_token,
    spreadsheet_id_from_source,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload Gmail send queue CSV to a private Google Sheet.")
    parser.add_argument("--source", required=True, help="Google Sheet URL or spreadsheet id.")
    parser.add_argument("--input", default="outbox/gmail_send_queue.csv", help="Local Gmail queue CSV path.")
    parser.add_argument("--credentials", default="config/google_oauth_client.json", help="OAuth client JSON path.")
    parser.add_argument("--token", default="state/google_sheets_token.json", help="Saved OAuth token JSON path.")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET_NAME, help="Sheet tab name.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = upload_queue(
        source=args.source,
        input_path=Path(args.input),
        credentials_path=Path(args.credentials),
        token_path=Path(args.token),
        sheet_name=args.sheet_name,
    )
    print(f"rows={summary['rows']}")
    print(f"spreadsheet_id={summary['spreadsheet_id']}")
    print(f"sheet_name={summary['sheet_name']}")
    print(f"updated_rows={summary['updated_rows']}")
    return 0


def upload_queue(
    *,
    source: str,
    input_path: Path,
    credentials_path: Path,
    token_path: Path,
    sheet_name: str = DEFAULT_SHEET_NAME,
) -> dict[str, object]:
    if not input_path.exists():
        raise ValueError(f"Gmail 발송 준비 파일을 찾지 못했습니다: {input_path}")

    text = input_path.read_text(encoding="utf-8-sig")
    _ensure_gmail_results_csv(text)
    rows, columns = _count_rows(text)
    values = _csv_values(text)
    spreadsheet_id = spreadsheet_id_from_source(source)
    access_token = _valid_access_token(credentials_path=credentials_path, token_path=token_path)
    a1_range = _quote_sheet_name(sheet_name)

    _clear_values(spreadsheet_id=spreadsheet_id, a1_range=a1_range, access_token=access_token)
    update_result = _update_values(
        spreadsheet_id=spreadsheet_id,
        a1_range=a1_range,
        values=values,
        access_token=access_token,
    )
    return {
        "rows": rows,
        "columns": columns,
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "updated_rows": update_result.get("updatedRows", 0),
        "updated_cells": update_result.get("updatedCells", 0),
    }


def _csv_values(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    values = [[str(value) for value in row] for row in reader]
    if not values:
        raise ValueError("Gmail 발송 준비 파일이 비어 있습니다.")
    return values


def _clear_values(*, spreadsheet_id: str, a1_range: str, access_token: str) -> None:
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}/values/"
        f"{quote(a1_range, safe='')}:clear"
    )
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    _read_json_response(request)


def _update_values(
    *,
    spreadsheet_id: str,
    a1_range: str,
    values: list[list[str]],
    access_token: str,
) -> dict[str, object]:
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}/values/"
        f"{quote(a1_range, safe='')}?valueInputOption=RAW"
    )
    payload = json.dumps({"majorDimension": "ROWS", "values": values}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="PUT",
    )
    return _read_json_response(request)


if __name__ == "__main__":
    raise SystemExit(main())
