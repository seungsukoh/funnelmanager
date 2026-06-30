from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path


VARIABLE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")


@dataclass(frozen=True)
class EmailTemplate:
    name: str
    subject: str
    html_body: str
    text_body: str


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str
    missing_variables: tuple[str, ...]


def load_template(template_dir: Path, name: str) -> EmailTemplate:
    subject_path = template_dir / f"{name}.subject.txt"
    html_path = template_dir / f"{name}.html"
    text_path = template_dir / f"{name}.txt"

    missing = [str(path) for path in (subject_path, html_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing template file(s): {', '.join(missing)}")

    subject = subject_path.read_text(encoding="utf-8").strip()
    html_body = html_path.read_text(encoding="utf-8")
    text_body = text_path.read_text(encoding="utf-8") if text_path.exists() else _html_to_text(html_body)

    return EmailTemplate(name=name, subject=subject, html_body=html_body, text_body=text_body)


def render_template(template: EmailTemplate, variables: dict[str, str]) -> RenderedEmail:
    subject, missing_subject = _render(template.subject, variables, escape=False)
    html_body, missing_html = _render(template.html_body, variables, escape=True)
    text_body, missing_text = _render(template.text_body, variables, escape=False)
    missing = tuple(sorted(set(missing_subject + missing_html + missing_text)))
    return RenderedEmail(subject=subject, html_body=html_body, text_body=text_body, missing_variables=missing)


def enrich_variables(row: dict[str, str], email: str, name: str | None) -> dict[str, str]:
    variables = dict(row)
    variables.setdefault("email", email)
    variables.setdefault("이메일", email)
    if name:
        variables.setdefault("name", name)
        variables.setdefault("이름", name)
    return variables


def _render(template_text: str, variables: dict[str, str], *, escape: bool) -> tuple[str, list[str]]:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in variables or variables[key] == "":
            missing.append(key)
            return ""
        value = variables[key]
        return html.escape(value, quote=True) if escape else value

    return VARIABLE_PATTERN.sub(replace, template_text), missing


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p>", "\n\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()
