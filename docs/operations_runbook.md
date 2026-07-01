# 운영 런북

## 1. 폼 응답 수집기 실행

```powershell
$env:AUTOMAILER_WEBHOOK_TOKEN="dev-secret"
python receive_webhook.py --host 127.0.0.1 --port 8080 --output inbox\form_responses.csv
```

운영 환경에서는 `127.0.0.1`이 아니라 HTTPS로 접근 가능한 서버 주소가 필요하다.

## 2. Dry-run 실행

```powershell
python send_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\funnel_config.json --campaign-id forms-2026-07-01
```

확인할 파일:

```text
outbox/forms-2026-07-01_report.csv
```

검토 항목:

- 발송 예정 수
- 제외 수
- 제외 사유
- 매칭된 룰
- 선택된 템플릿
- 누락 변수

## 3. 테스트 발송

실제 수신자 대신 운영자 메일로만 보낸다.

```powershell
python send_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\funnel_config.json --campaign-id forms-test-1 --provider outlook --test-to your-email@example.com --send --outlook-display
```

`--outlook-display`는 Outlook 작성 창을 띄우고 자동 발송하지 않는다. 운영 검수 단계에서는 이 방식을 우선 사용한다.

## 4. 실제 발송

Outlook으로 발송:

```powershell
python send_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\funnel_config.json --campaign-id forms-live-1 --provider outlook --send
```

SendGrid로 발송:

```powershell
$env:MAIL_FROM_EMAIL="events@example.com"
$env:MAIL_FROM_NAME="Event Team"
$env:SENDGRID_API_KEY="SG.xxxxx"
python send_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\funnel_config.json --campaign-id forms-live-1 --provider sendgrid --send
```

## 5. 발송 후 확인

확인 파일:

- `outbox/<campaign-id>_report.csv`
- `state/send_history.jsonl`
- `state/lead_state.json`
- `state/lead_timeline.jsonl`

확인 항목:

- 실패 건수
- 스킵 사유
- 중복 제외
- 수신거부 제외
- provider 오류 메시지
- 리드별 마지막 단계와 다음 발송 가능 시각
- 리드별 타임라인 이벤트

## 6. 재실행 원칙

- 같은 `campaign-id`로 재실행하면 이미 성공한 수신자는 중복 발송되지 않는다.
- 템플릿이나 룰을 바꿔 다시 보내야 하면 새 `campaign-id`를 사용한다.
- 강제 재발송이 필요하면 `--allow-duplicates`를 사용할 수 있지만, 운영 사유를 별도로 기록해야 한다.

## 7. Drip campaign 실행

단계형 후속 메일은 `steps` 설정과 리드 상태 파일을 함께 사용한다.

먼저 발송 큐를 만든다.

```powershell
python plan_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\drip_config.json --campaign-id drip-2026-07-01 --output outbox\drip-2026-07-01_queue.csv
```

큐 파일에서 `ready`, `scheduled`, `skipped` 상태를 확인한 뒤 dry-run을 실행한다.

```powershell
python send_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\drip_config.json --campaign-id drip-2026-07-01
```

운영 확인 항목:

- `campaign_step`이 의도한 다음 단계로 이동했는지
- `next_send_at`이 과거인 리드만 발송됐는지
- `전환됨`, `제외`, `수신거부` 상태가 스킵됐는지
- `lead_timeline.jsonl`에 어떤 룰로 발송 또는 스킵됐는지 남았는지

특정 리드 타임라인 조회:

```powershell
python inspect_timeline.py --email minsu@example.com
```

## 8. 예약 실행과 승인 파일

자동 퍼널 운영은 바로 실제 발송하지 않고 먼저 승인 파일을 만든다.

```powershell
python run_due_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --campaign-id drip-daily
```

생성 파일:

- `outbox/due_queue.csv`
- `outbox/due_approval.csv`

운영자는 승인 파일에서 실제 발송할 행만 `approved=yes`로 바꾼다. 이후 승인된 고객만 미리보기로 처리한다.

```powershell
python run_due_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --campaign-id drip-daily --send-approved
```

실제 발송은 provider와 `--send`를 명시해야 한다.

```powershell
python run_due_campaign.py --contacts inbox\form_responses.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --campaign-id drip-daily --send-approved --provider outlook --send --outlook-display
```

완전 자동 발송으로 전환하기 전까지는 `--outlook-display` 또는 `--test-to`로 검수한다.

## 9. Windows 작업 스케줄러 연결

매일 오전 9시에 승인 파일만 만들려면 작업 스케줄러에서 다음 명령을 실행한다.

```powershell
python C:\workspace\projects\automailing\run_due_campaign.py --contacts C:\workspace\projects\automailing\inbox\form_responses.csv --funnel-config C:\workspace\projects\automailing\samples\drip_config.json --lead-state-path C:\workspace\projects\automailing\state\lead_state.json --campaign-id drip-daily --queue-output C:\workspace\projects\automailing\outbox\due_queue.csv --approval-output C:\workspace\projects\automailing\outbox\due_approval.csv
```

## 10. Gmail + Apps Script 소량 발송

Gmail 개인 계정으로 하루 100명 이하를 보낼 때는 전용 ESP 없이 Google Sheets와 Apps Script를 사용한다.

먼저 웹 화면에서 `발송 승인 준비`를 실행하고 보낼 고객만 승인한다. 이후 Gmail 발송용 CSV를 만든다.

```powershell
python export_gmail_queue.py --contacts inbox\form_responses.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --campaign-id gmail-daily --approval-path outbox\web_dashboard_approval.csv --output outbox\gmail_send_queue.csv
```

Google Sheets에 `outbox\gmail_send_queue.csv`를 가져온 뒤 Apps Script에 `integrations/gmail_apps_script_sender.js`를 붙여 넣고 `sendApprovedEmails`를 실행한다.

발송 후 Google Sheet의 `GmailQueue`를 CSV로 내려받거나, 공개/게시된 CSV 링크에서 결과 파일을 가져온다.

```powershell
python fetch_gmail_results.py --source "https://docs.google.com/spreadsheets/d/<sheet-id>/edit#gid=0" --output outbox\gmail_send_queue.csv
```

그다음 로컬 상태에 반영한다.

```powershell
python import_gmail_results.py --results outbox\gmail_send_queue.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --db-path state\send_history.jsonl --timeline-path state\lead_timeline.jsonl
```

반영 후 Gmail 결과와 고객 상태가 맞는지 비교한다.

```powershell
python compare_gmail_results.py --results outbox\gmail_send_queue.csv --lead-state-path state\lead_state.json --campaign-id gmail-daily
```

자세한 절차는 `docs/gmail_apps_script.md`를 따른다.
