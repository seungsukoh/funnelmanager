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

`메일 흐름` 탭에서 단계별 메시지를 관리한다.

- 어떤 고객에게 보낼지: 조건을 쉬운 문장으로 표시한다.
- 보낼 메일: 템플릿 이름을 선택하거나 새 이름을 입력한다.
- 다음 메일까지: 이 메일을 보낸 뒤 며칠 후 다음 단계로 넘길지 입력한다.
- 제목/본문: 화면에서 수정한 뒤 `메일 흐름 저장`을 누르면 템플릿 파일에 반영한다.

저장 대상:

- `samples/drip_config.json` 같은 메일 흐름 JSON
- `email_templates/*.subject.txt`
- `email_templates/*.txt`
- `email_templates/*.html`

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
3. 미리보기 만들기
4. 미리보기 결과와 고객별 기록 확인
5. Outlook display 모드 또는 ESP 테스트 발송
6. 실제 발송

## 쉬운 용어 기준

- `ready` -> 보낼 예정
- `scheduled` -> 나중에 보냄
- `skipped` -> 보내지 않음
- `sent` -> 미리보기 완료
- `lead` -> 고객
- `timeline` -> 고객별 기록
- `funnel` -> 메일 흐름
- `dry-run` -> 메일 미리보기
