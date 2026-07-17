from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from automailer.campaign import CampaignConfig, run_campaign
from automailer.planner import PlanConfig, build_send_queue
from automailer.word_template import load_word_template_bytes
from compare_gmail_results import compare_results as compare_gmail_results
from export_gmail_queue import export_queue as export_gmail_queue
from fetch_gmail_results import fetch_results as fetch_gmail_results
from fetch_private_gmail_results import (
    build_authorization_url as build_google_authorization_url,
    complete_authorization as complete_google_authorization,
    fetch_private_results as fetch_private_gmail_results,
)
from import_gmail_results import import_results as import_gmail_results
from upload_private_gmail_queue import upload_queue as upload_private_gmail_queue


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "email_templates"
GOOGLE_OAUTH_STATE_PATH = "state/google_oauth_state.json"


DEFAULTS = {
    "contacts": "samples/funnel_contacts.csv",
    "funnel_config": "samples/drip_config.json",
    "lead_state": "samples/lead_state_drip.json",
    "send_history": "state/send_history.jsonl",
    "timeline": "outbox/web_dashboard_timeline.jsonl",
    "campaign_id": "web-dashboard-demo",
    "queue_output": "outbox/web_dashboard_queue.csv",
    "approval_output": "outbox/web_dashboard_approval.csv",
    "gmail_source": "",
    "gmail_sheet_name": "GmailQueue",
    "gmail_results": "outbox/gmail_send_queue.csv",
    "google_credentials": "config/google_oauth_client.json",
    "google_token": "state/google_sheets_token.json",
    "outbox": "outbox",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Automailing local admin dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def make_handler():
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._html_response(FRIENDLY_DASHBOARD_HTML)
                return
            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if parsed.path == "/api/defaults":
                self._json_response(200, DEFAULTS)
                return
            if parsed.path == "/api/queue":
                query = parse_qs(parsed.query)
                path = _safe_path(query.get("path", [DEFAULTS["queue_output"]])[0])
                self._json_response(200, {"rows": _read_csv(path), "path": _relative(path)})
                return
            if parsed.path == "/api/timeline":
                query = parse_qs(parsed.query)
                path = _safe_path(query.get("path", [DEFAULTS["timeline"]])[0])
                email = query.get("email", [""])[0].strip()
                self._json_response(200, {"rows": _read_jsonl(path, email=email), "path": _relative(path)})
                return
            if parsed.path == "/api/lead-state":
                query = parse_qs(parsed.query)
                path = _safe_path(query.get("path", [DEFAULTS["lead_state"]])[0])
                self._json_response(200, {"state": _read_json(path), "path": _relative(path)})
                return
            if parsed.path == "/api/message-flow":
                query = parse_qs(parsed.query)
                payload = {key: query[key][0] for key in DEFAULTS if key in query and query[key]}
                result = _handle_message_flow(payload)
                self._json_response(200, result)
                return
            if parsed.path == "/api/approval":
                query = parse_qs(parsed.query)
                path = _safe_path(query.get("path", [DEFAULTS["approval_output"]])[0])
                rows = _read_csv(path)
                self._json_response(200, {"rows": rows, "path": _relative(path), "counts": _count_approval(rows)})
                return
            if parsed.path == "/api/progress":
                self._json_response(200, {"markdown": _read_text(BASE_DIR / "docs" / "progress.md")})
                return
            if parsed.path == "/oauth/google/callback":
                html_result = _handle_google_oauth_callback(parse_qs(parsed.query))
                self._html_response(html_result)
                return
            if parsed.path == "/file":
                query = parse_qs(parsed.query)
                path = _safe_path(query.get("path", [""])[0])
                self._file_response(path)
                return
            self._json_response(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self._read_json_body()
                if parsed.path == "/api/plan":
                    result = _handle_plan(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/dry-run":
                    result = _handle_dry_run(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/message-flow/save":
                    result = _handle_save_message_flow(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/word-template/import":
                    result = _handle_import_word_template(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/approval/prepare":
                    result = _handle_prepare_approval(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/approval/save":
                    result = _handle_save_approval(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/import":
                    result = _handle_import_gmail_results(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/export":
                    result = _handle_export_gmail_queue(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/fetch":
                    result = _handle_fetch_gmail_results(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/fetch-private":
                    result = _handle_fetch_private_gmail_results(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/upload-private":
                    result = _handle_upload_private_gmail_queue(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/compare":
                    result = _handle_compare_gmail_results(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/google/auth-url":
                    result = _handle_google_auth_url(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/google/status":
                    result = _handle_google_setup_status(payload)
                    self._json_response(200, result)
                    return
                self._json_response(404, {"ok": False, "error": "not found"})
            except Exception as error:
                self._json_response(400, {"ok": False, "error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object.")
            return payload

        def _html_response(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json_response(self, status: int, payload: dict[str, object]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _file_response(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self._json_response(404, {"ok": False, "error": "file not found"})
                return
            suffix = path.suffix.lower()
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".csv": "text/csv; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".jsonl": "application/x-ndjson; charset=utf-8",
                ".txt": "text/plain; charset=utf-8",
                ".md": "text/markdown; charset=utf-8",
            }.get(suffix, "text/plain; charset=utf-8")
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return DashboardHandler


def _handle_plan(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    output = build_send_queue(
        PlanConfig(
            contacts_path=_safe_path(config["contacts"]),
            funnel_config_path=_safe_path(config["funnel_config"]),
            campaign_id=config["campaign_id"],
            output_path=_safe_path(config["queue_output"]),
            suppression_list_path=None,
            db_path=_safe_path(config["send_history"]),
            lead_state_path=_safe_path(config["lead_state"]),
            email_column=None,
            limit=None,
        )
    )
    rows = _read_csv(output)
    return {
        "ok": True,
        "queue_path": _relative(output),
        "rows": rows,
        "counts": _count_statuses(rows),
    }


def _handle_dry_run(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = run_campaign(
        CampaignConfig(
            contacts_path=_safe_path(config["contacts"]),
            funnel_config_path=_safe_path(config["funnel_config"]),
            template_dir=TEMPLATE_DIR,
            template_name=None,
            word_template_path=None,
            subject_template=None,
            template_column=None,
            campaign_id=config["campaign_id"],
            email_column=None,
            name_column=None,
            suppression_list_path=None,
            db_path=_safe_path(config["send_history"]),
            lead_state_path=_safe_path(config["lead_state"]),
            timeline_path=_safe_path(config["timeline"]),
            outbox_dir=_safe_path(config["outbox"]),
            limit=None,
            test_to=None,
            allow_duplicates=False,
            provider="dryrun",
            outlook_display=False,
            real_send=False,
        )
    )
    report_path = _safe_path(summary.report_path) if summary.report_path else None
    report_rows = _read_csv(report_path) if report_path else []
    return {
        "ok": summary.failed == 0,
        "summary": {
            "processed": summary.processed,
            "sent": summary.sent,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "report_path": summary.report_path,
            "errors": summary.errors,
        },
        "report_rows": report_rows,
    }


def _handle_message_flow(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    funnel_path = _safe_path(config["funnel_config"])
    funnel = _read_json(funnel_path)
    return {
        "ok": True,
        "path": _relative(funnel_path),
        "steps": _message_flow_steps(funnel),
        "templates": _available_templates(),
    }


def _handle_save_message_flow(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    funnel_path = _safe_path(config["funnel_config"])
    funnel = _read_json(funnel_path)
    saved_steps = payload.get("steps")
    if not isinstance(saved_steps, list):
        raise ValueError("steps must be a list.")

    configured_steps = funnel.get("steps")
    if not isinstance(configured_steps, list):
        raise ValueError("funnel config does not have a steps list.")

    steps_by_id = {
        str(step.get("id") or step.get("name") or "").strip(): step
        for step in configured_steps
        if isinstance(step, dict)
    }
    seen_templates: dict[str, tuple[str, str]] = {}
    config_changed = False

    for raw_step in saved_steps:
        if not isinstance(raw_step, dict):
            continue
        step_id = str(raw_step.get("id") or "").strip()
        if not step_id or step_id not in steps_by_id:
            continue

        template_name = _safe_template_name(raw_step.get("template"))
        subject = str(raw_step.get("subject") or "").strip()
        text_body = str(raw_step.get("text_body") or "").replace("\r\n", "\n")
        if not subject:
            raise ValueError(f"{step_id}: subject is required.")
        if not text_body.strip():
            raise ValueError(f"{step_id}: body is required.")

        template_signature = (subject, text_body)
        if template_name in seen_templates and seen_templates[template_name] != template_signature:
            raise ValueError(f"{template_name}: same mail name is used with different content.")
        seen_templates[template_name] = template_signature

        step = steps_by_id[step_id]
        current_template = str(step.get("template") or "").strip()
        if current_template != template_name:
            step["template"] = template_name
            config_changed = True

        current_template_content = _template_payload(template_name)
        if (
            current_template_content["subject"].strip() != subject
            or current_template_content["text_body"].replace("\r\n", "\n").strip() != text_body.strip()
        ):
            _write_template(template_name, subject, text_body)

        next_step = str(raw_step.get("next_step") or "").strip()
        if next_step:
            if step.get("next_step") != next_step:
                step["next_step"] = next_step
                config_changed = True
        elif "next_step" in step:
            step.pop("next_step", None)
            config_changed = True

        schedule_mode = str(raw_step.get("schedule_mode") or "").strip()
        if schedule_mode == "days":
            schedule_mode = "previous_days"
        if schedule_mode not in {"first_days", "previous_days", "date", "none"}:
            schedule_mode = ""

        delay = str(raw_step.get("next_send_after_days") or "").strip()
        send_date = str(raw_step.get("next_send_at") or "").strip()
        send_time = _normalise_send_time(raw_step.get("next_send_time"))

        if schedule_mode in {"first_days", "previous_days"} or delay:
            if not delay:
                raise ValueError(f"{step_id}: delay days are required.")
            delay_days = int(delay)
            if delay_days < 0:
                raise ValueError(f"{step_id}: delay days cannot be negative.")
            if step.get("next_send_after_days") != delay_days:
                step["next_send_after_days"] = delay_days
                config_changed = True
            if "next_send_at" in step:
                step.pop("next_send_at", None)
                config_changed = True
            if send_time:
                if step.get("next_send_time") != send_time:
                    step["next_send_time"] = send_time
                    config_changed = True
            elif "next_send_time" in step:
                step.pop("next_send_time", None)
                config_changed = True
            if schedule_mode and step.get("schedule_mode") != schedule_mode:
                step["schedule_mode"] = schedule_mode
                config_changed = True
        elif schedule_mode == "date" or send_date:
            if step.get("next_send_at") != send_date:
                step["next_send_at"] = send_date
                config_changed = True
            if "next_send_after_days" in step:
                step.pop("next_send_after_days", None)
                config_changed = True
            if send_time:
                if step.get("next_send_time") != send_time:
                    step["next_send_time"] = send_time
                    config_changed = True
            elif "next_send_time" in step:
                step.pop("next_send_time", None)
                config_changed = True
            if step.get("schedule_mode") != "date":
                step["schedule_mode"] = "date"
                config_changed = True
        else:
            if "next_send_after_days" in step:
                step.pop("next_send_after_days", None)
                config_changed = True
            if "next_send_at" in step:
                step.pop("next_send_at", None)
                config_changed = True
            if "next_send_time" in step:
                step.pop("next_send_time", None)
                config_changed = True
            if "schedule_mode" in step:
                step.pop("schedule_mode", None)
                config_changed = True

    if config_changed:
        funnel_path.write_text(json.dumps(funnel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _handle_message_flow(config)


def _handle_import_word_template(payload: dict[str, object]) -> dict[str, object]:
    filename = str(payload.get("filename") or "").strip()
    encoded = str(payload.get("content_base64") or "").strip()
    if not filename:
        raise ValueError("filename is required.")
    if not encoded:
        raise ValueError("word file content is required.")

    content = base64.b64decode(encoded, validate=True)
    if len(content) > 5_000_000:
        raise ValueError("Word file is too large. Use a file under 5 MB.")

    template = load_word_template_bytes(filename, content)
    return {
        "ok": True,
        "filename": filename,
        "subject": template.subject,
        "text_body": template.text_body,
        "html_body": template.html_body,
    }


def _handle_prepare_approval(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    plan = _handle_plan(config)
    approval_path = _safe_path(config["approval_output"])
    previous = {
        _approval_key(row): str(row.get("approved") or "").strip().lower()
        for row in _read_csv(approval_path)
    }
    approval_rows = [
        _approval_row(row, approved=previous.get(_approval_key(row), "no"))
        for row in plan["rows"]
        if row.get("status") == "ready"
    ]
    _write_approval(approval_path, approval_rows)
    return {
        "ok": True,
        "path": _relative(approval_path),
        "rows": approval_rows,
        "counts": _count_approval(approval_rows),
        "queue_counts": plan["counts"],
    }


def _handle_save_approval(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    approval_path = _safe_path(config["approval_output"])
    updates = payload.get("rows")
    if not isinstance(updates, list):
        raise ValueError("rows must be a list.")

    approval_rows = _read_csv(approval_path)
    approved_by_key = {
        _approval_key(row): "yes" if row.get("approved") in (True, "true", "yes", "1", "on") else "no"
        for row in updates
        if isinstance(row, dict)
    }
    for row in approval_rows:
        key = _approval_key(row)
        if key in approved_by_key:
            row["approved"] = approved_by_key[key]

    _write_approval(approval_path, approval_rows)
    return {
        "ok": True,
        "path": _relative(approval_path),
        "rows": approval_rows,
        "counts": _count_approval(approval_rows),
    }


def _handle_import_gmail_results(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = import_gmail_results(
        results_path=_safe_path(config["gmail_results"]),
        funnel_config_path=_safe_path(config["funnel_config"]),
        lead_state_path=_safe_path(config["lead_state"]),
        db_path=_safe_path(config["send_history"]),
        timeline_path=_safe_path(config["timeline"]),
        default_campaign_id=config["campaign_id"],
    )
    return {"ok": True, "summary": summary}


def _handle_export_gmail_queue(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = export_gmail_queue(
        contacts_path=_safe_path(config["contacts"]),
        funnel_config_path=_safe_path(config["funnel_config"]),
        campaign_id=config["campaign_id"],
        approval_path=_safe_path(config["approval_output"]),
        output_path=_safe_path(config["gmail_results"]),
        template_dir=TEMPLATE_DIR,
        lead_state_path=_safe_path(config["lead_state"]),
        db_path=_safe_path(config["send_history"]),
    )
    return {"ok": True, "summary": summary}


def _handle_fetch_gmail_results(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = fetch_gmail_results(
        source=config["gmail_source"],
        output_path=_safe_path(config["gmail_results"]),
    )
    return {"ok": True, "summary": summary}


def _handle_fetch_private_gmail_results(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = fetch_private_gmail_results(
        source=config["gmail_source"],
        output_path=_safe_path(config["gmail_results"]),
        credentials_path=_safe_path(config["google_credentials"]),
        token_path=_safe_path(config["google_token"]),
        sheet_name=config["gmail_sheet_name"],
    )
    return {"ok": True, "summary": summary}


def _handle_upload_private_gmail_queue(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = upload_private_gmail_queue(
        source=config["gmail_source"],
        input_path=_safe_path(config["gmail_results"]),
        credentials_path=_safe_path(config["google_credentials"]),
        token_path=_safe_path(config["google_token"]),
        sheet_name=config["gmail_sheet_name"],
    )
    return {"ok": True, "summary": summary}


def _handle_compare_gmail_results(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    result = compare_gmail_results(
        results_path=_safe_path(config["gmail_results"]),
        lead_state_path=_safe_path(config["lead_state"]),
        campaign_id=config["campaign_id"],
    )
    return {"ok": True, **result}


def _handle_google_auth_url(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    redirect_uri = str(payload.get("redirect_uri") or "").strip()
    if not redirect_uri:
        raise ValueError("redirect_uri is required.")
    result = build_google_authorization_url(
        credentials_path=_safe_path(config["google_credentials"]),
        token_path=_safe_path(config["google_token"]),
        state_path=_safe_path(GOOGLE_OAUTH_STATE_PATH),
        redirect_uri=redirect_uri,
    )
    return {"ok": True, **result}


def _handle_google_setup_status(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    credentials_path = _safe_path(config["google_credentials"])
    token_path = _safe_path(config["google_token"])
    source = config["gmail_source"].strip()
    sheet_name = config["gmail_sheet_name"].strip() or "GmailQueue"

    credential = _google_credential_status(credentials_path)
    token = _google_token_status(token_path)
    steps = [
        {
            "id": "cloud",
            "label": "Google Cloud 설정",
            "done": credential["valid"],
            "detail": credential["detail"],
        },
        {
            "id": "sheet",
            "label": "비공개 시트 입력",
            "done": bool(source),
            "detail": "Gmail 시트 링크가 입력됐습니다." if source else "Gmail 시트 링크를 입력하세요.",
        },
        {
            "id": "connect",
            "label": "Google 연결",
            "done": token["valid"],
            "detail": token["detail"],
        },
        {
            "id": "fetch",
            "label": "결과 가져오기 준비",
            "done": credential["valid"] and bool(source) and token["valid"],
            "detail": "비공개 시트 가져오기를 실행할 수 있습니다."
            if credential["valid"] and bool(source) and token["valid"]
            else "위 항목을 완료하면 비공개 시트 가져오기를 실행할 수 있습니다.",
        },
    ]
    return {
        "ok": True,
        "credentials_path": _relative(credentials_path),
        "token_path": _relative(token_path),
        "redirect_uri": "http://127.0.0.1:8765/oauth/google/callback",
        "sheet_name": sheet_name,
        "steps": steps,
    }


def _google_credential_status(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "valid": False,
            "detail": f"{_relative(path)} 파일이 필요합니다.",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"valid": False, "detail": "Google 인증 파일이 JSON 형식이 아닙니다."}

    raw = data.get("installed") or data.get("web") or data
    client_id = str(raw.get("client_id") or "").strip() if isinstance(raw, dict) else ""
    client_secret = str(raw.get("client_secret") or "").strip() if isinstance(raw, dict) else ""
    if not client_id or not client_secret:
        return {"valid": False, "detail": "Google 인증 파일에 client_id/client_secret이 없습니다."}
    if "YOUR_GOOGLE" in client_id or "YOUR_GOOGLE" in client_secret:
        return {"valid": False, "detail": "예시 파일이 아니라 Google Cloud에서 받은 JSON을 넣어야 합니다."}
    return {"valid": True, "detail": "Google 인증 파일이 준비됐습니다."}


def _google_token_status(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "valid": False,
            "detail": "아직 Google 연결을 완료하지 않았습니다.",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"valid": False, "detail": "Google 토큰 파일이 JSON 형식이 아닙니다."}
    if not isinstance(data, dict) or not data.get("refresh_token"):
        return {"valid": False, "detail": "Google 토큰에 refresh_token이 없습니다. Google 연결을 다시 실행하세요."}
    scope = str(data.get("scope") or "")
    if scope and "https://www.googleapis.com/auth/spreadsheets" not in scope.split():
        return {"valid": False, "detail": "Google Sheet 업로드 권한이 없습니다. Google 연결을 다시 실행하세요."}
    return {"valid": True, "detail": "Google 연결이 완료됐습니다."}


def _handle_google_oauth_callback(query: dict[str, list[str]]) -> str:
    error = query.get("error", [""])[0]
    if error:
        return _google_oauth_result_html(False, f"Google 연결 실패: {html.escape(error)}")

    try:
        code = query.get("code", [""])[0]
        state = query.get("state", [""])[0]
        result = complete_google_authorization(
            state_path=_safe_path(GOOGLE_OAUTH_STATE_PATH),
            code=code,
            state=state,
        )
        return _google_oauth_result_html(True, f"Google 연결 완료: {html.escape(result['token_path'])}")
    except Exception as exc:
        return _google_oauth_result_html(False, html.escape(str(exc)))


def _google_oauth_result_html(ok: bool, message: str) -> str:
    title = "Google 연결 완료" if ok else "Google 연결 실패"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Noto Sans KR", sans-serif; background: #f4f6f8; color: #18212f; }}
    main {{ width: min(560px, calc(100% - 32px)); margin: 80px auto; padding: 24px; background: #fff; border: 1px solid #d7dde5; border-radius: 8px; }}
    h1 {{ margin: 0 0 10px; font-size: 22px; }}
    p {{ line-height: 1.6; color: #617086; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>{message}</p>
    <p>이 창을 닫고 자동 메일 발송 화면에서 비공개 시트 가져오기를 누르세요.</p>
  </main>
</body>
</html>"""


def _request_config(payload: dict[str, object]) -> dict[str, str]:
    config = dict(DEFAULTS)
    for key in DEFAULTS:
        value = payload.get(key)
        if value is not None and str(value).strip():
            config[key] = str(value).strip()
    return config


def _safe_path(value: str | Path | None) -> Path:
    if value is None or str(value).strip() == "":
        raise ValueError("path is required")
    raw = Path(str(value))
    path = raw if raw.is_absolute() else BASE_DIR / raw
    resolved = path.resolve()
    if not _is_relative_to(resolved, BASE_DIR):
        raise ValueError(f"path escapes workspace: {value}")
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [dict(row) for row in reader]


def _read_jsonl(path: Path, *, email: str = "") -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            if email and row.get("email") != email:
                continue
            rows.append(row)
    return rows[-100:]


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"contacts": {}}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _count_statuses(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _approval_row(row: dict[str, str], *, approved: str) -> dict[str, str]:
    return {
        "approved": "yes" if approved in {"yes", "true", "1", "on"} else "no",
        "email": row.get("email", ""),
        "template": row.get("template", ""),
        "rule": row.get("rule", ""),
        "campaign_step": row.get("campaign_step", ""),
        "next_send_at": row.get("next_send_at", ""),
        "detail": row.get("detail", ""),
    }


def _approval_key(row: dict[str, object]) -> str:
    return f"{str(row.get('email') or '').strip().lower()}|{str(row.get('template') or '').strip()}"


def _write_approval(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["approved", "email", "template", "rule", "campaign_step", "next_send_at", "detail"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _count_approval(rows: list[dict[str, str]]) -> dict[str, int]:
    approved = sum(1 for row in rows if str(row.get("approved") or "").strip().lower() == "yes")
    return {"ready": len(rows), "approved": approved, "waiting": len(rows) - approved}


def _message_flow_steps(funnel: dict[str, object]) -> list[dict[str, object]]:
    raw_steps = funnel.get("steps", [])
    if not isinstance(raw_steps, list):
        return []

    steps: list[dict[str, object]] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            continue
        template_name = str(raw_step.get("template") or "").strip()
        template = _template_payload(template_name) if template_name else _empty_template("")
        step_id = str(raw_step.get("id") or raw_step.get("name") or f"step_{index}").strip()
        steps.append(
            {
                "id": step_id,
                "order": index,
                "stage_label": _stage_label(raw_step, index),
                "priority": raw_step.get("priority", ""),
                "audience": _describe_conditions(raw_step.get("conditions")),
                "template": template_name,
                "subject": template["subject"],
                "text_body": template["text_body"],
                "schedule_mode": raw_step.get("schedule_mode", ""),
                "next_send_after_days": raw_step.get("next_send_after_days", ""),
                "next_send_at": raw_step.get("next_send_at", ""),
                "next_send_time": raw_step.get("next_send_time", ""),
                "next_step": raw_step.get("next_step") or raw_step.get("set_step") or "",
                "status_after": raw_step.get("set_status", ""),
                "send_after_label": _send_after_label(raw_step),
            }
        )
    return steps


def _available_templates() -> list[dict[str, str]]:
    names = set()
    if TEMPLATE_DIR.exists():
        for path in TEMPLATE_DIR.glob("*.subject.txt"):
            names.add(path.name.removesuffix(".subject.txt"))
        for path in TEMPLATE_DIR.glob("*.html"):
            names.add(path.stem)
        for path in TEMPLATE_DIR.glob("*.txt"):
            if not path.name.endswith(".subject.txt"):
                names.add(path.stem)
    return [_template_payload(name) for name in sorted(names)]


def _template_payload(name: str) -> dict[str, str]:
    safe_name = _safe_template_name(name)
    return {
        "name": safe_name,
        "subject": _read_text(TEMPLATE_DIR / f"{safe_name}.subject.txt").strip(),
        "text_body": _read_text(TEMPLATE_DIR / f"{safe_name}.txt"),
        "html_body": _read_text(TEMPLATE_DIR / f"{safe_name}.html"),
    }


def _empty_template(name: str) -> dict[str, str]:
    return {"name": name, "subject": "", "text_body": "", "html_body": ""}


def _safe_template_name(value: object) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("mail name is required.")
    if len(name) > 80:
        raise ValueError("mail name is too long.")
    if not all(character.isalnum() or character in "_-" for character in name):
        raise ValueError("mail name can contain only letters, numbers, _ and -.")
    return name


def _write_template(name: str, subject: str, text_body: str) -> None:
    safe_name = _safe_template_name(name)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    (TEMPLATE_DIR / f"{safe_name}.subject.txt").write_text(subject.strip() + "\n", encoding="utf-8")
    normalised_text = text_body.replace("\r\n", "\n").strip() + "\n"
    (TEMPLATE_DIR / f"{safe_name}.txt").write_text(normalised_text, encoding="utf-8")
    (TEMPLATE_DIR / f"{safe_name}.html").write_text(_text_to_html(normalised_text), encoding="utf-8")


def _text_to_html(text_body: str) -> str:
    paragraphs = [part.strip() for part in text_body.replace("\r\n", "\n").split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [text_body.strip()]
    body = "\n".join(f"  <p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)
    return f"<!doctype html>\n<html lang=\"ko\">\n<body>\n{body}\n</body>\n</html>\n"


def _describe_conditions(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "전체 고객"
    parts = [_describe_condition(condition) for condition in value if isinstance(condition, dict)]
    visible_parts = [part for part in parts if part]
    return ", ".join(visible_parts) if visible_parts else "전체 고객"


def _stage_label(step: dict[str, object], index: int) -> str:
    conditions = step.get("conditions")
    stage_id = str(step.get("id") or step.get("name") or "").strip()
    attendance = _condition_value(conditions, "attendance", "equals")
    campaign_step = _condition_value(conditions, "campaign_step", "equals")
    is_first_touch = _has_condition(conditions, "campaign_step", "is_empty")

    if attendance and is_first_touch:
        return f"{attendance} 고객 첫 메일"
    if campaign_step:
        return f"{_humanise_identifier(campaign_step)} 단계 메일"
    if stage_id:
        return _humanise_identifier(stage_id)
    return f"단계 {index}"


def _condition_value(conditions: object, field: str, operator: str) -> str:
    if not isinstance(conditions, list):
        return ""
    for condition in conditions:
        if (
            isinstance(condition, dict)
            and str(condition.get("field") or "") == field
            and str(condition.get("operator") or "equals") == operator
        ):
            return str(condition.get("value") or "").strip()
    return ""


def _has_condition(conditions: object, field: str, operator: str) -> bool:
    if not isinstance(conditions, list):
        return False
    return any(
        isinstance(condition, dict)
        and str(condition.get("field") or "") == field
        and str(condition.get("operator") or "equals") == operator
        for condition in conditions
    )


def _humanise_identifier(value: str) -> str:
    cleaned = value.replace("_", " ").replace("-", " ").strip()
    labels = {
        "attended first touch": "참석 고객 첫 메일",
        "attended second touch": "참석 고객 두 번째 메일",
        "attended complete": "참석 고객 완료",
        "no show first touch": "미참석 고객 첫 메일",
        "no show second touch": "미참석 고객 두 번째 메일",
    }
    return labels.get(cleaned.lower(), cleaned or value)


def _describe_condition(condition: dict[str, object]) -> str:
    field = str(condition.get("field") or "")
    operator = str(condition.get("operator") or "equals")
    expected = str(condition.get("value") or "")

    if field == "campaign_step" and operator == "is_empty":
        return "첫 연락 대상"
    if field == "campaign_step" and operator == "equals":
        return f"{expected} 단계 고객"
    if field == "attendance" and operator == "equals":
        return f"{expected} 고객"
    if field == "lead_tags" and operator == "contains":
        return f"{expected} 분류 고객"

    field_label = {
        "email": "이메일",
        "name": "이름",
        "event_name": "행사",
        "marketing_consent": "마케팅 동의",
        "unsubscribed": "수신 거부",
        "lead_status": "고객 상태",
    }.get(field, field or "항목")
    operator_label = {
        "equals": "같음",
        "not_equals": "다름",
        "contains": "포함",
        "not_contains": "포함 안 함",
        "is_empty": "비어 있음",
        "is_not_empty": "있음",
        "truthy": "예",
        "falsy": "아니오",
    }.get(operator, operator)
    return f"{field_label} {operator_label} {expected}".strip()


def _send_after_label(step: dict[str, object]) -> str:
    mode = str(step.get("schedule_mode") or "").strip()
    time_value = _normalise_send_time(step.get("next_send_time")) or "09:00"
    if mode == "date" or step.get("next_send_at"):
        date_value = str(step.get("next_send_at") or "날짜 미정").strip()
        return f"{date_value} {time_value}에 다음 메일"

    value = step.get("next_send_after_days")
    if value not in (None, ""):
        base = "첫 메일" if mode == "first_days" else "이 단계 메일"
        return f"{base} 발송 후 {value}일 뒤 {time_value}에 다음 메일"
    if step.get("next_step") or step.get("set_step"):
        return "다음 단계로 이동"
    return "후속 메일 없음"


def _normalise_send_time(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = raw.split(":")
    if len(parts) < 2:
        raise ValueError("send time must be HH:MM.")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("send time must be between 00:00 and 23:59.")
    return f"{hour:02d}:{minute:02d}"


FRIENDLY_DASHBOARD_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>자동 메일 발송</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --line: #d7dde5;
      --text: #18212f;
      --muted: #617086;
      --blue: #1769aa;
      --green: #1f7a4d;
      --red: #b42318;
      --amber: #9a6700;
      --soft: #f9fafb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, "Noto Sans KR", sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }
    .wrap {
      width: min(1320px, calc(100% - 32px));
      margin: 0 auto;
      padding: 22px 0 34px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 16px;
    }
    h1 {
      margin: 0 0 5px;
      font-size: 26px;
    }
    .sub {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }
    button {
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
      padding: 9px 12px;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--blue);
      background: var(--blue);
      color: #fff;
    }
    button:disabled {
      opacity: .62;
      cursor: not-allowed;
    }
    .workflow {
      margin-bottom: 14px;
    }
    .workflow-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      margin-bottom: 8px;
    }
    .workflow-head h2 {
      margin: 0;
      font-size: 18px;
    }
    .workflow-head span {
      color: var(--muted);
      line-height: 1.45;
    }
    .workflow-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }
    .work-card {
      min-height: 184px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 8px;
    }
    .work-card.next {
      border-color: var(--blue);
      box-shadow: 0 0 0 2px rgba(23, 105, 170, .12);
    }
    .work-number {
      width: 26px;
      height: 26px;
      display: inline-grid;
      place-items: center;
      border-radius: 999px;
      background: #e7eef7;
      color: var(--blue);
      font-weight: 700;
      font-size: 12px;
    }
    .work-card h3 {
      margin: 0;
      font-size: 15px;
    }
    .work-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .work-status {
      min-height: 36px;
      color: var(--text);
      font-weight: 700;
      line-height: 1.45;
    }
    .work-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .work-actions button {
      min-height: 40px;
      padding: 7px 9px;
      font-size: 13px;
    }
    .steps, .cards {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .step, .card, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .step {
      min-height: 82px;
      padding: 13px;
    }
    .step strong {
      display: block;
      margin-bottom: 7px;
      font-size: 15px;
    }
    .step span, .card span, .muted {
      color: var(--muted);
      line-height: 1.45;
    }
    .card {
      min-height: 82px;
      padding: 14px;
    }
    .card span {
      display: block;
      margin-bottom: 8px;
      font-size: 12px;
    }
    .card strong {
      font-size: 28px;
    }
    .layout {
      display: grid;
      grid-template-columns: 350px minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    .panel h2 {
      margin: 0;
      padding: 14px 15px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
    }
    .panel-body {
      padding: 14px 15px;
    }
    .flow-list {
      display: grid;
      gap: 8px;
    }
    .flow-item {
      border-left: 3px solid var(--blue);
      padding: 7px 0 7px 10px;
      background: var(--soft);
    }
    .flow-item b {
      display: block;
      margin-bottom: 4px;
    }
    details {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }
    summary {
      cursor: pointer;
      color: var(--muted);
      font-weight: 700;
    }
    label {
      display: block;
      margin: 10px 0 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      min-height: 36px;
      font: inherit;
      background: #fff;
    }
    textarea {
      min-height: 150px;
      resize: vertical;
      line-height: 1.5;
    }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      padding: 10px 10px 0;
      border-bottom: 1px solid var(--line);
      background: var(--soft);
      border-radius: 8px 8px 0 0;
    }
    .tab {
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      background: transparent;
      color: var(--muted);
    }
    .tab.active {
      border-bottom-color: var(--blue);
      color: var(--text);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    .table-wrap {
      overflow-x: auto;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      background: var(--soft);
      font-size: 12px;
    }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #e7eef7;
    }
    .ready, .sent, .matched { color: var(--green); background: #e5f4ed; }
    .skipped, .needs_review { color: var(--red); background: #fbe8e6; }
    .scheduled, .pending { color: var(--amber); background: #fff3d9; }
    .ignored { color: var(--muted); background: #eef1f5; }
    .note {
      min-height: 20px;
      margin: 10px 0 0;
      color: var(--muted);
    }
    .message-row {
      border-bottom: 1px solid var(--line);
      padding: 14px 0 16px;
    }
    .message-row:first-child {
      padding-top: 0;
    }
    .message-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    .message-head strong {
      font-size: 16px;
    }
    .message-head span {
      color: var(--muted);
      white-space: nowrap;
    }
    .stage-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 14px;
      background: #fff;
    }
    .stage-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--soft);
      border-radius: 8px 8px 0 0;
    }
    .stage-head strong {
      display: block;
      margin-bottom: 4px;
      font-size: 16px;
    }
    .stage-head span {
      color: var(--muted);
      line-height: 1.45;
    }
    .stage-grid {
      display: grid;
      grid-template-columns: minmax(260px, 36%) minmax(0, 1fr);
      gap: 14px;
      padding: 14px;
    }
    .stage-section-title {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .stage-list {
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
      background: #fff;
    }
    .stage-list-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 8px 9px;
      border-bottom: 1px solid var(--line);
    }
    .stage-list-row:last-child {
      border-bottom: 0;
    }
    .stage-list-row b {
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    .stage-list-row small {
      display: block;
      color: var(--muted);
      margin-top: 2px;
    }
    .field-hint {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .message-tools {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-top: 10px;
    }
    .gmail-flow {
      display: grid;
      gap: 10px;
      margin-bottom: 12px;
    }
    .gmail-stage {
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .gmail-stage.done {
      border-color: #b8dcc8;
      background: #f1faf4;
    }
    .gmail-stage.next {
      border-color: var(--blue);
      box-shadow: 0 0 0 2px rgba(23, 105, 170, .1);
    }
    .gmail-stage strong,
    .gmail-stage span {
      display: block;
    }
    .gmail-stage span {
      color: var(--muted);
      line-height: 1.45;
      margin-top: 3px;
    }
    .setup-guide {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      margin-bottom: 14px;
      background: var(--soft);
    }
    .setup-guide h3 {
      margin: 0 0 6px;
      font-size: 16px;
    }
    .setup-steps {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .setup-step {
      border-left: 3px solid var(--amber);
      background: #fff;
      padding: 9px 10px;
      min-height: 76px;
    }
    .setup-step.done {
      border-left-color: var(--green);
    }
    .setup-step b {
      display: block;
      margin-bottom: 5px;
    }
    .setup-step span {
      display: block;
      color: var(--muted);
      line-height: 1.45;
    }
    .setup-meta {
      display: grid;
      gap: 5px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    code {
      display: inline-block;
      max-width: 100%;
      overflow-wrap: anywhere;
      padding: 2px 5px;
      border-radius: 4px;
      background: #eef1f5;
      color: var(--text);
    }
    .link-button {
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      padding: 9px 12px;
      font-weight: 700;
      text-decoration: none;
    }
    .file-name {
      color: var(--muted);
      font-size: 12px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: 1fr 130px;
      gap: 10px;
    }
    pre {
      margin: 0;
      max-height: 380px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border-radius: 6px;
      padding: 12px;
      background: #111827;
      color: #f9fafb;
      font-size: 12px;
    }
    @media (max-width: 980px) {
      header, .layout { display: block; }
      .actions { justify-content: flex-start; margin-top: 12px; }
      .workflow-head { display: block; }
      .workflow-head span { display: block; margin-top: 4px; }
      .workflow-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .steps, .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .layout > .panel { margin-bottom: 14px; }
      .message-head { display: block; }
      .message-head span { display: block; margin-top: 4px; white-space: normal; }
      .stage-grid { grid-template-columns: 1fr; }
      .setup-steps { grid-template-columns: 1fr; }
    }
    @media (max-width: 620px) {
      .workflow-grid, .steps, .cards, .form-grid { grid-template-columns: 1fr; }
      button, .work-actions button, .message-tools button, .link-button {
        min-height: 44px;
      }
      .table-wrap {
        overflow: visible;
      }
      .responsive-table,
      .responsive-table thead,
      .responsive-table tbody,
      .responsive-table tr,
      .responsive-table th,
      .responsive-table td {
        display: block;
      }
      .responsive-table thead {
        display: none;
      }
      .responsive-table tr {
        border: 1px solid var(--line);
        border-radius: 8px;
        margin-bottom: 10px;
        background: #fff;
        overflow: hidden;
      }
      .responsive-table td {
        display: grid;
        grid-template-columns: 96px minmax(0, 1fr);
        gap: 8px;
        padding: 9px 10px;
      }
      .responsive-table td::before {
        content: attr(data-label);
        color: var(--muted);
        font-size: 12px;
        font-weight: 700;
      }
      .gmail-stage {
        grid-template-columns: 34px minmax(0, 1fr);
      }
      .gmail-stage button {
        grid-column: 1 / -1;
      }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <header>
      <div>
        <h1>자동 메일 발송</h1>
        <p class="sub">행사 후 고객별 후속 메일 관리</p>
      </div>
      <div class="actions">
        <button id="refreshBtn">화면 새로고침</button>
      </div>
    </header>

    <section class="workflow">
      <div class="workflow-head">
        <div>
          <h2>오늘 진행 순서</h2>
          <span>왼쪽부터 차례대로 확인하면 발송 준비부터 결과 반영까지 이어집니다.</span>
        </div>
        <span id="nextStepText">다음 작업을 확인하는 중입니다.</span>
      </div>
      <div class="workflow-grid">
        <article class="work-card" id="workflowPeople">
          <span class="work-number">1</span>
          <h3>명단 확인</h3>
          <p>오늘 보낼 사람과 제외할 사람을 나눕니다.</p>
          <div class="work-status" id="peopleStepStatus">아직 확인 전입니다.</div>
          <div class="work-actions">
            <button id="planBtn" class="primary">명단 확인</button>
            <button type="button" data-open-tab="people">목록 보기</button>
          </div>
        </article>
        <article class="work-card" id="workflowFlow">
          <span class="work-number">2</span>
          <h3>단계별 메일</h3>
          <p>퍼널 단계마다 보낼 메일을 확인합니다.</p>
          <div class="work-status" id="flowStepStatus">메일 흐름을 불러오는 중입니다.</div>
          <div class="work-actions">
            <button type="button" data-open-tab="flow">메일 보기</button>
            <button id="saveFlowBtn">저장</button>
          </div>
        </article>
        <article class="work-card" id="workflowApproval">
          <span class="work-number">3</span>
          <h3>발송 승인</h3>
          <p>실제로 보낼 고객만 체크합니다.</p>
          <div class="work-status" id="approvalStepStatus">승인 목록 전입니다.</div>
          <div class="work-actions">
            <button id="prepareApprovalBtn" class="primary">승인 준비</button>
            <button type="button" data-open-tab="approval">승인 보기</button>
          </div>
        </article>
        <article class="work-card" id="workflowPreview">
          <span class="work-number">4</span>
          <h3>미리보기</h3>
          <p>보내기 전에 메일 내용을 파일로 확인합니다.</p>
          <div class="work-status" id="previewStepStatus">미리보기 전입니다.</div>
          <div class="work-actions">
            <button id="dryRunBtn" class="primary">미리보기 만들기</button>
            <button type="button" data-open-tab="preview">결과 보기</button>
          </div>
        </article>
        <article class="work-card" id="workflowGmail">
          <span class="work-number">5</span>
          <h3>Gmail 결과</h3>
          <p>발송 결과를 가져와 고객 상태에 반영합니다.</p>
          <div class="work-status" id="gmailStepStatus">결과 확인 전입니다.</div>
          <div class="work-actions">
            <button id="exportGmailBtn" class="primary">발송 준비</button>
            <button id="connectGoogleBtn">Google 연결</button>
            <button type="button" data-open-tab="gmail">전체 단계</button>
          </div>
        </article>
      </div>
    </section>

    <section class="cards">
      <div class="card"><span>지금 보낼 사람</span><strong id="readyCount">0</strong></div>
      <div class="card"><span>나중에 보낼 사람</span><strong id="scheduledCount">0</strong></div>
      <div class="card"><span>보내지 않을 사람</span><strong id="skippedCount">0</strong></div>
      <div class="card"><span>미리보기 완료</span><strong id="sentCount">0</strong></div>
    </section>

    <section class="layout">
      <aside class="panel">
        <h2>퍼널 단계</h2>
        <div class="panel-body">
          <div id="flowSummary" class="flow-list"></div>
          <details>
            <summary>파일 설정</summary>
            <label for="contacts">명단 파일</label>
            <input id="contacts">
            <label for="funnel_config">메일 흐름 파일</label>
            <input id="funnel_config">
            <label for="lead_state">고객 상태 파일</label>
            <input id="lead_state">
            <label for="campaign_id">이번 발송 이름</label>
            <input id="campaign_id">
            <label for="queue_output">받을 사람 확인 파일</label>
            <input id="queue_output">
            <label for="approval_output">발송 승인 파일</label>
            <input id="approval_output">
            <label for="gmail_source">Gmail 시트 링크</label>
            <input id="gmail_source">
            <label for="gmail_sheet_name">Gmail 시트 이름</label>
            <input id="gmail_sheet_name">
            <label for="gmail_results">Gmail 준비/결과 파일</label>
            <input id="gmail_results">
            <label for="google_credentials">Google 인증 파일</label>
            <input id="google_credentials">
            <label for="google_token">Google 토큰 파일</label>
            <input id="google_token">
            <label for="timeline">고객별 기록 파일</label>
            <input id="timeline">
          </details>
          <p class="note" id="statusLine"></p>
        </div>
      </aside>

      <section class="panel">
        <div class="tabs">
          <button class="tab active" data-tab="people">명단 확인</button>
          <button class="tab" data-tab="flow">단계별 메일</button>
          <button class="tab" data-tab="approval">발송 승인</button>
          <button class="tab" data-tab="gmail">Gmail 확인</button>
          <button class="tab" data-tab="preview">미리보기 결과</button>
          <button class="tab" data-tab="history">고객별 기록</button>
          <button class="tab" data-tab="state">고객 상태</button>
          <button class="tab" data-tab="pm">진행 기록</button>
        </div>
        <div class="panel-body">
          <div id="peopleTab"></div>
          <div id="flowTab" hidden></div>
          <div id="approvalTab" hidden></div>
          <div id="gmailTab" hidden></div>
          <div id="previewTab" hidden></div>
          <div id="historyTab" hidden></div>
          <div id="stateTab" hidden></div>
          <div id="pmTab" hidden></div>
        </div>
      </section>
    </section>
  </main>

  <script>
    const fields = ["contacts", "funnel_config", "lead_state", "campaign_id", "queue_output", "approval_output", "gmail_source", "gmail_sheet_name", "gmail_results", "google_credentials", "google_token", "timeline"];
    const statusLabels = {
      ready: "보낼 예정",
      sent: "미리보기 완료",
      skipped: "보내지 않음",
      scheduled: "나중에 보냄",
      failed: "문제 있음",
      matched: "같음",
      needs_review: "확인 필요",
      pending: "아직 대기",
      ignored: "제외"
    };
    const templateLabels = {
      event_followup: "참석 고객 첫 메일",
      event_second_touch: "참석 고객 두 번째 메일",
      no_show_followup: "미참석 고객 첫 메일"
    };
    const stageLabels = {
      attended_first_touch: "참석 고객 첫 메일 단계",
      attended_second_touch: "참석 고객 두 번째 메일 단계",
      no_show_first_touch: "미참석 고객 첫 메일 단계",
      no_show_second_touch: "미참석 고객 두 번째 메일 단계",
      closed: "종료됨"
    };
    const eventLabels = {
      dry_run_sent: "미리보기 완료",
      skipped: "제외",
      sent: "발송 완료",
      failed: "발송 실패"
    };
    const detailLabels = {
      ready: "발송 가능",
      "수신거부": "수신거부로 제외"
    };
    let peopleRows = [];
    let previewRows = [];
    let flowSteps = [];
    let templates = [];
    let approvalRows = [];
    let gmailRows = [];
    let gmailCounts = {};
    let gmailQueuePending = 0;
    let gmailUploadedRows = 0;
    let googleSetup = null;
    let isBusy = false;

    function formData() {
      const data = {};
      for (const key of fields) data[key] = document.getElementById(key).value;
      return data;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || "작업에 실패했습니다.");
      return data;
    }

    function busy(value) {
      isBusy = value;
      for (const id of ["planBtn", "dryRunBtn", "prepareApprovalBtn", "prepareApprovalInTabBtn", "exportGmailBtn", "exportGmailInTabBtn", "uploadPrivateGmailBtn", "uploadPrivateGmailInTabBtn", "connectGoogleBtn", "connectGoogleInTabBtn", "connectGoogleGuideBtn", "fetchPrivateGmailBtn", "fetchPrivateGmailInTabBtn", "fetchGmailBtn", "fetchGmailInTabBtn", "importGmailBtn", "importGmailInTabBtn", "compareGmailBtn", "compareGmailInTabBtn", "saveFlowBtn", "saveApprovalBtn", "refreshBtn"]) {
        const element = document.getElementById(id);
        if (element) element.disabled = value;
      }
      if (!value) updateWorkflowStatus();
    }

    function note(text) {
      document.getElementById("statusLine").textContent = text;
    }

    function badge(value) {
      const label = statusLabels[value] || value || "";
      return `<span class="badge ${safe(value)}">${safe(label)}</span>`;
    }

    function friendlyTemplate(value) {
      return templateLabels[value] || value || "";
    }

    function friendlyStage(value) {
      if (!value) return "";
      const step = flowSteps.find(item => item.id === value || item.template === value);
      return step ? (step.stage_label || step.audience || value) : (stageLabels[value] || value);
    }

    function friendlyDate(value) {
      if (!value) return "";
      const text = String(value);
      const date = new Date(text);
      if (Number.isNaN(date.getTime())) return text;
      const year = date.getUTCFullYear();
      if (year <= 2000) return "지금 발송 가능";
      if (year >= 2099) return "예약 대기";
      return text.replace("T", " ").replace(/\+00:00$/, "").replace(/:00$/, "");
    }

    function friendlyDetail(value) {
      if (!value) return "";
      const text = String(value);
      if (detailLabels[text]) return detailLabels[text];
      if (text.startsWith("not due until ")) return "예약일 전이라 대기";
      if (text.startsWith("terminal status: ")) return `${text.replace("terminal status: ", "")} 상태로 제외`;
      return text;
    }

    function renderCell(row, column) {
      const value = row[column.key] || "";
      if (column.key === "status" || column.key === "review_status") return badge(value);
      if (column.key === "template" || column.key === "template_name") return safe(friendlyTemplate(value));
      if (column.key === "campaign_step" || column.key === "customer_step" || column.key === "rule") return safe(friendlyStage(value));
      if (column.key === "next_send_at" || column.key === "occurred_at") return safe(friendlyDate(value));
      if (column.key === "event_type") return safe(eventLabels[value] || value || "");
      if (column.key === "detail") {
        const detail = String(value || "");
        if (detail.toLowerCase().endsWith(".html")) {
          return `<a class="link-button" href="/file?path=${encodeURIComponent(detail)}" target="_blank" rel="noopener">미리보기 열기</a>`;
        }
        return safe(friendlyDetail(detail));
      }
      return safe(value);
    }

    function table(targetId, rows, columns) {
      const target = document.getElementById(targetId);
      if (!rows.length) {
        target.innerHTML = "<p class='note'>아직 표시할 내용이 없습니다.</p>";
        return;
      }
      target.innerHTML = `
        <div class="table-wrap"><table class="responsive-table">
          <thead><tr>${columns.map(col => `<th>${safe(col.label)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map(row => `<tr>${columns.map(col => `<td data-label="${safe(col.label)}">${renderCell(row, col)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table></div>`;
    }

    function showPeople() {
      table("peopleTab", peopleRows, [
        { key: "email", label: "받는 사람" },
        { key: "status", label: "결과" },
        { key: "template", label: "보낼 메일" },
        { key: "campaign_step", label: "현재 단계" },
        { key: "next_send_at", label: "다음 예정일" },
        { key: "detail", label: "이유" }
      ]);
    }

    function showPreview() {
      table("previewTab", previewRows, [
        { key: "original_email", label: "받는 사람" },
        { key: "status", label: "결과" },
        { key: "template", label: "보낸 메일" },
        { key: "detail", label: "미리보기 파일/이유" }
      ]);
    }

    function showHistory(rows) {
      table("historyTab", rows, [
        { key: "occurred_at", label: "시간" },
        { key: "email", label: "고객" },
        { key: "event_type", label: "일어난 일" },
        { key: "template_name", label: "메일" },
        { key: "detail", label: "상세" }
      ]);
    }

    function showState(state) {
      const contacts = state.contacts || {};
      const rows = Object.entries(contacts).map(([email, item]) => ({
        email,
        status: item.status || "",
        campaign_step: item.campaign_step || "",
        next_send_at: item.next_send_at || "",
        tags: Array.isArray(item.tags) ? item.tags.join(", ") : ""
      }));
      table("stateTab", rows, [
        { key: "email", label: "고객" },
        { key: "status", label: "상태" },
        { key: "campaign_step", label: "현재 단계" },
        { key: "next_send_at", label: "다음 예정일" },
        { key: "tags", label: "분류" }
      ]);
    }

    function showFlow() {
      const summary = document.getElementById("flowSummary");
      if (!flowSteps.length) {
        summary.innerHTML = "<p class='note'>등록된 메일 흐름이 없습니다.</p>";
        document.getElementById("flowTab").innerHTML = "<p class='note'>등록된 메일 흐름이 없습니다.</p>";
        updateWorkflowStatus();
        return;
      }

      summary.innerHTML = flowSteps.map(step => `
        <div class="flow-item">
          <b>${safe(step.order)}. ${safe(step.stage_label || step.audience)}</b>
          <span>${safe(step.template)} · ${safe(step.send_after_label)}</span>
        </div>`).join("");

      const options = templates.map(template => `<option value="${safe(template.name)}"></option>`).join("");
      document.getElementById("flowTab").innerHTML = `
        <datalist id="templateNames">${options}</datalist>
        ${flowSteps.map((step, index) => `
          <section class="stage-card message-row" data-index="${index}">
            <div class="stage-head">
              <div>
                <strong>${safe(step.order)}. ${safe(step.stage_label || step.audience)}</strong>
                <span>${safe(step.audience)}</span>
              </div>
              <span>${safe(step.send_after_label)}</span>
            </div>
            <div class="stage-grid">
              <div>
                <p class="stage-section-title">이 단계의 명단</p>
                ${stagePeopleHtml(step)}
              </div>
              <div>
                <p class="stage-section-title">이 단계에서 보낼 메일</p>
                <div class="form-grid">
                  <div>
                    <label>메일 이름</label>
                    <input data-flow-field="template" list="templateNames" value="${safe(step.template)}">
                  </div>
                  <div>
                    <label>이 단계 메일 발송 후</label>
                    <input data-flow-field="next_send_after_days" type="number" min="0" value="${safe(step.next_send_after_days)}">
                    <p class="field-hint">첫 메일이 아니라 이 단계 메일의 실제 발송일 기준입니다.</p>
                  </div>
                </div>
                <label>제목</label>
                <input data-flow-field="subject" value="${safe(step.subject)}">
                <label>본문</label>
                <textarea data-flow-field="text_body">${safe(step.text_body)}</textarea>
                <div class="message-tools">
                  <button data-action="import-word" type="button">Word 파일 불러오기</button>
                  <span class="file-name" data-flow-field="word_name">선택된 Word 파일 없음</span>
                  <input data-flow-field="word_file" type="file" accept=".docx" hidden>
                </div>
              </div>
            </div>
          </section>`).join("")}`;

      for (const button of document.querySelectorAll('[data-action="import-word"]')) {
        button.addEventListener("click", event => {
          event.currentTarget.closest(".message-row").querySelector('[data-flow-field="word_file"]').click();
        });
      }
      for (const input of document.querySelectorAll('[data-flow-field="word_file"]')) {
        input.addEventListener("change", importWordFile);
      }
      updateWorkflowStatus();
    }

    function collectFlow() {
      return Array.from(document.querySelectorAll(".message-row")).map(row => {
        const index = Number(row.dataset.index);
        const step = flowSteps[index];
        const value = field => row.querySelector(`[data-flow-field="${field}"]`).value;
        return {
          id: step.id,
          template: value("template"),
          next_send_after_days: value("next_send_after_days"),
          subject: value("subject"),
          text_body: value("text_body")
        };
      });
    }

    function stageRows(step) {
      return peopleRows.filter(row =>
        row.rule === step.id ||
        (step.template && row.template === step.template) ||
        row.campaign_step === step.id
      );
    }

    function stagePeopleHtml(step) {
      const rows = stageRows(step);
      if (!rows.length) {
        return "<p class='note'>이 단계에 표시할 명단이 아직 없습니다.</p>";
      }
      const shown = rows.slice(0, 8).map(row => `
        <div class="stage-list-row">
          <div>
            <b>${safe(row.email)}</b>
            <small>${safe(row.detail || row.campaign_step || "")}</small>
          </div>
          ${badge(row.status)}
        </div>`).join("");
      const extra = rows.length > 8 ? `<p class="note">외 ${rows.length - 8}명 더 있음</p>` : "";
      return `<div class="stage-list">${shown}</div>${extra}`;
    }

    function showApproval() {
      const target = document.getElementById("approvalTab");
      if (!approvalRows.length) {
        target.innerHTML = `
          <p class="note">아직 승인할 메일이 없습니다. 먼저 받을 사람을 확인한 뒤 발송 승인 준비를 누르세요.</p>
          <button type="button" id="prepareApprovalInTabBtn">발송 승인 준비</button>`;
        document.getElementById("prepareApprovalInTabBtn").addEventListener("click", prepareApproval);
        updateWorkflowStatus();
        return;
      }

      const approvedCount = approvalRows.filter(row => row.approved === "yes").length;
      const waitingCount = approvalRows.length - approvedCount;
      target.innerHTML = `
        <div class="message-tools">
          <button type="button" id="approveAllBtn">전체 승인</button>
          <button type="button" id="clearApprovalBtn">전체 해제</button>
          <button type="button" class="primary" id="saveApprovalBtn">승인 목록 저장</button>
          <span class="file-name">승인 ${approvedCount}건 / 대기 ${waitingCount}건</span>
        </div>
        <div class="table-wrap"><table class="responsive-table">
          <thead><tr><th>승인</th><th>받는 사람</th><th>보낼 메일</th><th>단계</th><th>상세</th></tr></thead>
          <tbody>
            ${approvalRows.map((row, index) => `
              <tr>
                <td data-label="승인"><input type="checkbox" data-approval-index="${index}" ${row.approved === "yes" ? "checked" : ""}></td>
                <td data-label="받는 사람">${safe(row.email)}</td>
                <td data-label="보낼 메일">${safe(friendlyTemplate(row.template))}</td>
                <td data-label="단계">${safe(stageLabelForRow(row))}</td>
                <td data-label="상세">${safe(friendlyDetail(row.detail || ""))}</td>
              </tr>`).join("")}
          </tbody>
        </table></div>`;
      document.getElementById("approveAllBtn").addEventListener("click", () => setApprovalChecks(true));
      document.getElementById("clearApprovalBtn").addEventListener("click", () => setApprovalChecks(false));
      document.getElementById("saveApprovalBtn").addEventListener("click", saveApproval);
      updateWorkflowStatus();
    }

    function approvedCount() {
      return approvalRows.filter(row => row.approved === "yes").length;
    }

    function previewSentCount() {
      return previewRows.filter(row => row.status === "sent").length;
    }

    function googleStepDone(id) {
      const steps = googleSetup && Array.isArray(googleSetup.steps) ? googleSetup.steps : [];
      const step = steps.find(item => item.id === id);
      return Boolean(step && step.done);
    }

    function gmailActionHtml(number, title, detail, buttonId, buttonText, done, isNext) {
      return `
        <div class="gmail-stage ${done ? "done" : ""} ${isNext ? "next" : ""}">
          <span class="work-number">${number}</span>
          <div>
            <strong>${safe(title)}</strong>
            <span>${safe(detail)}</span>
          </div>
          <button type="button" id="${safe(buttonId)}">${safe(buttonText)}</button>
        </div>`;
    }

    function showGmailCompare(counts = {}) {
      const target = document.getElementById("gmailTab");
      gmailCounts = counts;
      const matched = counts.matched || 0;
      const needsReview = counts.needs_review || 0;
      const pending = counts.pending || 0;
      const ignored = counts.ignored || 0;
      const approved = approvedCount();
      const previewSent = previewSentCount();
      const googleReady = googleStepDone("fetch");
      const canStart = approved > 0 && previewSent > 0;
      const nextGmailStep = !googleReady
        ? 1
        : !gmailQueuePending
          ? 2
          : !gmailUploadedRows
            ? 3
            : !gmailRows.length
              ? 4
              : 5;
      const summary = `
        <div class="gmail-flow">
          ${gmailActionHtml(1, "Google 연결", googleReady ? "비공개 시트를 읽고 쓸 준비가 됐습니다." : "Google 설정과 시트 링크를 먼저 확인합니다.", "connectGoogleInTabBtn", "Google 연결", googleReady, nextGmailStep === 1)}
          ${gmailActionHtml(2, "발송 준비", gmailQueuePending ? `승인된 ${gmailQueuePending}건을 Gmail 준비 파일에 담았습니다.` : "승인된 고객으로 Gmail 준비 파일을 만듭니다.", "exportGmailInTabBtn", "발송 준비", gmailQueuePending > 0, nextGmailStep === 2 && canStart)}
          ${gmailActionHtml(3, "시트 업로드", gmailUploadedRows ? `비공개 시트에 ${gmailUploadedRows}건을 올렸습니다.` : "Gmail 준비 파일을 비공개 Google Sheet에 올립니다.", "uploadPrivateGmailInTabBtn", "시트에 올리기", gmailUploadedRows > 0, nextGmailStep === 3)}
          ${gmailActionHtml(4, "결과 가져오기", gmailRows.length ? "Gmail 발송 결과를 불러왔습니다." : "발송 후 Sheet의 결과를 앱으로 가져옵니다.", "fetchPrivateGmailInTabBtn", "결과 가져오기", gmailRows.length > 0, nextGmailStep === 4)}
          ${gmailActionHtml(5, "결과 반영", matched || needsReview || pending || ignored ? "고객 상태와 Gmail 결과를 비교했습니다." : "성공/실패 결과를 고객 상태에 반영합니다.", "importGmailInTabBtn", "결과 반영", Boolean(matched || needsReview || pending || ignored), nextGmailStep === 5)}
        </div>
        <div class="message-tools">
          <button type="button" id="fetchGmailInTabBtn">CSV 링크로 가져오기</button>
          <button type="button" id="compareGmailInTabBtn">결과 확인</button>
          <span class="file-name">같음 ${matched}건 / 확인 필요 ${needsReview}건 / 대기 ${pending}건 / 제외 ${ignored}건</span>
        </div>`;

      if (!gmailRows.length) {
        target.innerHTML = `${googleGuideHtml()}${summary}<p class="note">아직 확인할 Gmail 결과가 없습니다.</p>`;
      } else {
        target.innerHTML = `${googleGuideHtml()}${summary}
          <div class="table-wrap"><table class="responsive-table">
            <thead><tr><th>확인</th><th>고객</th><th>Gmail 상태</th><th>메일</th><th>현재 단계</th><th>상세</th></tr></thead>
            <tbody>
              ${gmailRows.map(row => `
                <tr>
                  <td data-label="확인">${badge(row.status)}</td>
                  <td data-label="고객">${safe(row.email)}</td>
                  <td data-label="Gmail 상태">${safe(statusLabels[row.gmail_status] || row.gmail_status || "")}</td>
                  <td data-label="메일">${safe(friendlyTemplate(row.template))}</td>
                  <td data-label="현재 단계">${safe(friendlyStage(row.customer_step))}</td>
                  <td data-label="상세">${safe(friendlyDetail(row.detail))}</td>
                </tr>`).join("")}
            </tbody>
          </table></div>`;
      }

      document.getElementById("exportGmailInTabBtn").addEventListener("click", exportGmailQueue);
      document.getElementById("uploadPrivateGmailInTabBtn").addEventListener("click", uploadPrivateGmailQueue);
      document.getElementById("connectGoogleInTabBtn").addEventListener("click", connectGoogle);
      document.getElementById("fetchPrivateGmailInTabBtn").addEventListener("click", fetchPrivateGmailResults);
      document.getElementById("fetchGmailInTabBtn").addEventListener("click", fetchGmailResults);
      document.getElementById("importGmailInTabBtn").addEventListener("click", importGmailResults);
      document.getElementById("compareGmailInTabBtn").addEventListener("click", () => compareGmailResults(true));
      const statusButton = document.getElementById("refreshGoogleStatusBtn");
      if (statusButton) statusButton.addEventListener("click", () => refreshGoogleStatus(true));
      const connectButton = document.getElementById("connectGoogleGuideBtn");
      if (connectButton) connectButton.addEventListener("click", connectGoogle);
      updateWorkflowStatus();
    }

    function googleGuideHtml() {
      const steps = googleSetup && googleSetup.steps ? googleSetup.steps : [
        { label: "Google Cloud 설정", done: false, detail: "Google Sheets API와 OAuth Client를 준비합니다." },
        { label: "비공개 시트 입력", done: false, detail: "Gmail 시트 링크를 입력합니다." },
        { label: "Google 연결", done: false, detail: "Google 연결을 눌러 권한을 승인합니다." },
        { label: "결과 가져오기 준비", done: false, detail: "준비가 끝나면 비공개 시트 가져오기를 누릅니다." }
      ];
      const redirectUri = googleSetup ? googleSetup.redirect_uri : `${window.location.origin}/oauth/google/callback`;
      const credentialsPath = googleSetup ? googleSetup.credentials_path : "config/google_oauth_client.json";
      const tokenPath = googleSetup ? googleSetup.token_path : "state/google_sheets_token.json";
      const stepHtml = steps.map(step => `
        <div class="setup-step ${step.done ? "done" : ""}">
          <b>${step.done ? "완료" : "필요"} · ${safe(step.label)}</b>
          <span>${safe(step.detail)}</span>
        </div>`).join("");
      return `
        <section class="setup-guide">
          <h3>비공개 Google Sheet 연결 안내</h3>
          <p class="note">고객 이메일이 들어간 Sheet는 공개하지 않고 Google 로그인 권한으로 읽고 씁니다.</p>
          <div class="message-tools">
            <a class="link-button" href="https://console.cloud.google.com/apis/library/sheets.googleapis.com" target="_blank" rel="noopener">Google Sheets API 열기</a>
            <a class="link-button" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">OAuth Client 만들기</a>
            <button type="button" id="connectGoogleGuideBtn">Google 연결</button>
            <button type="button" id="refreshGoogleStatusBtn">설정 상태 확인</button>
          </div>
          <div class="setup-meta">
            <span>1. Google Cloud에서 Sheets API를 켜고 OAuth Client를 만듭니다.</span>
            <span>2. 승인된 리디렉션 URI에 <code>${safe(redirectUri)}</code> 를 넣습니다.</span>
            <span>3. 받은 JSON을 <code>${safe(credentialsPath)}</code> 로 저장합니다.</span>
            <span>4. Google 연결 후 읽기/쓰기 토큰은 <code>${safe(tokenPath)}</code> 에 저장됩니다.</span>
          </div>
          <div class="setup-steps">${stepHtml}</div>
        </section>`;
    }

    function stageLabelForRow(row) {
      const step = flowSteps.find(item => item.id === row.rule || item.template === row.template);
      return step ? (step.stage_label || step.audience) : (row.campaign_step || row.rule || "");
    }

    function setApprovalChecks(checked) {
      for (const input of document.querySelectorAll("[data-approval-index]")) input.checked = checked;
    }

    function collectApproval() {
      return Array.from(document.querySelectorAll("[data-approval-index]")).map(input => {
        const row = approvalRows[Number(input.dataset.approvalIndex)];
        return { email: row.email, template: row.template, approved: input.checked };
      });
    }

    async function importWordFile(event) {
      const input = event.currentTarget;
      const file = input.files && input.files[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".docx")) {
        note("Word .docx 파일만 불러올 수 있습니다.");
        input.value = "";
        return;
      }

      const section = input.closest(".message-row");
      note(`${file.name} 내용을 불러오는 중입니다...`);
      try {
        const content = await fileToBase64(file);
        const data = await api("/api/word-template/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, content_base64: content })
        });
        const subjectInput = section.querySelector('[data-flow-field="subject"]');
        const bodyInput = section.querySelector('[data-flow-field="text_body"]');
        if (!subjectInput.value.trim()) subjectInput.value = data.subject || "";
        bodyInput.value = data.text_body || "";
        section.querySelector('[data-flow-field="word_name"]').textContent = file.name;
        note(`${file.name} 내용을 본문에 넣었습니다.`);
      } catch (error) {
        note(error.message);
      } finally {
        input.value = "";
      }
    }

    function fileToBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
        reader.onerror = () => reject(new Error("Word 파일을 읽지 못했습니다."));
        reader.readAsDataURL(file);
      });
    }

    function metrics() {
      const count = key => peopleRows.filter(row => row.status === key).length;
      document.getElementById("readyCount").textContent = count("ready");
      document.getElementById("scheduledCount").textContent = count("scheduled");
      document.getElementById("skippedCount").textContent = count("skipped");
      document.getElementById("sentCount").textContent = previewRows.filter(row => row.status === "sent").length;
      updateWorkflowStatus();
    }

    function updateWorkflowStatus() {
      const ready = peopleRows.filter(row => row.status === "ready").length;
      const scheduled = peopleRows.filter(row => row.status === "scheduled").length;
      const skipped = peopleRows.filter(row => row.status === "skipped").length;
      const approved = approvedCount();
      const waiting = approvalRows.length - approved;
      const previewSent = previewSentCount();
      const gmailTotal = Object.values(gmailCounts || {}).reduce((sum, value) => sum + Number(value || 0), 0);
      const approvalReady = approvalRows.length > 0 && approved > 0;

      setText("peopleStepStatus", peopleRows.length ? `보낼 사람 ${ready}명 / 나중 ${scheduled}명 / 제외 ${skipped}명` : "아직 확인 전입니다.");
      setText("flowStepStatus", flowSteps.length ? `${flowSteps.length}개 단계가 준비됐습니다.` : "메일 흐름을 불러오는 중입니다.");
      setText(
        "approvalStepStatus",
        approvalRows.length
          ? approved
            ? `승인 ${approved}건 / 대기 ${waiting}건`
            : `승인이 필요합니다. 대기 ${waiting}건`
          : "승인 목록 전입니다."
      );
      setText(
        "previewStepStatus",
        previewRows.length
          ? `미리보기 ${previewSent}건 완료`
          : approvalReady
            ? "미리보기 전입니다."
            : "승인 저장 후 만들 수 있습니다."
      );
      setText(
        "gmailStepStatus",
        gmailTotal
          ? `같음 ${gmailCounts.matched || 0}건 / 확인 필요 ${gmailCounts.needs_review || 0}건`
          : gmailUploadedRows
            ? `비공개 시트 업로드 ${gmailUploadedRows}건`
          : gmailQueuePending
            ? `Gmail 발송 준비 ${gmailQueuePending}건`
            : previewSent
              ? "Gmail 발송 준비 전입니다."
              : "승인과 미리보기 후 진행합니다."
      );

      const nextId = !peopleRows.length
        ? "workflowPeople"
        : ready > 0 && !approvalReady
          ? "workflowApproval"
          : ready > 0 && !previewRows.length
            ? "workflowPreview"
            : ready > 0 && !gmailTotal
              ? "workflowGmail"
              : "";
      for (const card of document.querySelectorAll(".work-card")) {
        card.classList.toggle("next", card.id === nextId);
      }
      const labels = {
        workflowPeople: "다음 작업: 명단 확인",
        workflowApproval: "다음 작업: 발송 승인",
        workflowPreview: "다음 작업: 미리보기 만들기",
        workflowGmail: "다음 작업: Gmail 발송 결과"
      };
      setText("nextStepText", labels[nextId] || "오늘 흐름을 모두 확인했습니다.");
      applyActionAvailability({ ready, approved, previewSent, gmailTotal });
    }

    function setText(id, text) {
      const element = document.getElementById(id);
      if (element) element.textContent = text;
    }

    function setActionDisabled(ids, disabled, reason = "") {
      if (isBusy) return;
      for (const id of ids) {
        const element = document.getElementById(id);
        if (!element) continue;
        element.disabled = disabled;
        element.title = disabled ? reason : "";
      }
    }

    function applyActionAvailability({ ready, approved, previewSent, gmailTotal }) {
      if (isBusy) return;
      const hasSource = Boolean((document.getElementById("gmail_source")?.value || "").trim());
      const googleReady = googleStepDone("fetch");
      const canPrepareApproval = ready > 0;
      const canPreview = approved > 0;
      const canExportGmail = approved > 0 && previewSent > 0;
      const canUploadPrivate = gmailQueuePending > 0 && hasSource && googleReady;
      const canFetchPrivate = hasSource && googleReady;
      const canFetchCsv = hasSource;
      const canImport = gmailRows.length > 0 || gmailTotal > 0;
      const canCompare = Boolean((document.getElementById("gmail_results")?.value || "").trim());

      setActionDisabled(["prepareApprovalBtn", "prepareApprovalInTabBtn"], !canPrepareApproval, "먼저 명단 확인을 완료하세요.");
      setActionDisabled(["dryRunBtn"], !canPreview, "발송 승인에서 보낼 고객을 승인하고 저장하세요.");
      setActionDisabled(["exportGmailBtn", "exportGmailInTabBtn"], !canExportGmail, "승인 저장과 미리보기 완료 후 준비할 수 있습니다.");
      setActionDisabled(["uploadPrivateGmailBtn", "uploadPrivateGmailInTabBtn"], !canUploadPrivate, "Gmail 준비 파일, 시트 링크, Google 연결이 필요합니다.");
      setActionDisabled(["fetchPrivateGmailBtn", "fetchPrivateGmailInTabBtn"], !canFetchPrivate, "비공개 시트 링크와 Google 연결이 필요합니다.");
      setActionDisabled(["fetchGmailBtn", "fetchGmailInTabBtn"], !canFetchCsv, "Gmail 시트 링크를 입력하세요.");
      setActionDisabled(["importGmailBtn", "importGmailInTabBtn"], !canImport, "먼저 Gmail 결과를 가져오거나 확인하세요.");
      setActionDisabled(["compareGmailBtn", "compareGmailInTabBtn"], !canCompare, "Gmail 준비/결과 파일 경로가 필요합니다.");
      setActionDisabled(["connectGoogleBtn", "connectGoogleInTabBtn", "connectGoogleGuideBtn"], false);
      setActionDisabled(["saveFlowBtn", "refreshBtn", "planBtn"], false);
    }

    async function plan() {
      busy(true);
      note("받을 사람을 확인하는 중입니다...");
      try {
        const data = await api("/api/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        peopleRows = data.rows || [];
        showPeople();
        if (flowSteps.length) showFlow();
        metrics();
        note("받을 사람 확인이 끝났습니다.");
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function preview() {
      if (approvedCount() === 0) {
        note("먼저 발송 승인에서 보낼 고객을 승인하고 저장하세요.");
        switchTab("approval");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("메일 미리보기를 만드는 중입니다...");
      try {
        const data = await api("/api/dry-run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        previewRows = data.report_rows || [];
        showPreview();
        await refreshHistory();
        metrics();
        note(`미리보기 완료: ${data.summary.sent}건 준비, ${data.summary.skipped}건 제외`);
        switchTab("preview");
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function loadFlow() {
      const query = encodeURIComponent(document.getElementById("funnel_config").value);
      const data = await api(`/api/message-flow?funnel_config=${query}`);
      flowSteps = data.steps || [];
      templates = data.templates || [];
      showFlow();
    }

    async function saveFlow() {
      busy(true);
      note("메일 흐름을 저장하는 중입니다...");
      try {
        const data = await api("/api/message-flow/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...formData(), steps: collectFlow() })
        });
        flowSteps = data.steps || [];
        templates = data.templates || [];
        showFlow();
        await plan();
        switchTab("flow");
        note("메일 흐름을 저장했습니다.");
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function prepareApproval() {
      if (!peopleRows.some(row => row.status === "ready")) {
        note("오늘 보낼 사람이 없습니다. 먼저 명단 확인 결과를 확인하세요.");
        switchTab("people");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("오늘 보낼 메일 승인 목록을 만드는 중입니다...");
      try {
        const data = await api("/api/approval/prepare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        approvalRows = data.rows || [];
        showApproval();
        switchTab("approval");
        note(`승인할 메일 ${approvalRows.length}건을 준비했습니다.`);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function saveApproval() {
      busy(true);
      note("승인 목록을 저장하는 중입니다...");
      try {
        const data = await api("/api/approval/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...formData(), rows: collectApproval() })
        });
        approvalRows = data.rows || [];
        showApproval();
        note(`승인 목록을 저장했습니다. 승인 ${data.counts.approved}건, 대기 ${data.counts.waiting}건`);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function exportGmailQueue() {
      if (approvedCount() === 0 || previewSentCount() === 0) {
        note("Gmail 발송 준비는 승인 저장과 미리보기 완료 후 진행할 수 있습니다.");
        switchTab("gmail");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("Gmail 발송 준비 파일을 만드는 중입니다...");
      try {
        const data = await api("/api/gmail/export", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        gmailQueuePending = data.summary.pending || 0;
        updateWorkflowStatus();
        switchTab("gmail");
        note(`Gmail 발송 준비 완료: ${gmailQueuePending}건`);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function uploadPrivateGmailQueue() {
      if (!gmailQueuePending || !googleStepDone("fetch")) {
        note("먼저 Gmail 발송 준비를 완료하고 Google 연결 상태를 확인하세요.");
        switchTab("gmail");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("Gmail 발송 준비 파일을 비공개 시트에 올리는 중입니다...");
      try {
        const data = await api("/api/gmail/upload-private", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        gmailUploadedRows = data.summary.rows || 0;
        updateWorkflowStatus();
        switchTab("gmail");
        note(`비공개 시트 업로드 완료: ${gmailUploadedRows}건`);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function connectGoogle() {
      busy(true);
      note("Google 연결 주소를 만드는 중입니다...");
      try {
        const data = await api("/api/google/auth-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...formData(), redirect_uri: `${window.location.origin}/oauth/google/callback` })
        });
        window.open(data.auth_url, "_blank", "noopener");
        note("새 창에서 Google 로그인을 완료한 뒤 이 화면으로 돌아오세요.");
        await refreshGoogleStatus(false);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function refreshGoogleStatus(showBusy = true) {
      if (showBusy) {
        busy(true);
        note("Google 설정 상태를 확인하는 중입니다...");
      }
      try {
        const data = await api("/api/google/status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        googleSetup = data;
        showGmailCompare(gmailCounts);
        if (showBusy) note("Google 설정 상태를 확인했습니다.");
      } catch (error) {
        if (showBusy) note(error.message);
        throw error;
      } finally {
        if (showBusy) busy(false);
      }
    }

    async function fetchPrivateGmailResults() {
      if (!googleStepDone("fetch")) {
        note("비공개 시트를 가져오려면 Google 연결과 시트 링크가 필요합니다.");
        switchTab("gmail");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("비공개 Gmail 시트 결과를 가져오는 중입니다...");
      try {
        const data = await api("/api/gmail/fetch-private", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        note(`비공개 시트 가져오기 완료: ${data.summary.rows}행을 저장했습니다.`);
        await compareGmailResults(false);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function fetchGmailResults() {
      if (!(document.getElementById("gmail_source").value || "").trim()) {
        note("Gmail 시트 링크를 먼저 입력하세요.");
        switchTab("gmail");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("Gmail 시트 결과를 가져오는 중입니다...");
      try {
        const data = await api("/api/gmail/fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        note(`Gmail 시트 가져오기 완료: ${data.summary.rows}행을 저장했습니다.`);
        await compareGmailResults(false);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function importGmailResults() {
      if (!gmailRows.length) {
        note("먼저 Gmail 결과를 가져오거나 결과 확인을 실행하세요.");
        switchTab("gmail");
        updateWorkflowStatus();
        return;
      }
      busy(true);
      note("Gmail 발송 결과를 고객 상태에 반영하는 중입니다...");
      try {
        const data = await api("/api/gmail/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        await Promise.all([refreshState(), refreshHistory()]);
        await compareGmailResults(false);
        note(`Gmail 결과 반영 완료: 성공 ${data.summary.imported}건, 실패 ${data.summary.failed}건, 건너뜀 ${data.summary.skipped}건`);
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function compareGmailResults(showBusy = true) {
      if (showBusy) {
        busy(true);
        note("Gmail 결과와 고객 상태를 확인하는 중입니다...");
      }
      try {
        const data = await api("/api/gmail/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData())
        });
        gmailRows = data.rows || [];
        showGmailCompare(data.counts || {});
        switchTab("gmail");
        if (showBusy) note(`Gmail 결과 확인 완료: 같음 ${data.counts.matched}건, 확인 필요 ${data.counts.needs_review}건, 대기 ${data.counts.pending}건`);
      } catch (error) {
        if (showBusy) note(error.message);
        throw error;
      } finally {
        if (showBusy) busy(false);
      }
    }

    async function refreshPeople() {
      const path = encodeURIComponent(document.getElementById("queue_output").value);
      const data = await api(`/api/queue?path=${path}`);
      peopleRows = data.rows || [];
      showPeople();
      if (flowSteps.length) showFlow();
    }

    async function refreshApproval() {
      const path = encodeURIComponent(document.getElementById("approval_output").value);
      const data = await api(`/api/approval?path=${path}`);
      approvalRows = data.rows || [];
      showApproval();
    }

    async function refreshHistory() {
      const path = encodeURIComponent(document.getElementById("timeline").value);
      const data = await api(`/api/timeline?path=${path}`);
      showHistory(data.rows || []);
    }

    async function refreshState() {
      const path = encodeURIComponent(document.getElementById("lead_state").value);
      const data = await api(`/api/lead-state?path=${path}`);
      showState(data.state || {});
    }

    async function refreshPm() {
      const data = await api("/api/progress");
      document.getElementById("pmTab").innerHTML = `<pre>${safe(data.markdown || "")}</pre>`;
    }

    async function refreshAll() {
      busy(true);
      try {
        await Promise.all([refreshPeople(), refreshApproval(), refreshHistory(), refreshState(), refreshPm(), loadFlow(), refreshGoogleStatus(false)]);
        metrics();
        note("화면을 새로고침했습니다.");
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    function switchTab(name) {
      for (const button of document.querySelectorAll(".tab")) {
        button.classList.toggle("active", button.dataset.tab === name);
      }
      for (const id of ["people", "flow", "approval", "gmail", "preview", "history", "state", "pm"]) {
        document.getElementById(`${id}Tab`).hidden = id !== name;
      }
    }

    function safe(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function bindClick(id, handler) {
      const element = document.getElementById(id);
      if (element) element.addEventListener("click", handler);
    }

    async function boot() {
      const defaults = await api("/api/defaults");
      for (const key of fields) document.getElementById(key).value = defaults[key] || "";
      bindClick("planBtn", plan);
      bindClick("dryRunBtn", preview);
      bindClick("prepareApprovalBtn", prepareApproval);
      bindClick("exportGmailBtn", exportGmailQueue);
      bindClick("uploadPrivateGmailBtn", uploadPrivateGmailQueue);
      bindClick("connectGoogleBtn", connectGoogle);
      bindClick("fetchPrivateGmailBtn", fetchPrivateGmailResults);
      bindClick("fetchGmailBtn", fetchGmailResults);
      bindClick("importGmailBtn", importGmailResults);
      bindClick("compareGmailBtn", () => compareGmailResults(true));
      bindClick("saveFlowBtn", saveFlow);
      bindClick("refreshBtn", refreshAll);
      document.getElementById("funnel_config").addEventListener("change", loadFlow);
      for (const button of document.querySelectorAll(".tab")) {
        button.addEventListener("click", () => switchTab(button.dataset.tab));
      }
      for (const button of document.querySelectorAll("[data-open-tab]")) {
        button.addEventListener("click", () => switchTab(button.dataset.openTab));
      }
      await refreshGoogleStatus(false);
      await plan();
      await refreshAll();
    }

    boot().catch(error => note(error.message));
  </script>
</body>
</html>
"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler())
    print(f"Automailing admin listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
