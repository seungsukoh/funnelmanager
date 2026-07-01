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

Gmail + Apps Script로 발송한 뒤 Google Sheet의 결과 CSV를 `Gmail 결과 파일`에 지정하고 `Gmail 결과 반영`을 누른다.

기본 파일:

```text
outbox/gmail_send_queue.csv
```

반영 내용:

- `sent`: 고객 상태와 다음 퍼널 단계 업데이트
- `failed`: 실패 기록만 남기고 다음 단계로 이동하지 않음
- `pending`: 아직 보내지 않은 상태이므로 건너뜀

## 기본 샘플 설정

- 연락처: `samples/funnel_contacts.csv`
- 퍼널 설정: `samples/drip_config.json`
- 리드 상태: `samples/lead_state_drip.json`
- 큐 출력: `outbox/web_dashboard_queue.csv`
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
