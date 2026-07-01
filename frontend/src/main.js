import "./styles.css";

const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const workflow = [
  {
    title: "명단 확인",
    detail: "폼, 엑셀, Google Sheet에서 들어온 고객을 확인합니다.",
    status: "준비됨"
  },
  {
    title: "단계별 메일",
    detail: "퍼널 단계마다 다른 제목과 본문을 관리합니다.",
    status: "로컬 API 필요"
  },
  {
    title: "발송 승인",
    detail: "오늘 보낼 사람만 체크해서 승인합니다.",
    status: "로컬 API 필요"
  },
  {
    title: "미리보기",
    detail: "실제 발송 전 개인화된 메일 내용을 검토합니다.",
    status: "로컬 API 필요"
  },
  {
    title: "Gmail 결과",
    detail: "비공개 Google Sheet에 올리고 발송 결과를 반영합니다.",
    status: "연동 준비"
  }
];

function apiUrl(path) {
  return `${apiBase}${path}`;
}

async function loadDefaults() {
  const response = await fetch(apiUrl("/api/defaults"), {
    headers: { Accept: "application/json" }
  });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json();
}

function renderShell({ connected, defaults, error }) {
  const statusText = connected ? "API 연결됨" : "백엔드 연결 필요";
  const statusClass = connected ? "ok" : "warn";

  document.querySelector("#app").innerHTML = `
    <main class="page">
      <section class="hero">
        <div>
          <p class="eyebrow">Cloudflare Pages Preview</p>
          <h1>Funnel Manager</h1>
          <p class="lead">main 브랜치가 배포되면 이 화면이 Cloudflare에서 바로 열립니다. 실제 발송 기능은 Python API 또는 Cloudflare Worker 백엔드와 연결됩니다.</p>
        </div>
        <div class="status-panel">
          <span class="status ${statusClass}">${statusText}</span>
          <span class="status ok">Vite 빌드 준비됨</span>
        </div>
      </section>

      <section class="workflow" aria-label="오늘 진행 순서">
        ${workflow
          .map(
            (item, index) => `
              <article class="step">
                <span class="step-number">${index + 1}</span>
                <h2>${item.title}</h2>
                <p>${item.detail}</p>
                <strong>${connected ? "사용 가능" : item.status}</strong>
              </article>
            `
          )
          .join("")}
      </section>

      <section class="operations">
        <div class="panel">
          <h2>Cloudflare 자동 배포</h2>
          <ol>
            <li>GitHub 저장소를 Cloudflare Pages에 연결</li>
            <li>Production branch를 main으로 설정</li>
            <li>Root directory를 frontend로 설정</li>
            <li>Build command는 npm install && npm run build</li>
            <li>Output directory는 dist</li>
          </ol>
        </div>

        <div class="panel">
          <h2>현재 연결 상태</h2>
          ${
            connected
              ? `<dl class="config">
                  <div><dt>명단</dt><dd>${defaults.contacts || "-"}</dd></div>
                  <div><dt>메일 흐름</dt><dd>${defaults.funnel_config || "-"}</dd></div>
                  <div><dt>캠페인</dt><dd>${defaults.campaign_id || "-"}</dd></div>
                </dl>`
              : `<p class="muted">Cloudflare 화면은 배포 가능하지만, 현재 Python 로컬 API는 클라우드에서 실행되지 않습니다.</p>
                 <p class="error">${error || "API 연결 정보가 없습니다."}</p>`
          }
          <button id="checkApiButton" type="button">API 다시 확인</button>
        </div>
      </section>
    </main>
  `;

  document.querySelector("#checkApiButton").addEventListener("click", boot);
}

async function boot() {
  try {
    const defaults = await loadDefaults();
    renderShell({ connected: true, defaults });
  } catch (error) {
    renderShell({ connected: false, defaults: {}, error: error.message });
  }
}

boot();
