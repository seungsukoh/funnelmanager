# Cloudflare Pages 자동 배포

목표는 `main` 브랜치에 푸시하면 Cloudflare Pages가 자동으로 빌드하고, 운영 URL에서 바로 확인하는 것이다.

## 현재 배포 구조

- `frontend/`: Vite 기반 Cloudflare Pages 화면
- `web_app.py`: 기존 Python 로컬 API와 파일 기반 처리
- Cloudflare Pages는 정적 프론트엔드 배포에 적합하다.
- 현재 Python API는 Cloudflare Pages 안에서 직접 실행되지 않는다.

즉, 지금 단계에서는 Cloudflare에서 화면을 바로 볼 수 있고, 실제 발송/파일 처리 기능은 로컬 Python API 또는 다음 단계의 클라우드 백엔드 연결이 필요하다.

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
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Build output directory | `dist` |

환경 변수에는 다음 값을 추가한다.

| 이름 | 값 |
| --- | --- |
| `NODE_VERSION` | `18` 또는 `20` |

이후 `main`에 푸시하면 Cloudflare Pages가 자동으로 새 버전을 배포한다.

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
