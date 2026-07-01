import { approvalRowsFor, flowStepsFor, getMetaJson, hasDatabase, saveGmailRows, setMetaJson } from "./cloud-api.js";

export const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets";
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
  const token = hasDb ? await getStoredToken(env) : null;
  const tokenValid = Boolean(token?.refresh_token);
  const sheetReady = Boolean(String(source || "").trim());

  return {
    hasDb,
    hasClient: Boolean(client),
    tokenValid,
    sheetReady,
    ready: hasDb && Boolean(client) && tokenValid && sheetReady,
    tokenScope: token?.scope || ""
  };
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
    scope: SHEETS_SCOPE,
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
    scope: token.scope || SHEETS_SCOPE,
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
