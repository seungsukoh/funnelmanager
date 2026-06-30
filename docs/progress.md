# 진행 기록

## 2026-07-01

### PM 상태

- 현재 단계: Phase 1 로컬/파일 기반 MVP
- 목표: CSV/XLSX 응답을 읽고, 필드 매핑과 조건 룰에 따라 다른 메일 템플릿을 선택한 뒤 dry-run 또는 Outlook/ESP로 발송한다.
- 운영 원칙: 실제 발송보다 dry-run, 테스트 발송, 중복 방지, 수신거부 제외를 먼저 안정화한다.

### 완료

- 제품 요구사항 문서 작성: `docs/requirements.md`
- 기본 메일 발송 CLI 골격 작성
- CSV/XLSX 연락처 읽기
- HTML/텍스트 템플릿 렌더링
- SendGrid/Postmark/dry-run provider 구조
- Outlook 데스크톱 발송 provider 초안
- Word `.docx` 템플릿 단순 본문 변환 초안
- 필드 매핑 설정 파일 지원
- 조건 기반 퍼널 룰 설정 파일 지원
- dry-run 결과 리포트 생성
- 샘플 퍼널 설정 파일 작성: `samples/funnel_config.json`
- 조건 룰 dry-run smoke test 통과: 4건 중 발송 2건, 제외 2건
- 수신거부 목록 smoke test 통과: 4건 중 발송 1건, 제외 3건
- 기존 행별 템플릿 선택 dry-run 유지 확인: 2건 발송, 실패 0건
- Google Forms Apps Script webhook 예제 작성
- Microsoft Forms Power Automate payload 예제 작성
- webhook 응답 CSV 수신기 작성: `receive_webhook.py`
- webhook CSV 수신 smoke test 통과
- webhook 수집 CSV를 퍼널 실행기에 연결한 dry-run 통과: 2건 발송, 실패 0건
- webhook idempotency 처리 구현: `source + external_response_id` 기준 중복 수집 방지
- webhook idempotency smoke test 통과: 같은 응답 2회 입력 시 CSV 1행 유지
- 실제 HTTP webhook server smoke test 통과: POST 수신 후 CSV 생성
- HTTP webhook으로 생성된 CSV를 퍼널 실행기에 연결한 dry-run 통과: 1건 발송, 실패 0건
- 운영 런북 작성: `docs/operations_runbook.md`
- Google Sheets CSV 증분 동기화 구현: `sync_responses.py`
- Google Sheets 증분 동기화 smoke test 통과: 첫 실행 2건 추가, 재실행 0건 추가/2건 중복
- Google Sheets 동기화 CSV를 퍼널 실행기에 연결한 dry-run 통과: 2건 발송, 실패 0건
- 퍼널 전문가 검토 메모 작성: `docs/funnel_strategy.md`
- 리드 상태 저장 기반 추가: `state/lead_state.json`
- 룰 action 업데이트 지원: `set_status`, `add_tags`, `remove_tags`, `set_step`, `next_step`, `next_send_at`, `next_send_after_days`
- 상태 기반 스킵 smoke test 통과: 4건 중 발송 1건, `next_send_at` 미래 1건 제외, `전환됨` 1건 제외, 수신거부 1건 제외
- 리드 상태 단위 검증 통과: 상태/태그/단계/다음 발송일 저장 및 row enrichment 확인
- 단계형 drip campaign 설정 지원: `steps` 배열
- drip campaign 신규 리드 dry-run 통과: 4건 중 첫 단계 발송 2건, 제외 2건
- drip campaign 기존 리드 dry-run 통과: 4건 중 두 번째 단계 발송 1건, 상태/일정/수신거부 제외 3건
- 리드별 타임라인 JSONL 기록 추가: `state/lead_timeline.jsonl` 또는 `--timeline-path`
- 기존 flat rule 회귀 검증 통과: 4건 중 발송 2건, 제외 2건
- 기존 행별 템플릿 회귀 검증 통과: 2건 발송, 실패 0건
- 발송 큐 생성 CLI 추가: `plan_campaign.py`
- drip 발송 큐 smoke test 통과: ready 1건, scheduled 1건, skipped 2건
- 리드 타임라인 조회 CLI 추가: `inspect_timeline.py`
- 타임라인 조회 smoke test 통과: `minsu@example.com` 이벤트 필터링 확인
- 타임라인 조회 CLI Windows UTF-8 출력 보정
- 로컬 웹 관리자 대시보드 추가: `web_app.py`
- 웹 API smoke test 통과: defaults, plan, dry-run
- 웹 대시보드 문서 작성: `docs/web_dashboard.md`
- 로컬 서버 실행: `http://127.0.0.1:8765`
- 기본 브라우저 열기 완료
- 웹 화면을 쉬운 사용자 흐름으로 개편: 명단 선택 -> 받을 사람 확인 -> 메일 미리보기 -> 고객별 기록 확인
- 어려운 용어 치환: 큐/룰/dry-run/리드/타임라인을 보낼 예정/메일 흐름/미리보기/고객/고객별 기록으로 표시
- 쉬운 화면 smoke test 통과: 계획 4행, 미리보기 발송 1건, 제외 3건
- 브라우저에서 새 화면 다시 열기 완료
- Git 저장소 초기화 복구 및 GitHub 원격 연결: `https://github.com/seungsukoh/funnelmanager`
- 웹 화면에 `메일 흐름` 탭 추가: 고객 유형별 메일 이름, 다음 메일까지, 제목, 본문 편집 지원
- 메일 흐름 저장 API 추가: 퍼널 `steps`와 `email_templates` 템플릿 파일 동시 저장
- 메일 흐름 API smoke test 통과: 3단계 로드 및 첫 템플릿 제목 확인
- 새 웹 서버 실행 및 브라우저 열기 완료: `http://127.0.0.1:8765`

### 진행 중

- Outlook display 모드 사용자 테스트 준비
- 실제 provider 발송 후 lead_state 업데이트 검증 준비

### 다음 작업

- Outlook 실제 발송은 사용자 테스트 주소와 Outlook 로그인 상태 확인 후 진행
- 실제 provider 발송 후 lead_state 업데이트 검증
- 데이터 소스/필드 매핑 화면 추가
- 실제 발송 전 승인 단계와 테스트 수신자 입력 화면 추가

### 리스크

- Outlook 자동 발송은 회사 보안 정책에 따라 경고창 또는 차단이 발생할 수 있다.
- Word 문서를 이메일 본문으로 변환하면 복잡한 서식은 유지되지 않을 수 있다.
- Microsoft Forms는 직접 API보다 Power Automate webhook 방식이 현실적이다.
