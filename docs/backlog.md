# 백로그

## Phase 1: 로컬/파일 기반 MVP

- [x] CSV 연락처 파일 읽기
- [x] XLSX 연락처 파일 읽기
- [x] HTML/텍스트 템플릿 렌더링
- [x] dry-run outbox 생성
- [x] SendGrid provider 초안
- [x] Postmark provider 초안
- [x] Outlook provider 초안
- [x] 필드 매핑 설정 파일
- [x] 조건 기반 템플릿 선택
- [x] 조건 기반 스킵 처리
- [x] dry-run 결과 CSV 리포트
- [x] 수신거부 목록 검증 smoke test
- [ ] Outlook display 모드 사용자 테스트

## Phase 2: 관리자 화면

- [x] 로컬 웹 대시보드
- [x] 사용자 친화 발송 준비 흐름
- [x] 발송 큐 화면
- [x] dry-run 결과 화면
- [x] 리드 상태 화면
- [x] 리드 타임라인 화면
- [x] PM 진행 기록 화면
- [ ] 데이터 소스 목록
- [ ] 필드 매핑 편집 화면
- [ ] 퍼널 룰 편집 화면
- [ ] 템플릿 미리보기
- [ ] 발송 이력 검색 화면

## Phase 3: 폼 연동

- [x] Google Forms Apps Script webhook 예제
- [x] Google Sheets 증분 동기화
- [x] Microsoft Forms Power Automate webhook 예제
- [x] Webhook CSV 수신기
- [x] Webhook 수집 CSV 캠페인 실행 smoke test
- [x] webhook idempotency 처리
- [x] webhook 로컬 테스트 payload
- [x] webhook HTTP server smoke test
- [x] 운영 런북

## Phase 3.5: 상태 기반 퍼널 엔진

- [x] 리드 상태 저장: 신규, 육성중, 관심있음, 전환됨, 제외, 수신거부
- [x] 태그 저장 및 룰 조건에서 사용
- [x] campaign step 저장
- [x] next_send_at 기반 예정 발송
- [x] 단계형 drip campaign 설정
- [x] 룰 match trace
- [x] 리드별 타임라인
- [x] 발송 큐 파일 생성
- [x] 리드 타임라인 조회 CLI
- [ ] 실제 provider 발송 후 lead_state 업데이트 검증

## Phase 4: 운영 안정화

- [ ] 승인 플로우
- [ ] 감사 로그
- [ ] 수신거부 링크
- [ ] bounce/spam webhook
- [ ] rate limit
- [ ] 알림
