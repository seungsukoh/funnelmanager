# Automailing MVP

폼 또는 엑셀 연락처 파일을 읽어서 선택한 메일 템플릿으로 자동 발송하는 작은 도구입니다.

자체 SMTP 서버를 운영하지 않고 SendGrid 또는 Postmark 같은 외부 메일 API를 사용합니다. 기본 실행은 항상 dry-run이며, 실제 발송은 `--send` 옵션을 명시해야 합니다.

## 지원 범위

- CSV 연락처 파일
- XLSX 연락처 파일
- `{{이름}}`, `{{event_name}}` 같은 템플릿 변수 치환
- 행별 템플릿 선택
- 조건 기반 템플릿 선택
- Google Forms/Microsoft Forms webhook 수신기
- Word `.docx` 문서를 메일 본문 템플릿으로 사용
- 테스트 수신자 강제 지정
- 수신거부 목록 제외
- JSONL 발송 이력 기반 중복 발송 방지
- SendGrid/Postmark API 또는 Outlook 데스크톱 앱 발송
- Gmail + Google Apps Script 소량 발송 큐 export
- 비공개 Google Sheet OAuth 읽기
- dry-run outbox 파일 생성

## 빠른 실행

```powershell
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id demo
```

실행 후 `outbox/` 폴더에 렌더링된 메일이 저장됩니다. 실제 메일은 발송되지 않습니다.

## 조건 기반 퍼널 실행

`samples/funnel_config.json`처럼 필드 매핑과 조건 룰을 정의하면 응답값에 따라 다른 템플릿을 자동 선택할 수 있습니다.

```powershell
python send_campaign.py --contacts samples\funnel_contacts.csv --funnel-config samples\funnel_config.json --campaign-id funnel-demo
```

예시 룰:

- `참석여부 = 참석`이면 `event_followup` 템플릿 사용
- `참석여부 = 미참석`이면 `no_show_followup` 템플릿 사용
- `마케팅동의 = 아니오`이면 발송 제외
- `수신거부 = 예`이면 발송 제외

실행 후 `outbox/funnel-demo_report.csv`에서 행별 처리 결과를 확인할 수 있습니다.

## 리드 상태 기반 스킵

`--lead-state-path`를 사용하면 리드 상태, 태그, 현재 단계, 다음 발송 가능 시각을 반영해 발송 여부를 결정할 수 있습니다.

```powershell
python send_campaign.py --contacts samples\funnel_contacts.csv --funnel-config samples\funnel_config.json --lead-state-path samples\lead_state_seed.json --campaign-id lead-state-demo
```

상태 파일에서 `status`가 `전환됨`, `제외`, `수신거부`이면 전역 종료 조건으로 스킵합니다. `next_send_at`이 미래이면 아직 발송 시점이 아니므로 스킵합니다.

## 단계형 drip campaign

`steps` 설정을 사용하면 현재 단계와 다음 발송 가능 시각을 기반으로 순차 후속 메일을 보낼 수 있습니다.

```powershell
python send_campaign.py --contacts samples\funnel_contacts.csv --funnel-config samples\drip_config.json --lead-state-path samples\lead_state_drip.json --timeline-path outbox\drip_timeline.jsonl --campaign-id drip-demo
```

실행 후 확인할 파일:

- `outbox/drip-demo_report.csv`
- `outbox/drip_timeline.jsonl`

`steps`의 각 단계는 `conditions`, `template`, `set_status`, `add_tags`, `next_step`, `next_send_after_days`를 가질 수 있습니다.

## 발송 큐와 타임라인 조회

실제 발송 전 이번 실행에서 누가 발송 예정인지 큐 파일만 만들 수 있습니다.

```powershell
python plan_campaign.py --contacts samples\funnel_contacts.csv --funnel-config samples\drip_config.json --lead-state-path samples\lead_state_drip.json --campaign-id drip-demo --output outbox\drip_queue.csv
```

리드별 타임라인은 다음처럼 조회합니다.

```powershell
python inspect_timeline.py --timeline-path outbox\drip_timeline.jsonl --email minsu@example.com
```

## 로컬 웹 대시보드

브라우저에서 받을 사람 확인, 메일 미리보기, 고객 상태, 고객별 기록을 확인할 수 있습니다.
`단계별 메일` 탭에서는 퍼널 단계마다 해당 명단과 메일 내용을 나누어 보고, 보낼 메일 이름, 제목, 본문, 다음 메일까지의 일수를 수정할 수 있습니다.
Word `.docx` 파일을 불러와 현재 단계의 메일 본문에 넣을 수도 있습니다.
`발송 승인` 탭에서는 오늘 보낼 메일 목록을 만들고 실제 발송 허용 대상을 체크해 승인 파일로 저장합니다.

```powershell
python web_app.py --host 127.0.0.1 --port 8765
```

접속:

```text
http://127.0.0.1:8765
```

자세한 내용은 `docs/web_dashboard.md`를 참고하세요.

## 예약 실행과 발송 승인

오늘 보낼 메일을 확인하고 승인 파일을 만들 수 있습니다.

```powershell
python run_due_campaign.py --contacts samples\funnel_contacts.csv --funnel-config samples\drip_config.json --lead-state-path samples\lead_state_drip.json --campaign-id due-demo
```

승인 파일에서 `approved`를 `yes`로 바꾼 대상만 처리합니다. `--send`를 빼면 실제 발송 없이 미리보기만 만듭니다.

```powershell
python run_due_campaign.py --contacts samples\funnel_contacts.csv --funnel-config samples\drip_config.json --lead-state-path samples\lead_state_drip.json --campaign-id due-demo --send-approved
```

## Gmail + Apps Script 발송

하루 100명 이하 소량 발송은 Gmail + Apps Script로 시작할 수 있습니다. 승인된 고객만 Google Sheets에 올릴 CSV로 내보냅니다.
웹 화면에서는 `발송 승인` 후 `오늘 진행 순서`의 `Gmail 결과` 단계에서 `발송 준비`를 누르면 같은 파일을 만들 수 있습니다.

```powershell
python export_gmail_queue.py --contacts samples\funnel_contacts.csv --funnel-config samples\drip_config.json --lead-state-path samples\lead_state_drip.json --campaign-id gmail-demo --approval-path outbox\web_dashboard_approval.csv --output outbox\gmail_send_queue.csv
```

Google Sheets에서 `integrations/gmail_apps_script_sender.js`를 붙여 넣고 `sendApprovedEmails`를 실행합니다.

공개 또는 게시된 Google Sheet CSV 링크가 있으면 결과 파일을 바로 내려받을 수 있습니다.

```powershell
python fetch_gmail_results.py --source "https://docs.google.com/spreadsheets/d/<sheet-id>/edit#gid=0" --output outbox\gmail_send_queue.csv
```

고객 이메일이 들어간 시트는 비공개 Google Sheet로 운영하는 것이 안전합니다. Google OAuth 클라이언트 JSON을 `config\google_oauth_client.json`에 저장한 뒤 웹 화면에서 `Google 연결`을 한 번 완료하고 `비공개 시트 가져오기`를 누릅니다.
웹 화면의 `Gmail 확인` 탭에서 필요한 Google 설정과 준비 상태를 안내합니다.

```powershell
python fetch_private_gmail_results.py --source "https://docs.google.com/spreadsheets/d/<sheet-id>/edit#gid=0" --sheet-name GmailQueue --credentials config\google_oauth_client.json --token state\google_sheets_token.json --output outbox\gmail_send_queue.csv
```

발송 결과를 로컬 고객 상태에 반영합니다.

```powershell
python import_gmail_results.py --results outbox\gmail_send_queue.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --db-path state\send_history.jsonl --timeline-path state\lead_timeline.jsonl
```

Gmail 결과와 로컬 고객 상태가 맞는지 확인합니다.

```powershell
python compare_gmail_results.py --results outbox\gmail_send_queue.csv --lead-state-path state\lead_state.json --campaign-id gmail-demo
```

자세한 절차는 `docs/gmail_apps_script.md`를 참고하세요.

## 폼 응답 webhook 수신

Google Forms Apps Script 또는 Microsoft Power Automate에서 webhook을 호출하면 응답을 CSV로 누적할 수 있습니다.

```powershell
$env:AUTOMAILER_WEBHOOK_TOKEN="dev-secret"
python receive_webhook.py --host 127.0.0.1 --port 8080 --output inbox\form_responses.csv
```

자세한 연동 절차는 `docs/forms_integration.md`를 참고하세요.

일상 운영 절차는 `docs/operations_runbook.md`를 참고하세요.

## Google Sheets CSV 증분 동기화

Google Forms 응답이 연결된 Google Sheets를 CSV로 export할 수 있으면 새 응답만 inbox CSV로 누적할 수 있습니다.

```powershell
python sync_responses.py --source-csv samples\google_sheets_export.csv --output inbox\google_forms.csv --source-name google_sheets --response-id-column Timestamp
```

이후 기존 퍼널 실행기를 그대로 사용합니다.

```powershell
python send_campaign.py --contacts inbox\google_forms.csv --funnel-config samples\funnel_config.json --campaign-id google-forms-demo
```

## 실제 발송 설정

PowerShell 예시:

```powershell
$env:MAIL_PROVIDER="sendgrid"
$env:MAIL_FROM_EMAIL="events@example.com"
$env:MAIL_FROM_NAME="Event Team"
$env:SENDGRID_API_KEY="SG.xxxxx"
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id event-2026-07 --send
```

Postmark 예시:

```powershell
$env:MAIL_PROVIDER="postmark"
$env:MAIL_FROM_EMAIL="events@example.com"
$env:MAIL_FROM_NAME="Event Team"
$env:POSTMARK_SERVER_TOKEN="xxxxx"
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id event-2026-07 --send
```

## Outlook으로 발송

Outlook 데스크톱 앱이 설치되어 있고 계정이 로그인되어 있으면 SMTP/ESP 없이 기본 Outlook 계정으로 보낼 수 있습니다.

먼저 Outlook 작성 창만 띄워 확인합니다.

```powershell
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id outlook-test --provider outlook --test-to me@example.com --send --outlook-display
```

문제가 없으면 실제 발송합니다.

```powershell
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id outlook-test --provider outlook --test-to me@example.com --send
```

특정 Outlook 계정을 사용하려면 환경변수로 지정합니다.

```powershell
$env:OUTLOOK_ACCOUNT_EMAIL="sender@example.com"
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id outlook-live --provider outlook --send
```

회사 보안 정책에 따라 Outlook 자동화 경고창이 뜨거나 자동 발송이 차단될 수 있습니다. 이 경우 `--outlook-display`로 작성 창을 띄운 뒤 수동 발송하는 방식이 가장 안정적입니다.

## Word 문서를 템플릿으로 사용

Word `.docx` 본문에 `{{이름}}`, `{{event_name}}` 같은 변수를 넣어두면 연락처 파일의 값으로 치환됩니다.

```powershell
python send_campaign.py --contacts samples\contacts.csv --word-template templates\followup.docx --subject "{{event_name}} 후속 안내" --campaign-id word-test
```

Outlook으로 테스트 발송:

```powershell
python send_campaign.py --contacts samples\contacts.csv --word-template templates\followup.docx --subject "{{event_name}} 후속 안내" --campaign-id word-outlook-test --provider outlook --test-to me@example.com --send --outlook-display
```

현재 Word 템플릿은 문단과 표 텍스트를 이메일 HTML로 변환합니다. 복잡한 Word 서식을 100% 유지해야 하면 HTML 템플릿을 쓰는 편이 더 안정적입니다.

## 테스트 발송

실제 수신자에게 보내기 전에 모든 메일을 본인 주소로 강제 전송할 수 있습니다.

```powershell
python send_campaign.py --contacts samples\contacts.csv --template-name event_followup --campaign-id test-1 --test-to me@example.com --send
```

## 템플릿

기본 템플릿 위치는 `email_templates/`입니다.

한 템플릿은 세 파일로 구성됩니다.

- `event_followup.subject.txt`
- `event_followup.html`
- `event_followup.txt`

연락처 파일의 열 이름을 그대로 변수로 사용할 수 있습니다.

예:

```html
안녕하세요, {{이름}}님.
{{event_name}} 참석 후속 안내입니다.
```

## 행별 템플릿 선택

연락처 파일에 `template` 열을 추가하면 행마다 다른 템플릿을 사용할 수 있습니다.

```csv
이름,이메일,event_name,template
김민수,minsu@example.com,AI 세미나,event_followup
박지영,jiyoung@example.com,AI 세미나,no_show_followup
```

실행:

```powershell
python send_campaign.py --contacts contacts.csv --template-column template --campaign-id ai-seminar-2026 --send
```

## 수신거부 목록

`suppression.csv` 파일을 만들고 이메일 주소를 넣으면 해당 주소는 발송에서 제외됩니다.

```csv
email
blocked@example.com
```

실행:

```powershell
python send_campaign.py --contacts contacts.csv --template-name event_followup --suppression-list suppression.csv --send
```

## 중복 발송 방지

기본 idempotency key는 다음 값으로 만들어집니다.

```text
campaign_id + template_name + recipient_email
```

같은 캠페인에서 같은 템플릿을 같은 이메일에 다시 보내지 않습니다. 테스트를 반복하려면 `--campaign-id`를 새 값으로 바꾸거나 dry-run을 사용하세요.

## 폼즈/구글폼/네이버폼 사용 방식

가장 단순한 운영 방식은 폼 응답을 CSV 또는 XLSX로 내보낸 뒤 이 프로그램에 넣는 것입니다.

1. 폼에서 응답 다운로드
2. 연락처 파일의 이메일 열 확인
3. 템플릿 선택
4. dry-run으로 미리보기
5. `--test-to`로 테스트 발송
6. `--send`로 실제 발송

## 주의

- 마케팅성 메일은 별도 수신동의와 수신거부 링크가 필요합니다.
- SendGrid/Postmark의 SPF, DKIM, DMARC 도메인 인증을 먼저 완료하세요.
- 대량 발송 전 반드시 dry-run과 테스트 발송을 먼저 하세요.
