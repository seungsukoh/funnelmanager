from __future__ import annotations

import argparse
import csv
import io
import json
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/oauth/google/callback"
DEFAULT_SHEET_NAME = "GmailQueue"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Gmail results from a private Google Sheet.")
    parser.add_argument("--source", help="Google Sheet URL or spreadsheet id.")
    parser.add_argument("--output", default="outbox/gmail_send_queue.csv", help="Output CSV path.")
    parser.add_argument("--credentials", default="config/google_oauth_client.json", help="OAuth client JSON path.")
    parser.add_argument("--token", default="state/google_sheets_token.json", help="Saved OAuth token JSON path.")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET_NAME, help="Sheet tab name.")
    parser.add_argument("--range-name", help="A1 range. Defaults to the whole sheet tab.")
    parser.add_argument(
        "--print-auth-url",
        action="store_true",
        help="Print a Google authorization URL instead of fetching results.",
    )
    parser.add_argument("--state-path", default="state/google_oauth_state.json", help="Temporary OAuth state path.")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI, help="OAuth redirect URI.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_auth_url:
        result = build_authorization_url(
            credentials_path=Path(args.credentials),
            token_path=Path(args.token),
            state_path=Path(args.state_path),
            redirect_uri=args.redirect_uri,
        )
        print(result["auth_url"])
        return 0

    if not args.source:
        raise SystemExit("--source is required unless --print-auth-url is used.")

    summary = fetch_private_results(
        source=args.source,
        output_path=Path(args.output),
        credentials_path=Path(args.credentials),
        token_path=Path(args.token),
        sheet_name=args.sheet_name,
        range_name=args.range_name,
    )
    print(f"rows={summary['rows']}")
    print(f"output={summary['output_path']}")
    print(f"spreadsheet_id={summary['spreadsheet_id']}")
    print(f"sheet_name={summary['sheet_name']}")
    return 0


def build_authorization_url(
    *,
    credentials_path: Path,
    token_path: Path,
    state_path: Path,
    redirect_uri: str,
) -> dict[str, str]:
    client = _load_oauth_client(credentials_path)
    state = secrets.token_urlsafe(24)
    session = {
        "state": state,
        "credentials_path": str(credentials_path),
        "token_path": str(token_path),
        "redirect_uri": redirect_uri,
        "created_at": int(time.time()),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SHEETS_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return {
        "auth_url": f"{client['auth_uri']}?{urlencode(params)}",
        "redirect_uri": redirect_uri,
        "state_path": str(state_path),
    }


def complete_authorization(*, state_path: Path, code: str, state: str) -> dict[str, str]:
    if not code:
        raise ValueError("Google authorization code is missing.")
    if not state_path.exists():
        raise ValueError("Google 연결 준비 기록을 찾지 못했습니다. 웹 화면에서 Google 연결을 다시 누르세요.")

    session = json.loads(state_path.read_text(encoding="utf-8"))
    expected_state = str(session.get("state") or "")
    if not expected_state or state != expected_state:
        raise ValueError("Google 연결 상태값이 맞지 않습니다. 웹 화면에서 Google 연결을 다시 누르세요.")

    credentials_path = Path(str(session.get("credentials_path") or ""))
    token_path = Path(str(session.get("token_path") or ""))
    redirect_uri = str(session.get("redirect_uri") or DEFAULT_REDIRECT_URI)
    client = _load_oauth_client(credentials_path)
    token = _post_form(
        client["token_uri"],
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    _save_token(token_path, _normalize_token(token))
    try:
        state_path.unlink()
    except OSError:
        pass
    return {"token_path": str(token_path), "connected": "true"}


def fetch_private_results(
    *,
    source: str,
    output_path: Path,
    credentials_path: Path,
    token_path: Path,
    sheet_name: str = DEFAULT_SHEET_NAME,
    range_name: str | None = None,
) -> dict[str, object]:
    access_token = _valid_access_token(credentials_path=credentials_path, token_path=token_path)
    spreadsheet_id = spreadsheet_id_from_source(source)
    values = _fetch_values(
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        range_name=range_name,
        access_token=access_token,
    )
    text = _values_to_csv_text(values)
    _ensure_gmail_results_csv(text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8-sig", newline="")
    rows, columns = _count_rows(text)
    return {
        "rows": rows,
        "columns": columns,
        "output_path": str(output_path),
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
    }


def spreadsheet_id_from_source(source: str) -> str:
    value = source.strip()
    if not value:
        raise ValueError("Gmail 시트 링크가 비어 있습니다.")

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
        if not match:
            raise ValueError("Google Sheet 주소에서 spreadsheet id를 찾지 못했습니다.")
        return match.group(1)

    if "/" in value or " " in value:
        raise ValueError("Google Sheet 주소 또는 spreadsheet id를 입력하세요.")
    return value


def _load_oauth_client(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"Google 인증 파일을 찾지 못했습니다: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("installed") or data.get("web") or data
    client_id = str(raw.get("client_id") or "").strip()
    client_secret = str(raw.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ValueError("Google 인증 파일에 client_id/client_secret이 필요합니다.")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": str(raw.get("auth_uri") or "https://accounts.google.com/o/oauth2/v2/auth"),
        "token_uri": str(raw.get("token_uri") or "https://oauth2.googleapis.com/token"),
    }


def _valid_access_token(*, credentials_path: Path, token_path: Path) -> str:
    token = _load_token(token_path)
    access_token = str(token.get("access_token") or "")
    expires_at = float(token.get("expires_at") or 0)
    if access_token and expires_at > time.time() + 60:
        return access_token

    refresh_token = str(token.get("refresh_token") or "")
    if not refresh_token:
        raise ValueError("Google 연결 토큰이 없습니다. 먼저 웹 화면에서 Google 연결을 완료하세요.")

    client = _load_oauth_client(credentials_path)
    refreshed = _post_form(
        client["token_uri"],
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    merged = {**token, **_normalize_token(refreshed), "refresh_token": refresh_token}
    _save_token(token_path, merged)
    return str(merged["access_token"])


def _load_token(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def _save_token(path: Path, token: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_token(token: dict[str, object]) -> dict[str, object]:
    normalized = dict(token)
    expires_in = int(normalized.get("expires_in") or 0)
    if expires_in:
        normalized["expires_at"] = int(time.time()) + expires_in
    return normalized


def _post_form(url: str, data: dict[str, str]) -> dict[str, object]:
    encoded = urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    return _read_json_response(request)


def _fetch_values(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    range_name: str | None,
    access_token: str,
) -> list[list[object]]:
    a1_range = range_name.strip() if range_name and range_name.strip() else _quote_sheet_name(sheet_name)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}/values/"
        f"{quote(a1_range, safe='')}?majorDimension=ROWS"
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
    response = _read_json_response(request)
    values = response.get("values")
    if not isinstance(values, list):
        raise ValueError("Google Sheet에서 값을 읽지 못했습니다.")
    return values


def _read_json_response(request: urllib.request.Request) -> dict[str, object]:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ValueError(f"Google API 요청 실패: {error.code} {detail}") from error
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _quote_sheet_name(sheet_name: str) -> str:
    cleaned = sheet_name.strip() or DEFAULT_SHEET_NAME
    escaped = cleaned.replace("'", "''")
    return f"'{escaped}'"


def _values_to_csv_text(values: list[list[object]]) -> str:
    if not values:
        raise ValueError("Google Sheet에 데이터가 없습니다.")

    width = max(len(row) for row in values)
    headers = [str(value) for value in values[0]]
    if len(headers) < width:
        headers.extend(f"extra_{index}" for index in range(len(headers) + 1, width + 1))

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in values[1:]:
        normalized = [str(value) for value in row]
        if len(normalized) < len(headers):
            normalized.extend("" for _ in range(len(headers) - len(normalized)))
        writer.writerow(normalized[: len(headers)])
    return output.getvalue()


def _ensure_gmail_results_csv(text: str) -> None:
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
