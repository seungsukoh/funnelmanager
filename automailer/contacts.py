from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


EMAIL_COLUMN_CANDIDATES = (
    "email",
    "e-mail",
    "email address",
    "mail",
    "메일",
    "메일주소",
    "이메일",
    "이메일주소",
    "전자메일",
)

NAME_COLUMN_CANDIDATES = ("name", "full name", "username", "이름", "성명", "고객명", "참가자명")


def load_contacts(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".xlsx":
        return load_xlsx(path)
    raise ValueError(f"Unsupported contact file extension: {path.suffix}")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            return []
        return [clean_row(row) for row in reader]


def load_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        with archive.open(sheet_path) as sheet_file:
            sheet = ElementTree.parse(sheet_file).getroot()

    rows = _read_sheet_rows(sheet, shared_strings)
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return []

    headers = [value.strip() for value in rows[0]]
    contacts = []
    for row in rows[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        contacts.append(clean_row(dict(zip(headers, padded))))
    return contacts


def clean_row(row: dict[str, object]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        cleaned[str(key).strip()] = "" if value is None else str(value).strip()
    return cleaned


def detect_column(rows: Iterable[dict[str, str]], candidates: Iterable[str]) -> str | None:
    for row in rows:
        keys = list(row.keys())
        lowered = {_normalise_header(key): key for key in keys}
        for candidate in candidates:
            found = lowered.get(_normalise_header(candidate))
            if found:
                return found
        break
    return None


def normalise_email(value: str) -> str:
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def _normalise_header(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value.strip().lower())


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    with archive.open("xl/sharedStrings.xml") as file:
        root = ElementTree.parse(file).getroot()
    values = []
    for item in root.iter(_ns("si")):
        parts = [text.text or "" for text in item.iter(_ns("t"))]
        values.append("".join(parts))
    return values


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    if "xl/workbook.xml" not in archive.namelist():
        return "xl/worksheets/sheet1.xml"

    with archive.open("xl/workbook.xml") as file:
        workbook = ElementTree.parse(file).getroot()
    first_sheet = workbook.find(f".//{_ns('sheet')}")
    if first_sheet is None:
        return "xl/worksheets/sheet1.xml"

    rel_id = first_sheet.attrib.get(_r_ns("id"))
    if not rel_id or "xl/_rels/workbook.xml.rels" not in archive.namelist():
        return "xl/worksheets/sheet1.xml"

    with archive.open("xl/_rels/workbook.xml.rels") as file:
        rels = ElementTree.parse(file).getroot()
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def _read_sheet_rows(root: ElementTree.Element, shared_strings: list[str]) -> list[list[str]]:
    rows = []
    for row in root.iter(_ns("row")):
        cells: list[str] = []
        for cell in row.iter(_ns("c")):
            ref = cell.attrib.get("r", "")
            index = _column_index(ref)
            while len(cells) <= index:
                cells.append("")
            cells[index] = _cell_value(cell, shared_strings)
        rows.append(cells)
    return rows


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter(_ns("t"))).strip()

    value_node = cell.find(_ns("v"))
    if value_node is None or value_node.text is None:
        return ""

    raw_value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)].strip()
        except (IndexError, ValueError):
            return ""
    return raw_value.strip()


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    if not letters:
        return 0
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _ns(tag: str) -> str:
    return f"{{http://schemas.openxmlformats.org/spreadsheetml/2006/main}}{tag}"


def _r_ns(tag: str) -> str:
    return f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}{tag}"
