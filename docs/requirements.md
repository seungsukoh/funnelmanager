# 자동 퍼널 메일 관리 앱 요구사항

작성일: 2026-07-01

## 1. 제품 개요

이 앱은 Google Forms, Microsoft Forms, CSV, XLSX 등에서 수집된 응답 데이터를 기반으로 조건별로 다른 이메일을 자동 발송하는 관리자용 자동 퍼널 관리 도구다.

핵심 흐름은 다음과 같다.

```text
응답 수집 -> 필드 매핑/정규화 -> 조건 판단 -> 템플릿 렌더링 -> 발송 -> 결과 추적
```

제품의 목적은 단순 대량 발송이 아니라, 각 응답자의 상태와 응답값에 따라 적절한 후속 메일을 안전하게 보내고, 왜 어떤 메일이 발송되었는지 추적 가능하게 만드는 것이다.

## 2. 주요 사용자

### 운영자

- 폼 응답 또는 연락처 파일을 등록한다.
- 필드 매핑, 템플릿, 퍼널 조건을 설정한다.
- 테스트 발송과 dry-run 결과를 확인한다.
- 발송 실패, 중복 제외, 수신거부 처리를 확인한다.

### 승인자

- 실제 발송 전 대상 수, 조건, 템플릿, 동의 기준을 검토한다.
- 승인 또는 반려한다.
- 발송 사고 방지를 위해 변경 이력을 확인한다.

### 관리자

- 발신 계정, API 키, 권한, 수신거부 목록, 보관 정책을 관리한다.
- 감사 로그와 전체 발송 정책을 관리한다.

## 3. MVP 목표

1차 MVP는 복잡한 마케팅 자동화 플랫폼이 아니라, 폼/파일 기반 응답을 조건별로 분류하고 안전하게 이메일을 보내는 운영 도구로 만든다.

### MVP에 포함

- CSV/XLSX 연락처 및 응답 파일 업로드
- Google Forms 응답 연동을 위한 webhook 또는 Google Sheets 기반 수집 구조
- Microsoft Forms 응답 연동을 위한 Power Automate webhook 수신 구조
- 필드 매핑과 필수값 검증
- 조건 기반 템플릿 선택
- HTML/텍스트 템플릿 변수 치환
- Word `.docx` 템플릿을 PDF 첨부 또는 단순 본문 변환에 활용
- SendGrid, Postmark, Outlook, dry-run 발송
- 테스트 발송
- 발송 전 dry-run 결과 확인
- 수신거부/차단 목록 제외
- 중복 발송 방지
- 발송 성공/실패/스킵 로그
- 간단한 관리자 화면 또는 CLI 기반 운영

### MVP에서 제외

- 복잡한 드래그앤드롭 퍼널 빌더
- SMS, 카카오톡, 전화 등 멀티채널 자동화
- AI 카피 자동 생성
- A/B 테스트
- 고급 CRM 기능
- 실시간 웹 행동 추적
- 대규모 조직 권한 관리
- 전용 IP 워밍업 자동화

## 4. 핵심 개념

### 데이터 소스

응답이 들어오는 출처다.

- CSV
- XLSX
- Google Forms via Google Sheets 또는 Apps Script webhook
- Microsoft Forms via Power Automate webhook
- 수동 입력

### 연락처

메일을 받을 수 있는 사람이다.

필수 속성:

- 이메일
- 이름
- 출처
- 동의 상태
- 수신거부 상태
- 태그
- 커스텀 필드

### 폼 응답

폼 제출 또는 업로드 파일의 한 행이다.

필수 속성:

- 원본 응답 ID
- 원본 payload
- 정규화된 필드
- 제출 시각
- 처리 상태
- 연결된 연락처

### 퍼널

하나의 자동화 캠페인이다.

예:

- 세미나 신청자 후속 관리
- 상담 신청 리드 응대
- 미결제자 리마인드
- 노쇼 대상 자료 공유
- VIP 신청자 별도 안내

### 룰

어떤 조건일 때 어떤 액션을 실행할지 정의한다.

예:

```text
조건: 참석 여부 = 참석
액션: 참석 감사 메일 발송
```

```text
조건: 참석 여부 = 미참석 AND 마케팅 동의 = 예
액션: 자료 공유 및 다음 이벤트 안내 메일 발송
```

### 액션

룰이 만족되었을 때 실행하는 동작이다.

- 이메일 발송
- 발송 예약
- 태그 추가
- 상태 변경
- 관리자 검토 큐로 이동
- 발송 제외 처리
- dry-run 결과 생성

## 5. 기능 요구사항

### FR-001 데이터 소스 등록

시스템은 CSV, XLSX, Google Forms, Microsoft Forms 데이터 소스를 등록할 수 있어야 한다.

필수 요구:

- 데이터 소스 이름 설정
- 데이터 소스 유형 선택
- 샘플 응답 미리보기
- 연결 상태 표시
- 마지막 동기화 시각 표시

### FR-002 CSV/XLSX 업로드

운영자는 CSV 또는 XLSX 파일을 업로드해 응답 데이터를 가져올 수 있어야 한다.

필수 요구:

- 첫 행을 컬럼명으로 인식
- 이메일 형식 검증
- 빈 이메일 행 제외
- 중복 이메일 또는 중복 응답 감지
- 업로드 결과 요약 제공

### FR-003 Google Forms 연동

Google Forms는 Google Sheets 응답 저장 또는 Apps Script webhook 방식으로 연동한다.

권장 MVP 방식:

- Google Forms 응답을 Google Sheets에 저장
- Apps Script `onFormSubmit` 트리거에서 앱 webhook으로 응답 전송

후속 방식:

- Google Sheets API로 주기적 증분 동기화
- 마지막 처리 row 또는 timestamp 저장

### FR-004 Microsoft Forms 연동

Microsoft Forms는 Power Automate webhook 방식으로 연동한다.

권장 MVP 방식:

- Microsoft Forms 제출 트리거
- Power Automate `Get response details`
- HTTP 액션으로 앱 webhook 호출

후속 방식:

- Microsoft Graph로 OneDrive/SharePoint Excel 응답 파일 읽기

### FR-005 필드 매핑

운영자는 원본 컬럼을 시스템 표준 필드에 매핑할 수 있어야 한다.

표준 필드:

- 이메일
- 이름
- 회사
- 전화번호
- 이벤트명
- 신청 유형
- 참석 여부
- 결제 상태
- 마케팅 동의 여부
- 제출 시각

필수 요구:

- 이메일 필드는 필수
- 이름 필드는 권장
- 매핑 저장
- 같은 데이터 소스 재사용 시 기존 매핑 자동 적용
- 필수 필드 누락 시 발송 단계로 진행 불가

### FR-006 데이터 정규화

시스템은 응답 데이터를 발송 가능한 형태로 정규화해야 한다.

필수 요구:

- 이메일 소문자 변환
- 앞뒤 공백 제거
- 동의값 표준화: 예/아니오, yes/no, true/false
- 날짜값 표준화
- 선택지 값 표준화
- 오류 행 리포트

### FR-007 퍼널 생성

운영자는 퍼널을 생성하고 데이터 소스와 연결할 수 있어야 한다.

필수 요구:

- 퍼널명
- 설명
- 데이터 소스
- 실행 방식: 수동, 자동, 예약
- 상태: 초안, 검수 대기, 승인됨, 활성, 일시정지, 종료

### FR-008 조건 룰 설정

운영자는 응답값, 연락처 상태, 태그, 이전 발송 결과, 시간 조건을 기반으로 룰을 만들 수 있어야 한다.

지원 조건:

- 필드 equals / not equals
- 필드 contains
- 필드 is empty / is not empty
- 날짜 before / after
- 태그 포함 여부
- 이전 메일 발송 여부
- 이전 메일 실패 여부
- 마지막 발송 후 N일 경과

필수 요구:

- AND 조건 지원
- OR 조건은 MVP 후속으로 가능
- 룰 우선순위 설정
- 어떤 룰에도 맞지 않을 때 기본 처리 설정
- 충돌 가능성이 있는 룰 경고

### FR-009 액션 설정

룰에 매칭되면 실행할 액션을 설정할 수 있어야 한다.

MVP 액션:

- 특정 템플릿으로 이메일 발송
- 발송하지 않고 스킵
- 관리자 검토 필요로 표시
- 태그 추가
- 상태 변경

후속 액션:

- N일 후 다음 단계 예약
- 조건 재평가
- CRM으로 전달
- webhook 호출

### FR-010 템플릿 관리

운영자는 이메일 템플릿을 만들고 관리할 수 있어야 한다.

필수 요구:

- 제목 템플릿
- HTML 본문
- 텍스트 본문
- 변수 삽입
- 템플릿 미리보기
- 테스트 발송
- 템플릿 버전 관리
- 사용 중인 템플릿 수정 시 재승인 요구

지원 변수 예:

```text
{{이름}}
{{email}}
{{회사}}
{{event_name}}
{{followup_url}}
{{신청유형}}
```

### FR-011 Word 템플릿 활용

운영자는 Word `.docx` 문서를 템플릿으로 활용할 수 있어야 한다.

MVP 권장 방식:

- Word 문서를 PDF 첨부로 생성
- 메일 본문은 HTML 템플릿으로 별도 관리

제한:

- Word 서식을 메일 본문으로 100% 유지하는 것은 보장하지 않는다.
- 복잡한 표, 이미지, 머리글, 바닥글은 이메일 본문 변환 시 깨질 수 있다.

### FR-012 발송 provider

시스템은 여러 발송 방식을 지원해야 한다.

MVP provider:

- dry-run
- Outlook 데스크톱 앱
- SendGrid
- Postmark

후속 provider:

- Microsoft Graph
- Gmail API
- AWS SES

필수 요구:

- provider별 발송 결과 저장
- provider message id 저장
- provider 오류 메시지 저장
- 발신자 주소 검증

### FR-013 dry-run

실제 발송 전 dry-run을 실행할 수 있어야 한다.

dry-run 결과에는 다음이 포함되어야 한다.

- 처리 대상 수
- 발송 예정 수
- 제외 수
- 제외 사유
- 룰 매칭 결과
- 사용할 템플릿
- 렌더링된 제목/본문 미리보기
- 누락 변수

### FR-014 테스트 발송

운영자는 실제 대상 대신 지정한 테스트 이메일로 발송할 수 있어야 한다.

필수 요구:

- 모든 수신자를 테스트 주소로 강제 대체
- 실제 개인화 값은 유지
- 테스트 메일임을 제목 또는 헤더에 표시하는 옵션
- 테스트 발송 기록 저장

### FR-015 승인 플로우

실제 발송 전 승인 단계를 둘 수 있어야 한다.

필수 요구:

- 작성자와 승인자 분리
- 승인 요청 전 dry-run 필수
- 승인 화면에서 예상 발송 수 확인
- 승인 화면에서 제외 대상 수 확인
- 승인 후 조건/템플릿 변경 시 재승인
- 반려 사유 기록

### FR-016 전역 발송 게이트

어떤 룰에 매칭되더라도 다음 조건 중 하나라도 해당하면 발송하지 않아야 한다.

- 이메일 형식 오류
- 수신거부 상태
- 마케팅 동의 없음
- 하드 바운스 이력
- 스팸 신고 이력
- 동일 캠페인/템플릿/수신자 중복 발송
- 일일 또는 시간당 발송량 제한 초과
- 발신자 계정 비활성

### FR-017 중복 발송 방지

시스템은 동일 응답 또는 동일 수신자에게 같은 캠페인 메일이 중복 발송되지 않도록 해야 한다.

기본 idempotency key:

```text
campaign_id + template_id + recipient_email + response_id
```

필수 요구:

- CSV/XLSX 재업로드 시 이미 처리한 행 감지
- Forms webhook 재전송 시 중복 처리 방지
- 강제 재발송 시 권한과 사유 요구

### FR-018 수신거부 관리

시스템은 수신거부 목록을 관리해야 한다.

필수 요구:

- 전역 수신거부
- 캠페인별 수신거부
- 로그인 없는 수신거부 링크
- 수신거부 즉시 반영
- 수신거부 이력 보관
- 발송 전 수신거부 목록 검사

### FR-019 반송/스팸 관리

시스템은 반송 및 스팸 신고 이벤트를 발송 제외 정책에 반영해야 한다.

MVP:

- 수동으로 반송/차단 목록 업로드
- 실패 사유 기록

후속:

- SendGrid/Postmark webhook으로 bounce/spam 이벤트 자동 수신
- 하드 바운스 자동 차단
- 소프트 바운스 반복 시 차단
- 스팸 신고 자동 차단

### FR-020 발송 모니터링

운영자는 발송 상태를 확인할 수 있어야 한다.

상태:

- 대기
- 예약됨
- 발송 중
- 성공
- 실패
- 재시도 예정
- 차단됨
- 중복 제외
- 수동 확인 필요

필수 요구:

- 수신자별 상태 조회
- 오류 사유 표시
- 재시도 횟수 표시
- 수동 재발송
- 발송 제외 처리

### FR-021 로그 및 감사

시스템은 모든 주요 행동과 발송 판단을 기록해야 한다.

수신자 이벤트:

- 수집
- 동의 확인
- 대상 선정
- 제외
- 발송 시도
- 성공
- 실패
- 수신거부
- 반송
- 스팸 신고

관리자 이벤트:

- 파일 업로드
- 데이터 소스 연결
- 필드 매핑 변경
- 룰 변경
- 템플릿 변경
- dry-run 실행
- 테스트 발송
- 승인
- 반려
- 실제 발송 시작
- 강제 재발송

## 6. 화면 요구사항

### 대시보드

- 전체 퍼널 상태
- 오늘 수집된 응답 수
- 오늘 발송 예정 수
- 성공/실패 수
- 승인 대기 항목
- 최근 오류
- 중복 발송 차단 내역

### 데이터 소스 화면

- 데이터 소스 목록
- 연결 상태
- 마지막 동기화 시각
- 샘플 응답 미리보기
- 필드 매핑
- 동기화 오류

### 퍼널 관리 화면

- 퍼널 목록
- 퍼널 생성/수정
- 룰 우선순위
- 조건 설정
- 액션 설정
- dry-run 실행
- 활성/일시정지/종료

### 템플릿 화면

- 템플릿 목록
- 제목/본문 편집
- 변수 삽입
- 샘플 데이터 미리보기
- 테스트 발송
- 버전 이력

### 검수/승인 화면

- 승인 대기 목록
- 변경 전/후 비교
- 예상 발송 수
- 제외 대상 수
- 테스트 결과
- 승인/반려

### 발송 모니터링 화면

- 발송 큐
- 수신자별 상태
- 실패 사유
- 재시도
- 발송 제외 처리
- 로그 다운로드

### 설정 화면

- 발신자 계정
- provider 설정
- 수신거부 목록
- 차단 목록
- 권한/역할
- 개인정보 보관 기간
- 감사 로그

## 7. 데이터 모델 초안

### Contact

- id
- email
- name
- phone
- company
- source
- consent_status
- unsubscribed_at
- tags
- custom_fields
- created_at
- updated_at

### ResponseSource

- id
- type
- name
- connection_config
- last_synced_at
- status
- created_at
- updated_at

### FormResponse

- id
- source_id
- external_response_id
- contact_id
- raw_payload
- normalized_fields
- submitted_at
- processed_status
- processed_at

### FieldMapping

- id
- source_id
- source_column
- target_field
- required
- transform_rule

### Funnel

- id
- name
- description
- status
- source_id
- created_at
- updated_at

### Rule

- id
- funnel_id
- name
- priority
- condition_json
- action_json
- enabled

### EmailTemplate

- id
- name
- subject
- body_html
- body_text
- word_template_path
- variables
- version
- status

### EmailMessage

- id
- response_id
- contact_id
- template_id
- provider
- to_email
- subject
- rendered_body_snapshot
- status
- idempotency_key
- provider_message_id
- error_message
- sent_at
- created_at

### DeliveryEvent

- id
- email_message_id
- event_type
- event_payload
- occurred_at

### Suppression

- id
- email
- scope
- reason
- source
- created_at

### AuditLog

- id
- actor_id
- action
- target_type
- target_id
- metadata
- created_at

## 8. 비기능 요구사항

### 보안

- API 키, OAuth 토큰, SMTP 비밀번호는 평문 저장 금지
- 환경변수 또는 secret manager 사용
- 관리자 권한 분리
- 개인정보 조회/다운로드 로그 기록
- HTTPS 사용

### 개인정보/컴플라이언스

- 거래성/운영 안내 메일과 광고성/마케팅 메일 구분
- 광고성 메일은 사전 동의 확인
- 수신거부 링크 포함
- 동의 일시, 출처, 문구 버전 보관
- 개인정보 보관 기간 설정
- 삭제 요청 대응 가능

### 신뢰성

- 모든 webhook은 idempotent하게 처리
- provider 장애 시 실패 상태 보존
- 실패 재시도 정책 제공
- 중복 발송 방지
- 발송 전 dry-run 필수화 가능

### 관측성

- 처리 로그
- 발송 로그
- provider 응답 코드
- 오류 리포트
- 캠페인별 성공/실패 통계

### 성능

- MVP 기준 수천 건 단위 배치 처리
- 후속 단계에서 큐/워커 기반 수만 건 처리
- provider rate limit 준수

### 사용성

- 비개발자가 필드 매핑과 조건을 설정할 수 있어야 한다.
- 조건은 코드가 아니라 문장형 UI로 표현해야 한다.
- 발송 전 예상 결과를 사람이 검토할 수 있어야 한다.
- 위험한 액션에는 확인과 승인 절차가 필요하다.

## 9. 단계별 개발 우선순위

### Phase 1: 로컬/파일 기반 MVP

- CSV/XLSX 업로드
- 필드 매핑
- 조건 기반 템플릿 선택
- HTML/텍스트 템플릿
- Outlook/SendGrid/Postmark/dry-run 발송
- 테스트 발송
- 중복 발송 방지
- 수신거부 목록
- 발송 로그

### Phase 2: 웹 관리자 화면

- 대시보드
- 데이터 소스 관리
- 퍼널/룰 관리
- 템플릿 관리
- dry-run 결과 화면
- 발송 모니터링

### Phase 3: 폼 연동

- Google Forms Apps Script webhook
- Google Sheets 증분 동기화
- Microsoft Forms Power Automate webhook
- webhook 중복 처리
- 폼 스키마 변경 감지

### Phase 4: 운영 안정화

- 승인 플로우
- 감사 로그
- 수신거부 링크
- bounce/spam webhook
- 재시도 큐
- rate limit
- 알림

### Phase 5: 고급 자동화

- 단계형 drip campaign
- 오픈/클릭 추적
- 세그먼트 저장
- A/B 테스트
- CRM 연동
- Microsoft Graph/Gmail API 발송

## 10. 수용 기준

MVP는 다음 조건을 만족하면 완료로 본다.

- 운영자가 CSV/XLSX 파일을 업로드할 수 있다.
- 이메일/이름 등 필수 필드를 매핑할 수 있다.
- 응답값에 따라 서로 다른 템플릿이 선택된다.
- 템플릿 변수 누락을 감지한다.
- dry-run으로 발송 예정/제외/실패 대상을 확인할 수 있다.
- 테스트 주소로 테스트 발송할 수 있다.
- Outlook 또는 외부 provider로 실제 발송할 수 있다.
- 수신거부 목록의 이메일은 발송되지 않는다.
- 같은 캠페인에서 같은 수신자에게 중복 발송되지 않는다.
- 발송 성공/실패/스킵 로그가 남는다.
- 특정 수신자에게 왜 어떤 메일이 갔는지 로그로 설명할 수 있다.
