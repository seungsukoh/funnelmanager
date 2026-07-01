# 쉬운 발송 준비 화면

## 실행

```powershell
python web_app.py --host 127.0.0.1 --port 8765
```

접속:

```text
http://127.0.0.1:8765
```

## 화면 흐름

사용자가 보는 화면은 다음 순서로 구성한다.

1. 명단 선택
2. 받을 사람 확인
3. 메일 흐름 확인
4. 메일 미리보기
5. 고객별 기록 확인
6. 테스트 발송

첫 화면의 `오늘 진행 순서`는 실제 운영 순서대로 배치한다.

1. 명단 확인
2. 단계별 메일
3. 발송 승인
4. 미리보기
5. Gmail 결과

각 단계는 현재 상태와 실행 버튼을 함께 보여주며, 다음에 할 작업은 강조해서 표시한다.
`Gmail 결과` 단계에서는 승인된 고객으로 Gmail 발송 준비 파일을 만들고, 발송 후 결과를 가져와 고객 상태에 반영한다.

## 메일 흐름 관리

`단계별 메일` 탭에서 퍼널 단계별 메시지를 관리한다.

- 어떤 고객에게 보낼지: 조건을 쉬운 문장으로 표시한다.
- 이 단계의 명단: 현재 받을 사람 확인 결과 중 이 단계에 해당하는 고객을 표시한다.
- 보낼 메일: 템플릿 이름을 선택하거나 새 이름을 입력한다.
- 다음 메일까지: 이 메일을 보낸 뒤 며칠 후 다음 단계로 넘길지 입력한다.
- 제목/본문: 화면에서 수정한 뒤 `메일 흐름 저장`을 누르면 템플릿 파일에 반영한다.
- Word 파일 불러오기: `.docx` 파일을 선택하면 Word 본문을 현재 단계의 메일 본문에 넣는다.

저장 대상:

- `samples/drip_config.json` 같은 메일 흐름 JSON
- `email_templates/*.subject.txt`
- `email_templates/*.txt`
- `email_templates/*.html`

## 발송 승인

`발송 승인` 탭은 실제 발송 전 마지막 확인 단계다.

- `발송 승인 준비`: 현재 명단과 고객 상태를 기준으로 오늘 보낼 메일만 모은다.
- 승인 체크: 실제 발송을 허용할 고객만 체크한다.
- `승인 목록 저장`: 승인 결과를 CSV 파일로 저장한다.

기본 승인 파일:

```text
outbox/web_dashboard_approval.csv
```

예약 실행기는 이 파일에서 `approved=yes`인 행만 처리한다.

## Gmail 결과 반영

Gmail + Apps Script로 발송한 뒤 Google Sheet 결과를 앱에 반영한다.

기본 파일:

```text
outbox/gmail_send_queue.csv
```

사용 방식:

- `Gmail 시트 링크`: Google Sheet 주소 또는 CSV export 주소
- `Gmail 발송 준비`: 승인된 고객만 `Gmail 결과 파일`에 저장
- `Google 연결`: 비공개 Google Sheet를 읽기 위한 Google 로그인 연결
- `비공개 시트 가져오기`: 로그인 권한으로 비공개 Google Sheet를 읽어 결과 파일 저장
- `Gmail 시트 가져오기`: 시트 결과를 `Gmail 결과 파일`로 저장
- `Gmail 결과 반영`: 성공/실패 결과를 고객 상태와 고객별 기록에 반영
- `Gmail 결과 확인`: Gmail 결과와 앱 고객 상태가 맞는지 비교

비공개 Sheet 사용 시 추가 파일:

- Google 인증 파일: `config/google_oauth_client.json`
- Google 토큰 파일: `state/google_sheets_token.json`
- Gmail 시트 이름: `GmailQueue`

`Gmail 확인` 탭에는 비공개 Google Sheet 연결 안내가 표시된다.

- Google Sheets API 열기
- OAuth Client 만들기
- 승인된 리디렉션 URI 확인
- Google 인증 파일/토큰 준비 상태 확인
- Google 연결 실행

반영 내용:

- `sent`: 고객 상태와 다음 퍼널 단계 업데이트
- `failed`: 실패 기록만 남기고 다음 단계로 이동하지 않음
- `pending`: 아직 보내지 않은 상태이므로 건너뜀

`Gmail 확인` 탭은 결과를 `같음`, `확인 필요`, `아직 대기`로 나누어 보여준다.

## 기본 샘플 설정

- 연락처: `samples/funnel_contacts.csv`
- 퍼널 설정: `samples/drip_config.json`
- 리드 상태: `samples/lead_state_drip.json`
- 큐 출력: `outbox/web_dashboard_queue.csv`
- Gmail 결과: `outbox/gmail_send_queue.csv`
- Google 인증 파일: `config/google_oauth_client.json`
- 타임라인: `outbox/web_dashboard_timeline.jsonl`

## 운영 원칙

웹 화면은 현재 실제 발송 버튼을 제공하지 않는다. 실제 발송 전에는 다음 순서를 따른다.

1. 받을 사람 확인
2. 메일 흐름 확인
3. 발송 승인 준비
4. 미리보기 만들기
5. 미리보기 결과와 고객별 기록 확인
6. Outlook display 모드 또는 ESP 테스트 발송
7. 실제 발송

## 쉬운 용어 기준

- `ready` -> 보낼 예정
- `scheduled` -> 나중에 보냄
- `skipped` -> 보내지 않음
- `sent` -> 미리보기 완료
- `lead` -> 고객
- `timeline` -> 고객별 기록
- `funnel` -> 메일 흐름
- `dry-run` -> 메일 미리보기

UX/UI 검토 내용은 `docs/ux_review.md`에 기록한다.
