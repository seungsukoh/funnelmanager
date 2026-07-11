# 폼 연동 가이드

## 개요

폼 연동 MVP는 Google Forms 또는 Microsoft Forms가 앱의 webhook으로 응답을 보내고, 앱은 이를 CSV 파일로 누적하는 방식이다.

```text
Forms -> Webhook -> inbox/form_responses.csv -> send_campaign.py
```

## Webhook 수신기 실행

로컬 테스트:

```powershell
$env:AUTOMAILER_WEBHOOK_TOKEN="dev-secret"
python receive_webhook.py --host 127.0.0.1 --port 8080 --output inbox\form_responses.csv
```

수신 URL:

```text
http://127.0.0.1:8080/webhooks/form-response
```

실제 Google Apps Script 또는 Power Automate에서 호출하려면 인터넷에서 접근 가능한 HTTPS 주소가 필요하다. 로컬 PC 테스트는 ngrok, Cloudflare Tunnel, 사내 테스트 서버 등을 사용한다.

PowerShell 로컬 호출 예:

```powershell
$headers = @{ "X-Automailer-Token" = "dev-secret" }
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/webhooks/form-response" -Headers $headers -ContentType "application/json" -InFile samples\webhook_payload.json
```

## 표준 payload

```json
{
  "source": "google_forms",
  "external_response_id": "response-123",
  "submitted_at": "2026-07-01T00:00:00Z",
  "fields": {
    "이름": "김민수",
    "이메일": "minsu@example.com",
    "event_name": "AI 세미나",
    "followup_url": "https://example.com/events/ai-followup",
    "참석여부": "참석",
    "마케팅동의": "예",
    "수신거부": "아니오"
  }
}
```

## 중복 처리

Webhook 수신기는 `source + external_response_id`를 기준으로 `webhook_idempotency_key`를 생성한다.

- 같은 `source`와 `external_response_id`가 다시 들어오면 CSV에 추가하지 않는다.
- 신규 응답이면 HTTP `202`를 반환한다.
- 중복 응답이면 HTTP `200`과 `"duplicate": true`를 반환한다.
- `external_response_id`가 비어 있으면 제출 시각을 제외한 payload 내용으로 key를 만든다.

Forms/Power Automate는 네트워크 오류나 타임아웃 때 같은 이벤트를 다시 보낼 수 있으므로, 이 중복 처리는 필수 안전장치다.

## Google Forms

Google Forms는 응답을 Google Sheets에 연결한 뒤 Apps Script `onFormSubmit` 트리거를 붙이는 방식이 가장 단순하다.

1. Google Forms 응답을 Google Sheets에 연결한다.
2. Sheets에서 Apps Script를 연다.
3. `integrations/google_forms_on_submit.js` 내용을 붙여 넣는다.
4. `WEBHOOK_URL`과 `WEBHOOK_TOKEN`을 수정한다.
5. 설치형 트리거에서 `onFormSubmit`을 폼 제출 시 실행하도록 설정한다.

Cloudflare Pages에 배포한 경우 webhook 주소는 다음 형식이다.

```text
https://<cloudflare-pages-domain>/webhooks/form-response
```

Cloudflare Pages 프로젝트에는 Secret으로 `FORM_WEBHOOK_TOKEN`을 추가한다. Apps Script의
`WEBHOOK_TOKEN`은 이 값과 같아야 한다. D1 바인딩 이름은 `DB`여야 하며, webhook은 폼 응답을
`form_responses`에 중복 방지 키로 저장한 뒤 `contacts` 명단에 반영한다.

### Google Sheets CSV 증분 동기화

Apps Script 없이 Google Sheets 응답 시트를 CSV로 게시하거나 export CSV URL을 사용할 수도 있다.

로컬 샘플:

```powershell
python sync_responses.py --source-csv samples\google_sheets_export.csv --output inbox\google_forms.csv --source-name google_sheets --response-id-column Timestamp
```

Google Sheets CSV URL 예:

```powershell
python sync_responses.py --source-csv "https://docs.google.com/spreadsheets/d/<spreadsheet-id>/export?format=csv&gid=<sheet-gid>" --output inbox\google_forms.csv --source-name google_sheets --response-id-column Timestamp
```

같은 응답은 `state/sync_state.json`에 저장된 key로 중복 수집하지 않는다.

## Microsoft Forms

Microsoft Forms는 Power Automate를 통해 webhook을 호출한다.

권장 Flow:

1. Trigger: `When a new response is submitted`
2. Action: `Get response details`
3. Action: `HTTP`
4. Method: `POST`
5. URI: `https://your-app.example.com/webhooks/form-response`
6. Header: `X-Automailer-Token: <shared-secret>`
7. Body: `integrations/power_automate_payload_example.json` 형태로 작성

## 수집된 응답 발송

Webhook 수신 후 생성된 CSV를 기존 퍼널 설정으로 실행한다.

```powershell
python send_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\funnel_config.json --campaign-id forms-demo
```

먼저 dry-run 결과와 `outbox/forms-demo_report.csv`를 확인한 뒤 실제 발송 옵션을 붙인다.

운영 절차는 `docs/operations_runbook.md`를 기준으로 진행한다.
