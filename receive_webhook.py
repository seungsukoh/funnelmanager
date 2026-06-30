from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppendResult:
    appended: bool
    duplicate: bool
    idempotency_key: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Receive form webhook submissions and append them to CSV.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8080, help="Bind port.")
    parser.add_argument("--output", default="inbox/form_responses.csv", help="CSV output path.")
    parser.add_argument(
        "--token",
        default=os.getenv("AUTOMAILER_WEBHOOK_TOKEN", ""),
        help="Optional shared secret. Requests must send X-Automailer-Token.",
    )
    return parser.parse_args()


def flatten_payload(payload: dict[str, Any]) -> dict[str, str]:
    fields = payload.get("fields")
    if fields is None:
        fields = payload.get("namedValues")
    if fields is None:
        fields = payload

    row = {
        "source": str(payload.get("source", "webhook")),
        "external_response_id": str(payload.get("external_response_id", "")),
        "submitted_at": str(payload.get("submitted_at") or datetime.now(timezone.utc).isoformat()),
    }

    if isinstance(fields, dict):
        for key, value in fields.items():
            row[str(key)] = _string_value(value)

    row["webhook_idempotency_key"] = build_idempotency_key(row)
    return row


def build_idempotency_key(row: dict[str, str]) -> str:
    source = row.get("source", "").strip()
    external_id = row.get("external_response_id", "").strip()
    if external_id:
        raw_key = f"{source}|{external_id}"
    else:
        comparable = {
            key: value
            for key, value in sorted(row.items())
            if key not in {"submitted_at", "webhook_idempotency_key"}
        }
        raw_key = json.dumps(comparable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def append_csv(path: Path, row: dict[str, str]) -> AppendResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    existing_keys: set[str] = set()

    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = list(reader.fieldnames or [])
            existing_rows = list(reader)
            existing_keys = {
                existing.get("webhook_idempotency_key", "")
                for existing in existing_rows
                if existing.get("webhook_idempotency_key")
            }

    key = row.get("webhook_idempotency_key") or build_idempotency_key(row)
    row["webhook_idempotency_key"] = key
    if key in existing_keys:
        return AppendResult(appended=False, duplicate=True, idempotency_key=key)

    for key in row.keys():
        if key not in fieldnames:
            fieldnames.append(key)

    existing_rows.append(row)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
    return AppendResult(appended=True, duplicate=False, idempotency_key=row["webhook_idempotency_key"])


def make_handler(output_path: Path, token: str):
    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/webhooks/form-response":
                self._json_response(404, {"ok": False, "error": "not found"})
                return

            if token and self.headers.get("X-Automailer-Token") != token:
                self._json_response(401, {"ok": False, "error": "unauthorized"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("payload must be a JSON object")
                row = flatten_payload(payload)
                result = append_csv(output_path, row)
            except Exception as error:
                self._json_response(400, {"ok": False, "error": str(error)})
                return

            status = 200 if result.duplicate else 202
            self._json_response(
                status,
                {
                    "ok": True,
                    "duplicate": result.duplicate,
                    "idempotency_key": result.idempotency_key,
                    "output": str(output_path),
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _json_response(self, status: int, payload: dict[str, object]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return WebhookHandler


def _string_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    handler = make_handler(output_path, args.token)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Listening on http://{args.host}:{args.port}/webhooks/form-response")
    print(f"Writing responses to {output_path}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
