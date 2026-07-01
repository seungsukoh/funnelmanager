import "./styles.css";
import readXlsxFile from "read-excel-file/browser";

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
  "test_email",
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
  test_email: "",
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

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const importHeaderCandidates = {
  email: ["email", "e-mail", "email address", "mail", "메일", "메일주소", "이메일", "이메일주소", "전자메일"],
  name: ["name", "full name", "username", "이름", "성명", "고객명", "참가자명", "신청자", "수신자"],
  template: ["template", "mail template", "message", "메일", "템플릿", "메일종류", "메일이름", "발송메일"],
  stage: ["stage", "step", "funnel", "status", "단계", "퍼널", "상태", "퍼널단계", "고객단계", "고객상태", "진행단계", "진행상태"]
};

const importFieldLabels = {
  emailColumn: "이메일 주소",
  nameColumn: "이름",
  templateColumn: "메일 이름",
  stageColumn: "퍼널 단계"
};

const state = {
  config: { ...fallbackDefaults },
  backend: { connected: false, error: "", mode: "none", message: "" },
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
  googleSteps: [],
  googleStatusError: "",
  gmailTestResult: null,
  settingsOpen: false,
  advancedSettingsOpen: false,
  contactImport: null,
  contactImportDraft: null
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
  rememberBackend(payload);
  return payload;
}

function rememberBackend(payload) {
  if (!payload || typeof payload !== "object") return;
  if (payload.cloud_mode) {
    state.backend = {
      connected: true,
      error: "",
      mode: String(payload.cloud_mode),
      message: String(payload.message || payload.cloud_notice || "")
    };
  }
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
  if (id === "people") {
    if (state.contactImportDraft) return `새 명단 확인 중: 이메일 ${state.contactImportDraft.validCount}건`;
    return state.queueRows.length ? countsText(state.queueCounts) : "명단 확인 전";
  }
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

function contactImportText() {
  if (!state.contactImport) return "엑셀/CSV를 불러온 뒤 보낼 사람을 선택하세요.";
  const skipped = state.contactImport.skipped ? ` / ${state.contactImport.skipped}줄 건너뜀` : "";
  return `${state.contactImport.filename} / ${state.contactImport.imported}건 저장${skipped}`;
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
  const backendClass = state.backend.connected && state.backend.mode !== "cloud_preview" ? "ok" : "warn";
  const backendText =
    state.backend.mode === "cloud_preview"
      ? "클라우드 미리보기"
      : state.backend.connected
        ? "백엔드 연결됨"
        : "백엔드 연결 필요";

  document.querySelector("#app").innerHTML = `
    <main class="page">
      <header class="app-header">
        <div>
          <p class="eyebrow">Funnel Manager</p>
          <h1>자동 메일 퍼널 관리</h1>
        </div>
        <div class="header-actions">
          <span class="badge ${backendClass}">${backendText}</span>
          <button type="button" data-action="open-settings">연결 설정</button>
          <button type="button" data-action="refresh">새로 확인</button>
        </div>
      </header>

      ${state.settingsOpen ? renderSettingsPanel() : ""}
      ${state.backend.connected && state.backend.mode !== "cloud_preview" ? "" : renderBackendNotice()}
      ${state.notice ? `<div class="notice ${state.noticeTone}">${safe(state.notice)}</div>` : ""}
      ${renderStatusMonitor(nextId)}

      <section class="workflow" aria-label="오늘 진행 순서">
        ${renderWorkflowCard("people", 1, "명단 확인", "받을 사람 확인", "명단 확인", nextId)}
        ${renderWorkflowCard("flow", 2, "단계별 메일", "메일 내용 관리", "메일 흐름", nextId)}
        ${renderWorkflowCard("approval", 3, "발송 승인", "오늘 보낼 사람 선택", "승인 만들기", nextId)}
        ${renderWorkflowCard("preview", 4, "미리보기", "발송 전 내용 확인", "미리보기", nextId)}
        ${renderWorkflowCard("gmail", 5, "Gmail 결과", "시트 업로드와 결과 반영", "Gmail 확인", nextId)}
      </section>

      <section class="layout">
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

function renderStatusMonitor(nextId) {
  const database = googleStep("database");
  const secret = googleStep("cloud");
  const connect = googleStep("connect");
  const gmailSend = googleStep("gmail_send");
  const approved = Number(state.approvalCounts.approved || 0);
  const needsReview = Number(state.gmailCounts.needs_review || 0);

  return `
    <section class="status-monitor" aria-label="운영 상태">
      ${renderMonitorItem("저장소", database?.done ? "연결됨" : "확인 필요", database?.detail || "D1 상태를 확인하세요.", database?.done ? "ok" : "warn")}
      ${renderMonitorItem("Google", connect?.done ? "연결됨" : secret?.done ? "승인 필요" : "설정 필요", connect?.detail || secret?.detail || "Google 연결 상태를 확인하세요.", connect?.done ? "ok" : "warn")}
      ${renderMonitorItem("테스트 발송", state.gmailTestResult?.sent ? "완료" : gmailSend?.done ? "준비됨" : "대기", state.gmailTestResult?.sent ? `${state.gmailTestResult.recipient} 발송` : gmailSend?.detail || "테스트 발송 전", state.gmailTestResult?.sent || gmailSend?.done ? "ok" : "neutral")}
      ${renderMonitorItem(
        "불러온 명단",
        state.contactImportDraft ? "확인 중" : state.queueRows.length ? `${state.queueRows.length}건` : "없음",
        state.contactImportDraft ? `이메일 ${state.contactImportDraft.validCount}건 확인 후 저장 필요` : contactImportText(),
        state.contactImportDraft || state.queueRows.length ? "ok" : "neutral"
      )}
      ${renderMonitorItem("오늘 승인", `${approved}건`, approved ? "승인된 명단이 있습니다." : "발송 승인 전입니다.", approved ? "ok" : "neutral")}
      ${renderMonitorItem("다음 작업", workflowTitle(nextId), workflowStatus(nextId), "focus")}
      ${renderMonitorItem("확인 필요", `${needsReview}건`, needsReview ? "Gmail 결과 확인이 필요합니다." : "처리할 오류가 없습니다.", needsReview ? "warn" : "ok")}
    </section>`;
}

function renderMonitorItem(label, value, detail, tone) {
  return `
    <div class="monitor-item ${tone}">
      <span>${safe(label)}</span>
      <strong>${safe(value)}</strong>
      <small>${safe(detail)}</small>
    </div>`;
}

function workflowTitle(id) {
  return {
    people: "명단 확인",
    flow: "단계별 메일",
    approval: "발송 승인",
    preview: "미리보기",
    gmail: "Gmail 결과"
  }[id] || "확인";
}

function googleStep(id) {
  return state.googleSteps.find((step) => step.id === id);
}

function renderSettingsPanel() {
  return `
    <section class="settings-panel" aria-label="연결 설정">
      <div class="settings-head">
        <div>
          <h2>연결 설정</h2>
          <p>Google 연결과 운영 입력값을 확인합니다.</p>
        </div>
        <div class="button-row">
          <button type="button" data-action="google-status">Google 상태 확인</button>
          <button type="button" data-action="connect-google">Google 연결</button>
          <button type="button" data-action="close-settings">닫기</button>
        </div>
      </div>
      ${renderGoogleSteps()}
      <div class="settings-grid">
        <section class="settings-group">
          <h3>운영 입력</h3>
          ${renderConfigGroup([
            ["campaign_id", "캠페인 이름"],
            ["gmail_source", "Google Sheet 링크"],
            ["gmail_sheet_name", "Sheet 이름"],
            ["test_email", "테스트 수신자"]
          ])}
        </section>
        <section class="settings-group">
          <h3>명단과 기록</h3>
          ${renderConfigGroup([
            ["contacts", "명단 파일"],
            ["funnel_config", "메일 흐름 파일"],
            ["lead_state", "고객 상태 파일"]
          ])}
        </section>
      </div>
      <div class="advanced-settings">
        <button type="button" data-action="toggle-advanced-settings">${state.advancedSettingsOpen ? "파일 설정 닫기" : "파일 설정 더보기"}</button>
        ${state.advancedSettingsOpen ? `
          <div class="settings-grid">
            <section class="settings-group">
              <h3>출력 파일</h3>
              ${renderConfigGroup([
                ["queue_output", "명단 확인 파일"],
                ["approval_output", "발송 승인 파일"],
                ["gmail_results", "Gmail 준비/결과 파일"],
                ["timeline", "고객별 기록 파일"]
              ])}
            </section>
            <section class="settings-group">
              <h3>로컬 Google 파일</h3>
              ${renderConfigGroup([
                ["google_credentials", "Google 인증 파일"],
                ["google_token", "Google 토큰 파일"]
              ])}
            </section>
          </div>` : ""}
      </div>
    </section>`;
}

function renderConfigGroup(fields) {
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

function renderBackendNotice() {
  if (state.backend.mode === "cloud_preview") {
    return `
      <section class="backend-notice">
        <strong>Cloudflare 미리보기 백엔드가 연결됐습니다.</strong>
        <span>명단 확인과 화면 흐름은 샘플 데이터로 확인할 수 있습니다. 실제 발송과 Google Sheet 연결은 저장소와 비밀키를 붙이는 다음 단계가 필요합니다.</span>
        ${state.backend.message ? `<small>${safe(state.backend.message)}</small>` : ""}
      </section>`;
  }
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
          <p>엑셀 또는 CSV 명단을 불러오고, 오늘 보낼 수 있는 사람과 제외된 사람을 구분합니다.</p>
        </div>
        <div class="button-row">
          <label class="file-button">
            엑셀/CSV 불러오기
            <input type="file" accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" data-contacts-file />
          </label>
          <button class="primary" type="button" data-action="plan">명단 확인</button>
        </div>
      </div>
      ${state.contactImport ? `
        <div class="inline-status">
          <strong>최근 명단</strong>
          <span>${safe(contactImportText())}</span>
        </div>` : ""}
      ${renderContactImportReview()}
      <div class="summary-row">
        ${summaryItem("보낼 예정", state.queueCounts.ready || 0)}
        ${summaryItem("기다림", state.queueCounts.scheduled || 0)}
        ${summaryItem("제외", state.queueCounts.skipped || 0)}
      </div>
      ${renderTable(state.queueRows, ["status", "email", "template", "rule", "campaign_step", "next_send_at", "detail"], "아직 명단을 확인하지 않았습니다.")}
    </section>`;
}

function renderContactImportReview() {
  const draft = state.contactImportDraft;
  if (!draft) return "";
  const disabled = draft.validCount ? "" : "disabled";
  return `
    <section class="import-review" aria-label="새 명단 확인">
      <div class="import-review-head">
        <div>
          <span class="mini-badge">새 명단 확인</span>
          <h3>저장 전에 앱이 찾은 열을 확인하세요</h3>
          <p>${safe(draft.filename)}에서 이메일 ${draft.validCount}건을 찾았습니다. 맞지 않으면 아래에서 바로 바꿀 수 있습니다.</p>
        </div>
        <div class="button-row">
          <button type="button" data-action="clear-contact-draft">다시 선택</button>
          <button class="primary" type="button" data-action="save-contact-draft" ${disabled}>이대로 명단 저장</button>
        </div>
      </div>
      <div class="import-stats">
        <div><span>확인된 이메일</span><strong>${draft.validCount}</strong></div>
        <div><span>건너뜀</span><strong>${draft.skippedCount}</strong></div>
        <div><span>제목 행</span><strong>${draft.headerRowIndex >= 0 ? `${draft.headerRowIndex + 1}번째 줄` : "자동 판단"}</strong></div>
      </div>
      <div class="mapping-grid">
        ${renderImportColumnSelect("emailColumn", draft, true)}
        ${renderImportColumnSelect("nameColumn", draft)}
        ${renderImportColumnSelect("templateColumn", draft)}
        ${renderImportColumnSelect("stageColumn", draft)}
      </div>
      ${draft.confidenceNotes.length ? `<p class="import-help">${safe(draft.confidenceNotes.join(" "))}</p>` : ""}
      ${renderImportPreview(draft)}
    </section>`;
}

function renderImportColumnSelect(field, draft, required = false) {
  const value = Number(draft[field]);
  const options = [];
  if (!required) options.push(`<option value="-1" ${value < 0 ? "selected" : ""}>사용 안 함</option>`);
  for (let index = 0; index < draft.columnCount; index += 1) {
    const selected = value === index ? "selected" : "";
    options.push(`<option value="${index}" ${selected}>${safe(importColumnLabel(draft, index))}</option>`);
  }
  return `
    <label class="field import-field">
      <span>${safe(importFieldLabels[field])}</span>
      <select data-import-field="${field}">${options.join("")}</select>
      <small>${safe(importColumnSample(draft, value))}</small>
    </label>`;
}

function renderImportPreview(draft) {
  if (!draft.previewRows.length) {
    return `<p class="empty">이메일 열을 다시 선택하면 미리보기가 표시됩니다.</p>`;
  }
  return `
    <div class="table-wrap import-preview">
      <table>
        <thead>
          <tr><th>이름</th><th>이메일</th><th>메일 이름</th><th>퍼널 단계</th></tr>
        </thead>
        <tbody>
          ${draft.previewRows.map((row) => `
            <tr>
              <td>${safe(row.name || "")}</td>
              <td>${safe(row.email || "")}</td>
              <td>${safe(row.template || "")}</td>
              <td>${safe(row.campaign_step || "")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>`;
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
          <button type="button" data-action="open-settings">연결 설정</button>
        </div>
      </div>
      <div class="gmail-actions">
        <button type="button" data-action="export-gmail">Gmail 발송 준비</button>
        <button type="button" data-action="upload-gmail">비공개 시트에 올리기</button>
        <button type="button" data-action="fetch-private-gmail">결과 가져오기</button>
        <button type="button" data-action="test-gmail">테스트 발송</button>
        <button class="primary" type="button" data-action="import-gmail">결과 반영</button>
        <button type="button" data-action="compare-gmail">결과 확인</button>
      </div>
      ${renderGmailTestResult()}
      <div class="summary-row">
        ${summaryItem("같음", state.gmailCounts.matched || 0)}
        ${summaryItem("확인 필요", state.gmailCounts.needs_review || 0)}
        ${summaryItem("대기", state.gmailCounts.pending || 0)}
      </div>
      ${renderTable(state.gmailRows, ["review_status", "email", "gmail_status", "template", "lead_status", "detail"], "아직 Gmail 결과를 확인하지 않았습니다.")}
    </section>`;
}

function renderGmailTestResult() {
  if (!state.gmailTestResult) return "";
  const result = state.gmailTestResult;
  const title = result.sent ? "최근 테스트 발송 완료" : "최근 테스트 발송 미완료";
  const detail = result.sent
    ? `${result.recipient} 주소로 테스트 메일을 보냈습니다.${result.sentAt ? ` (${result.sentAt})` : ""}`
    : result.message || "테스트 발송이 완료되지 않았습니다.";
  return `
    <div class="checklist">
      <div class="${result.sent ? "done" : ""}">
        <strong>${safe(title)}</strong>
        <span>${safe(detail)}</span>
      </div>
    </div>`;
}

function renderGoogleSteps() {
  if (state.googleStatusError) {
    return `
      <div class="checklist">
        <div>
          <strong>Google 상태 확인 실패</strong>
          <span>${safe(state.googleStatusError)} Google 상태 버튼을 다시 눌러 확인하세요.</span>
        </div>
      </div>`;
  }
  if (!state.googleSteps.length) {
    return `
      <div class="checklist">
        <div>
          <strong>Google 상태 미확인</strong>
          <span>Google 상태 버튼을 누르면 D1 저장소, Google Secret, Gmail 권한을 확인합니다.</span>
        </div>
      </div>`;
  }
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

  for (const input of document.querySelectorAll("[data-contacts-file]")) {
    input.addEventListener("change", () => importContactsFile(input.files?.[0], input));
  }

  for (const select of document.querySelectorAll("[data-import-field]")) {
    select.addEventListener("change", () => updateContactImportColumn(select.dataset.importField, select.value));
  }

  for (const button of document.querySelectorAll("[data-action]")) {
    button.disabled = state.busy || button.hasAttribute("disabled");
    button.addEventListener("click", () => runAction(button.dataset.action));
  }
}

function countApprovals(rows) {
  const approved = rows.filter((row) => row.approved === "yes").length;
  return { ready: rows.length, approved, waiting: rows.length - approved };
}

async function runAction(action) {
  const handlers = {
    "open-settings": openSettings,
    "close-settings": closeSettings,
    "toggle-advanced-settings": toggleAdvancedSettings,
    refresh: refreshAll,
    plan,
    "load-flow": loadFlow,
    "save-flow": saveFlow,
    "prepare-approval": prepareApproval,
    "save-approval": saveApproval,
    preview,
    "google-status": () => googleStatus({ activate: !state.settingsOpen }),
    "connect-google": () => connectGoogle({ activate: !state.settingsOpen }),
    "export-gmail": exportGmail,
    "upload-gmail": uploadGmail,
    "fetch-private-gmail": fetchPrivateGmail,
    "test-gmail": testGmail,
    "import-gmail": importGmail,
    "compare-gmail": compareGmail,
    "save-contact-draft": saveContactImportDraft,
    "clear-contact-draft": clearContactImportDraft
  };
  await handlers[action]?.();
}

function messageFrom(data, fallback) {
  return data.message || fallback;
}

async function openSettings() {
  state.settingsOpen = true;
  state.advancedSettingsOpen = false;
  render();
}

async function closeSettings() {
  formData();
  state.settingsOpen = false;
  render();
}

async function toggleAdvancedSettings() {
  state.advancedSettingsOpen = !state.advancedSettingsOpen;
  render();
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
    setNotice(messageFrom(data, `명단 확인 완료: ${countsText(state.queueCounts)}`), "success");
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
    setNotice(messageFrom(data, `메일 흐름 ${state.flowSteps.length}개를 불러왔습니다.`), "success");
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
    setNotice(messageFrom(data, "메일 흐름을 저장했습니다."), "success");
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
    setNotice(messageFrom(data, `승인 대상 ${state.approvalRows.length}건을 만들었습니다.`), "success");
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
    setNotice(messageFrom(data, `승인 저장 완료: ${state.approvalCounts.approved || 0}건`), "success");
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
    setNotice(messageFrom(data, `미리보기 완료: ${state.previewSummary.sent || 0}건`), "success");
  });
}

async function googleStatus({ activate = true } = {}) {
  await withBusy("Google 연결 상태를 확인하는 중입니다.", async () => {
    try {
      const data = await api("/api/google/status", {
        method: "POST",
        body: JSON.stringify(formData())
      });
      state.googleStatusError = "";
      state.googleSteps = data.steps || [];
      if (activate) state.activeTab = "gmail";
      setNotice(messageFrom(data, "Google 연결 상태를 확인했습니다."), "success");
    } catch (error) {
      if (activate) state.activeTab = "gmail";
      state.googleSteps = [];
      state.googleStatusError = error.message;
      throw error;
    }
  });
}

async function connectGoogle({ activate = true } = {}) {
  await withBusy("Google 연결 주소를 만드는 중입니다.", async () => {
    const redirectOrigin = apiBase || window.location.origin;
    const data = await api("/api/google/auth-url", {
      method: "POST",
      body: JSON.stringify({
        ...formData(),
        redirect_uri: `${redirectOrigin}/oauth/google/callback`
      })
    });
    if (data.auth_url) window.open(data.auth_url, "_blank", "noopener");
    if (activate) state.activeTab = "gmail";
    setNotice(messageFrom(data, data.auth_url ? "새 창에서 Google 연결을 완료하세요." : "Google 연결 준비 상태를 확인했습니다."), "success");
  });
}

async function exportGmail() {
  await withBusy("Gmail 발송 준비 파일을 만드는 중입니다.", async () => {
    const data = await api("/api/gmail/export", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    setNotice(messageFrom(data, `Gmail 발송 준비 완료: ${data.summary?.pending || 0}건`), "success");
  });
}

async function uploadGmail() {
  await withBusy("비공개 Google Sheet에 올리는 중입니다.", async () => {
    const data = await api("/api/gmail/upload-private", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    setNotice(messageFrom(data, `비공개 시트 업로드 완료: ${data.summary?.rows || 0}건`), "success");
  });
}

async function fetchPrivateGmail() {
  await withBusy("비공개 Google Sheet 결과를 가져오는 중입니다.", async () => {
    const data = await api("/api/gmail/fetch-private", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    setNotice(messageFrom(data, `Gmail 결과 가져오기 완료: ${data.summary?.rows || 0}건`), "success");
  });
}

async function testGmail() {
  await withBusy("테스트 메일을 발송하는 중입니다.", async () => {
    const data = await api("/api/gmail/test-send", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    if (data.steps) {
      state.googleStatusError = "";
      state.googleSteps = data.steps;
    }
    state.gmailTestResult = {
      sent: Boolean(data.summary?.sent),
      recipient: data.summary?.recipient || state.config.test_email || "",
      message: messageFrom(data, "테스트 발송이 완료되지 않았습니다."),
      messageId: data.summary?.message_id || "",
      sentAt: data.summary?.sent_at || ""
    };
    state.activeTab = "gmail";
    setNotice(
      messageFrom(data, `테스트 메일 발송 완료: ${data.summary?.recipient || ""}`),
      data.summary?.sent ? "success" : "info"
    );
  });
}

async function importContactsFile(file, input) {
  if (!file) return;
  await withBusy("명단 파일을 읽는 중입니다.", async () => {
    const table = await tableFromContactsFile(file);
    state.contactImportDraft = buildContactImportDraft(file.name, table);
    state.activeTab = "people";
    setNotice(
      `이메일 ${state.contactImportDraft.validCount}건을 찾았습니다. 저장 전에 열을 확인하세요.`,
      state.contactImportDraft.validCount ? "success" : "info"
    );
  });
  if (input) input.value = "";
}

async function saveContactImportDraft() {
  if (!state.contactImportDraft) return;
  await withBusy("확인한 명단을 저장하는 중입니다.", async () => {
    const rows = contactRowsFromDraft(state.contactImportDraft);
    if (!rows.length) throw new Error("저장할 이메일 주소가 없습니다. 이메일 열을 다시 확인하세요.");
    const data = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ ...formData(), rows })
    });
    state.queueRows = data.rows || [];
    state.queueCounts = data.counts || {};
    state.approvalRows = [];
    state.approvalCounts = {};
    state.previewRows = [];
    state.previewSummary = null;
    state.contactImport = {
      filename: state.contactImportDraft.filename,
      received: data.summary?.received || rows.length,
      imported: data.summary?.imported || 0,
      skipped: state.contactImportDraft.skippedCount
    };
    state.contactImportDraft = null;
    state.activeTab = "people";
    setNotice(messageFrom(data, `명단 ${state.contactImport.imported}건을 저장했습니다.`), "success");
  });
}

async function clearContactImportDraft() {
  state.contactImportDraft = null;
  setNotice("새 명단 선택을 취소했습니다.");
  render();
}

function updateContactImportColumn(field, value) {
  if (!state.contactImportDraft) return;
  state.contactImportDraft[field] = Number(value);
  state.contactImportDraft = refreshContactImportDraft(state.contactImportDraft);
  render();
}

async function importGmail() {
  await withBusy("Gmail 결과를 고객 상태에 반영하는 중입니다.", async () => {
    const data = await api("/api/gmail/import", {
      method: "POST",
      body: JSON.stringify(formData())
    });
    state.activeTab = "gmail";
    await compareGmail(false);
    setNotice(messageFrom(data, `Gmail 결과 반영 완료: 성공 ${data.summary?.imported || 0}건`), "success");
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
    setNotice(messageFrom(data, `Gmail 결과 확인 완료: ${countsText(state.gmailCounts)}`), "success");
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

async function tableFromContactsFile(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".xlsx")) return readXlsxFile(file);
  if (name.endsWith(".csv")) return parseCsv(await file.text());
  throw new Error("엑셀 .xlsx 또는 CSV 파일만 불러올 수 있습니다.");
}

function buildContactImportDraft(filename, table) {
  const tableRows = normalizeContactTable(table);
  if (!tableRows.length) throw new Error("명단 파일에서 읽을 수 있는 내용이 없습니다.");
  const inferred = inferContactColumns(tableRows);
  return refreshContactImportDraft({
    filename,
    tableRows,
    ...inferred
  });
}

function normalizeContactTable(table) {
  const rows = (Array.isArray(table) ? table : [])
    .map((row) => (Array.isArray(row) ? row : []).map((value) => String(value ?? "").trim()))
    .filter((row) => row.some(Boolean));
  const columnCount = Math.max(0, ...rows.map((row) => row.length));
  return rows.map((row) => Array.from({ length: columnCount }, (_, index) => row[index] || ""));
}

function inferContactColumns(tableRows) {
  const columnCount = Math.max(0, ...tableRows.map((row) => row.length));
  const emailColumn = inferEmailColumn(tableRows, columnCount);
  if (emailColumn < 0) throw new Error("이메일 주소가 들어 있는 열을 찾지 못했습니다.");

  const firstEmailRow = firstEmailRowFor(tableRows, emailColumn);
  const headerRowIndex = inferHeaderRow(tableRows, firstEmailRow, emailColumn);
  const dataStartIndex = headerRowIndex >= 0 ? headerRowIndex + 1 : Math.max(firstEmailRow, 0);
  const headers = buildImportHeaders(tableRows, headerRowIndex, columnCount);
  const nameColumn = inferHeaderColumn(headers, "name", [emailColumn]) ?? inferNameColumn(tableRows, dataStartIndex, emailColumn, columnCount);
  const templateColumn = inferHeaderColumn(headers, "template", [emailColumn, nameColumn]) ?? -1;
  const stageColumn = inferHeaderColumn(headers, "stage", [emailColumn, nameColumn, templateColumn]) ?? -1;
  const baseNotes = [
    headerRowIndex >= 0
      ? `${headerRowIndex + 1}번째 줄을 제목으로 보고 확인했습니다.`
      : "제목 행이 없어도 이메일 주소 모양을 보고 찾았습니다."
  ];

  return {
    columnCount,
    headerRowIndex,
    dataStartIndex,
    headers,
    emailColumn,
    nameColumn,
    templateColumn,
    stageColumn,
    baseNotes
  };
}

function inferEmailColumn(rows, columnCount) {
  let bestColumn = -1;
  let bestScore = 0;
  for (let column = 0; column < columnCount; column += 1) {
    const emailValues = rows.filter((row) => isEmail(rowValue(row, column))).length;
    const headerScore = rows.slice(0, 20).reduce((score, row) => score + headerCandidateScore(rowValue(row, column), "email"), 0);
    const score = emailValues * 10 + headerScore * 3;
    if (score > bestScore) {
      bestScore = score;
      bestColumn = column;
    }
  }
  return bestColumn;
}

function firstEmailRowFor(rows, emailColumn) {
  return rows.findIndex((row) => isEmail(rowValue(row, emailColumn)));
}

function inferHeaderRow(rows, firstEmailRow, emailColumn) {
  const end = firstEmailRow > 0 ? firstEmailRow - 1 : Math.min(rows.length - 1, 4);
  const start = Math.max(0, end - 6);
  let bestRow = -1;
  let bestScore = 0;
  for (let index = start; index <= end; index += 1) {
    const row = rows[index] || [];
    const emailCount = row.filter(isEmail).length;
    const score = headerRowScore(row) + headerCandidateScore(rowValue(row, emailColumn), "email") - emailCount * 4;
    if (score > bestScore) {
      bestScore = score;
      bestRow = index;
    }
  }
  return bestScore >= 3 ? bestRow : -1;
}

function headerRowScore(row) {
  const textCells = row.filter((cell) => cell && !isEmail(cell) && Number.isNaN(Number(cell))).length;
  const candidateScore = row.reduce((score, cell) => (
    score
    + headerCandidateScore(cell, "email")
    + headerCandidateScore(cell, "name")
    + headerCandidateScore(cell, "template")
    + headerCandidateScore(cell, "stage")
  ), 0);
  return candidateScore + (textCells >= 2 ? 1 : 0);
}

function buildImportHeaders(rows, headerRowIndex, columnCount) {
  const headerRow = headerRowIndex >= 0 ? rows[headerRowIndex] || [] : [];
  return Array.from({ length: columnCount }, (_, index) => {
    const header = String(headerRow[index] || "").trim();
    return header || `${spreadsheetColumnName(index)}열`;
  });
}

function inferHeaderColumn(headers, kind, excluded = []) {
  let bestColumn = -1;
  let bestScore = 0;
  for (let index = 0; index < headers.length; index += 1) {
    if (excluded.includes(index)) continue;
    const score = headerCandidateScore(headers[index], kind);
    if (score > bestScore) {
      bestScore = score;
      bestColumn = index;
    }
  }
  return bestScore > 0 ? bestColumn : null;
}

function inferNameColumn(rows, dataStartIndex, emailColumn, columnCount) {
  let bestColumn = -1;
  let bestScore = 0;
  const sampleRows = rows.slice(dataStartIndex, dataStartIndex + 30);
  for (let column = 0; column < columnCount; column += 1) {
    if (column === emailColumn) continue;
    const values = sampleRows.map((row) => rowValue(row, column)).filter(Boolean);
    const textValues = values.filter((value) => !isEmail(value) && Number.isNaN(Number(value)) && value.length <= 40);
    const score = textValues.length * 2 + (column === emailColumn - 1 ? 3 : 0) + (column === emailColumn + 1 ? 1 : 0);
    if (score > bestScore) {
      bestScore = score;
      bestColumn = column;
    }
  }
  return bestScore > 0 ? bestColumn : -1;
}

function refreshContactImportDraft(draft) {
  const rows = contactRowsFromDraft(draft);
  let skippedCount = 0;
  for (let index = draft.dataStartIndex; index < draft.tableRows.length; index += 1) {
    if (index === draft.headerRowIndex) continue;
    const row = draft.tableRows[index];
    if (row.some(Boolean) && !isEmail(rowValue(row, draft.emailColumn))) skippedCount += 1;
  }
  const confidenceNotes = [...(draft.baseNotes || [])];
  if (skippedCount) confidenceNotes.push(`${skippedCount}줄은 이메일 주소가 없어 저장하지 않습니다.`);
  if (draft.templateColumn < 0) confidenceNotes.push("메일 이름이 없으면 첫 번째 메일 단계로 저장합니다.");
  return {
    ...draft,
    previewRows: rows.slice(0, 5),
    validCount: rows.length,
    skippedCount,
    confidenceNotes
  };
}

function contactRowsFromDraft(draft) {
  if (!draft || draft.emailColumn < 0) return [];
  const objects = [];
  for (let index = draft.dataStartIndex; index < draft.tableRows.length; index += 1) {
    if (index === draft.headerRowIndex) continue;
    const row = draft.tableRows[index];
    const email = normalizeEmail(rowValue(row, draft.emailColumn));
    if (!EMAIL_PATTERN.test(email)) continue;
    const object = { email };
    const name = rowValue(row, draft.nameColumn);
    const template = rowValue(row, draft.templateColumn);
    const stage = rowValue(row, draft.stageColumn);
    if (name) object.name = name;
    if (template) object.template = template;
    if (stage) object.campaign_step = stage;
    draft.headers.forEach((header, column) => {
      const value = rowValue(row, column);
      if (header && value) object[header] = value;
    });
    objects.push(object);
  }
  return objects;
}

function importColumnLabel(draft, index) {
  const columnName = spreadsheetColumnName(index);
  const header = draft.headers[index] || "";
  const generated = header === `${columnName}열`;
  const sample = firstColumnValue(draft, index);
  if (header && !generated) return `${columnName}열 · ${header}`;
  if (sample) return `${columnName}열 · 예: ${sample}`;
  return `${columnName}열`;
}

function importColumnSample(draft, index) {
  if (index < 0) return "필요 없으면 비워둘 수 있습니다.";
  const sample = firstColumnValue(draft, index);
  return sample ? `예: ${sample}` : "값이 비어 있습니다.";
}

function firstColumnValue(draft, index) {
  if (index < 0) return "";
  for (let rowIndex = draft.dataStartIndex; rowIndex < draft.tableRows.length; rowIndex += 1) {
    if (rowIndex === draft.headerRowIndex) continue;
    const value = rowValue(draft.tableRows[rowIndex], index);
    if (value) return value.length > 36 ? `${value.slice(0, 36)}...` : value;
  }
  return "";
}

function rowValue(row, index) {
  if (index < 0 || !Array.isArray(row)) return "";
  return String(row[index] ?? "").trim();
}

function normalizeEmail(value) {
  const match = String(value || "").match(/[^\s<>"'(),;]+@[^\s<>"'(),;]+\.[^\s<>"'(),;]+/);
  return match ? match[0].replace(/[.,;]+$/, "").toLowerCase() : "";
}

function isEmail(value) {
  return EMAIL_PATTERN.test(normalizeEmail(value));
}

function headerCandidateScore(value, kind) {
  const normalized = normalizeImportHeader(value);
  if (!normalized) return 0;
  return (importHeaderCandidates[kind] || []).reduce((score, candidate) => {
    const token = normalizeImportHeader(candidate);
    if (!token) return score;
    if (normalized === token) return Math.max(score, 4);
    if (token.length >= 3 && normalized.includes(token)) return Math.max(score, 2);
    return score;
  }, 0);
}

function normalizeImportHeader(value) {
  return String(value || "").toLowerCase().replace(/[()[\]{}]/g, "").replace(/[\s_\-.]+/g, "");
}

function spreadsheetColumnName(index) {
  let name = "";
  let value = index + 1;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name || "A";
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  row.push(cell);
  rows.push(row);
  return rows;
}

async function refreshAll() {
  await withBusy("현재 상태를 확인하는 중입니다.", async () => {
    const previousTab = state.activeTab;
    const defaults = await api("/api/defaults");
    state.config = { ...fallbackDefaults, ...defaults, ...state.config };
    if (state.backend.mode !== "cloud_preview") {
      state.backend = { connected: true, error: "", mode: "local", message: "" };
    }
    await loadFlow();
    await googleStatus({ activate: false });
    state.activeTab = previousTab;
    setNotice("현재 상태를 확인했습니다.", "success");
  });
}

async function boot() {
  try {
    const defaults = await api("/api/defaults");
    state.config = { ...fallbackDefaults, ...defaults };
    if (state.backend.mode !== "cloud_preview") {
      state.backend = { connected: true, error: "", mode: "local", message: "" };
    }
    await Promise.allSettled([loadFlow(), googleStatus({ activate: false })]);
    state.activeTab = "people";
    setNotice("");
  } catch (error) {
    state.backend = { connected: false, error: error.message, mode: "none", message: "" };
    setNotice("백엔드 연결 후 실제 실행 버튼을 사용할 수 있습니다.", "info");
  } finally {
    state.busy = false;
    render();
  }
}

boot();
