# Gmail + Apps Script 발송 가이드

## 언제 쓰는가

하루 100명 이하의 소량 발송이면 Gmail 개인 계정과 Google Apps Script로 시작할 수 있다. Outlook 없이도 동작한다.

권장 운영 기준:

- 개인 Gmail: 하루 20~90명 운영 권장
- Google Workspace: 하루 수백 명까지 운영 가능
- 대량/상시 운영: SendGrid, Brevo, Resend 같은 전용 발송 서비스 검토

## 전체 흐름

```text
로컬 앱에서 받을 사람 확인
-> 발송 승인
-> Gmail 발송용 CSV export
-> Google Sheet에 CSV 가져오기
-> Apps Script가 Gmail로 발송
```

## 1. 승인 파일 만들기

웹 화면에서 `발송 승인 준비`를 누르고 보낼 고객만 승인한다.

기본 파일:

```text
outbox/web_dashboard_approval.csv
```

## 2. Gmail 발송용 큐 만들기

승인된 고객만 Google Sheets에 올릴 CSV로 만든다.

```powershell
python export_gmail_queue.py --contacts samples\funnel_contacts.csv --funnel-config samples\drip_config.json --lead-state-path samples\lead_state_drip.json --campaign-id gmail-demo --approval-path outbox\web_dashboard_approval.csv --output outbox\gmail_send_queue.csv
```

출력 파일:

```text
outbox/gmail_send_queue.csv
```

이 파일에는 Gmail에서 바로 보낼 `email`, `subject`, `html_body`, `text_body`가 들어 있다.

## 3. Google Sheet 준비

1. 새 Google Sheet를 만든다.
2. 시트 이름을 `GmailQueue`로 만든다.
3. `outbox/gmail_send_queue.csv`를 가져온다.
4. Apps Script 편집기를 연다.
5. `integrations/gmail_apps_script_sender.js` 내용을 붙여 넣는다.
6. `SENDER_NAME`을 원하는 발신자 이름으로 바꾼다.

## 4. 테스트 발송

Apps Script에서 `sendApprovedEmails` 함수를 실행한다. 처음 실행할 때 Google 권한 승인이 필요하다.

발송 후 Google Sheet에서 확인한다.

- `status = sent`: 발송 성공
- `status = failed`: 발송 실패
- `sent_at`: 발송 시각
- `error`: 실패 사유

## 5. 매일 자동 실행

Apps Script에서 `installDailyTrigger`를 한 번 실행하면 매일 오전 9시에 `sendApprovedEmails`가 실행된다.

기본 스크립트는 안전하게 `DAILY_SEND_LIMIT = 90`으로 제한한다.

## 6. 발송 결과 가져오기

Gmail 발송 후 `GmailQueue` 시트를 CSV로 다운로드하거나 export URL로 저장한다. 그 결과를 로컬 앱에 반영한다.

웹 화면에서는 `Gmail 결과 파일`에 CSV 경로를 넣고 `Gmail 결과 반영`을 누른다.

터미널에서는 다음 명령을 사용한다.

```powershell
python import_gmail_results.py --results outbox\gmail_send_queue.csv --funnel-config samples\drip_config.json --lead-state-path state\lead_state.json --db-path state\send_history.jsonl --timeline-path state\lead_timeline.jsonl
```

반영 내용:

- `status=sent`: 발송 이력 저장, 고객 상태/다음 단계 업데이트, 고객별 기록 추가
- `status=failed`: 실패 이력 저장, 고객 상태는 이동하지 않음, 고객별 기록 추가
- `status=pending`: 아직 발송 전이므로 건너뜀

## 주의사항

- Gmail 개인 계정은 보통 하루 약 100명 수준으로 보는 것이 안전하다.
- 수신자 수 기준으로 계산된다.
- 새 계정은 한도가 더 낮거나 제한될 수 있다.
- 마케팅 메일은 수신 동의와 수신거부 처리가 필요하다.
- Gmail 발송 결과는 Google Sheet에 기록되므로, 운영 후 `import_gmail_results.py`로 로컬 상태에 반영한다.
