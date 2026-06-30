from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from automailer.rendering import EmailTemplate


def load_word_template(path: Path, subject_template: str | None = None) -> EmailTemplate:
    if path.suffix.lower() != ".docx":
        raise ValueError("--word-template currently supports .docx files.")

    with zipfile.ZipFile(path) as archive:
        root = _document_root(archive)

    html_body, text_body = _document_to_bodies(root)
    subject = subject_template or path.stem
    return EmailTemplate(name=path.stem, subject=subject, html_body=html_body, text_body=text_body)


def load_word_template_bytes(filename: str, content: bytes, subject_template: str | None = None) -> EmailTemplate:
    path = Path(filename)
    if path.suffix.lower() != ".docx":
        raise ValueError("Word import currently supports .docx files.")

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = _document_root(archive)

    html_body, text_body = _document_to_bodies(root)
    subject = subject_template or path.stem
    return EmailTemplate(name=path.stem, subject=subject, html_body=html_body, text_body=text_body)


def _document_root(archive: zipfile.ZipFile) -> ElementTree.Element:
    with archive.open("word/document.xml") as file:
        return ElementTree.parse(file).getroot()


def _document_to_bodies(root: ElementTree.Element) -> tuple[str, str]:
    body = root.find(_w("body"))
    if body is None:
        return "", ""

    html_parts = ['<main style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2933;">']
    text_parts: list[str] = []

    for child in body:
        tag = _local_name(child.tag)
        if tag == "p":
            text = _paragraph_text(child).strip()
            if text:
                html_parts.append(f"  <p>{html.escape(text)}</p>")
                text_parts.append(text)
        elif tag == "tbl":
            rows = _table_rows(child)
            if rows:
                html_parts.append(_table_html(rows))
                text_parts.extend("\t".join(row) for row in rows)

    html_parts.append("</main>")
    return "\n".join(html_parts), "\n\n".join(text_parts)


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        tag = _local_name(node.tag)
        if tag == "t" and node.text:
            parts.append(node.text)
        elif tag in {"tab"}:
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts)


def _table_rows(table: ElementTree.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.findall(_w("tr")):
        cells = []
        for tc in tr.findall(_w("tc")):
            paragraphs = [_paragraph_text(p).strip() for p in tc.findall(_w("p"))]
            cells.append(" ".join(value for value in paragraphs if value))
        if any(cells):
            rows.append(cells)
    return rows


def _table_html(rows: list[list[str]]) -> str:
    output = [
        '  <table style="border-collapse: collapse; margin: 12px 0;">',
    ]
    for row in rows:
        output.append("    <tr>")
        for cell in row:
            output.append(
                '      <td style="border: 1px solid #d0d7de; padding: 6px 8px;">'
                f"{html.escape(cell)}</td>"
            )
        output.append("    </tr>")
    output.append("  </table>")
    return "\n".join(output)


def _w(tag: str) -> str:
    return f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{tag}"


def _local_name(tag: str) -> str:
    return re.sub(r"^\{.*\}", "", tag)
