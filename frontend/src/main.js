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

const DELIVERY_SET_STORAGE_KEY = "automailing.deliverySets.v1";
const DEFAULT_SEND_TIME = "09:00";

const statusLabels = {
  ready: "보낼 예정",
  scheduled: "기다림",
  skipped: "제외",
  sent: "발송 완료",
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

const defaultFormAutoSend = {
  enabled: false,
  daily_limit: 20,
  sent_today: 0,
  remaining_today: 20,
  followups_enabled: false,
  followup_daily_limit: 20,
  followup_sent_today: 0,
  followup_remaining_today: 20,
  followup_due_count: 0,
  followup_due_preview: [],
  followup_gmail_ready: false,
  followup_ready: false,
  followup_status_label: "확인 전",
  followup_status_detail: "후속 메일 상태를 아직 확인하지 않았습니다.",
  followup_blockers: [],
  date: ""
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
  googleSetup: {},
  googleStatusError: "",
  gmailTestResult: null,
  deliverySets: [],
  activeSetId: "",
  formAutoSend: { ...defaultFormAutoSend },
  settingsOpen: false,
  advancedSettingsOpen: false,
  contactImport: null,
  contactImportDraft: null,
  contactSelection: new Set()
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
  state.config = { ...state.config };
  return state.config;
}

function setConfigValue(key, value, source = null) {
  const nextValue = String(value || "");
  state.config[key] = nextValue.trim();
  for (const input of document.querySelectorAll(`[data-config="${key}"]`)) {
    if (input !== source && input.value !== nextValue) input.value = nextValue;
  }
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
  const sheet = state.contactImport.sheetName ? ` / ${state.contactImport.sheetName}` : "";
  const skipped = state.contactImport.skipped ? ` / ${state.contactImport.skipped}줄 건너뜀` : "";
  return `${state.contactImport.filename}${sheet} / ${state.contactImport.imported}건 저장${skipped}`;
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
        ${renderWorkflowCard("flow", 2, "메일 시리즈", "퍼널메일 관리", "메일 흐름", nextId)}
        ${renderWorkflowCard("approval", 3, "발송 승인", "오늘 보낼 사람 선택", "승인 만들기", nextId)}
        ${renderWorkflowCard("preview", 4, "미리보기", "발송 전 내용 확인", "미리보기", nextId)}
        ${renderWorkflowCard("gmail", 5, "Gmail 결과", "시트 업로드와 결과 반영", "Gmail 확인", nextId)}
      </section>

      <section class="layout">
        <section class="work-panel">
          <nav class="tabs" aria-label="작업 탭">
            ${tabButton("people", "명단 확인")}
            ${tabButton("flow", "메일 시리즈")}
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
  const autoSend = state.formAutoSend;

  return `
    <section class="status-monitor" aria-label="운영 상태">
      ${renderMonitorItem("저장소", database?.done ? "연결됨" : "확인 필요", database?.detail || "D1 상태를 확인하세요.", database?.done ? "ok" : "warn")}
      ${renderMonitorItem("Google", connect?.done ? "연결됨" : secret?.done ? "승인 필요" : "설정 필요", connect?.detail || secret?.detail || "Google 연결 상태를 확인하세요.", connect?.done ? "ok" : "warn")}
      ${renderMonitorItem("테스트 발송", state.gmailTestResult?.sent ? "완료" : gmailSend?.done ? "준비됨" : "대기", state.gmailTestResult?.sent ? `${state.gmailTestResult.recipient} 발송` : gmailSend?.detail || "테스트 발송 전", state.gmailTestResult?.sent || gmailSend?.done ? "ok" : "neutral")}
      ${renderMonitorItem("폼 자동 발송", autoSend.enabled ? "켜짐" : "꺼짐", autoSend.enabled ? `오늘 ${autoSend.sent_today || 0}/${autoSend.daily_limit || 20}건 발송` : "폼 응답은 명단에만 등록됩니다.", autoSend.enabled ? "warn" : "neutral")}
      ${renderMonitorItem("후속 자동 발송", autoSend.followups_enabled ? "켜짐" : "꺼짐", autoSend.followup_status_detail || (autoSend.followups_enabled ? `오늘 ${autoSend.followup_sent_today || 0}/${autoSend.followup_daily_limit || 20}건, 지금 대상 ${autoSend.followup_due_count || 0}건` : "예약된 후속 메일은 수동 확인합니다."), autoSend.followup_ready ? "ok" : autoSend.followups_enabled ? "warn" : "neutral")}
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
    flow: "메일 시리즈",
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
      ${renderConnectionSetupGuide()}
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
        ${renderFormAutoSendSettings()}
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

function renderFormAutoSendSettings() {
  const settings = state.formAutoSend;
  const followupAction = settings.followups_enabled
    ? { action: "disable-followup-auto-send", label: "후속 자동 발송 끄기", className: "" }
    : { action: "enable-followup-auto-send", label: "후속 자동 발송 켜기", className: "primary" };
  const followupTone = settings.followup_ready ? "ok" : settings.followup_blockers?.length ? "warn" : "neutral";
  const blockerText = (settings.followup_blockers || []).join(" ");
  return `
    <section class="settings-group">
      <h3>폼 자동 발송</h3>
      <div class="automation-control">
        <div class="automation-head">
          <div>
            <span class="mini-badge ${followupTone}">후속 자동 발송 ${settings.followups_enabled ? "켜짐" : "꺼짐"}</span>
            <strong>후속 메일 자동 발송</strong>
            <p>${safe(settings.followup_status_detail || "상태 확인 전입니다.")}</p>
          </div>
          <div class="button-row automation-buttons">
            <button type="button" class="${followupAction.className}" data-action="${followupAction.action}">${followupAction.label}</button>
            <button type="button" data-action="check-followup-status">상태 확인</button>
            <button type="button" data-action="run-due-followups">후속 메일 지금 실행</button>
          </div>
        </div>
        <div class="automation-status-grid">
          ${renderAutomationStat("현재 상태", settings.followup_status_label || "확인 전", settings.followup_gmail_ready ? "Gmail 발송 준비됨" : "Gmail 권한 확인 필요", followupTone)}
          ${renderAutomationStat("지금 발송 대상", `${Number(settings.followup_due_count || 0)}건`, "예약일이 지났고 아직 발송 전인 명단", Number(settings.followup_due_count || 0) ? "ok" : "neutral")}
          ${renderAutomationStat("오늘 후속 발송", `${Number(settings.followup_sent_today || 0)}/${Number(settings.followup_daily_limit || 20)}건`, `남은 한도 ${Number(settings.followup_remaining_today || 0)}건`, Number(settings.followup_remaining_today || 0) ? "ok" : "warn")}
        </div>
        ${blockerText ? `<p class="automation-warning">${safe(blockerText)}</p>` : ""}
        ${renderFollowupDuePreview(settings.followup_due_preview || [])}
      </div>
      <label class="checkbox-field">
        <input type="checkbox" data-form-auto-send-enabled ${settings.enabled ? "checked" : ""} />
        <span>새 Google Form 응답이 들어오면 첫 단계 메일을 바로 발송</span>
      </label>
      <label class="field">
        <span>첫 메일 하루 자동 발송 제한</span>
        <input type="number" min="1" max="500" data-form-auto-send-limit value="${safe(settings.daily_limit || 20)}" />
      </label>
      <label class="checkbox-field">
        <input type="checkbox" data-followup-auto-send-enabled ${settings.followups_enabled ? "checked" : ""} />
        <span>예약일이 지난 후속 메일도 자동 발송</span>
      </label>
      <label class="field">
        <span>후속 메일 하루 자동 발송 제한</span>
        <input type="number" min="1" max="500" data-followup-auto-send-limit value="${safe(settings.followup_daily_limit || 20)}" />
      </label>
      <p class="settings-note">첫 메일 ${Number(settings.sent_today || 0)}건, 후속 메일 ${Number(settings.followup_sent_today || 0)}건을 오늘 자동 발송했습니다. 후속 자동 발송은 각 단계 메일의 실제 발송일 기준 예약을 따릅니다.</p>
      <button type="button" data-action="save-form-auto-send">자동 발송 설정 저장</button>
    </section>`;
}

function renderAutomationStat(label, value, detail, tone = "neutral") {
  return `
    <div class="automation-stat ${tone}">
      <span>${safe(label)}</span>
      <strong>${safe(value)}</strong>
      <small>${safe(detail)}</small>
    </div>`;
}

function renderFollowupDuePreview(rows) {
  if (!rows.length) {
    return `<p class="settings-note">상태 확인을 누르면 지금 발송 가능한 후속 메일 대상이 표시됩니다.</p>`;
  }
  return `
    <div class="followup-preview">
      <strong>지금 발송 대상 미리보기</strong>
      <ul>
        ${rows.map((row) => `
          <li>
            <span>${safe(row.email || "")}</span>
            <small>${safe(row.campaign_step || row.template || "후속 메일")} · ${safe(row.next_send_at || "예약일 확인 필요")}</small>
          </li>`).join("")}
      </ul>
    </div>`;
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

function cloneData(value) {
  return JSON.parse(JSON.stringify(value ?? null));
}

function deliverySetId(name = "set") {
  const base = String(name || "set").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "set";
  let candidate = `${base}-${Date.now().toString(36)}`;
  while (state.deliverySets.some((set) => set.id === candidate)) {
    candidate = `${base}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1000)}`;
  }
  return candidate;
}

function deliverySetSnapshot(overrides = {}) {
  const config = { ...state.config };
  return {
    id: overrides.id || state.activeSetId || deliverySetId(config.campaign_id),
    name: overrides.name || activeDeliverySet()?.name || config.campaign_id || "퍼널메일 시리즈",
    status: overrides.status || activeDeliverySet()?.status || "active",
    description: overrides.description ?? activeDeliverySet()?.description ?? "",
    config,
    flowSteps: cloneData(state.flowSteps || []),
    formAutoSend: cloneData(state.formAutoSend || {}),
    updated_at: new Date().toISOString()
  };
}

function normaliseDeliverySet(raw = {}, index = 0) {
  const config = { ...fallbackDefaults, ...(raw.config || {}) };
  const name = String(raw.name || config.campaign_id || `퍼널메일 시리즈 ${index + 1}`).trim();
  return {
    id: String(raw.id || deliverySetId(name)),
    name,
    status: raw.status === "paused" ? "paused" : "active",
    description: String(raw.description || ""),
    config,
    flowSteps: Array.isArray(raw.flowSteps) ? raw.flowSteps : [],
    formAutoSend: raw.formAutoSend && typeof raw.formAutoSend === "object" ? { ...defaultFormAutoSend, ...raw.formAutoSend } : { ...defaultFormAutoSend },
    updated_at: raw.updated_at || ""
  };
}

function loadDeliverySetsFromStorage() {
  try {
    const saved = JSON.parse(localStorage.getItem(DELIVERY_SET_STORAGE_KEY) || "{}");
    const sets = Array.isArray(saved.sets) ? saved.sets.map(normaliseDeliverySet) : [];
    state.deliverySets = sets;
    state.activeSetId = sets.some((set) => set.id === saved.activeSetId)
      ? saved.activeSetId
      : sets[0]?.id || "";
  } catch {
    state.deliverySets = [];
    state.activeSetId = "";
  }
}

function persistDeliverySets() {
  try {
    localStorage.setItem(
      DELIVERY_SET_STORAGE_KEY,
      JSON.stringify({
        activeSetId: state.activeSetId,
        sets: state.deliverySets
      })
    );
  } catch {
    setNotice("브라우저 저장소에 퍼널메일 시리즈를 저장하지 못했습니다.", "error");
  }
}

function activeDeliverySet() {
  return state.deliverySets.find((set) => set.id === state.activeSetId) || null;
}

function ensureDeliverySets() {
  if (state.deliverySets.length) return;
  const set = normaliseDeliverySet(deliverySetSnapshot({ id: deliverySetId(state.config.campaign_id) }));
  state.deliverySets = [set];
  state.activeSetId = set.id;
  persistDeliverySets();
}

function applyDeliverySet(set) {
  if (!set) return;
  state.activeSetId = set.id;
  state.config = { ...fallbackDefaults, ...state.config, ...set.config };
  state.flowSteps = cloneData(set.flowSteps || []);
  state.formAutoSend = { ...defaultFormAutoSend, ...(set.formAutoSend || {}) };
}

async function selectDeliverySet(id) {
  const set = state.deliverySets.find((item) => item.id === id);
  if (!set) return;
  if (id === state.activeSetId) {
    setNotice(`${set.name} 시리즈가 이미 열려 있습니다.`);
    render();
    return;
  }
  if (state.activeSetId) await saveActiveDeliverySet({ silent: true });
  applyDeliverySet(set);
  persistDeliverySets();
  state.activeTab = "flow";
  setNotice(`${set.name} 시리즈를 불러왔습니다.`, "success");
  render();
}

async function loadSelectedDeliverySet() {
  ensureDeliverySets();
  const selectedId = document.querySelector("[data-delivery-set-select]")?.value || state.activeSetId;
  if (!selectedId) {
    setNotice("불러올 퍼널메일 시리즈를 선택하세요.", "error");
    render();
    return;
  }
  await selectDeliverySet(selectedId);
}

async function saveActiveDeliverySet({ silent = false } = {}) {
  formData();
  const current = activeDeliverySet();
  const snapshot = deliverySetSnapshot({
    id: current?.id || deliverySetId(state.config.campaign_id),
    name: current?.name,
    status: current?.status,
    description: current?.description
  });
  const index = state.deliverySets.findIndex((set) => set.id === snapshot.id);
  if (index >= 0) state.deliverySets[index] = snapshot;
  else state.deliverySets.push(snapshot);
  state.activeSetId = snapshot.id;
  persistDeliverySets();
  if (!silent) {
    setNotice(`"${snapshot.name}"을 저장했습니다.`, "success");
    render();
  }
}

async function createDeliverySet() {
  if (state.activeSetId) await saveActiveDeliverySet({ silent: true });
  const number = state.deliverySets.length + 1;
  const id = deliverySetId(`email-series-${number}`);
  const config = {
    ...state.config,
    campaign_id: `email-series-${number}`,
    funnel_config: state.config.funnel_config || fallbackDefaults.funnel_config
  };
  const set = normaliseDeliverySet({
    id,
    name: `퍼널메일 시리즈 ${number}`,
    status: "active",
    description: "",
    config,
    flowSteps: [],
    formAutoSend: { ...state.formAutoSend, enabled: false, followups_enabled: false }
  });
  state.deliverySets.push(set);
  applyDeliverySet(set);
  persistDeliverySets();
  state.activeTab = "flow";
  setNotice("새 퍼널메일 시리즈를 만들었습니다. 메일을 추가한 뒤 시리즈 저장을 누르세요.", "success");
  render();
}

async function duplicateDeliverySet() {
  if (state.activeSetId) await saveActiveDeliverySet({ silent: true });
  const current = activeDeliverySet();
  const source = current || deliverySetSnapshot();
  const copy = normaliseDeliverySet({
    ...cloneData(source),
    id: deliverySetId(`${source.name}-copy`),
    name: `${source.name} 복사본`,
    updated_at: new Date().toISOString()
  });
  state.deliverySets.push(copy);
  applyDeliverySet(copy);
  persistDeliverySets();
  state.activeTab = "flow";
  setNotice(`${copy.name} 시리즈를 만들었습니다.`, "success");
  render();
}

async function deleteDeliverySet() {
  const current = activeDeliverySet();
  if (!current) return;
  if (state.deliverySets.length <= 1) {
    setNotice("최소 하나의 퍼널메일 시리즈는 남겨야 합니다.", "error");
    return;
  }
  if (!globalThis.confirm(`${current.name} 시리즈를 삭제할까요? 브라우저에 저장된 이 시리즈 내용이 삭제됩니다.`)) return;
  state.deliverySets = state.deliverySets.filter((set) => set.id !== current.id);
  applyDeliverySet(state.deliverySets[0]);
  persistDeliverySets();
  setNotice("퍼널메일 시리즈를 삭제했습니다.", "success");
  render();
}

function updateDeliverySetField(field, value) {
  const current = activeDeliverySet();
  if (!current) return;
  current[field] = String(value || "").trim();
  current.updated_at = new Date().toISOString();
}

function renderConnectionSetupGuide() {
  const setup = state.googleSetup || {};
  const redirectUri = setup.redirect_uri || `${apiBase || window.location.origin}/oauth/google/callback`;
  const credentialsPath = setup.credentials_path || state.config.google_credentials || fallbackDefaults.google_credentials;
  const tokenPath = setup.token_path || state.config.google_token || fallbackDefaults.google_token;
  const sheetName = state.config.gmail_sheet_name || setup.sheet_name || fallbackDefaults.gmail_sheet_name;
  const sheetSource = state.config.gmail_source || "";
  const testEmail = state.config.test_email || "";

  return `
    <section class="connection-guide" aria-label="Google 메일 연결 절차">
      <div class="connection-guide-head">
        <div>
          <h3>메일 연결 절차</h3>
          <p>연결 설정에서 필요한 값을 바로 수정하고, 상태 확인으로 빠진 항목을 확인한 뒤 Google 연결을 완료합니다.</p>
        </div>
        <div class="button-row">
          <a class="link-button" href="https://console.cloud.google.com/apis/library/sheets.googleapis.com" target="_blank" rel="noopener">Sheets API</a>
          <a class="link-button" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">OAuth Client</a>
        </div>
      </div>
      <ol class="connection-steps">
        <li>
          <strong>Google Cloud 준비</strong>
          <span>Sheets API를 켜고 OAuth Client를 만듭니다. 승인된 리디렉션 URI에는 아래 값을 그대로 등록합니다.</span>
        </li>
        <li>
          <strong>인증 파일 저장</strong>
          <span>Google Cloud에서 받은 OAuth JSON을 아래 인증 파일 경로에 저장합니다. 화면에는 파일 경로만 표시합니다.</span>
        </li>
        <li>
          <strong>시트 입력</strong>
          <span>고객 이메일과 발송 결과를 관리할 Google Sheet 링크와 Sheet 이름을 운영 입력에 넣습니다.</span>
        </li>
        <li>
          <strong>Google 연결</strong>
          <span>Google 연결을 눌러 권한을 승인합니다. 발급된 토큰은 로컬 토큰 파일에 저장되고 내용은 화면에 표시하지 않습니다.</span>
        </li>
        <li>
          <strong>상태 확인과 테스트</strong>
          <span>상태 확인으로 모든 항목이 완료인지 확인하고, 테스트 수신자에 실제 받을 주소를 넣어 테스트 발송을 실행합니다.</span>
        </li>
      </ol>
      <div class="connection-values" aria-label="현재 연결 설정값">
        ${renderConnectionValue("승인 리디렉션 URI", redirectUri, "Google Cloud OAuth Client에 등록할 값", "neutral")}
        ${renderConnectionInput("Google Sheet 링크", "gmail_source", sheetSource, sheetSource ? "운영 입력에 저장된 시트 링크" : "여기에 시트 링크 입력", sheetSource ? "ok" : "warn", "https://docs.google.com/spreadsheets/...")}
        ${renderConnectionInput("Sheet 이름", "gmail_sheet_name", sheetName, "발송 준비/결과를 읽고 쓸 탭 이름", "neutral", "GmailQueue")}
        ${renderConnectionInput("Google 인증 파일", "google_credentials", credentialsPath, "client_secret 값은 파일 안에만 보관", "neutral", "config/google_oauth_client.json")}
        ${renderConnectionInput("Google 토큰 파일", "google_token", tokenPath, "refresh_token 값은 화면에 표시하지 않음", "neutral", "state/google_sheets_token.json")}
        ${renderConnectionInput("테스트 수신자", "test_email", testEmail, testEmail ? "테스트 메일을 받을 주소" : "테스트 발송 전 입력 권장", testEmail ? "ok" : "warn", "name@example.com")}
      </div>
      <p class="sensitive-note">표시하지 않는 값: OAuth client_secret, access_token, refresh_token, 메일 계정 비밀번호.</p>
    </section>`;
}

function renderConnectionValue(label, value, detail, tone = "neutral") {
  return `
    <div class="connection-value ${tone}">
      <span>${safe(label)}</span>
      <code>${safe(value)}</code>
      <small>${safe(detail)}</small>
    </div>`;
}

function renderConnectionInput(label, key, value, detail, tone = "neutral", placeholder = "") {
  return `
    <label class="connection-value editable ${tone}">
      <span>${safe(label)}</span>
      <input data-config="${safe(key)}" value="${safe(value)}" placeholder="${safe(placeholder)}" />
      <small>${safe(detail)}</small>
    </label>`;
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
      ${renderContactActions()}
      <div class="summary-row">
        ${summaryItem("보낼 예정", state.queueCounts.ready || 0)}
        ${summaryItem("기다림", state.queueCounts.scheduled || 0)}
        ${summaryItem("제외", state.queueCounts.skipped || 0)}
      </div>
      ${renderContactsTable()}
    </section>`;
}

function renderContactActions() {
  const selectedRows = selectedContactRows();
  const readyRows = selectedRows.filter((row) => row.status === "ready");
  const hasRows = state.queueRows.length > 0;
  const hasSelected = selectedRows.length > 0;
  const hasReady = readyRows.length > 0;
  return `
    <div class="contact-actions">
      <div>
        <strong>선택한 명단 ${selectedRows.length}명</strong>
        <span>${hasSelected ? `바로 승인 가능 ${readyRows.length}명` : "보낼 사람을 체크하세요."}</span>
      </div>
      <div class="button-row">
        <button type="button" data-action="select-all-contacts" ${hasRows ? "" : "disabled"}>전체 선택</button>
        <button type="button" data-action="clear-contact-selection" ${hasSelected ? "" : "disabled"}>선택 해제</button>
        <button class="primary" type="button" data-action="approve-selected-contacts" ${hasReady ? "" : "disabled"}>선택한 명단만 보내기</button>
        <button type="button" data-action="delete-selected-contacts" ${hasSelected ? "" : "disabled"}>선택 삭제</button>
        <button class="danger" type="button" data-action="delete-all-contacts" ${hasRows ? "" : "disabled"}>전체 삭제</button>
      </div>
    </div>`;
}

function renderContactsTable() {
  if (!state.queueRows.length) {
    return `<p class="empty">아직 명단을 확인하지 않았습니다.</p>`;
  }
  const visibleRows = state.queueRows.slice(0, 80);
  const allVisibleSelected = visibleRows.length > 0 && visibleRows.every((row) => state.contactSelection.has(String(row.email || "").toLowerCase()));
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="select-col"><input type="checkbox" data-contact-toggle-visible ${allVisibleSelected ? "checked" : ""} aria-label="표시된 명단 선택" /></th>
            <th>${safe(columnLabel("status"))}</th>
            <th>${safe(columnLabel("email"))}</th>
            <th>${safe(columnLabel("template"))}</th>
            <th>${safe(columnLabel("campaign_step"))}</th>
            <th>${safe(columnLabel("next_send_at"))}</th>
            <th>${safe(columnLabel("detail"))}</th>
          </tr>
        </thead>
        <tbody>
          ${visibleRows.map((row) => {
            const email = String(row.email || "").toLowerCase();
            return `
            <tr class="${state.contactSelection.has(email) ? "selected-row" : ""}">
              <td class="select-col"><input type="checkbox" data-contact-select="${safe(email)}" ${state.contactSelection.has(email) ? "checked" : ""} aria-label="${safe(row.email)} 선택" /></td>
              <td>${safe(statusLabels[row.status] || row.status || "")}</td>
              <td>${safe(row.email || "")}</td>
              <td>${safe(row.template || "")}</td>
              <td>${safe(row.campaign_step || row.rule || "")}</td>
              <td>${safe(row.next_send_at || "")}</td>
              <td>${safe(row.detail || "")}</td>
            </tr>
          `;
          }).join("")}
        </tbody>
      </table>
      ${state.queueRows.length > visibleRows.length ? `<p class="table-note">처음 ${visibleRows.length}건만 표시합니다. 전체 선택은 불러온 명단 전체에 적용됩니다.</p>` : ""}
    </div>`;
}

function renderContactImportReview() {
  const draft = state.contactImportDraft;
  if (!draft) return "";
  const disabled = draft.validCount ? "" : "disabled";
  const sourceLabel = draft.sheetName ? `${draft.filename} · ${draft.sheetName}` : draft.filename;
  return `
    <section class="import-review" aria-label="새 명단 확인">
      <div class="import-review-head">
        <div>
          <span class="mini-badge">새 명단 확인</span>
          <h3>저장 전에 앱이 찾은 열을 확인하세요</h3>
          <p>${safe(sourceLabel)}에서 이메일 ${draft.validCount}건을 찾았습니다. 맞지 않으면 아래에서 바로 바꿀 수 있습니다.</p>
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
          <h2>퍼널메일 시리즈</h2>
          <p>시리즈별로 메일 순서와 이전 메일 기준 발송 시점을 관리합니다.</p>
        </div>
      </div>
      ${renderDeliverySetManager()}
      <div class="flow-help">
        <strong>메일 흐름의 역할</strong>
        <span>첫 메일은 조건이 맞거나 승인되면 발송되고, 후속 메일은 첫 메일 또는 이전 메일 발송 후 +며칠 뒤 정해진 시간에 보내거나 특정 날짜와 시간을 지정합니다.</span>
      </div>
      <div class="flow-list">
        ${
          state.flowSteps.length
            ? state.flowSteps.map(renderFlowStep).join("")
            : `<p class="empty">아직 메일 흐름을 불러오지 않았습니다.</p>`
        }
      </div>
      <div class="flow-add-row">
        <button type="button" data-action="add-flow-step" class="primary">메일 추가</button>
      </div>
    </section>`;
}

function renderDeliverySetManager() {
  ensureDeliverySets();
  const current = activeDeliverySet();
  const options = state.deliverySets.map((set) => {
    const selected = set.id === state.activeSetId ? "selected" : "";
    const status = set.status === "paused" ? "일시정지" : "활성";
    return `<option value="${safe(set.id)}" ${selected}>${safe(set.name)} · ${status}</option>`;
  }).join("");
  const stepCount = state.flowSteps.length;
  const updated = current?.updated_at ? new Date(current.updated_at).toLocaleString("ko-KR") : "아직 저장 전";
  return `
    <section class="set-manager" aria-label="퍼널메일 시리즈 관리">
      <div class="set-manager-head">
        <div>
          <h3>퍼널메일 시리즈</h3>
          <p>행사, 상품, 고객군별로 연결 설정과 메일 순서를 따로 저장합니다.</p>
        </div>
        <div class="button-row">
          <button type="button" data-action="new-delivery-set">새 퍼널메일 시리즈 추가</button>
          <button type="button" data-action="save-delivery-set" class="primary">퍼널메일 시리즈 저장</button>
          <button type="button" data-action="load-delivery-set">퍼널메일 시리즈 불러오기</button>
          <button type="button" data-action="duplicate-delivery-set">복제</button>
          <button type="button" data-action="delete-delivery-set" class="danger">삭제</button>
        </div>
      </div>
      <div class="set-grid">
        <label class="field">
          <span>현재 시리즈</span>
          <select data-delivery-set-select>${options}</select>
        </label>
        <label class="field">
          <span>시리즈 이름</span>
          <input data-delivery-set-field="name" value="${safe(current?.name || "")}" />
        </label>
        <label class="field">
          <span>상태</span>
          <select data-delivery-set-field="status">
            <option value="active" ${current?.status === "paused" ? "" : "selected"}>활성</option>
            <option value="paused" ${current?.status === "paused" ? "selected" : ""}>일시정지</option>
          </select>
        </label>
        <label class="field">
          <span>설명</span>
          <input data-delivery-set-field="description" value="${safe(current?.description || "")}" placeholder="예: 7월 세미나 참석 고객" />
        </label>
      </div>
      <div class="set-summary">
        <span>메일 ${stepCount}개</span>
        <span>캠페인 ${safe(state.config.campaign_id || "미입력")}</span>
        <span>발송 설정 ${safe(state.config.funnel_config || "미입력")}</span>
        <span>마지막 저장 ${safe(updated)}</span>
      </div>
    </section>`;
}

function renderFlowStep(step, index) {
  const mode = flowArrivalMode(index);
  const link = incomingFlowLink(index);
  const canSelectPrevious = index > 0;
  return `
    <article class="flow-step">
      <div class="flow-head">
        <div>
          <span class="mini-badge ${link ? "ok" : ""}">${link ? "후속 메일" : "첫 메일"}</span>
          <h3>${safe(step.stage_label || step.template || `메일 ${index + 1}`)}</h3>
          <p>${safe(flowScheduleLabel(step, index))}</p>
        </div>
        <div class="button-row">
          <label class="file-button">
            Word 불러오기
            <input type="file" accept=".docx" data-word-index="${index}" />
          </label>
          <button type="button" data-flow-delete-index="${index}">삭제</button>
        </div>
      </div>
      <div class="flow-grid">
        <label class="field">
          <span>단계 이름</span>
          <input data-flow-index="${index}" data-flow-field="stage_label" value="${safe(step.stage_label || "")}" />
        </label>
        <label class="field">
          <span>대상 설명</span>
          <input data-flow-index="${index}" data-flow-field="audience" value="${safe(step.audience || "")}" />
        </label>
        <label class="field">
          <span>메일 이름</span>
          <input data-flow-index="${index}" data-flow-field="template" value="${safe(step.template || "")}" />
        </label>
        <label class="field">
          <span>발송 기준</span>
          <select data-flow-arrival-mode data-flow-index="${index}">
            <option value="start" ${mode === "start" ? "selected" : ""}>시리즈 시작 메일</option>
            <option value="first_days" ${mode === "first_days" ? "selected" : ""} ${canSelectPrevious ? "" : "disabled"}>첫 메일 발송 이후</option>
            <option value="previous_days" ${mode === "previous_days" ? "selected" : ""} ${canSelectPrevious ? "" : "disabled"}>이전 메일 발송 이후</option>
            <option value="date" ${mode === "date" ? "selected" : ""} ${canSelectPrevious ? "" : "disabled"}>특정 날짜에 발송</option>
          </select>
        </label>
      </div>
      <div class="flow-grid schedule-grid">
        ${renderPreviousStepControl(index, mode)}
        ${renderFlowScheduleControls(index, mode)}
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

function renderPreviousStepControl(index, mode) {
  if (mode === "start") {
    return `
      <label class="field">
        <span>기준 메일</span>
        <input value="없음 · 이 시리즈의 시작 메일" disabled />
      </label>`;
  }
  const source = scheduleSource(index, mode);
  const label = source ? source.step.stage_label || source.step.template || `메일 ${source.index + 1}` : "이전 메일 없음";
  return `
    <label class="field">
      <span>기준 메일</span>
      <input value="${safe(label)}" disabled />
    </label>`;
}

function renderFlowScheduleControls(index, mode) {
  const link = incomingFlowLink(index);
  if (mode === "date") {
    return `
      <label class="field">
        <span>발송 날짜</span>
        <input type="date" data-flow-index="${index}" data-flow-link-field="next_send_at" value="${safe(link?.step.next_send_at || "")}" />
      </label>
      <label class="field">
        <span>발송 시간</span>
        <input type="time" data-flow-index="${index}" data-flow-link-field="next_send_time" value="${safe(sendTimeValue(link?.step))}" />
      </label>`;
  }
  if (isRelativeScheduleMode(mode)) {
    return `
      <label class="field">
        <span>+ 며칠 후</span>
        <input type="number" min="0" step="1" data-flow-index="${index}" data-flow-link-field="next_send_after_days" value="${safe(link?.step.next_send_after_days || "")}" />
        <small>예: 3을 입력하면 기준 메일 발송 3일 뒤입니다.</small>
      </label>
      <label class="field">
        <span>발송 시간</span>
        <input type="time" data-flow-index="${index}" data-flow-link-field="next_send_time" value="${safe(sendTimeValue(link?.step))}" />
      </label>`;
  }
  return `
    <label class="field">
      <span>발송 시점</span>
      <input value="조건이 맞거나 승인되면 첫 메일로 발송" disabled />
    </label>`;
}

function renderPreviousStepOptions(index) {
  const link = incomingFlowLink(index);
  const current = link ? String(link.index) : String(defaultPreviousStepIndex(index));
  const options = [];
  state.flowSteps.forEach((candidate, candidateIndex) => {
    if (candidateIndex >= index) return;
    const label = candidate.stage_label || candidate.template || `메일 ${candidateIndex + 1}`;
    options.push(`<option value="${candidateIndex}" ${current === String(candidateIndex) ? "selected" : ""}>${safe(candidateIndex + 1)}. ${safe(label)}</option>`);
  });
  return options.join("");
}

function isRelativeScheduleMode(mode) {
  return mode === "first_days" || mode === "previous_days" || mode === "days";
}

function sendTimeValue(step) {
  return String(step?.next_send_time || DEFAULT_SEND_TIME).slice(0, 5);
}

function scheduleSourceIndex(index, mode) {
  if (index <= 0) return -1;
  if (mode === "first_days") return 0;
  return index - 1;
}

function scheduleSource(index, mode) {
  const sourceIndex = scheduleSourceIndex(index, mode);
  const step = state.flowSteps[sourceIndex];
  return step ? { index: sourceIndex, step } : null;
}

function flowStepIndexById(id) {
  const targetId = String(id || "");
  if (!targetId) return -1;
  return state.flowSteps.findIndex((step, index) => flowStepId(step, index) === targetId);
}

function outgoingScheduleMode(step, index = -1) {
  if (!step.next_step) return "none";
  if (index >= 0) {
    const nextIndex = flowStepIndexById(step.next_step);
    if (nextIndex <= index) return "none";
  }
  if (step.schedule_mode === "date") return "date";
  if (step.schedule_mode === "first_days") return "first_days";
  if (step.schedule_mode === "previous_days" || step.schedule_mode === "days") return "previous_days";
  if (step.next_send_at) return "date";
  if (step.next_send_after_days !== undefined && String(step.next_send_after_days).trim() !== "") return "previous_days";
  return "previous_days";
}

function flowArrivalMode(index) {
  const link = incomingFlowLink(index);
  if (!link) return "start";
  if (link.step.next_send_at || link.step.schedule_mode === "date") return "date";
  if (link.step.schedule_mode === "first_days") return "first_days";
  if (link.step.schedule_mode === "previous_days" || link.step.schedule_mode === "days") return "previous_days";
  return link.index === 0 && index > 1 ? "first_days" : "previous_days";
}

function flowScheduleLabel(step, index) {
  const mode = flowArrivalMode(index);
  const link = incomingFlowLink(index);
  if (!link || mode === "start") return "첫 메일 · 조건이 맞거나 승인되면 발송";
  const previousLabel = link.step.stage_label || link.step.template || `메일 ${link.index + 1}`;
  const time = sendTimeValue(link.step);
  if (mode === "date") {
    return link.step.next_send_at
      ? `${link.step.next_send_at} ${time}에 발송`
      : `특정 날짜 ${time}에 발송`;
  }
  const days = String(link.step.next_send_after_days || "").trim() || "1";
  const baseLabel = mode === "first_days" ? "첫 메일" : previousLabel;
  return `${baseLabel} 발송 후 ${days}일 뒤 ${time} 발송`;
}

function incomingFlowLink(index) {
  const current = state.flowSteps[index];
  if (!current) return null;
  const currentId = flowStepId(current, index);
  for (let candidateIndex = 0; candidateIndex < state.flowSteps.length; candidateIndex += 1) {
    if (candidateIndex >= index) continue;
    const candidate = state.flowSteps[candidateIndex];
    if (String(candidate.next_step || "") === currentId) {
      return { index: candidateIndex, step: candidate };
    }
  }
  return null;
}

function clearIncomingFlowLinks(index, exceptIndex = -1) {
  const current = state.flowSteps[index];
  if (!current) return;
  const currentId = flowStepId(current, index);
  state.flowSteps.forEach((candidate, candidateIndex) => {
    if (candidateIndex === exceptIndex) return;
    if (String(candidate.next_step || "") === currentId) {
      candidate.next_step = "";
      candidate.next_send_after_days = "";
      candidate.next_send_at = "";
      candidate.next_send_time = "";
      candidate.schedule_mode = "none";
      candidate.send_after_label = "후속 발송 없음";
    }
  });
}

function defaultPreviousStepIndex(index) {
  if (index > 0) return index - 1;
  return -1;
}

function ensureIncomingFlowLink(index, mode = "days", previousIndex = null) {
  const current = state.flowSteps[index];
  if (!current) return null;
  const currentId = flowStepId(current, index);
  const selectedIndex = previousIndex ?? scheduleSourceIndex(index, mode);
  const previous = state.flowSteps[selectedIndex];
  if (!previous || selectedIndex >= index) return null;
  clearIncomingFlowLinks(index, selectedIndex);
  previous.next_step = currentId;
  previous.schedule_mode = mode === "days" ? "previous_days" : mode;
  if (mode === "date") {
    previous.next_send_after_days = "";
    previous.next_send_at = previous.next_send_at || "";
    previous.next_send_time = sendTimeValue(previous);
    previous.send_after_label = previous.next_send_at ? `${previous.next_send_at} ${previous.next_send_time}에 다음 메일` : "특정 날짜에 다음 메일";
  } else {
    previous.next_send_at = "";
    previous.next_send_after_days = String(previous.next_send_after_days || "").trim() || "1";
    previous.next_send_time = sendTimeValue(previous);
    previous.send_after_label = `이 메일 발송 후 ${previous.next_send_after_days}일 뒤 ${previous.next_send_time}에 다음 메일`;
  }
  return { index: selectedIndex, step: previous };
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

function applyGoogleSetup(data = {}) {
  if (Array.isArray(data.steps)) state.googleSteps = data.steps;
  state.googleSetup = {
    credentials_path: data.credentials_path || state.googleSetup.credentials_path || state.config.google_credentials,
    token_path: data.token_path || state.googleSetup.token_path || state.config.google_token,
    redirect_uri: data.redirect_uri || state.googleSetup.redirect_uri || `${apiBase || window.location.origin}/oauth/google/callback`,
    sheet_name: data.sheet_name || state.googleSetup.sheet_name || state.config.gmail_sheet_name || fallbackDefaults.gmail_sheet_name
  };
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
    next_send_at: "다음 발송일시",
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
      setConfigValue(input.dataset.config, input.value, input);
    });
  }

  for (const input of document.querySelectorAll("[data-delivery-set-field]")) {
    input.addEventListener("input", () => updateDeliverySetField(input.dataset.deliverySetField, input.value));
    input.addEventListener("change", () => updateDeliverySetField(input.dataset.deliverySetField, input.value));
  }

  const autoSendEnabled = document.querySelector("[data-form-auto-send-enabled]");
  if (autoSendEnabled) {
    autoSendEnabled.addEventListener("change", () => {
      state.formAutoSend.enabled = autoSendEnabled.checked;
      render();
    });
  }

  const autoSendLimit = document.querySelector("[data-form-auto-send-limit]");
  if (autoSendLimit) {
    autoSendLimit.addEventListener("input", () => {
      state.formAutoSend.daily_limit = Number(autoSendLimit.value || 20);
    });
  }

  const followupSendEnabled = document.querySelector("[data-followup-auto-send-enabled]");
  if (followupSendEnabled) {
    followupSendEnabled.addEventListener("change", () => {
      state.formAutoSend.followups_enabled = followupSendEnabled.checked;
      render();
    });
  }

  const followupSendLimit = document.querySelector("[data-followup-auto-send-limit]");
  if (followupSendLimit) {
    followupSendLimit.addEventListener("input", () => {
      state.formAutoSend.followup_daily_limit = Number(followupSendLimit.value || 20);
    });
  }

  for (const input of document.querySelectorAll("[data-flow-index]")) {
    input.addEventListener("input", () => updateFlowField(input));
    input.addEventListener("change", () => updateFlowField(input));
  }

  for (const input of document.querySelectorAll("[data-flow-arrival-mode]")) {
    input.addEventListener("change", () => updateFlowArrivalMode(input));
  }

  for (const input of document.querySelectorAll("[data-flow-previous-step]")) {
    input.addEventListener("change", () => updateFlowPreviousStep(input));
  }

  for (const input of document.querySelectorAll("[data-flow-link-field]")) {
    input.addEventListener("input", () => updateFlowLinkField(input));
    input.addEventListener("change", () => updateFlowLinkField(input));
  }

  for (const button of document.querySelectorAll("[data-flow-delete-index]")) {
    button.addEventListener("click", () => deleteFlowStep(Number(button.dataset.flowDeleteIndex)));
  }

  for (const input of document.querySelectorAll("[data-approval-index]")) {
    input.addEventListener("change", () => {
      const row = state.approvalRows[Number(input.dataset.approvalIndex)];
      if (row) row.approved = input.checked ? "yes" : "no";
      state.approvalCounts = countApprovals(state.approvalRows);
      render();
    });
  }

  for (const input of document.querySelectorAll("[data-contact-select]")) {
    input.addEventListener("change", () => {
      const email = String(input.dataset.contactSelect || "").toLowerCase();
      if (input.checked) state.contactSelection.add(email);
      else state.contactSelection.delete(email);
      syncContactSelection();
      render();
    });
  }

  for (const input of document.querySelectorAll("[data-contact-toggle-visible]")) {
    input.addEventListener("change", () => {
      const visibleRows = state.queueRows.slice(0, 80);
      for (const row of visibleRows) {
        const email = String(row.email || "").toLowerCase();
        if (input.checked) state.contactSelection.add(email);
        else state.contactSelection.delete(email);
      }
      syncContactSelection();
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

function syncContactSelection(rows = state.queueRows) {
  const existing = new Set(rows.map((row) => String(row.email || "").toLowerCase()).filter(Boolean));
  for (const email of Array.from(state.contactSelection)) {
    if (!existing.has(email)) state.contactSelection.delete(email);
  }
}

function selectedContactRows() {
  syncContactSelection();
  return state.queueRows.filter((row) => state.contactSelection.has(String(row.email || "").toLowerCase()));
}

function selectedContactEmails() {
  return selectedContactRows().map((row) => String(row.email || "").toLowerCase());
}

async function selectAllContacts() {
  for (const row of state.queueRows) {
    const email = String(row.email || "").toLowerCase();
    if (email) state.contactSelection.add(email);
  }
  setNotice(`명단 ${state.contactSelection.size}명을 선택했습니다.`);
  render();
}

async function clearContactSelection() {
  state.contactSelection.clear();
  setNotice("명단 선택을 해제했습니다.");
  render();
}

function updateFlowField(input) {
  if (!input.dataset.flowField) return;
  const step = state.flowSteps[Number(input.dataset.flowIndex)];
  if (!step) return;
  const field = input.dataset.flowField;
  step[field] = input.value;
  if (input.dataset.flowRepaint === "yes") render();
}

function updateFlowArrivalMode(input) {
  const index = Number(input.dataset.flowIndex);
  const mode = input.value;
  if (mode === "start") {
    clearIncomingFlowLinks(index);
  } else {
    ensureIncomingFlowLink(index, mode);
  }
  render();
}

function updateFlowPreviousStep(input) {
  const index = Number(input.dataset.flowIndex);
  const previousIndex = Number(input.value);
  const mode = flowArrivalMode(index) === "date" ? "date" : "previous_days";
  ensureIncomingFlowLink(index, mode, previousIndex);
  render();
}

function updateFlowLinkField(input) {
  const index = Number(input.dataset.flowIndex);
  const field = input.dataset.flowLinkField;
  const mode = flowArrivalMode(index);
  const link = ensureIncomingFlowLink(index, mode);
  if (!link) return;
  link.step[field] = input.value;
  if (field === "next_send_after_days") {
    link.step.next_send_at = "";
    link.step.schedule_mode = isRelativeScheduleMode(mode) ? mode : "previous_days";
    link.step.send_after_label = input.value ? `이 메일 발송 후 ${input.value}일 뒤 ${sendTimeValue(link.step)}에 다음 메일` : "다음 메일까지 간격 필요";
  } else if (field === "next_send_at") {
    link.step.next_send_after_days = "";
    link.step.schedule_mode = "date";
    link.step.send_after_label = input.value ? `${input.value} ${sendTimeValue(link.step)}에 다음 메일` : "특정 날짜 선택 필요";
  } else if (field === "next_send_time") {
    link.step.next_send_time = sendTimeValue(link.step);
    if (mode === "date") {
      link.step.schedule_mode = "date";
      link.step.send_after_label = link.step.next_send_at ? `${link.step.next_send_at} ${link.step.next_send_time}에 다음 메일` : "특정 날짜 선택 필요";
    } else {
      link.step.schedule_mode = isRelativeScheduleMode(mode) ? mode : "previous_days";
      link.step.send_after_label = link.step.next_send_after_days ? `이 메일 발송 후 ${link.step.next_send_after_days}일 뒤 ${link.step.next_send_time}에 다음 메일` : "다음 메일까지 간격 필요";
    }
  }
}

async function addFlowStep() {
  const index = state.flowSteps.length;
  const id = flowStepId({}, index);
  state.flowSteps.push({
    id,
    order: index + 1,
    stage_label: `새 메일 ${index + 1}`,
    priority: (index + 1) * 10,
    audience: "대상 설명을 입력하세요",
    template: `email_${index + 1}`,
    subject: "",
    text_body: "",
    schedule_mode: "none",
    next_send_after_days: "",
    next_send_at: "",
    next_send_time: "",
    next_step: "",
    status_after: "",
    send_after_label: "후속 발송 없음"
  });
  if (index > 0) ensureIncomingFlowLink(index, "previous_days", index - 1);
  state.activeTab = "flow";
  setNotice("메일 단계를 추가했습니다. 제목과 본문을 입력한 뒤 저장하세요.");
  render();
}

async function deleteFlowStep(index) {
  const removed = state.flowSteps[index];
  if (!removed) return;
  const removedId = flowStepId(removed, index);
  state.flowSteps.splice(index, 1);
  state.flowSteps.forEach((step, stepIndex) => {
    step.order = stepIndex + 1;
    if (step.next_step === removedId) step.next_step = "";
  });
  setNotice("메일 단계를 삭제했습니다. 저장을 눌러 반영하세요.");
  render();
}

function nextFlowStepId(index) {
  const next = state.flowSteps[index + 1];
  return next ? flowStepId(next, index + 1) : "";
}

function flowStepId(step, index) {
  if (step.id) return String(step.id);
  if (step.template) return String(step.template).trim().replace(/[^a-zA-Z0-9_-]+/g, "_") || `email_${index + 1}`;
  if (globalThis.crypto?.randomUUID) return `flow_${globalThis.crypto.randomUUID()}`;
  return `flow_${Date.now()}_${index + 1}`;
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
    "add-flow-step": addFlowStep,
    "save-delivery-set": saveActiveDeliverySet,
    "load-delivery-set": loadSelectedDeliverySet,
    "new-delivery-set": createDeliverySet,
    "duplicate-delivery-set": duplicateDeliverySet,
    "delete-delivery-set": deleteDeliverySet,
    "prepare-approval": prepareApproval,
    "save-approval": saveApproval,
    preview,
    "google-status": () => googleStatus({ activate: !state.settingsOpen }),
    "connect-google": () => connectGoogle({ activate: !state.settingsOpen }),
    "save-form-auto-send": saveFormAutoSend,
    "enable-followup-auto-send": () => setFollowupAutoSend(true),
    "disable-followup-auto-send": () => setFollowupAutoSend(false),
    "check-followup-status": checkFollowupStatus,
    "run-due-followups": runDueFollowups,
    "export-gmail": exportGmail,
    "upload-gmail": uploadGmail,
    "fetch-private-gmail": fetchPrivateGmail,
    "test-gmail": testGmail,
    "import-gmail": importGmail,
    "compare-gmail": compareGmail,
    "save-contact-draft": saveContactImportDraft,
    "clear-contact-draft": clearContactImportDraft,
    "select-all-contacts": selectAllContacts,
    "clear-contact-selection": clearContactSelection,
    "approve-selected-contacts": approveSelectedContacts,
    "delete-selected-contacts": deleteSelectedContacts,
    "delete-all-contacts": deleteAllContacts
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

async function loadFormAutoSend() {
  try {
    const data = await api("/api/forms/auto-send");
    applyFormAutoSendResponse(data);
  } catch {
    state.formAutoSend = { ...defaultFormAutoSend };
  }
}

function applyFormAutoSendResponse(data = {}) {
  const followups = data.status?.followups || {};
  state.formAutoSend = {
    ...state.formAutoSend,
    ...(data.settings || {}),
    followup_due_count: Number(followups.due_count || 0),
    followup_due_preview: followups.due_preview || [],
    followup_gmail_ready: Boolean(followups.gmail_ready),
    followup_ready: Boolean(followups.ready),
    followup_status_label: followups.label || "확인 전",
    followup_status_detail: followups.detail || "후속 메일 상태를 아직 확인하지 않았습니다.",
    followup_blockers: followups.blockers || []
  };
}

function formAutoSendPayload(overrides = {}) {
  const enabledInput = document.querySelector("[data-form-auto-send-enabled]");
  const dailyLimitInput = document.querySelector("[data-form-auto-send-limit]");
  const followupsInput = document.querySelector("[data-followup-auto-send-enabled]");
  const followupLimitInput = document.querySelector("[data-followup-auto-send-limit]");

  return {
    enabled: Boolean(overrides.enabled ?? (enabledInput ? enabledInput.checked : state.formAutoSend.enabled)),
    daily_limit: automationLimit(overrides.daily_limit ?? (dailyLimitInput ? dailyLimitInput.value : state.formAutoSend.daily_limit), state.formAutoSend.daily_limit || 20),
    followups_enabled: Boolean(overrides.followups_enabled ?? (followupsInput ? followupsInput.checked : state.formAutoSend.followups_enabled)),
    followup_daily_limit: automationLimit(overrides.followup_daily_limit ?? (followupLimitInput ? followupLimitInput.value : state.formAutoSend.followup_daily_limit), state.formAutoSend.followup_daily_limit || 20)
  };
}

function automationLimit(value, fallback = 20) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(Math.max(Math.floor(number), 1), 500);
}

async function saveFormAutoSend(overrides = {}, successMessage = "") {
  await withBusy("폼 자동 발송 설정을 저장하는 중입니다.", async () => {
    const payload = formAutoSendPayload(overrides);
    const data = await api("/api/forms/auto-send", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    applyFormAutoSendResponse(data);
    setNotice(successMessage || messageFrom(data, "폼 자동 발송 설정을 저장했습니다."), "success");
  });
}

async function setFollowupAutoSend(enabled) {
  await saveFormAutoSend(
    { followups_enabled: enabled },
    enabled ? "후속 메일 자동 발송을 켰습니다." : "후속 메일 자동 발송을 껐습니다."
  );
}

async function checkFollowupStatus() {
  await withBusy("후속 메일 자동 발송 상태를 확인하는 중입니다.", async () => {
    const data = await api("/api/forms/auto-send");
    applyFormAutoSendResponse(data);
    const followups = data.status?.followups;
    setNotice(followups?.detail || "후속 메일 자동 발송 상태를 확인했습니다.", followups?.ready ? "success" : "info");
  });
}

async function runDueFollowups() {
  await withBusy("예약일이 지난 후속 메일을 발송하는 중입니다.", async () => {
    const payload = formAutoSendPayload();
    const data = await api("/api/forms/send-due-followups", {
      method: "POST",
      body: JSON.stringify({ limit: payload.followup_daily_limit })
    });
    if (data.rows) {
      state.queueRows = data.rows;
      state.queueCounts = data.counts || {};
      syncContactSelection();
    }
    if (data.summary?.settings) {
      state.formAutoSend = {
        ...state.formAutoSend,
        ...data.summary.settings
      };
    }
    await loadFormAutoSend();
    setNotice(messageFrom(data, "후속 메일 실행을 완료했습니다."), data.summary?.sent ? "success" : "info");
  });
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
    syncContactSelection();
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
    const steps = normalizeFlowStepsForSave();
    const data = await api("/api/message-flow/save", {
      method: "POST",
      body: JSON.stringify({ ...formData(), steps })
    });
    state.flowSteps = data.steps || [];
    state.templates = data.templates || [];
    await saveActiveDeliverySet({ silent: true });
    state.activeTab = "flow";
    setNotice(messageFrom(data, "메일 흐름과 현재 퍼널메일 시리즈를 저장했습니다."), "success");
  });
}

function normalizeFlowStepsForSave() {
  return state.flowSteps.map((step, index) => {
    const mode = outgoingScheduleMode(step, index);
    const normalized = {
      ...step,
      id: flowStepId(step, index),
      order: index + 1,
      priority: Number(step.priority || (index + 1) * 10),
      schedule_mode: mode
    };
    if (isRelativeScheduleMode(mode)) {
      normalized.next_send_at = "";
      normalized.next_send_after_days = String(step.next_send_after_days || "").trim();
      normalized.next_send_time = sendTimeValue(step);
      if (!normalized.next_step) throw new Error(`${normalized.stage_label || normalized.template || `메일 ${index + 1}`}: 다음 메일이 선택되지 않았습니다.`);
      if (!normalized.next_send_after_days) throw new Error(`${normalized.stage_label || normalized.template || `메일 ${index + 1}`}: 다음 메일까지 며칠 뒤인지 입력하세요.`);
      if (!normalized.next_send_time) throw new Error(`${normalized.stage_label || normalized.template || `메일 ${index + 1}`}: 발송 시간을 선택하세요.`);
      const baseLabel = mode === "first_days" ? "첫 메일" : "이 메일";
      normalized.send_after_label = normalized.next_send_after_days
        ? `다음 메일은 ${baseLabel} 발송 후 ${normalized.next_send_after_days}일 뒤 ${normalized.next_send_time}`
        : "후속 발송 없음";
    } else if (mode === "date") {
      normalized.next_send_after_days = "";
      normalized.next_send_at = String(step.next_send_at || "").trim();
      normalized.next_send_time = sendTimeValue(step);
      if (!normalized.next_step) throw new Error(`${normalized.stage_label || normalized.template || `메일 ${index + 1}`}: 다음 메일이 선택되지 않았습니다.`);
      if (!normalized.next_send_at) throw new Error(`${normalized.stage_label || normalized.template || `메일 ${index + 1}`}: 다음 메일 발송 날짜를 선택하세요.`);
      if (!normalized.next_send_time) throw new Error(`${normalized.stage_label || normalized.template || `메일 ${index + 1}`}: 발송 시간을 선택하세요.`);
      normalized.send_after_label = normalized.next_send_at
        ? `다음 메일은 ${normalized.next_send_at} ${normalized.next_send_time}에 발송`
        : "특정 날짜 선택 필요";
    } else {
      normalized.next_send_after_days = "";
      normalized.next_send_at = "";
      normalized.next_send_time = "";
      normalized.next_step = "";
      normalized.send_after_label = "후속 발송 없음";
    }
    return normalized;
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

async function approveSelectedContacts() {
  const selectedRows = selectedContactRows();
  const readyEmails = selectedRows
    .filter((row) => row.status === "ready")
    .map((row) => row.email);
  if (!readyEmails.length) {
    setNotice("선택한 명단 중 지금 보낼 수 있는 사람이 없습니다.", "error");
    render();
    return;
  }

  await withBusy("선택한 명단만 발송 승인에 올리는 중입니다.", async () => {
    const data = await api("/api/approval/prepare", {
      method: "POST",
      body: JSON.stringify({
        ...formData(),
        selected_emails: readyEmails,
        approve_selected: true
      })
    });
    state.approvalRows = data.rows || [];
    state.approvalCounts = data.counts || countApprovals(state.approvalRows);
    state.queueCounts = data.queue_counts || state.queueCounts;
    state.activeTab = "approval";
    setNotice(messageFrom(data, `선택한 명단 ${state.approvalRows.length}건만 승인 목록에 올렸습니다.`), "success");
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
      applyGoogleSetup(data);
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
    applyGoogleSetup(data);
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
      applyGoogleSetup(data);
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
    syncContactSelection();
    state.approvalRows = [];
    state.approvalCounts = {};
    state.previewRows = [];
    state.previewSummary = null;
    state.contactImport = {
      filename: state.contactImportDraft.filename,
      sheetName: state.contactImportDraft.sheetName || "",
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

async function deleteSelectedContacts() {
  const emails = selectedContactEmails();
  if (!emails.length) {
    setNotice("삭제할 명단을 선택하세요.", "error");
    render();
    return;
  }
  if (!globalThis.confirm(`선택한 명단 ${emails.length}명을 삭제할까요? 승인 목록과 Gmail 결과도 함께 정리됩니다.`)) return;

  await withBusy("선택한 명단을 삭제하는 중입니다.", async () => {
    const data = await api("/api/contacts/delete", {
      method: "POST",
      body: JSON.stringify({ ...formData(), emails })
    });
    applyContactListResponse(data);
    state.contactSelection.clear();
    state.activeTab = "people";
    setNotice(messageFrom(data, `선택한 명단 ${data.summary?.deleted || 0}건을 삭제했습니다.`), "success");
  });
}

async function deleteAllContacts() {
  if (!state.queueRows.length) {
    setNotice("삭제할 명단이 없습니다.");
    render();
    return;
  }
  if (!globalThis.confirm("전체 명단을 삭제할까요? 승인 목록과 Gmail 결과도 함께 정리됩니다.")) return;

  await withBusy("전체 명단을 삭제하는 중입니다.", async () => {
    const data = await api("/api/contacts/delete", {
      method: "POST",
      body: JSON.stringify({ ...formData(), all: true })
    });
    applyContactListResponse(data);
    state.contactSelection.clear();
    state.contactImport = null;
    state.activeTab = "people";
    setNotice(messageFrom(data, `전체 명단 ${data.summary?.deleted || 0}건을 삭제했습니다.`), "success");
  });
}

function applyContactListResponse(data) {
  state.queueRows = data.rows || [];
  state.queueCounts = data.counts || {};
  state.approvalRows = data.approval_rows || [];
  state.approvalCounts = data.approval_counts || countApprovals(state.approvalRows);
  state.gmailRows = data.gmail_rows || state.gmailRows;
  state.gmailCounts = data.gmail_counts || state.gmailCounts;
  state.previewRows = [];
  state.previewSummary = null;
  syncContactSelection();
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
    if (data.rows) state.queueRows = data.rows;
    if (data.counts) state.queueCounts = data.counts;
    syncContactSelection();
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
  if (name.endsWith(".xlsx")) return tableFromXlsxFile(file);
  if (name.endsWith(".xls")) {
    throw new Error("구형 .xls 파일은 브라우저에서 직접 읽을 수 없습니다. Excel에서 .xlsx 또는 CSV로 다시 저장한 뒤 불러오세요.");
  }
  if (name.endsWith(".csv")) return parseCsv(await file.text());
  throw new Error("엑셀 .xlsx 또는 CSV 파일만 불러올 수 있습니다.");
}

async function tableFromXlsxFile(file) {
  let result;
  try {
    result = await readXlsxFile(file);
  } catch {
    throw new Error("엑셀 파일을 읽지 못했습니다. 암호가 걸린 파일이거나 실제 .xlsx 형식이 아닐 수 있습니다.");
  }

  if (looksLikeWorkbookSheets(result)) {
    const candidates = result
      .map((sheet, index) => ({
        rows: sheet.data || [],
        sheetName: sheet.sheet || `Sheet ${index + 1}`,
        sheetCount: result.length,
        score: contactTableScore(sheet.data || [])
      }))
      .sort((a, b) => b.score - a.score);
    return candidates[0] || { rows: [], sheetName: "", sheetCount: result.length };
  }

  return { rows: result, sheetName: "", sheetCount: 1 };
}

function looksLikeWorkbookSheets(value) {
  return Array.isArray(value) && value.some((item) => item && Array.isArray(item.data));
}

function contactTableScore(table) {
  const rows = normalizeContactTable(table);
  let emailCells = 0;
  let headerHits = 0;
  for (const row of rows.slice(0, 40)) {
    for (const cell of row) {
      if (isEmail(cell)) emailCells += 1;
      headerHits += headerCandidateScore(cell, "email") + headerCandidateScore(cell, "name");
    }
  }
  return emailCells * 20 + headerHits * 3 + rows.length;
}

function buildContactImportDraft(filename, source) {
  const table = Array.isArray(source) ? source : source?.rows;
  const tableRows = normalizeContactTable(table);
  if (!tableRows.length) {
    const prefix = source?.sheetCount > 1 ? `엑셀의 ${source.sheetCount}개 시트를 확인했지만` : "명단 파일에서";
    throw new Error(`${prefix} 값이 들어 있는 셀을 찾지 못했습니다. 명단이 이미지/피벗 결과가 아니라 실제 셀 값으로 들어 있는지 확인하세요.`);
  }
  const inferred = inferContactColumns(tableRows);
  const sheetName = Array.isArray(source) ? "" : source?.sheetName || "";
  const sheetNote = sheetName && source?.sheetCount > 1 ? [`여러 시트 중 '${sheetName}' 시트를 읽었습니다.`] : [];
  return refreshContactImportDraft({
    filename,
    sheetName,
    sheetCount: Array.isArray(source) ? 1 : source?.sheetCount || 1,
    tableRows,
    ...inferred,
    baseNotes: [...(inferred.baseNotes || []), ...sheetNote]
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
    await loadFormAutoSend();
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
    await Promise.allSettled([loadFlow(), googleStatus({ activate: false }), loadFormAutoSend()]);
    loadDeliverySetsFromStorage();
    if (state.deliverySets.length) applyDeliverySet(activeDeliverySet());
    ensureDeliverySets();
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
