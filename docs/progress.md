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
- 웹 화면을 퍼널 단계 중심으로 재구성: 각 단계에서 명단과 메일 내용을 좌우로 분리
- Word `.docx` 불러오기 API 추가: Word 본문을 단계별 메일 본문 입력칸에 반영
- 단계명 표시 개선: 내부 ID 대신 `참석 고객 첫 메일`, `미참석 고객 첫 메일`처럼 표시
- 메일 흐름 저장 안전장치 추가: 제목/본문이 실제로 바뀐 템플릿만 다시 저장
- 발송 승인 화면/API 추가: 오늘 보낼 메일을 승인 파일로 만들고 체크한 대상만 승인 저장
- 예약 실행 CLI 추가: `run_due_campaign.py`
- 예약 실행 smoke test 통과: ready 1건, scheduled 1건, skipped 2건 승인 파일 생성
- 승인된 대상만 dry-run 처리 smoke test 통과: 승인 1건 처리, 발송 미리보기 1건, 실패 0건
- Gmail + Apps Script 소량 발송 방향 확정: 개인 Gmail 하루 100명 이하 운영 기준
- Gmail 발송용 큐 export CLI 추가: `export_gmail_queue.py`
- Gmail Apps Script 발송 스크립트 추가: `integrations/gmail_apps_script_sender.js`
- Gmail 운영 가이드 작성: `docs/gmail_apps_script.md`
- Gmail 발송 결과 import CLI 추가: `import_gmail_results.py`
- Gmail 결과 import 샘플 추가: `samples/gmail_results.csv`
- 웹 화면에 `Gmail 결과 반영` 버튼/API 추가
- Gmail Sheet 결과 다운로드 CLI 추가: `fetch_gmail_results.py`
- Gmail 결과와 고객 상태 비교 CLI 추가: `compare_gmail_results.py`
- 웹 화면에 `Gmail 시트 가져오기`, `Gmail 결과 확인`, `Gmail 확인` 탭/API 추가
- 비공개 Google Sheet OAuth 읽기 CLI 추가: `fetch_private_gmail_results.py`
- 웹 화면에 `Google 연결`, `비공개 시트 가져오기` 버튼/API 추가
- Google OAuth 인증 파일 예시와 gitignore 보강: `config/google_oauth_client.example.json`
- 웹 화면 `Gmail 확인` 탭에 비공개 Google Sheet 설정 안내/상태 확인 추가
- UX/UI 검토 메모 작성: `docs/ux_review.md`
- 웹 첫 화면을 `오늘 진행 순서` 카드형 흐름으로 개선
- 다음 작업 강조와 단계별 상태 문구 추가
- 웹 화면에 승인된 고객 기준 `Gmail 발송 준비` 버튼/API 추가
- 비공개 Google Sheet 업로드 CLI/API/버튼 추가: `upload_private_gmail_queue.py`
- Google OAuth 범위를 Sheets 읽기/쓰기 권한으로 확장
- Cloudflare Pages 자동 배포용 Vite 프론트엔드 구조 추가: `frontend/`
- Cloudflare Pages 연결 가이드 작성: `docs/cloudflare_pages.md`
- Cloudflare Pages 루트 빌드 오류 대응: 루트 `package.json`에서 `frontend` 빌드 후 `dist/` 생성 지원
- Cloudflare 화면을 임시 배포 확인 화면에서 실제 퍼널 메일 운영 화면으로 교체
- Vite 화면에서 명단 확인/단계별 메일/발송 승인/미리보기/Gmail 결과 탭과 Python API 호출 연결
- Cloudflare Pages Functions 미리보기 백엔드 추가: 명단/메일 흐름/승인/미리보기/Gmail 결과 샘플 API 제공
- Cloudflare D1 저장소 지원 추가: D1 바인딩 `DB`가 있으면 메일 흐름/승인/Gmail 결과 저장
- Cloudflare Google OAuth/Sheets Functions 추가: OAuth URL 생성, 콜백 토큰 저장, Sheet 업로드/가져오기 기반 구현
- Cloudflare Gmail API 테스트 발송 추가: 테스트 수신자 1명만 허용, 발송 로그 D1 저장
- Gmail API 테스트 발송 검증: JS/Python 문법 검사, Vite 빌드, OAuth 권한 URL, 준비 전 무발송 응답, frontend audit 통과
- Google 상태 확인 UX 보강: 상태 API 실패도 화면에 표시하고 `/api/google/status` 브라우저 직접 확인 지원

### 진행 중

- Outlook display 모드 사용자 테스트 준비
- 실제 provider 발송 후 lead_state 업데이트 검증 준비
- Windows 작업 스케줄러 연결 절차 검증 준비
- 비공개 Gmail Sheet OAuth를 실제 운영 Google 계정으로 검증 준비
- 쉬운 운영 흐름 기준으로 사용자 테스트 준비
- Cloudflare 배포 후 사용할 백엔드 구조 검토
- Cloudflare Functions 미리보기 백엔드에서 실제 D1/R2/Google OAuth 백엔드로 전환 설계
- Cloudflare Google OAuth Secret과 실제 Google Sheet 운영 계정 검증 준비
- Gmail API 직접 발송은 테스트 발송 검증 단계로 제한

### 다음 작업

- 테스트 수신자 본인 이메일로 Gmail API 직접 발송 검증
- 승인 명단 전체 발송 전 이중 확인/일일 제한/중복 방지 잠금장치 설계
- Cloudflare Pages에 `GOOGLE_OAUTH_CLIENT` Secret 추가 후 Google 연결 검증
- 운영 Google Sheet URL로 `비공개 시트에 올리기`와 `결과 가져오기` 실제 테스트
- Cloudflare Pages 프로젝트에 D1 바인딩 `DB` 연결 후 저장 동작 확인
- Cloudflare Pages 재배포 후 실제 퍼널 메일 운영 화면 표시 확인
- Vite 화면의 버튼 동작을 클라우드 백엔드에서 실행할 API 구조 결정
- Cloudflare Pages에서 GitHub 저장소 연결 및 production branch `main` 배포 확인
- Python 로컬 API를 Cloudflare Worker/D1/R2 또는 별도 Python 서버로 분리할지 결정
- Outlook 실제 발송은 사용자 테스트 주소와 Outlook 로그인 상태 확인 후 진행
- 실제 provider 발송 후 lead_state 업데이트 검증
- 데이터 소스/필드 매핑 화면 추가
- Word 본문 변환에서 표/서식 보존 범위 사용자 검증
- 웹 화면에서 테스트 수신자 입력 후 승인 대상만 Outlook display로 여는 기능 추가
- Windows 작업 스케줄러 등록/해제 스크립트 추가
- 실제 Google Cloud OAuth Client 생성 및 비공개 Sheet 업로드/가져오기 테스트
- Gmail 결과 확인에서 확인 필요 항목만 다시 처리하는 운영 흐름 추가
- Google Apps Script 발송 실행까지 앱에서 안내/자동화할지 검토

### 리스크

- Outlook 자동 발송은 회사 보안 정책에 따라 경고창 또는 차단이 발생할 수 있다.
- Word 문서를 이메일 본문으로 변환하면 복잡한 서식은 유지되지 않을 수 있다.
- Microsoft Forms는 직접 API보다 Power Automate webhook 방식이 현실적이다.
