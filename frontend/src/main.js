import "./styles.css";

const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const configFields = [
  "contacts",
  "funnel_config",
  "lead_state",
  "campaign_id",
  "queue_output",
  "approval_output",
  "gmail_source",
  "gmail_sheet_name",
  "gmail_results",
  "google_credentials",
  "google_token",
  "timeline"
];

const fallbackDefaults = {
  contacts: "samples/funnel_contacts.csv",
  funnel_config: "samples/drip_config.json",
  lead_state: "samples/lead_state_drip.json",
  campaign_id: "web-dashboard-demo",
  queue_output: "outbox/web_dashboard_queue.csv",
  approval_output: "outbox/web_dashboard_approval.csv",
  gmail_source: "",
  gmail_sheet_name: "GmailQueue",
  gmail_results: "outbox/gmail_send_queue.csv",
  google_credentials: "config/google_oauth_client.json",
  google_token: "state/google_sheets_token.json",
  timeline: "outbox/web_dashboard_timeline.jsonl"
};

const statusLabels = {
  ready: "보낼 예정",
  scheduled: "기다림",
  skipped: "제외",
  sent: "미리보기 완료",
  pending: "대기",
  failed: "실패"
};

const state = {
  config: { ...fallbackDefaults },
  backend: { connected: false, error: "" },
  activeTab: "people",
  notice: "",
  noticeTone: "info",
  busy: false,
  queueRows: [],
  queueCounts: {},
  flowSteps: [],
  templates: [],
  approvalRows: [],
  approvalCounts: {},
  previewRows: [],
  previewSummary: null,
  gmailRows: [],
  gmailCounts: {},
  googleSteps: []
};

function apiUrl(path) {
  return `${apiBase}${path}`;
}

async function api(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {})
    }
  });

  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`API 응답을 읽지 못했습니다. 상태 ${response.status}`);
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `API ${response.status}`);
  }
  return payload;
}

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formData() {
  const data = { ...state.config };
  for (const key of configFields) {
    const input = document.querySelector(`[data-config="${key}"]`);
    if (input) data[key] = input.value.trim();
  }
  state.config = data;
  return data;
}

function setNotice(message, tone = "info") {
  state.notice = message;
  state.noticeTone = tone;
}

function setBusy(value) {
  state.busy = value;
  render();
}

function countsText(counts = {}) {
  const parts = Object.entries(counts)
    .filter(([, value]) => Number(value) > 0)
    .map(([key, value]) => `${statusLabels[key] || key} ${value}건`);
  return parts.length ? parts.join(" / ") : "아직 확인 전";
}

function workflowStatus(id) {
  if (id === "people") return state.queueRows.length ? countsText(state.queueCounts) : "명단 확인 전";
  if (id === "flow") return state.flowSteps.length ? `메일 단계 ${state.flowSteps.length}개` : "메일 흐름 확인 전";
  if (id === "approval") {
    return state.approvalRows.length
      ? `승인 ${state.approvalCounts.approved || 0}건 / 대기 ${state.approvalCounts.waiting || 0}건`
      : "승인 전";
  }
  if (id === "preview") {
    return state.previewSummary ? `미리보기 ${state.previewSummary.sent || 0}건` : "미리보기 전";
  }
  if (id === "gmail") {
    return Object.keys(state.gmailCounts).length ? countsText(state.gmailCounts) : "Gmail 확인 전";
  }
  return "";
}

function nextStepId() {
  if (!state.queueRows.length) return "people";
  if (!state.flowSteps.length) return "flow";
  if (!state.approvalRows.length || !state.approvalCounts.approved) return "approval";
  if (!state.previewSummary) return "preview";
  return "gmail";
}

function tabButton(id, label) {
  const active = state.activeTab === id ? "active" : "";
  return `<button class="tab ${active}" type="button" data-tab="${id}">${label}</button>`;
}

function render() {
  const nextId = nextStepId();
  const backendClass = state.backend.connected ? "ok" : "warn";
  const backendText = state.backend.connected ? "백엔드 연결됨" : "백엔드 연결 필요";

  document.querySelector("#app").innerHTML = `
    <main class="page">
      <header class="app-header">
        <div>
          <p class="eyebrow">Funnel Manager</p>
          <h1>자동 메일 퍼널 관리</h1>
        </div>
        <div class="header-actions">
          <span class="badge ${backendClass}">${backendText}</span>
          <button type="button" data-action="refresh">새로 확인</button>
        </div>
      </header>

      ${state.backend.connected ? "" : renderBackendNotice()}
      ${state.notice ? `<div class="notice ${state.noticeTone}">${safe(state.notice)}</div>` : ""}

      <section class="workflow" aria-label="오늘 진행 순서">
        ${renderWorkflowCard("people", 1, "명단 확인", "받을 사람 확인", "명단 확인", nextId)}
        ${renderWorkflowCard("flow", 2, "단계별 메일", "메일 내용 관리", "메일 흐름", nextId)}
        ${renderWorkflowCard("approval", 3, "발송 승인", "오늘 보낼 사람 선택", "승인 만들기", nextId)}
        ${renderWorkflowCard("preview", 4, "미리보기", "발송 전 내용 확인", "미리보기", nextId)}
        ${renderWorkflowCard("gmail", 5, "Gmail 결과", "시트 업로드와 결과 반영", "Gmail 확인", nextId)}
      </section>

      <section class="layout">
        <aside class="side-panel">
          <h2>운영 설정</h2>
          ${renderConfigFields()}
        </aside>

        <section class="work-panel">
          <nav class="tabs" aria-label="작업 탭">
            ${tabButton("people", "명단 확인")}
            ${tabButton("flow", "단계별 메일")}
            ${tabButton("approval", "발송 승인")}
            ${tabButton("preview", "미리보기")}
            ${tabButton("gmail", "Gmail 결과")}
          </nav>
          ${renderActiveTab()}
        </section>
      </section>
    </main>
  `;

  bindEvents();
}

function renderBackendNotice() {
  return `
    <section class="backend-notice">
      <strong>Cloudflare 화면은 열렸습니다.</strong>
      <span>실제 명단 처리와 발송 준비는 Python API 또는 클라우드 백엔드 연결 후 실행됩니다.</span>
      ${state.backend.error ? `<small>${safe(state.backend.error)}</small>` : ""}
    </section>`;
}

function renderWorkflowCard(id, number, title, detail, actionLabel, nextId) {
  const highlighted = id === nextId ? "next" : "";
  return `
    <article class="workflow-card ${highlighted}">
      <span class="step-number">${number}</span>
      <h2>${title}</h2>
      <p>${detail}</p>
      <strong>${safe(workflowStatus(id))}</strong>
      <button type="button" data-action="${workflowAction(id)}">${actionLabel}</button>
    </article>`;
}

function workflowAction(id) {
  return {
    people: "plan",
    flow: "load-flow",
    approval: "prepare-approval",
    preview: "preview",
    gmail: "compare-gmail"
  }[id];
}

function renderConfigFields() {
  const fields = [
    ["contacts", "명단 파일"],
    ["funnel_config", "메일 흐름 파일"],
    ["lead_state", "고객 상태 파일"],
    ["campaign_id", "캠페인 이름"],
    ["queue_output", "명단 확인 파일"],
    ["approval_output", "발송 승인 파일"],
    ["gmail_source", "Gmail 시트 링크"],
    ["gmail_sheet_name", "Gmail 시트 이름"],
    ["gmail_results", "Gmail 준비/결과 파일"],
    ["google_credentials", "Google 인증 파일"],
    ["google_token", "Google 토큰 파일"],
    ["timeline", "고객별 기록 파일"]
  ];

  return fields
    .map(
      ([key, label]) => `
        <label class="field">
          <span>${label}</span>
          <input data-config="${key}" value="${safe(state.config[key] || "")}" />
        </label>`
    )
    .join("");
}

function renderActiveTab() {
  if (state.activeTab === "people") return renderPeopleTab();
  if (state.activeTab === "flow") return renderFlowTab();
  if (state.activeTab === "approval") return renderApprovalTab();
  if (state.activeTab === "preview") return renderPreviewTab();
  return renderGmailTab();
}

function renderPeopleTab() {
  return `
    <section class="tab-panel">
      <div class="panel-title">
        <div>
          <h2>명단 확인</h2>
          <p>오늘 보낼 수 있는 사람과 제외된 사람을 구분합니다.</p>
        </div>
        <button class="primary" type="button" data-action="plan">명단 확인</button>
      </div>
      <div class="summary-row">
        ${summaryItem("보낼 예정", state.queueCounts.ready || 0)}
        ${summaryItem("기다림", state.queueCounts.scheduled || 0)}
        ${summaryItem("제외", state.queueCounts.skipped || 0)}
      </div>
      ${renderTable(state.queueRows, ["status", "email", "template", "rule", "campaign_step", "next_send_at", "detail"], "아직 명단을 확인하지 않았습니다.")}
    </section>`;
}

function renderFlowTab() {
  return `
    <section class="tab-panel">
      <div class="panel-title">
        <div>
          <h2>단계별 메일</h2>
          <p>퍼널 단계마다 다른 제목과 본문을 관리합니다.</p>
        </div>
        <div class="button-row">
          <button type="button" data-action="load-flow">불러오기</button>
          <button class="primary" type="button" data-action="save-flow">저장</button>
        </div>
      </div>
      <div class="flow-list">
        ${
          state.flowSteps.length
            ? state.flowSteps.map(renderFlowStep).join("")
            : `<p class="empty">아직 메일 흐름을 불러오지 않았습니다.</p>`
        }
      </div>
    </section>`;
}

function renderFlowStep(step, index) {
  return `
    <article class="flow-step">
      <div class="flow-head">
        <div>
          <span class="mini-badge">${safe(step.stage_label || `단계 ${index + 1}`)}</span>
          <h3>${safe(step.audience || "대상 조건 없음")}</h3>
        </div>
        <label class="file-button">
          Word 불러오기
          <input type="file" accept=".docx" data-word-index="${index}" />
        </label>
      </div>
      <div class="flow-grid">
        <label class="field">
          <span>메일 이름</span>
          <input data-flow-index="${index}" data-flow-field="template" value="${safe(step.template || "")}" />
        </label>
        <label class="field">
          <span>다음 메일까지</span>
          <input data-flow-index="${index}" data-flow-field="next_send_after_days" value="${safe(step.next_send_after_days || "")}" />
        </label>
      </div>
      <label class="field">
        <span>제목</span>
        <input data-flow-index="${index}" data-flow-field="subject" value="${safe(step.subject || "")}" />
      </label>
      <label class="field">
        <span>본문</span>
        <textarea rows="8" data-flow-index="${index}" data-flow-field="text_body">${safe(step.text_body || "")}</textarea>
      </label>
    </article>`;
}

function renderApprovalTab() {
  return `
    <section class="tab-panel">
      <div class="panel-title">
        <div>
          <h2>발송 승인</h2>
          <p>체크한 사람만 Gmail 발송 준비 파일에 들어갑니다.</p>
        </div>
        <div class="button-row">
          <button type="button" data-action="prepare-approval">오늘 보낼 사람 만들기</button>
          <button class="primary" type="button" data-action="save-approval">승인 저장</button>
        </div>
      </div>
      <div class="summary-row">
        ${summaryItem("승인 대상", state.approvalCounts.ready || state.approvalRows.length)}
        ${summaryItem("승인 완료", state.approvalCounts.approved || 0)}
        ${summaryItem("대기", state.approvalCounts.waiting || 0)}
      </div>
      ${
        state.approvalRows.length
          ? renderApprovalTable()
          : `<p class="empty">아직 승인 목록을 만들지 않았습니다.</p>`
      }
    </section>`;
}

function renderApprovalTable() {
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>승인</th><th>고객</th><th>메일</th><th>단계</th><th>상세</th></tr>
        </thead>
        <tbody>
          ${state.approvalRows.slice(0, 80).map((row, index) => `
            <tr>
              <td><input type="checkbox" data-approval-index="${index}" ${row.approved === "yes" ? "checked" : ""} /></td>
              <td>${safe(row.email)}</td>
              <td>${safe(row.template)}</td>
              <td>${safe(row.campaign_step || row.rule || "")}</td>
              <td>${safe(row.detail || row.next_send_at || "")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderPreviewTab() {
  return `
    <section class="tab-panel">
      <div class="panel-title">
        <div>
          <h2>미리보기</h2>
          <p>실제 발송 전 개인화된 메일 처리 결과를 확인합니다.</p>
        </div>
        <button class="primary" type="button" data-action="preview">미리보기 만들기</button>
      </div>
      <div class="summary-row">
        ${summaryItem("처리", state.previewSummary?.processed || 0)}
        ${summaryItem("미리보기", state.previewSummary?.sent || 0)}
        ${summaryItem("제외", state.previewSummary?.skipped || 0)}
        ${summaryItem("실패", state.previewSummary?.failed || 0)}
      </div>
      ${renderTable(state.previewRows, ["status", "email", "template", "rule", "detail", "error"], "아직 미리보기를 만들지 않았습니다.")}
    </section>`;
}

function renderGmailTab() {
  return `
    <section class="tab-panel">
      <div class="panel-title">
        <div>
          <h2>Gmail 결과</h2>
          <p>승인된 고객을 Google Sheet에 올리고 발송 결과를 반영합니다.</p>
        </div>
        <div class="button-row">
          <button type="button" data-action="google-status">Google 상태</button>
          <button type="button" data-action="connect-google">Google 연결</button>
        </div>
      </div>
      <div class="gmail-actions">
        <button type="button" data-action="export-gmail">Gmail 발송 준비</button>
        <button type="button" data-action="upload-gmail">비공개 시트에 올리기</button>
        <button type="button" data-action="fetch-private-gmail">결과 가져오기</button>
        <button class="primary" type="button" data-action="import-gmail">결과 반영</button>
        <button type="button" data-action="compare-gmail">결과 확인</button>
      </div>
      ${renderGoogleSteps()}
      <div class="summary-row">
        ${summaryItem("같음", state.gmailCounts.matched || 0)}
        ${summaryItem("확인 필요", state.gmailCounts.needs_review || 0)}
        ${summaryItem("대기", state.gmailCounts.pending || 0)}
      </div>
      ${renderTable(state.gmailRows, ["review_status", "email", "gmail_status", "template", "lead_status", "detail"], "아직 Gmail 결과를 확인하지 않았습니다.")}
    </section>`;
}

function renderGoogleSteps() {
  if (!state.googleSteps.length) return "";
  return `
    <div class="checklist">
      ${state.googleSteps.map((step) => `
        <div class="${step.done ? "done" : ""}">
          <strong>${safe(step.label)}</strong>
          <span>${safe(step.detail)}</span>
        </div>
      `).join("")}
    </div>`;
}

function summaryItem(label, value) {
  return `
    <div class="summary-item">
      <span>${label}</span>
      <strong>${Number(value || 0)}</strong>
    </div>`;
}

function renderTable(rows, columns, emptyText) {
  if (!rows.length) return `<p class="empty">${emptyText}</p>`;
  const visibleRows = rows.slice(0, 80);
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>${columns.map((column) => `<th>${safe(columnLabel(column))}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${visibleRows.map((row) => `
            <tr>
              ${columns.map((column) => `<td>${safe(row[column] || "")}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
      ${rows.length > visibleRows.length ? `<p class="table-note">처음 ${visibleRows.length}건만 표시합니다.</p>` : ""}
    </div>`;
}

function columnLabel(column) {
  return {
    status: "상태",
    review_status: "확인",
    email: "고객",
    template: "메일",
    rule: "조건",
    campaign_step: "단계",
    next_send_at: "다음 발송일",
    detail: "상세",
    error: "오류",
    gmail_status: "Gmail 상태",
    lead_status: "고객 상태"
  }[column] || column;
}

function bindEvents() {
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      render();
    });
  }

  for (const input of document.querySelectorAll("[data-config]")) {
    input.addEventListener("input", () => {
      state.config[input.dataset.config] = input.value;
    });
  }

  for (const input of document.querySelectorAll("[data-flow-index]")) {
    input.addEventListener("input", () => {
      const step = state.flowSteps[Number(input.dataset.flowIndex)];
      if (step) step[input.dataset.flowField] = input.value;
    });
  }

  for (const input of document.querySelectorAll("[data-approval-index]")) {
    input.addEventListener("change", () => {
      const row = state.approvalRows[Number(input.dataset.approvalIndex)];
      if (row) row.approved = input.checked ? "yes" : "no";
      state.approvalCounts = countApprovals(state.approvalRows);
      render();
    });
  }

  for (const input of document.querySelectorAll("[data-word-index]")) {
    input.addEventListener("change", () => importWordTemplate(Number(input.dataset.wordIndex), input.files?.[0]));
  }

  for (const button of document.querySelectorAll("[data-action]")) {
    button.disabled = state.busy;
    button.addEventListener("click", () => runAction(button.dataset.action));
  }
}

function countApprovals(rows) {
  const approved = rows.filter((row) => row.approved === "yes").length;
  return { ready: rows.length, approved, waiting: rows.length - approved };
}

async function runAction(action) {
  const handlers = {
    refresh: refreshAll,
    plan,
    "load-flow": loadFlow,
    "save-flow": saveFlow,
    "prepare-approval": prepareApproval,
    "save-approval": saveApproval,
    preview,
    "google-status": googleStatus,
    "connect-google": connectGoogle,
    "export-gmail": exportGmail,
    "upload-gmail": uploadGmail,
    "fetch-private-gmail": fetchPrivateGmail,
    "import-gmail": importGmail,
    "compare-gmail": compareGmail
  };
  await handlers[action]?.();
}

async function withBusy(message, task) {
  setNotice(message);
  setBusy(true);
  try {
    await task();
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    state.busy = false;
    render();
  }
}

async function plan() {
  await withBusy("명단을 확인하는 중입니다.", async () => {
    const data = await api("/api/plan", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.backend.connected = true;
    state.queueRows = data.rows || [];
    state.queueCounts = data.counts || {};
    state.activeTab = "people";
    setNotice(`명단 확인 완료: ${countsText(state.queueCounts)}`, "success");
  });
}

async function loadFlow() {
  await withBusy("메일 흐름을 불러오는 중입니다.", async () => {
    const query = new URLSearchParams(formData()).toString();
    const data = await api(`/api/message-flow?${query}`);
    state.backend.connected = true;
    state.flowSteps = data.steps || [];
    state.templates = data.templates || [];
    state.activeTab = "flow";
    setNotice(`메일 흐름 ${state.flowSteps.length}개를 불러왔습니다.`, "success");
  });
}

async function saveFlow() {
  await withBusy("메일 흐름을 저장하는 중입니다.", async () => {
    const data = await api("/api/message-flow/save", {
      method: "POST",
      body: JSON.stringify({ ...formData(), steps: state.flowSteps })
    });
    state.flowSteps = data.steps || [];
    state.templates = data.templates || [];
    state.activeTab = "flow";
    setNotice("메일 흐름을 저장했습니다.", "success");
  });
}

async function prepareApproval() {
  await withBusy("승인 목록을 만드는 중입니다.", async () => {
    const data = await api("/api/approval/prepare", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.approvalRows = data.rows || [];
    state.approvalCounts = data.counts || countApprovals(state.approvalRows);
    state.queueCounts = data.queue_counts || state.queueCounts;
    state.activeTab = "approval";
    setNotice(`승인 대상 ${state.approvalRows.length}건을 만들었습니다.`, "success");
  });
}

async function saveApproval() {
  await withBusy("승인 내용을 저장하는 중입니다.", async () => {
    const data = await api("/api/approval/save", {
      method: "POST",
      body: JSON.stringify({ ...formData(), rows: state.approvalRows })
    });
    state.approvalRows = data.rows || [];
    state.approvalCounts = data.counts || countApprovals(state.approvalRows);
    state.activeTab = "approval";
    setNotice(`승인 저장 완료: ${state.approvalCounts.approved || 0}건`, "success");
  });
}

async function preview() {
  await withBusy("메일 미리보기를 만드는 중입니다.", async () => {
    const data = await api("/api/dry-run", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.previewSummary = data.summary || {};
    state.previewRows = data.report_rows || [];
    state.activeTab = "preview";
    setNotice(`미리보기 완료: ${state.previewSummary.sent || 0}건`, "success");
  });
}

async function googleStatus() {
  await withBusy("Google 연결 상태를 확인하는 중입니다.", async () => {
    const data = await api("/api/google/status", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.googleSteps = data.steps || [];
    state.activeTab = "gmail";
    setNotice("Google 연결 상태를 확인했습니다.", "success");
  });
}

async function connectGoogle() {
  await withBusy("Google 연결 주소를 만드는 중입니다.", async () => {
    const redirectOrigin = apiBase || window.location.origin;
    const data = await api("/api/google/auth-url", {
      method: "POST",
      body: JSON.stringify({
        ...formData(),
        redirect_uri: `${redirectOrigin}/oauth/google/callback`
      })
    });
    window.open(data.auth_url, "_blank", "noopener");
    state.activeTab = "gmail";
    setNotice("새 창에서 Google 연결을 완료하세요.", "success");
  });
}

async function exportGmail() {
  await withBusy("Gmail 발송 준비 파일을 만드는 중입니다.", async () => {
    const data = await api("/api/gmail/export", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    setNotice(`Gmail 발송 준비 완료: ${data.summary?.pending || 0}건`, "success");
  });
}

async function uploadGmail() {
  await withBusy("비공개 Google Sheet에 올리는 중입니다.", async () => {
    const data = await api("/api/gmail/upload-private", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    setNotice(`비공개 시트 업로드 완료: ${data.summary?.rows || 0}건`, "success");
  });
}

async function fetchPrivateGmail() {
  await withBusy("비공개 Google Sheet 결과를 가져오는 중입니다.", async () => {
    const data = await api("/api/gmail/fetch-private", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    setNotice(`Gmail 결과 가져오기 완료: ${data.summary?.rows || 0}건`, "success");
  });
}

async function importGmail() {
  await withBusy("Gmail 결과를 고객 상태에 반영하는 중입니다.", async () => {
    const data = await api("/api/gmail/import", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    await compareGmail(false);
    setNotice(`Gmail 결과 반영 완료: 성공 ${data.summary?.imported || 0}건`, "success");
  });
}

async function compareGmail(showBusy = true) {
  const runner = async () => {
    const data = await api("/api/gmail/compare", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.gmailRows = data.rows || [];
    state.gmailCounts = data.counts || {};
    state.activeTab = "gmail";
    setNotice(`Gmail 결과 확인 완료: ${countsText(state.gmailCounts)}`, "success");
  };
  if (showBusy) await withBusy("Gmail 결과를 확인하는 중입니다.", runner);
  else await runner();
}

async function importWordTemplate(index, file) {
  if (!file) return;
  await withBusy("Word 문서를 읽는 중입니다.", async () => {
    const contentBase64 = await fileToBase64(file);
    const data = await api("/api/word-template/import", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content_base64: contentBase64 })
    });
    const step = state.flowSteps[index];
    if (step) {
      if (data.subject) step.subject = data.subject;
      step.text_body = data.text_body || "";
    }
    state.activeTab = "flow";
    setNotice("Word 문서를 메일 본문에 넣었습니다.", "success");
  });
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error("파일을 읽지 못했습니다."));
    reader.readAsDataURL(file);
  });
}

async function refreshAll() {
  await withBusy("현재 상태를 확인하는 중입니다.", async () => {
    const defaults = await api("/api/defaults");
    state.config = { ...fallbackDefaults, ...defaults, ...state.config };
    state.backend = { connected: true, error: "" };
    await loadFlow();
    await googleStatus();
    setNotice("현재 상태를 확인했습니다.", "success");
  });
}

async function boot() {
  try {
    const defaults = await api("/api/defaults");
    state.config = { ...fallbackDefaults, ...defaults };
    state.backend = { connected: true, error: "" };
    await Promise.allSettled([loadFlow(), googleStatus()]);
    setNotice("");
  } catch (error) {
    state.backend = { connected: false, error: error.message };
    setNotice("백엔드 연결 후 실제 실행 버튼을 사용할 수 있습니다.", "info");
  } finally {
    state.busy = false;
    render();
  }
}

boot();
