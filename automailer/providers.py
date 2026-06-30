from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SendRequest:
    to_email: str
    to_name: str | None
    subject: str
    html_body: str
    text_body: str
    template_name: str
    campaign_id: str


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider: str
    status_code: int | None = None
    message_id: str | None = None
    error: str | None = None


class MailProvider:
    name = "base"

    def send(self, request: SendRequest) -> SendResult:
        raise NotImplementedError


class DryRunProvider(MailProvider):
    name = "dryrun"

    def __init__(self, outbox_dir: Path):
        self.outbox_dir = outbox_dir
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, request: SendRequest) -> SendResult:
        safe_to = re.sub(r"[^a-zA-Z0-9_.@-]+", "_", request.to_email)
        safe_template = re.sub(r"[^a-zA-Z0-9_.-]+", "_", request.template_name)
        output_path = self.outbox_dir / f"{request.campaign_id}_{safe_template}_{safe_to}.html"
        output_path.write_text(_preview_document(request), encoding="utf-8")
        return SendResult(ok=True, provider=self.name, message_id=str(output_path))


class SendGridProvider(MailProvider):
    name = "sendgrid"

    def __init__(self, api_key: str, from_email: str, from_name: str | None):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name

    def send(self, request: SendRequest) -> SendResult:
        payload = {
            "personalizations": [
                {
                    "to": [_address(request.to_email, request.to_name)],
                    "subject": request.subject,
                }
            ],
            "from": _address(self.from_email, self.from_name),
            "content": [
                {"type": "text/plain", "value": request.text_body},
                {"type": "text/html", "value": request.html_body},
            ],
            "categories": [request.campaign_id],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return _post_json("https://api.sendgrid.com/v3/mail/send", payload, headers, self.name)


class PostmarkProvider(MailProvider):
    name = "postmark"

    def __init__(self, server_token: str, from_email: str, from_name: str | None):
        self.server_token = server_token
        self.from_email = from_email
        self.from_name = from_name

    def send(self, request: SendRequest) -> SendResult:
        payload = {
            "From": _format_from(self.from_email, self.from_name),
            "To": _format_from(request.to_email, request.to_name),
            "Subject": request.subject,
            "HtmlBody": request.html_body,
            "TextBody": request.text_body,
            "MessageStream": "outbound",
            "Tag": request.campaign_id[:100],
        }
        headers = {
            "X-Postmark-Server-Token": self.server_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return _post_json("https://api.postmarkapp.com/email", payload, headers, self.name)


class OutlookProvider(MailProvider):
    name = "outlook"

    def __init__(self, display_only: bool):
        self.display_only = display_only
        self.script_path = Path(__file__).resolve().parent.parent / "scripts" / "send_outlook_mail.ps1"

    def send(self, request: SendRequest) -> SendResult:
        if not self.script_path.exists():
            return SendResult(ok=False, provider=self.name, error=f"Missing script: {self.script_path}")

        payload = {
            "to_email": request.to_email,
            "subject": request.subject,
            "html_body": request.html_body,
            "account_email": os.getenv("OUTLOOK_ACCOUNT_EMAIL", ""),
        }
        mode = "display" if self.display_only else "send"

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as file:
            json.dump(payload, file, ensure_ascii=False)
            json_path = Path(file.name)

        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script_path),
                    "-MessageJson",
                    str(json_path),
                    "-Mode",
                    mode,
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if completed.returncode == 0:
                message = completed.stdout.strip() or f"outlook:{mode}"
                return SendResult(ok=True, provider=self.name, message_id=message)
            return SendResult(
                ok=False,
                provider=self.name,
                error=(completed.stderr or completed.stdout or "Outlook send failed.").strip(),
            )
        except FileNotFoundError:
            return SendResult(ok=False, provider=self.name, error="PowerShell was not found.")
        except subprocess.TimeoutExpired:
            return SendResult(ok=False, provider=self.name, error="Outlook automation timed out.")
        finally:
            try:
                json_path.unlink(missing_ok=True)
            except OSError:
                pass


def create_provider(name: str, outbox_dir: Path, *, outlook_display: bool = False) -> MailProvider:
    lowered = name.lower()
    if lowered == "dryrun":
        return DryRunProvider(outbox_dir)

    if lowered == "outlook":
        return OutlookProvider(display_only=outlook_display)

    from_email = os.getenv("MAIL_FROM_EMAIL")
    from_name = os.getenv("MAIL_FROM_NAME")
    if not from_email:
        raise RuntimeError("MAIL_FROM_EMAIL is required for real sends.")

    if lowered == "sendgrid":
        api_key = os.getenv("SENDGRID_API_KEY")
        if not api_key:
            raise RuntimeError("SENDGRID_API_KEY is required when MAIL_PROVIDER=sendgrid.")
        return SendGridProvider(api_key=api_key, from_email=from_email, from_name=from_name)

    if lowered == "postmark":
        token = os.getenv("POSTMARK_SERVER_TOKEN")
        if not token:
            raise RuntimeError("POSTMARK_SERVER_TOKEN is required when MAIL_PROVIDER=postmark.")
        return PostmarkProvider(server_token=token, from_email=from_email, from_name=from_name)

    raise RuntimeError(f"Unsupported MAIL_PROVIDER: {name}")


def _post_json(url: str, payload: dict, headers: dict[str, str], provider: str) -> SendResult:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            message_id = response.headers.get("X-Message-Id") or _json_field(body, "MessageID")
            return SendResult(
                ok=200 <= response.status < 300,
                provider=provider,
                status_code=response.status,
                message_id=message_id,
                error=None if 200 <= response.status < 300 else body,
            )
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return SendResult(ok=False, provider=provider, status_code=error.code, error=body)
    except urllib.error.URLError as error:
        return SendResult(ok=False, provider=provider, error=str(error.reason))


def _address(email: str, name: str | None) -> dict[str, str]:
    value = {"email": email}
    if name:
        value["name"] = name
    return value


def _format_from(email: str, name: str | None) -> str:
    return f"{name} <{email}>" if name else email


def _json_field(value: str, field: str) -> str | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    found = parsed.get(field)
    return str(found) if found is not None else None


def _preview_document(request: SendRequest) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{request.subject}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #17202a; }}
    .meta {{ border-bottom: 1px solid #d8dee9; margin-bottom: 24px; padding-bottom: 16px; }}
    .meta div {{ margin: 4px 0; }}
  </style>
</head>
<body>
  <section class="meta">
    <div><strong>To:</strong> {request.to_email}</div>
    <div><strong>Name:</strong> {request.to_name or ""}</div>
    <div><strong>Campaign:</strong> {request.campaign_id}</div>
    <div><strong>Template:</strong> {request.template_name}</div>
    <div><strong>Subject:</strong> {request.subject}</div>
  </section>
  {request.html_body}
</body>
</html>
"""
