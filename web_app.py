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
from fetch_gmail_results import fetch_results as fetch_gmail_results
from import_gmail_results import import_results as import_gmail_results


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "email_templates"


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
    "gmail_results": "outbox/gmail_send_queue.csv",
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
                if parsed.path == "/api/gmail/fetch":
                    result = _handle_fetch_gmail_results(payload)
                    self._json_response(200, result)
                    return
                if parsed.path == "/api/gmail/compare":
                    result = _handle_compare_gmail_results(payload)
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

        delay = str(raw_step.get("next_send_after_days") or "").strip()
        if delay:
            delay_days = int(delay)
            if delay_days < 0:
                raise ValueError(f"{step_id}: delay days cannot be negative.")
            if step.get("next_send_after_days") != delay_days:
                step["next_send_after_days"] = delay_days
                config_changed = True
        else:
            if "next_send_after_days" in step:
                step.pop("next_send_after_days", None)
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


def _handle_fetch_gmail_results(payload: dict[str, object]) -> dict[str, object]:
    config = _request_config(payload)
    summary = fetch_gmail_results(
        source=config["gmail_source"],
        output_path=_safe_path(config["gmail_results"]),
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
                "next_send_after_days": raw_step.get("next_send_after_days", ""),
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
    value = step.get("next_send_after_days")
    if value not in (None, ""):
        return f"이 메일 뒤 {value}일 후 다음 메일"
    if step.get("next_step") or step.get("set_step"):
        return "다음 단계로 이동"
    return "후속 메일 없음"


DASHBOARD_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Automailing Admin</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --surface: #ffffff;
      --line: #d9dee7;
      --text: #17202a;
      --muted: #637083;
      --blue: #1769aa;
      --green: #1f8a5b;
      --red: #b42318;
      --amber: #a15c07;
      --ink: #243447;
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
    .shell {
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      min-height: 100vh;
    }
    aside {
      background: #202b3a;
      color: #eef3f8;
      padding: 24px 18px;
    }
    aside h1 {
      margin: 0 0 6px;
      font-size: 20px;
      font-weight: 700;
    }
    aside p {
      margin: 0 0 22px;
      color: #b8c4d2;
      line-height: 1.5;
    }
    .nav-item {
      display: block;
      padding: 9px 10px;
      border-radius: 6px;
      color: #dce6ef;
      text-decoration: none;
      margin-bottom: 4px;
    }
    .nav-item.active { background: #314155; }
    main {
      padding: 24px;
      max-width: 1440px;
      width: 100%;
    }
    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
    }
    header h2 {
      margin: 0 0 4px;
      font-size: 24px;
    }
    header p {
      margin: 0;
      color: var(--muted);
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    button {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      min-height: 36px;
      padding: 8px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
    }
    button.primary {
      border-color: var(--blue);
      background: var(--blue);
      color: white;
    }
    button:disabled {
      opacity: .6;
      cursor: wait;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric, .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .metric {
      padding: 14px;
      min-height: 82px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .metric strong {
      font-size: 28px;
    }
    .work {
      display: grid;
      grid-template-columns: minmax(360px, 420px) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    .panel h3 {
      margin: 0;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
    }
    .panel-body {
      padding: 14px 16px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin: 0 0 6px;
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      margin-bottom: 12px;
      font-size: 13px;
      min-height: 36px;
    }
    .tabs {
      display: flex;
      gap: 4px;
      border-bottom: 1px solid var(--line);
      padding: 0 12px;
      background: #fbfcfd;
    }
    .tab {
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      background: transparent;
      min-height: 42px;
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
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      background: #fbfcfd;
    }
    .badge {
      display: inline-block;
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: #e7eef7;
      color: var(--ink);
    }
    .badge.ready, .badge.sent { background: #e5f4ed; color: var(--green); }
    .badge.skipped { background: #fbe8e6; color: var(--red); }
    .badge.scheduled { background: #fff3d9; color: var(--amber); }
    .split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      max-height: 360px;
      overflow: auto;
      background: #111827;
      color: #f9fafb;
      border-radius: 6px;
      padding: 12px;
      font-size: 12px;
    }
    .status-line {
      min-height: 20px;
      color: var(--muted);
      margin-top: 10px;
    }
    @media (max-width: 960px) {
      .shell, .work, .split { grid-template-columns: 1fr; }
      aside { position: static; }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      header { display: block; }
      .toolbar { margin-top: 12px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>Automailing</h1>
      <p>폼 응답 기반 자동 퍼널 메일 관리</p>
      <a class="nav-item active" href="#dashboard">Dashboard</a>
      <a class="nav-item" href="#queue">Send Queue</a>
      <a class="nav-item" href="#timeline">Timeline</a>
      <a class="nav-item" href="#state">Lead State</a>
    </aside>
    <main>
      <header>
        <div>
          <h2>운영 대시보드</h2>
          <p>발송 전 큐를 만들고 dry-run으로 결과를 검증합니다.</p>
        </div>
        <div class="toolbar">
          <button id="planBtn">큐 생성</button>
          <button id="dryRunBtn" class="primary">Dry-run 실행</button>
          <button id="refreshBtn">새로고침</button>
        </div>
      </header>

      <section class="grid">
        <div class="metric"><span>Ready</span><strong id="readyCount">0</strong></div>
        <div class="metric"><span>Scheduled</span><strong id="scheduledCount">0</strong></div>
        <div class="metric"><span>Skipped</span><strong id="skippedCount">0</strong></div>
        <div class="metric"><span>Dry-run Sent</span><strong id="sentCount">0</strong></div>
      </section>

      <section class="work">
        <div class="panel">
          <h3>실행 설정</h3>
          <div class="panel-body">
            <label for="contacts">응답/연락처 파일</label>
            <input id="contacts">
            <label for="funnel_config">퍼널 설정</label>
            <input id="funnel_config">
            <label for="lead_state">리드 상태</label>
            <input id="lead_state">
            <label for="campaign_id">캠페인 ID</label>
            <input id="campaign_id">
            <label for="queue_output">큐 출력 파일</label>
            <input id="queue_output">
            <label for="timeline">타임라인 파일</label>
            <input id="timeline">
            <div class="status-line" id="statusLine"></div>
          </div>
        </div>

        <div class="panel">
          <div class="tabs">
            <button class="tab active" data-tab="queue">발송 큐</button>
            <button class="tab" data-tab="report">Dry-run 결과</button>
            <button class="tab" data-tab="timeline">타임라인</button>
            <button class="tab" data-tab="state">리드 상태</button>
            <button class="tab" data-tab="progress">PM 기록</button>
          </div>
          <div class="panel-body">
            <div id="queueTab" class="tab-panel"></div>
            <div id="reportTab" class="tab-panel" hidden></div>
            <div id="timelineTab" class="tab-panel" hidden></div>
            <div id="stateTab" class="tab-panel" hidden></div>
            <div id="progressTab" class="tab-panel" hidden></div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const fields = ["contacts", "funnel_config", "lead_state", "campaign_id", "queue_output", "timeline"];
    let currentQueue = [];
    let currentReport = [];

    function payload() {
      const data = {};
      for (const key of fields) data[key] = document.getElementById(key).value;
      return data;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || "요청 실패");
      return data;
    }

    function setBusy(isBusy) {
      for (const id of ["planBtn", "dryRunBtn", "refreshBtn"]) {
        document.getElementById(id).disabled = isBusy;
      }
    }

    function setStatus(text) {
      document.getElementById("statusLine").textContent = text;
    }

    function renderTable(targetId, rows, columns) {
      const target = document.getElementById(targetId);
      if (!rows.length) {
        target.innerHTML = "<p>표시할 데이터가 없습니다.</p>";
        return;
      }
      const head = columns.map(col => `<th>${escapeHtml(col.label)}</th>`).join("");
      const body = rows.map(row => {
        const cells = columns.map(col => {
          const value = row[col.key] || "";
          if (col.key === "status") return `<td><span class="badge ${escapeHtml(value)}">${escapeHtml(value)}</span></td>`;
          return `<td>${escapeHtml(value)}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      target.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function renderTimeline(rows) {
      renderTable("timelineTab", rows, [
        { key: "occurred_at", label: "시간" },
        { key: "email", label: "이메일" },
        { key: "event_type", label: "이벤트" },
        { key: "rule_name", label: "룰" },
        { key: "template_name", label: "템플릿" },
        { key: "detail", label: "상세" }
      ]);
    }

    function renderLeadState(state) {
      const contacts = state.contacts || {};
      const rows = Object.entries(contacts).map(([email, value]) => ({
        email,
        status: value.status || "",
        campaign_step: value.campaign_step || "",
        next_send_at: value.next_send_at || "",
        tags: Array.isArray(value.tags) ? value.tags.join(", ") : ""
      }));
      renderTable("stateTab", rows, [
        { key: "email", label: "이메일" },
        { key: "status", label: "상태" },
        { key: "campaign_step", label: "단계" },
        { key: "next_send_at", label: "다음 발송" },
        { key: "tags", label: "태그" }
      ]);
    }

    function updateMetrics(queueRows, reportRows) {
      const counts = { ready: 0, scheduled: 0, skipped: 0 };
      for (const row of queueRows) counts[row.status] = (counts[row.status] || 0) + 1;
      document.getElementById("readyCount").textContent = counts.ready || 0;
      document.getElementById("scheduledCount").textContent = counts.scheduled || 0;
      document.getElementById("skippedCount").textContent = counts.skipped || 0;
      document.getElementById("sentCount").textContent = reportRows.filter(row => row.status === "sent").length;
    }

    async function planQueue() {
      setBusy(true);
      setStatus("큐 생성 중...");
      try {
        const data = await api("/api/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload())
        });
        currentQueue = data.rows || [];
        renderQueue();
        updateMetrics(currentQueue, currentReport);
        setStatus(`큐 생성 완료: ${data.queue_path}`);
      } catch (error) {
        setStatus(error.message);
      } finally {
        setBusy(false);
      }
    }

    async function dryRun() {
      setBusy(true);
      setStatus("Dry-run 실행 중...");
      try {
        const data = await api("/api/dry-run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload())
        });
        currentReport = data.report_rows || [];
        renderReport();
        await refreshTimeline();
        updateMetrics(currentQueue, currentReport);
        setStatus(`Dry-run 완료: processed=${data.summary.processed}, sent=${data.summary.sent}, skipped=${data.summary.skipped}, failed=${data.summary.failed}`);
      } catch (error) {
        setStatus(error.message);
      } finally {
        setBusy(false);
      }
    }

    function renderQueue() {
      renderTable("queueTab", currentQueue, [
        { key: "email", label: "이메일" },
        { key: "status", label: "상태" },
        { key: "rule", label: "룰" },
        { key: "template", label: "템플릿" },
        { key: "campaign_step", label: "단계" },
        { key: "next_send_at", label: "다음 발송" },
        { key: "detail", label: "상세" }
      ]);
    }

    function renderReport() {
      renderTable("reportTab", currentReport, [
        { key: "original_email", label: "이메일" },
        { key: "status", label: "상태" },
        { key: "rule", label: "룰" },
        { key: "template", label: "템플릿" },
        { key: "detail", label: "상세" }
      ]);
    }

    async function refreshQueue() {
      const path = encodeURIComponent(document.getElementById("queue_output").value);
      const data = await api(`/api/queue?path=${path}`);
      currentQueue = data.rows || [];
      renderQueue();
    }

    async function refreshTimeline() {
      const path = encodeURIComponent(document.getElementById("timeline").value);
      const data = await api(`/api/timeline?path=${path}`);
      renderTimeline(data.rows || []);
    }

    async function refreshState() {
      const path = encodeURIComponent(document.getElementById("lead_state").value);
      const data = await api(`/api/lead-state?path=${path}`);
      renderLeadState(data.state || {});
    }

    async function refreshProgress() {
      const data = await api("/api/progress");
      document.getElementById("progressTab").innerHTML = `<pre>${escapeHtml(data.markdown || "")}</pre>`;
    }

    async function refreshAll() {
      setBusy(true);
      try {
        await Promise.all([refreshQueue(), refreshTimeline(), refreshState(), refreshProgress()]);
        updateMetrics(currentQueue, currentReport);
        setStatus("새로고침 완료");
      } catch (error) {
        setStatus(error.message);
      } finally {
        setBusy(false);
      }
    }

    function switchTab(name) {
      for (const button of document.querySelectorAll(".tab")) {
        button.classList.toggle("active", button.dataset.tab === name);
      }
      for (const panel of document.querySelectorAll(".tab-panel")) panel.hidden = true;
      document.getElementById(`${name}Tab`).hidden = false;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function boot() {
      const defaults = await api("/api/defaults");
      for (const key of fields) document.getElementById(key).value = defaults[key] || "";
      document.getElementById("planBtn").addEventListener("click", planQueue);
      document.getElementById("dryRunBtn").addEventListener("click", dryRun);
      document.getElementById("refreshBtn").addEventListener("click", refreshAll);
      for (const button of document.querySelectorAll(".tab")) {
        button.addEventListener("click", () => switchTab(button.dataset.tab));
      }
      await planQueue();
      await refreshAll();
    }

    boot().catch(error => setStatus(error.message));
  </script>
</body>
</html>
"""


SIMPLE_DASHBOARD_HTML = r"""<!doctype html>
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
      width: min(1280px, calc(100% - 32px));
      margin: 0 auto;
      padding: 22px 0 32px;
    }
    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 26px;
    }
    .sub {
      color: var(--muted);
      margin: 0;
      line-height: 1.5;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      border-radius: 6px;
      padding: 9px 12px;
      min-height: 38px;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--blue);
      background: var(--blue);
      color: #fff;
    }
    button:disabled {
      opacity: .6;
      cursor: wait;
    }
    .steps {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .step {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      min-height: 88px;
    }
    .step strong {
      display: block;
      margin-bottom: 7px;
      font-size: 15px;
    }
    .step span {
      color: var(--muted);
      line-height: 1.45;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .card span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .card strong {
      font-size: 28px;
    }
    .layout {
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    .box {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .box h2 {
      margin: 0;
      padding: 14px 15px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
    }
    .box-body {
      padding: 14px 15px;
    }
    .flow {
      display: grid;
      gap: 8px;
    }
    .flow-row {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px;
      background: #fbfcfd;
    }
    .flow-row b {
      display: block;
      margin-bottom: 4px;
    }
    .flow-row p {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }
    details {
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
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
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      min-height: 36px;
      font-size: 13px;
    }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      padding: 10px 10px 0;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
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
      color: var(--text);
      border-bottom-color: var(--blue);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
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
      background: #fbfcfd;
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
      color: var(--muted);
      margin: 10px 0 0;
      min-height: 20px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      max-height: 360px;
      overflow: auto;
      background: #111827;
      color: #f9fafb;
      border-radius: 6px;
      padding: 12px;
      font-size: 12px;
    }
    @media (max-width: 920px) {
      header, .layout { display: block; }
      .actions { justify-content: flex-start; margin-top: 12px; }
      .steps, .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .layout > .box { margin-bottom: 14px; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <header>
      <div>
        <h1>자동 메일 발송 준비</h1>
        <p class="sub">명단을 확인하고, 누구에게 어떤 메일이 갈지 미리 본 뒤 테스트합니다.</p>
      </div>
      <div class="actions">
        <button id="planBtn">발송 대상 확인</button>
        <button id="dryRunBtn" class="primary">메일 미리보기 만들기</button>
        <button id="refreshBtn">화면 새로고침</button>
      </div>
    </header>

    <section class="steps">
      <div class="step"><strong>1. 명단 선택</strong><span>폼 응답이나 엑셀 명단을 불러옵니다.</span></div>
      <div class="step"><strong>2. 받을 사람 확인</strong><span>보낼 사람, 나중에 보낼 사람, 제외할 사람을 나눕니다.</span></div>
      <div class="step"><strong>3. 메일 미리보기</strong><span>실제 발송 없이 결과 파일을 만듭니다.</span></div>
      <div class="step"><strong>4. 테스트 발송</strong><span>내 메일로 먼저 확인한 뒤 실제 발송합니다.</span></div>
    </section>

    <section class="cards">
      <div class="card"><span>지금 보낼 사람</span><strong id="readyCount">0</strong></div>
      <div class="card"><span>나중에 보낼 사람</span><strong id="scheduledCount">0</strong></div>
      <div class="card"><span>보내지 않을 사람</span><strong id="skippedCount">0</strong></div>
      <div class="card"><span>미리보기 완료</span><strong id="sentCount">0</strong></div>
    </section>

    <section class="layout">
      <aside class="box">
        <h2>이번 발송 흐름</h2>
        <div class="box-body">
          <div class="flow">
            <div class="flow-row">
              <b>참석한 사람</b>
              <p>감사 메일을 보내고, 2일 뒤 추가 안내 대상으로 둡니다.</p>
            </div>
            <div class="flow-row">
              <b>미참석한 사람</b>
              <p>자료 공유 메일을 보내고, 3일 뒤 다시 확인합니다.</p>
            </div>
            <div class="flow-row">
              <b>동의하지 않았거나 거부한 사람</b>
              <p>자동으로 제외합니다.</p>
            </div>
            <div class="flow-row">
              <b>이미 전환된 사람</b>
              <p>더 이상 후속 메일을 보내지 않습니다.</p>
            </div>
          </div>

          <details>
            <summary>설정 파일 보기</summary>
            <label for="contacts">명단 파일</label>
            <input id="contacts">
            <label for="funnel_config">메일 흐름 설정</label>
            <input id="funnel_config">
            <label for="lead_state">고객 상태 파일</label>
            <input id="lead_state">
            <label for="campaign_id">이번 발송 이름</label>
            <input id="campaign_id">
            <label for="queue_output">대상 확인 파일</label>
            <input id="queue_output">
            <label for="timeline">고객 기록 파일</label>
            <input id="timeline">
          </details>
          <p class="note" id="statusLine"></p>
        </div>
      </aside>

      <section class="box">
        <div class="tabs">
          <button class="tab active" data-tab="people">받을 사람</button>
          <button class="tab" data-tab="preview">미리보기 결과</button>
          <button class="tab" data-tab="history">고객별 기록</button>
          <button class="tab" data-tab="state">고객 상태</button>
          <button class="tab" data-tab="pm">진행 기록</button>
        </div>
        <div class="box-body">
          <div id="peopleTab"></div>
          <div id="previewTab" hidden></div>
          <div id="historyTab" hidden></div>
          <div id="stateTab" hidden></div>
          <div id="pmTab" hidden></div>
        </div>
      </section>
    </section>
  </main>

  <script>
    const fields = ["contacts", "funnel_config", "lead_state", "campaign_id", "queue_output", "timeline"];
    const statusLabels = {
      ready: "보낼 예정",
      sent: "미리보기 완료",
      skipped: "보내지 않음",
      scheduled: "나중에 보냄",
      failed: "문제 있음"
    };
    let peopleRows = [];
    let previewRows = [];

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
      for (const id of ["planBtn", "dryRunBtn", "refreshBtn"]) document.getElementById(id).disabled = value;
    }

    function note(text) {
      document.getElementById("statusLine").textContent = text;
    }

    function badge(value) {
      const label = statusLabels[value] || value || "";
      return `<span class="badge ${safe(value)}">${safe(label)}</span>`;
    }

    function table(targetId, rows, columns) {
      const target = document.getElementById(targetId);
      if (!rows.length) {
        target.innerHTML = "<p class='note'>아직 표시할 내용이 없습니다.</p>";
        return;
      }
      target.innerHTML = `
        <table>
          <thead><tr>${columns.map(col => `<th>${safe(col.label)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map(row => `<tr>${columns.map(col => `<td>${col.key === "status" ? badge(row[col.key]) : safe(row[col.key] || "")}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>`;
    }

    function showPeople() {
      table("peopleTab", peopleRows, [
        { key: "email", label: "받는 사람" },
        { key: "status", label: "결과" },
        { key: "template", label: "메일 종류" },
        { key: "campaign_step", label: "현재 단계" },
        { key: "next_send_at", label: "다음 예정일" },
        { key: "detail", label: "이유" }
      ]);
    }

    function showPreview() {
      table("previewTab", previewRows, [
        { key: "original_email", label: "받는 사람" },
        { key: "status", label: "결과" },
        { key: "template", label: "메일 종류" },
        { key: "detail", label: "미리보기 파일/이유" }
      ]);
    }

    function showHistory(rows) {
      table("historyTab", rows, [
        { key: "occurred_at", label: "시간" },
        { key: "email", label: "고객" },
        { key: "event_type", label: "일어난 일" },
        { key: "template_name", label: "메일 종류" },
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

    function metrics() {
      const count = key => peopleRows.filter(row => row.status === key).length;
      document.getElementById("readyCount").textContent = count("ready");
      document.getElementById("scheduledCount").textContent = count("scheduled");
      document.getElementById("skippedCount").textContent = count("skipped");
      document.getElementById("sentCount").textContent = previewRows.filter(row => row.status === "sent").length;
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
        metrics();
        note("받을 사람 확인이 끝났습니다.");
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    async function preview() {
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

    async function refreshPeople() {
      const path = encodeURIComponent(document.getElementById("queue_output").value);
      const data = await api(`/api/queue?path=${path}`);
      peopleRows = data.rows || [];
      showPeople();
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
        await Promise.all([refreshPeople(), refreshHistory(), refreshState(), refreshPm()]);
        metrics();
        note("화면을 새로고침했습니다.");
      } catch (error) {
        note(error.message);
      } finally {
        busy(false);
      }
    }

    function switchTab(name) {
      for (const button of document.querySelectorAll(".tab")) button.classList.toggle("active", button.dataset.tab === name);
      for (const id of ["people", "preview", "history", "state", "pm"]) document.getElementById(`${id}Tab`).hidden = id !== name;
    }

    function safe(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function boot() {
      const defaults = await api("/api/defaults");
      for (const key of fields) document.getElementById(key).value = defaults[key] || "";
      document.getElementById("planBtn").addEventListener("click", plan);
      document.getElementById("dryRunBtn").addEventListener("click", preview);
      document.getElementById("refreshBtn").addEventListener("click", refreshAll);
      for (const button of document.querySelectorAll(".tab")) button.addEventListener("click", () => switchTab(button.dataset.tab));
      await plan();
      await refreshAll();
    }

    boot().catch(error => note(error.message));
  </script>
</body>
</html>
"""


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
      min-height: 38px;
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
      cursor: wait;
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
    .message-tools {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-top: 10px;
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
      .steps, .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .layout > .panel { margin-bottom: 14px; }
      .message-head { display: block; }
      .message-head span { display: block; margin-top: 4px; white-space: normal; }
      .stage-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 620px) {
      .steps, .cards, .form-grid { grid-template-columns: 1fr; }
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
        <button id="planBtn">받을 사람 확인</button>
        <button id="dryRunBtn" class="primary">메일 미리보기 만들기</button>
        <button id="prepareApprovalBtn">발송 승인 준비</button>
        <button id="fetchGmailBtn">Gmail 시트 가져오기</button>
        <button id="importGmailBtn">Gmail 결과 반영</button>
        <button id="compareGmailBtn">Gmail 결과 확인</button>
        <button id="saveFlowBtn">단계별 메일 저장</button>
        <button id="refreshBtn">화면 새로고침</button>
      </div>
    </header>

    <section class="steps">
      <div class="step"><strong>1. 명단 선택</strong><span>폼 응답이나 엑셀 명단을 불러옵니다.</span></div>
      <div class="step"><strong>2. 받을 사람 확인</strong><span>지금 보낼 사람과 제외할 사람을 나눕니다.</span></div>
      <div class="step"><strong>3. 단계별 메일 작성</strong><span>퍼널 단계마다 명단과 메일 내용을 따로 확인합니다.</span></div>
      <div class="step"><strong>4. 미리보기</strong><span>실제 발송 전 결과 파일을 만듭니다.</span></div>
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
            <label for="gmail_results">Gmail 결과 파일</label>
            <input id="gmail_results">
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
    const fields = ["contacts", "funnel_config", "lead_state", "campaign_id", "queue_output", "approval_output", "gmail_source", "gmail_results", "timeline"];
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
    let peopleRows = [];
    let previewRows = [];
    let flowSteps = [];
    let templates = [];
    let approvalRows = [];
    let gmailRows = [];

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
      for (const id of ["planBtn", "dryRunBtn", "prepareApprovalBtn", "fetchGmailBtn", "importGmailBtn", "compareGmailBtn", "saveFlowBtn", "refreshBtn"]) {
        const element = document.getElementById(id);
        if (element) element.disabled = value;
      }
    }

    function note(text) {
      document.getElementById("statusLine").textContent = text;
    }

    function badge(value) {
      const label = statusLabels[value] || value || "";
      return `<span class="badge ${safe(value)}">${safe(label)}</span>`;
    }

    function table(targetId, rows, columns) {
      const target = document.getElementById(targetId);
      if (!rows.length) {
        target.innerHTML = "<p class='note'>아직 표시할 내용이 없습니다.</p>";
        return;
      }
      target.innerHTML = `
        <table>
          <thead><tr>${columns.map(col => `<th>${safe(col.label)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map(row => `<tr>${columns.map(col => `<td>${col.key === "status" ? badge(row[col.key]) : safe(row[col.key] || "")}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>`;
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
                    <label>다음 메일까지</label>
                    <input data-flow-field="next_send_after_days" type="number" min="0" value="${safe(step.next_send_after_days)}">
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
        return;
      }

      const approvedCount = approvalRows.filter(row => row.approved === "yes").length;
      target.innerHTML = `
        <div class="message-tools">
          <button type="button" id="approveAllBtn">전체 승인</button>
          <button type="button" id="clearApprovalBtn">전체 해제</button>
          <button type="button" class="primary" id="saveApprovalBtn">승인 목록 저장</button>
          <span class="file-name">승인 ${approvedCount}건 / 대기 ${approvalRows.length}건</span>
        </div>
        <table>
          <thead><tr><th>승인</th><th>받는 사람</th><th>보낼 메일</th><th>단계</th><th>상세</th></tr></thead>
          <tbody>
            ${approvalRows.map((row, index) => `
              <tr>
                <td><input type="checkbox" data-approval-index="${index}" ${row.approved === "yes" ? "checked" : ""}></td>
                <td>${safe(row.email)}</td>
                <td>${safe(row.template)}</td>
                <td>${safe(stageLabelForRow(row))}</td>
                <td>${safe(row.detail || "")}</td>
              </tr>`).join("")}
          </tbody>
        </table>`;
      document.getElementById("approveAllBtn").addEventListener("click", () => setApprovalChecks(true));
      document.getElementById("clearApprovalBtn").addEventListener("click", () => setApprovalChecks(false));
      document.getElementById("saveApprovalBtn").addEventListener("click", saveApproval);
    }

    function showGmailCompare(counts = {}) {
      const target = document.getElementById("gmailTab");
      const matched = counts.matched || 0;
      const needsReview = counts.needs_review || 0;
      const pending = counts.pending || 0;
      const ignored = counts.ignored || 0;
      const summary = `
        <div class="message-tools">
          <button type="button" id="fetchGmailInTabBtn">Gmail 시트 가져오기</button>
          <button type="button" class="primary" id="importGmailInTabBtn">Gmail 결과 반영</button>
          <button type="button" id="compareGmailInTabBtn">Gmail 결과 확인</button>
          <span class="file-name">같음 ${matched}건 / 확인 필요 ${needsReview}건 / 대기 ${pending}건 / 제외 ${ignored}건</span>
        </div>`;

      if (!gmailRows.length) {
        target.innerHTML = `${summary}<p class="note">아직 확인할 Gmail 결과가 없습니다.</p>`;
      } else {
        target.innerHTML = `${summary}
          <table>
            <thead><tr><th>확인</th><th>고객</th><th>Gmail 상태</th><th>메일</th><th>현재 단계</th><th>상세</th></tr></thead>
            <tbody>
              ${gmailRows.map(row => `
                <tr>
                  <td>${badge(row.status)}</td>
                  <td>${safe(row.email)}</td>
                  <td>${safe(row.gmail_status)}</td>
                  <td>${safe(row.template)}</td>
                  <td>${safe(row.customer_step)}</td>
                  <td>${safe(row.detail)}</td>
                </tr>`).join("")}
            </tbody>
          </table>`;
      }

      document.getElementById("fetchGmailInTabBtn").addEventListener("click", fetchGmailResults);
      document.getElementById("importGmailInTabBtn").addEventListener("click", importGmailResults);
      document.getElementById("compareGmailInTabBtn").addEventListener("click", () => compareGmailResults(true));
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

    async function fetchGmailResults() {
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
        await Promise.all([refreshPeople(), refreshApproval(), refreshHistory(), refreshState(), refreshPm(), loadFlow()]);
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

    async function boot() {
      const defaults = await api("/api/defaults");
      for (const key of fields) document.getElementById(key).value = defaults[key] || "";
      document.getElementById("planBtn").addEventListener("click", plan);
      document.getElementById("dryRunBtn").addEventListener("click", preview);
      document.getElementById("prepareApprovalBtn").addEventListener("click", prepareApproval);
      document.getElementById("fetchGmailBtn").addEventListener("click", fetchGmailResults);
      document.getElementById("importGmailBtn").addEventListener("click", importGmailResults);
      document.getElementById("compareGmailBtn").addEventListener("click", () => compareGmailResults(true));
      document.getElementById("saveFlowBtn").addEventListener("click", saveFlow);
      document.getElementById("refreshBtn").addEventListener("click", refreshAll);
      document.getElementById("funnel_config").addEventListener("change", loadFlow);
      for (const button of document.querySelectorAll(".tab")) {
        button.addEventListener("click", () => switchTab(button.dataset.tab));
      }
      showGmailCompare();
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
