import {
  applyGmailResultsToContacts,
  approvalRowsFor,
  flowStepsFor,
  getMetaJson,
  hasDatabase,
  logGmailSend,
  saveGmailRows,
  setMetaJson
} from "./cloud-api.js";

export const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets";
export const GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send";
export const GOOGLE_SCOPES = [SHEETS_SCOPE, GMAIL_SEND_SCOPE];
export const GOOGLE_SCOPE_TEXT = GOOGLE_SCOPES.join(" ");
const TOKEN_KEY = "google_sheets_token";
const OAUTH_STATE_KEY = "google_oauth_state";

export function googleClient(env) {
  if (env?.GOOGLE_OAUTH_CLIENT) {
    try {
      const parsed = JSON.parse(env.GOOGLE_OAUTH_CLIENT);
      const raw = parsed.web || parsed.installed || parsed;
      return normalizeClient(raw);
    } catch {
      return null;
    }
  }

  if (env?.GOOGLE_CLIENT_ID && env?.GOOGLE_CLIENT_SECRET) {
    return normalizeClient({
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET
    });
  }

  return null;
}

function normalizeClient(raw) {
  if (!raw?.client_id || !raw?.client_secret) return null;
  return {
    client_id: raw.client_id,
    client_secret: raw.client_secret,
    auth_uri: raw.auth_uri || "https://accounts.google.com/o/oauth2/v2/auth",
    token_uri: raw.token_uri || "https://oauth2.googleapis.com/token"
  };
}

export async function googleSetup(env, source = "") {
  const hasDb = hasDatabase(env);
  const client = googleClient(env);
  let token = null;
  let databaseReady = hasDb;
  let databaseError = "";
  if (hasDb) {
    try {
      token = await getStoredToken(env);
    } catch (error) {
      databaseReady = false;
      databaseError = error.message || "D1 저장소 상태를 확인하지 못했습니다.";
    }
  }
  const hasToken = Boolean(token?.refresh_token || token?.access_token);
  const tokenScope = String(token?.scope || "");
  const tokenHasRequiredScopes = hasRequiredScopes(tokenScope);
  const tokenValid = Boolean(token?.refresh_token) && tokenHasRequiredScopes;
  const sheetReady = Boolean(String(source || "").trim());

  return {
    hasDb,
    databaseReady,
    databaseError,
    hasClient: Boolean(client),
    hasToken,
    tokenValid,
    tokenHasRequiredScopes,
    sheetReady,
    ready: databaseReady && Boolean(client) && tokenValid && sheetReady,
    sendReady: databaseReady && Boolean(client) && tokenValid,
    tokenScope
  };
}

function hasRequiredScopes(scopeText) {
  const scopes = new Set(String(scopeText || "").split(/\s+/).filter(Boolean));
  return GOOGLE_SCOPES.every((scope) => scopes.has(scope));
}

export async function buildAuthorization(env, redirectUri) {
  const client = googleClient(env);
  if (!hasDatabase(env)) {
    return { auth_url: "", message: "Google 연결에는 Cloudflare D1 바인딩 DB가 필요합니다." };
  }
  if (!client) {
    return { auth_url: "", message: "Google OAuth Secret을 먼저 설정하세요. GOOGLE_OAUTH_CLIENT 또는 GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET이 필요합니다." };
  }

  const state = crypto.randomUUID();
  await setMetaJson(env, OAUTH_STATE_KEY, {
    state,
    redirect_uri: redirectUri,
    created_at: new Date().toISOString()
  });

  const params = new URLSearchParams({
    client_id: client.client_id,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: GOOGLE_SCOPE_TEXT,
    access_type: "offline",
    prompt: "consent",
    include_granted_scopes: "true",
    state
  });

  return {
    auth_url: `${client.auth_uri}?${params.toString()}`,
    message: "Google 연결 주소를 만들었습니다."
  };
}

export async function completeAuthorization(env, { code, state }) {
  if (!hasDatabase(env)) throw new Error("Cloudflare D1 바인딩 DB가 필요합니다.");
  const client = googleClient(env);
  if (!client) throw new Error("Google OAuth Secret이 설정되지 않았습니다.");

  const savedState = await getMetaJson(env, OAUTH_STATE_KEY);
  if (!savedState?.state || savedState.state !== state) {
    throw new Error("Google 연결 상태값이 맞지 않습니다. 앱에서 Google 연결을 다시 누르세요.");
  }

  const token = await tokenRequest(client.token_uri, {
    code,
    client_id: client.client_id,
    client_secret: client.client_secret,
    redirect_uri: savedState.redirect_uri,
    grant_type: "authorization_code"
  });

  await storeToken(env, token);
  return token;
}

export async function accessToken(env) {
  const client = googleClient(env);
  if (!client) throw new Error("Google OAuth Secret이 설정되지 않았습니다.");
  const token = await getStoredToken(env);
  if (!token?.refresh_token && !token?.access_token) {
    throw new Error("Google 연결 토큰이 없습니다. 먼저 Google 연결을 완료하세요.");
  }
  if (!hasRequiredScopes(token.scope || "")) {
    throw new Error("Google Sheets/Gmail 발송 권한이 부족합니다. Google 연결을 다시 실행하세요.");
  }

  if (token.access_token && Number(token.expires_at || 0) > Date.now() + 60_000) {
    return token.access_token;
  }

  if (!token.refresh_token) {
    throw new Error("Google refresh_token이 없습니다. Google 연결을 다시 실행하세요.");
  }

  const refreshed = await tokenRequest(client.token_uri, {
    refresh_token: token.refresh_token,
    client_id: client.client_id,
    client_secret: client.client_secret,
    grant_type: "refresh_token"
  });
  const merged = { ...token, ...refreshed, refresh_token: refreshed.refresh_token || token.refresh_token };
  await storeToken(env, merged);
  return merged.access_token;
}

async function getStoredToken(env) {
  return getMetaJson(env, TOKEN_KEY);
}

async function storeToken(env, token) {
  const expiresAt = Date.now() + Number(token.expires_in || 3600) * 1000;
  await setMetaJson(env, TOKEN_KEY, {
    ...token,
    scope: token.scope || GOOGLE_SCOPE_TEXT,
    expires_at: expiresAt,
    saved_at: new Date().toISOString()
  });
}

async function tokenRequest(tokenUri, fields) {
  const response = await fetch(tokenUri, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Accept: "application/json"
    },
    body: new URLSearchParams(fields).toString()
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error_description || payload.error || `Google token error ${response.status}`);
  }
  return payload;
}

export function spreadsheetIdFromSource(source) {
  const value = String(source || "").trim();
  if (!value) throw new Error("Gmail 시트 링크를 입력하세요.");
  const match = value.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (match) return match[1];
  if (/^[a-zA-Z0-9-_]{20,}$/.test(value)) return value;
  throw new Error("Google Sheet 링크 또는 spreadsheet id 형식이 아닙니다.");
}

export async function uploadQueueToSheet(env, { source, sheetName = "GmailQueue", campaignId = "cloud-preview" }) {
  const token = await accessToken(env);
  const spreadsheetId = spreadsheetIdFromSource(source);
  const values = await gmailQueueValues(env, campaignId);
  const range = quoteSheet(sheetName);

  await sheetsRequest(
    `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}:clear`,
    token,
    { method: "POST", body: "{}" }
  );
  const result = await sheetsRequest(
    `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}?valueInputOption=RAW`,
    token,
    {
      method: "PUT",
      body: JSON.stringify({ majorDimension: "ROWS", values })
    }
  );

  return {
    rows: Math.max(values.length - 1, 0),
    columns: values[0],
    spreadsheet_id: spreadsheetId,
    sheet_name: sheetName,
    updated_rows: result.updatedRows || 0,
    updated_cells: result.updatedCells || 0
  };
}

async function gmailQueueValues(env, campaignId) {
  const approvals = (await approvalRowsFor(env)).filter((row) => String(row.approved || "").toLowerCase() === "yes");
  const steps = await flowStepsFor(env);
  const stepByTemplate = Object.fromEntries(steps.map((step) => [step.template, step]));
  const rows = approvals.length ? approvals : (await approvalRowsFor(env));
  const header = [
    "approved",
    "status",
    "email",
    "name",
    "campaign_id",
    "template",
    "rule",
    "subject",
    "text_body",
    "html_body",
    "dedupe_key",
    "sent_at",
    "error"
  ];

  return [
    header,
    ...rows.map((row) => {
      const step = stepByTemplate[row.template] || {};
      const email = row.email || "";
      const template = row.template || "";
      return [
        "yes",
        "pending",
        email,
        "",
        campaignId,
        template,
        row.rule || "",
        step.subject || "",
        step.text_body || "",
        "",
        `${campaignId}:${email}:${template}`,
        "",
        ""
      ];
    })
  ];
}

export async function fetchSheetResults(env, { source, sheetName = "GmailQueue" }) {
  const token = await accessToken(env);
  const spreadsheetId = spreadsheetIdFromSource(source);
  const range = quoteSheet(sheetName);
  const payload = await sheetsRequest(
    `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}`,
    token
  );
  const rows = valuesToObjects(payload.values || []);
  const gmailRows = rows
    .filter((row) => row.email)
    .map((row) => ({
      email: row.email || "",
      template: row.template || "",
      review_status: reviewStatus(row.status),
      gmail_status: row.status || "pending",
      lead_status: row.status === "sent" ? "진행중" : "",
      detail: row.error || row.sent_at || ""
    }));
  await saveGmailRows(env, gmailRows);
  return {
    rows: gmailRows.length,
    spreadsheet_id: spreadsheetId,
    sheet_name: sheetName
  };
}

export async function sendTestEmail(env, { to, subject, textBody }) {
  const recipient = normalizeEmail(to);
  const safeSubject = sanitizeHeader(subject || "[테스트] Funnel Manager Gmail API 연결 확인");
  const safeBody =
    textBody ||
    "Funnel Manager Gmail API 테스트 메일입니다.\n\n이 메일은 테스트 수신자 1명에게만 발송됐습니다.\n승인 명단 전체 발송 기능은 아직 열려 있지 않습니다.";

  return sendGmailMessage(env, {
    to: recipient,
    subject: safeSubject,
    textBody: safeBody,
    mode: "test"
  });
}

export async function sendWorkflowEmail(env, { contact, fields = {}, mode = "form_auto" }) {
  const recipient = normalizeEmail(contact?.email);
  const steps = await flowStepsFor(env);
  const step = steps.find((candidate) => candidate.template === contact?.template) || steps[0];
  if (!step?.template) throw new Error("자동 발송할 메일 단계가 없습니다. 단계별 메일을 먼저 저장하세요.");

  const template = step.template;
  await assertNotSentBefore(env, recipient, template);

  const context = templateContext(contact, fields);
  const subject = sanitizeHeader(renderTemplate(step.subject, context));
  const textBody = renderTemplate(step.text_body, context);
  if (!subject || !textBody.trim()) {
    throw new Error("자동 발송할 메일 제목과 본문을 먼저 입력하세요.");
  }

  try {
    const result = await sendGmailMessage(env, {
      to: recipient,
      subject,
      textBody,
      mode
    });
    await saveGmailRows(env, [{
      email: recipient,
      template,
      review_status: "matched",
      gmail_status: "sent",
      lead_status: "진행중",
      detail: result.sent_at
    }]);
    const contact_summary = await applyGmailResultsToContacts(env);
    return {
      ...result,
      template,
      contact_summary
    };
  } catch (error) {
    await saveGmailRows(env, [{
      email: recipient,
      template,
      review_status: "needs_review",
      gmail_status: "failed",
      lead_status: "확인필요",
      detail: error.message || "Gmail 발송 실패"
    }]);
    await applyGmailResultsToContacts(env);
    throw error;
  }
}

async function sendGmailMessage(env, { to, subject, textBody, mode }) {
  const recipient = normalizeEmail(to);
  const safeSubject = sanitizeHeader(subject || "");
  const safeBody = String(textBody || "");

  try {
    const token = await accessToken(env);
    const raw = base64UrlEncode(
      [
        `To: ${recipient}`,
        `Subject: ${encodeSubject(safeSubject)}`,
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "Content-Transfer-Encoding: 8bit",
        "",
        safeBody
      ].join("\r\n")
    );
    const response = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8"
      },
      body: JSON.stringify({ raw })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error?.message || `Gmail API ${response.status}`);
    }
    const sentAt = new Date().toISOString();
    const logError = await safeLogGmailSend(env, {
      recipient,
      subject: safeSubject,
      mode,
      status: "sent",
      message_id: payload.id || ""
    });
    return {
      sent: true,
      recipient,
      subject: safeSubject,
      message_id: payload.id || "",
      sent_at: sentAt,
      log_error: logError
    };
  } catch (error) {
    await safeLogGmailSend(env, {
      recipient,
      subject: safeSubject,
      mode,
      status: "failed",
      error: error.message || "Gmail send failed"
    });
    throw error;
  }
}

async function assertNotSentBefore(env, email, template) {
  if (!hasDatabase(env)) return;
  const row = await env.DB.prepare(
    `SELECT gmail_status, review_status
     FROM gmail_results
     WHERE email = ? AND template = ?`
  )
    .bind(email, template)
    .first();
  const gmailStatus = String(row?.gmail_status || "").toLowerCase();
  const reviewStatus = String(row?.review_status || "").toLowerCase();
  if (gmailStatus === "sent" || reviewStatus === "matched") {
    throw new Error("이미 같은 메일을 발송한 고객입니다.");
  }
}

function templateContext(contact, fields) {
  const context = {};
  for (const [key, value] of Object.entries(fields || {})) {
    context[String(key || "").trim()] = String(value || "");
  }
  const email = String(contact?.email || "");
  const name = String(contact?.name || context["이름"] || context.name || email.split("@")[0] || "");
  return {
    ...context,
    email,
    Email: email,
    이메일: email,
    메일: email,
    name,
    Name: name,
    이름: name,
    성명: name,
    template: String(contact?.template || ""),
    campaign_step: String(contact?.campaign_step || "")
  };
}

function renderTemplate(value, context) {
  return String(value || "").replace(/{{\s*([^}]+?)\s*}}/g, (_, key) => {
    const cleanKey = String(key || "").trim();
    return context[cleanKey] ?? "";
  });
}

async function safeLogGmailSend(env, row) {
  try {
    await logGmailSend(env, row);
    return "";
  } catch (error) {
    return error.message || "Gmail 발송 로그를 저장하지 못했습니다.";
  }
}

function normalizeEmail(value) {
  const email = String(value || "").trim();
  if (!email || /[\r\n]/.test(email) || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw new Error("테스트 수신자 이메일을 정확히 입력하세요.");
  }
  return email;
}

function sanitizeHeader(value) {
  return String(value || "").replace(/[\r\n]+/g, " ").trim();
}

function encodeSubject(value) {
  return `=?UTF-8?B?${base64EncodeUtf8(value)}?=`;
}

function base64EncodeUtf8(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64UrlEncode(value) {
  return base64EncodeUtf8(value).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
}

function valuesToObjects(values) {
  if (!values.length) return [];
  const headers = values[0].map((header) => String(header || "").trim());
  return values.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, String(row[index] || "")])));
}

function reviewStatus(status) {
  const value = String(status || "").toLowerCase();
  if (value === "sent") return "matched";
  if (value === "failed") return "needs_review";
  return "pending";
}

function quoteSheet(sheetName) {
  const safeName = String(sheetName || "GmailQueue").replaceAll("'", "''");
  return `'${safeName}'`;
}

async function sheetsRequest(url, token, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json; charset=utf-8"
    },
    body: options.body
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error?.message || `Google Sheets API ${response.status}`);
  }
  return payload;
}
