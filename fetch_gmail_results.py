from __future__ import annotations

import argparse
import csv
import io
import re
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Gmail Apps Script send results CSV from Google Sheets.")
    parser.add_argument("--source", required=True, help="Google Sheets URL or direct CSV export URL.")
    parser.add_argument("--output", default="outbox/gmail_send_queue.csv", help="Output CSV path.")
    parser.add_argument("--gid", help="Google Sheet tab gid. Defaults to gid in the URL or 0.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = fetch_results(source=args.source, output_path=Path(args.output), gid=args.gid)
    print(f"rows={summary['rows']}")
    print(f"output={summary['output_path']}")
    print(f"source_url={summary['source_url']}")
    return 0


def fetch_results(*, source: str, output_path: Path, gid: str | None = None) -> dict[str, object]:
    source_url = resolve_csv_url(source, gid=gid)
    request = urllib.request.Request(source_url, headers={"User-Agent": "Automailing/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

    text = _decode_csv_bytes(data)
    _ensure_csv(text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8", newline="")

    rows, columns = _count_rows(text)
    return {
        "rows": rows,
        "columns": columns,
        "output_path": str(output_path),
        "source_url": source_url,
    }


def resolve_csv_url(source: str, *, gid: str | None = None) -> str:
    value = source.strip()
    if not value:
        raise ValueError("Gmail 시트 링크가 비어 있습니다.")

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Gmail 시트 링크는 http 또는 https 주소여야 합니다.")

    if "docs.google.com" not in parsed.netloc or "/spreadsheets/d/" not in parsed.path:
        return value

    if parsed.path.endswith("/export") and "format=csv" in parsed.query:
        return value

    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        return value

    sheet_id = match.group(1)
    selected_gid = gid or _first_query_value(parsed.query, "gid") or _first_query_value(parsed.fragment, "gid") or "0"
    return f"https://docs.google.com/spreadsheets/d/{quote(sheet_id)}/export?format=csv&gid={quote(selected_gid)}"


def _first_query_value(query: str, key: str) -> str | None:
    values = parse_qs(query).get(key)
    if not values:
        return None
    return values[0]


def _decode_csv_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _ensure_csv(text: str) -> None:
    sample = text[:2048].lstrip().lower()
    if sample.startswith("<!doctype html") or sample.startswith("<html") or "<html" in sample:
        raise ValueError("CSV를 받지 못했습니다. Google Sheet 공유 또는 CSV 게시 설정을 확인하세요.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 헤더를 찾지 못했습니다.")
    required = {"email", "status", "template"}
    available = {str(column).strip().lower() for column in reader.fieldnames}
    if not required.issubset(available):
        raise ValueError("Gmail 결과 CSV에는 email, status, template 열이 필요합니다.")


def _count_rows(text: str) -> tuple[int, list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return len(rows), list(reader.fieldnames or [])


if __name__ == "__main__":
    raise SystemExit(main())
