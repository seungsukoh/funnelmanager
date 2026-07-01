# Cloudflare Pages 자동 배포

목표는 `main` 브랜치에 푸시하면 Cloudflare Pages가 자동으로 빌드하고, 운영 URL에서 바로 확인하는 것이다.

## 현재 배포 구조

- `frontend/`: Vite 기반 Cloudflare Pages 화면
- `functions/`: Cloudflare Pages Functions API
- `migrations/0001_core.sql`: D1 데이터베이스 초기 테이블
- `web_app.py`: 기존 Python 로컬 API와 파일 기반 처리

Cloudflare에서는 D1 바인딩이 있으면 저장형 API로 동작하고, D1 바인딩이 없으면 샘플 데이터 미리보기 API로 동작한다.
Google OAuth와 실제 Gmail 발송은 다음 단계에서 Secret과 토큰 저장소를 연결해야 한다.

## Cloudflare Pages 연결

Cloudflare Dashboard에서 설정한다.

1. Workers & Pages로 이동한다.
2. Create application을 누른다.
3. Pages 탭에서 Connect to Git을 선택한다.
4. GitHub 저장소 `seungsukoh/funnelmanager`를 선택한다.
5. Production branch를 `main`으로 설정한다.
6. Build settings를 다음처럼 넣는다.

| 항목 | 값 |
| --- | --- |
| Framework preset | Vite |
| Root directory | 비워 둠 |
| Build command | `npm run build` |
| Build output directory | `dist` |

환경 변수에는 다음 값을 추가한다.

| 이름 | 값 |
| --- | --- |
| `NODE_VERSION` | `18` 또는 `20` |

이후 `main`에 푸시하면 Cloudflare Pages가 자동으로 새 버전을 배포한다.

## 루트 디렉터리로 빌드하는 이유

Cloudflare Pages Functions는 저장소 루트의 `functions/` 폴더를 사용한다.
따라서 화면과 미리보기 API를 같이 배포하려면 Root directory를 비워 두고 루트에서 빌드하는 구성이 가장 단순하다.

Cloudflare 설정:

| 항목 | 값 |
| --- | --- |
| Root directory | 비워 둠 |
| Build command | `npm run build` |
| Build output directory | `dist` |

루트 빌드는 내부적으로 `frontend` 의존성을 설치하고 Vite 결과물을 루트 `dist/`에 만든다.
`functions/`는 Cloudflare Pages가 API로 배포한다.

Root directory를 `frontend`로 설정하면 정적 화면만 배포되고 `functions/` API는 빠진다.

## D1 데이터베이스 연결

Cloudflare Dashboard에서 D1 데이터베이스를 만든다.

1. Workers & Pages > D1 SQL Database로 이동한다.
2. 데이터베이스를 만든다. 예: `funnelmanager`
3. Pages 프로젝트 > Settings > Functions > D1 database bindings로 이동한다.
4. Variable name을 `DB`로 입력한다.
5. 방금 만든 D1 데이터베이스를 선택한다.
6. Pages를 다시 배포한다.

테이블은 첫 API 호출 시 자동으로 생성된다. 수동으로 만들고 싶으면 다음 SQL을 사용한다.

```text
migrations/0001_core.sql
```

Cloudflare CLI를 사용할 수 있으면 다음 흐름도 가능하다.

```powershell
npx wrangler d1 create funnelmanager
npx wrangler d1 execute funnelmanager --remote --file migrations/0001_core.sql
```

D1이 연결되면 화면 상단 상태가 `백엔드 연결됨`으로 바뀌고, 메일 흐름 저장/승인 저장 같은 변경사항이 D1에 남는다.

## Google OAuth와 비공개 Sheet 연결

Google Sheet 업로드/가져오기를 Cloudflare에서 실행하려면 D1과 Google OAuth Secret이 모두 필요하다.

Google Cloud Console에서 OAuth Client를 만든다.

1. Google Cloud Console > APIs & Services > Credentials로 이동한다.
2. OAuth Client ID를 만든다.
3. Application type은 Web application으로 선택한다.
4. Authorized redirect URI에 Cloudflare Pages URL을 넣는다.

```text
https://<cloudflare-pages-domain>/oauth/google/callback
```

Cloudflare Pages 프로젝트 설정에서 Secret을 추가한다.

권장 방식:

| 이름 | 값 |
| --- | --- |
| `GOOGLE_OAUTH_CLIENT` | Google에서 받은 OAuth Client JSON 전체 |

대체 방식:

| 이름 | 값 |
| --- | --- |
| `GOOGLE_CLIENT_ID` | OAuth client id |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |

설정 후 Pages를 다시 배포한다. 앱 화면에서 다음 순서로 진행한다.

1. `Gmail 시트 링크`에 운영 Google Sheet URL을 입력한다.
2. `Google 연결`을 누른다.
3. Google 권한 승인 화면에서 승인한다.
4. 앱으로 돌아와 `Google 상태`를 누른다.
5. `비공개 시트에 올리기` 또는 `결과 가져오기`를 실행한다.

권한 범위는 Google Sheets 읽기/쓰기이다.

```text
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/gmail.send
```

토큰은 D1의 `app_meta` 테이블에 저장된다. Cloudflare Secret에는 Google OAuth client 정보만 저장한다.

Gmail API 직접 발송은 안전하게 `테스트 발송`부터 시작한다.

1. `테스트 수신자`에 본인 이메일을 입력한다.
2. `Google 상태`에서 D1, OAuth Secret, Google 연결이 준비됐는지 확인한다.
3. `테스트 발송`을 누른다.
4. 받은 편지함에서 테스트 메일을 확인한다.

현재 직접 발송은 테스트 수신자 1명만 허용한다. 승인 명단 전체 발송은 별도 잠금장치와 재확인 화면을 붙인 뒤 활성화한다.

## 환경 변수

나중에 백엔드 API가 클라우드에 올라가면 Cloudflare Pages 환경 변수에 추가한다.

| 이름 | 예시 | 설명 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `https://api.example.com` | 프론트엔드가 호출할 API 주소 |

로컬 개발에서는 Vite 개발 서버가 `/api` 요청을 `http://127.0.0.1:8765`로 프록시한다.

```powershell
python web_app.py --host 127.0.0.1 --port 8765
cd frontend
npm install
npm run dev
```

프론트엔드 주소:

```text
http://127.0.0.1:5173
```

## 다음 백엔드 선택지

### 선택지 A: Cloudflare Worker + D1/R2

Cloudflare 안에서 완결되는 구조다.

- 고객/상태/발송 이력: D1
- 템플릿/첨부 파일/CSV: R2
- API: Worker 또는 Pages Functions
- 장점: Cloudflare Pages와 가장 잘 맞는다.
- 단점: 기존 Python 파일 기반 코드를 JavaScript/TypeScript API로 옮겨야 한다.

### 선택지 B: 별도 Python 서버 + Cloudflare DNS

Python 코드를 유지하는 구조다.

- API 서버: Render, Fly.io, Railway, Cloud Run, VPS 등
- 화면: Cloudflare Pages
- 도메인/DNS/보안: Cloudflare
- 장점: 기존 Python 코드를 더 많이 재사용한다.
- 단점: Cloudflare만으로 끝나지 않는다.

### 선택지 C: Cloudflare Tunnel

로컬 PC에서 실행 중인 Python 앱을 Cloudflare URL로 노출하는 구조다.

- 장점: 가장 빠르게 외부에서 볼 수 있다.
- 단점: PC가 꺼지면 앱도 내려가며, `main` 배포 자동화와는 맞지 않는다.

## PM 판단

사용자가 원하는 “main 배포 후 바로 보기”는 Cloudflare Pages + Vite가 맞다. 다만 “실제 자동 메일 운영”까지 클라우드에서 처리하려면 다음 단계에서 백엔드를 클라우드 구조로 분리해야 한다.
