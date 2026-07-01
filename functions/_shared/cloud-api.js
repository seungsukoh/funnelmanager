export const CLOUD_MODE = "cloud_preview";
export const CLOUD_NOTICE =
  "Cloudflare에서는 현재 샘플 데이터로 화면 흐름을 확인합니다. 실제 발송은 D1/R2/Google OAuth 연결 후 활성화됩니다.";

export const DEFAULTS = {
  contacts: "cloud/sample-contacts",
  funnel_config: "cloud/sample-funnel",
  lead_state: "cloud/sample-state",
  campaign_id: "cloud-preview",
  queue_output: "cloud/queue",
  approval_output: "cloud/approval",
  gmail_source: "",
  gmail_sheet_name: "GmailQueue",
  gmail_results: "cloud/gmail-results",
  google_credentials: "Cloudflare Secret: GOOGLE_OAUTH_CLIENT",
  google_token: "Cloudflare KV/D1 token store",
  timeline: "cloud/timeline",
  cloud_backend: true,
  cloud_mode: CLOUD_MODE,
  cloud_notice: CLOUD_NOTICE
};

export const QUEUE_ROWS = [
  {
    status: "ready",
    email: "minsu@example.com",
    template: "event_followup",
    rule: "참석 고객",
    campaign_step: "참석 고객 첫 메일",
    next_send_at: "",
    detail: "오늘 보낼 수 있습니다."
  },
  {
    status: "scheduled",
    email: "jiyoung@example.com",
    template: "second_followup",
    rule: "관심 고객",
    campaign_step: "두 번째 안내",
    next_send_at: "2026-07-03",
    detail: "다음 발송일을 기다립니다."
  },
  {
    status: "skipped",
    email: "hana@example.com",
    template: "no_show_followup",
    rule: "미참석 고객",
    campaign_step: "미참석 고객 첫 메일",
    next_send_at: "",
    detail: "마케팅 동의가 없어 제외했습니다."
  },
  {
    status: "skipped",
    email: "jun@example.com",
    template: "event_followup",
    rule: "수신거부",
    campaign_step: "참석 고객 첫 메일",
    next_send_at: "",
    detail: "수신거부 고객입니다."
  }
];

export const FLOW_STEPS = [
  {
    id: "attended_first",
    order: 1,
    stage_label: "참석 고객 첫 메일",
    priority: 10,
    audience: "참석여부가 참석인 고객",
    template: "event_followup",
    subject: "{{이름}}님, 행사 참석 감사드립니다",
    text_body: "{{이름}}님 안녕하세요.\n행사에 참석해 주셔서 감사합니다.\n다음 상담이 필요하시면 회신해 주세요.",
    next_send_after_days: 2,
    next_step: "attended_second",
    status_after: "진행중",
    send_after_label: "2일 뒤"
  },
  {
    id: "noshow_first",
    order: 2,
    stage_label: "미참석 고객 첫 메일",
    priority: 20,
    audience: "참석여부가 미참석인 고객",
    template: "no_show_followup",
    subject: "{{이름}}님, 행사 자료를 보내드립니다",
    text_body: "{{이름}}님 안녕하세요.\n참석하지 못하신 분들을 위해 행사 핵심 자료를 정리했습니다.",
    next_send_after_days: 3,
    next_step: "noshow_second",
    status_after: "진행중",
    send_after_label: "3일 뒤"
  },
  {
    id: "attended_second",
    order: 3,
    stage_label: "두 번째 안내",
    priority: 30,
    audience: "첫 메일 이후 관심 고객",
    template: "second_followup",
    subject: "{{이름}}님, 다음 단계 안내드립니다",
    text_body: "{{이름}}님께 맞는 다음 단계를 안내드립니다.\n편한 시간에 상담 일정을 선택해 주세요.",
    next_send_after_days: "",
    next_step: "",
    status_after: "상담안내",
    send_after_label: "후속 발송 없음"
  }
];

export const GMAIL_ROWS = [
  {
    review_status: "matched",
    email: "minsu@example.com",
    gmail_status: "sent",
    template: "event_followup",
    lead_status: "진행중",
    detail: "샘플 결과입니다."
  },
  {
    review_status: "pending",
    email: "jiyoung@example.com",
    gmail_status: "pending",
    template: "second_followup",
    lead_status: "진행중",
    detail: "아직 발송 전입니다."
  },
  {
    review_status: "needs_review",
    email: "error@example.com",
    gmail_status: "failed",
    template: "event_followup",
    lead_status: "확인필요",
    detail: "실제 운영에서는 오류 원인을 확인합니다."
  }
];

const CORE_SCHEMA = `
CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
  email TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'ready',
  template TEXT NOT NULL DEFAULT '',
  rule TEXT NOT NULL DEFAULT '',
  campaign_step TEXT NOT NULL DEFAULT '',
  next_send_at TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS funnel_steps (
  id TEXT PRIMARY KEY,
  sort_order INTEGER NOT NULL DEFAULT 0,
  stage_label TEXT NOT NULL DEFAULT '',
  priority INTEGER NOT NULL DEFAULT 0,
  audience TEXT NOT NULL DEFAULT '',
  template TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  text_body TEXT NOT NULL DEFAULT '',
  next_send_after_days TEXT NOT NULL DEFAULT '',
  next_step TEXT NOT NULL DEFAULT '',
  status_after TEXT NOT NULL DEFAULT '',
  send_after_label TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS approvals (
  email TEXT NOT NULL,
  template TEXT NOT NULL,
  approved TEXT NOT NULL DEFAULT 'no',
  rule TEXT NOT NULL DEFAULT '',
  campaign_step TEXT NOT NULL DEFAULT '',
  next_send_at TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (email, template)
);

CREATE TABLE IF NOT EXISTS gmail_results (
  email TEXT NOT NULL,
  template TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'pending',
  gmail_status TEXT NOT NULL DEFAULT 'pending',
  lead_status TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (email, template)
);

CREATE TABLE IF NOT EXISTS gmail_send_logs (
  id TEXT PRIMARY KEY,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'test',
  status TEXT NOT NULL DEFAULT 'pending',
  message_id TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
`;

export function hasDatabase(env) {
  return Boolean(env?.DB && typeof env.DB.prepare === "function");
}

export function cloudMode(env) {
  return hasDatabase(env) ? "cloud_d1" : CLOUD_MODE;
}

export function cloudNotice(env) {
  return hasDatabase(env)
    ? "Cloudflare D1 저장소가 연결됐습니다. Google OAuth Secret을 설정하면 비공개 Google Sheet 연동을 실행할 수 있습니다."
    : CLOUD_NOTICE;
}

export function json(payload = {}, status = 200, env = undefined) {
  return new Response(
    JSON.stringify(
      {
        ok: status < 400,
        ...payload,
        cloud_mode: cloudMode(env),
        cloud_notice: cloudNotice(env)
      },
      null,
      2
    ),
    {
      status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      }
    }
  );
}

export function html(markup, status = 200) {
  return new Response(markup, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}

export async function ensureDatabase(env) {
  if (!hasDatabase(env)) return false;
  if (typeof env.DB.exec === "function") {
    await env.DB.exec(CORE_SCHEMA);
  } else {
    for (const statement of CORE_SCHEMA.split(";").map((part) => part.trim()).filter(Boolean)) {
      await env.DB.prepare(statement).run();
    }
  }
  await seedDatabase(env);
  return true;
}

export async function getMeta(env, key) {
  if (!(await ensureDatabase(env))) return null;
  const row = await env.DB.prepare("SELECT value FROM app_meta WHERE key = ?").bind(key).first();
  return row?.value ?? null;
}

export async function setMeta(env, key, value) {
  if (!(await ensureDatabase(env))) return false;
  await env.DB.prepare(
    `INSERT INTO app_meta (key, value, updated_at)
     VALUES (?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(key) DO UPDATE SET
       value = excluded.value,
       updated_at = CURRENT_TIMESTAMP`
  )
    .bind(key, value)
    .run();
  return true;
}

export async function getMetaJson(env, key) {
  const value = await getMeta(env, key);
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export async function setMetaJson(env, key, value) {
  return setMeta(env, key, JSON.stringify(value));
}

async function seedDatabase(env) {
  const seeded = await env.DB.prepare("SELECT value FROM app_meta WHERE key = ?").bind("seeded_v1").first();
  if (seeded) return;

  for (const row of QUEUE_ROWS) {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO contacts
        (email, name, status, template, rule, campaign_step, next_send_at, detail, data_json)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        row.email,
        displayName(row.email),
        row.status,
        row.template,
        row.rule,
        row.campaign_step,
        row.next_send_at,
        row.detail,
        JSON.stringify(row)
      )
      .run();
  }

  for (const step of FLOW_STEPS) {
    await upsertFlowStep(env, step);
  }

  for (const row of GMAIL_ROWS) {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO gmail_results
        (email, template, review_status, gmail_status, lead_status, detail)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
      .bind(row.email, row.template, row.review_status, row.gmail_status, row.lead_status, row.detail)
      .run();
  }

  await env.DB.prepare("INSERT INTO app_meta (key, value) VALUES (?, ?)").bind("seeded_v1", new Date().toISOString()).run();
}

function displayName(email) {
  return String(email || "").split("@")[0] || "";
}

export async function readBody(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

export function countBy(rows, field) {
  return rows.reduce((counts, row) => {
    const key = row[field] || "unknown";
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

export function approvalRows() {
  return QUEUE_ROWS.filter((row) => row.status === "ready").map((row) => ({
    approved: "no",
    email: row.email,
    template: row.template,
    rule: row.rule,
    campaign_step: row.campaign_step,
    next_send_at: row.next_send_at,
    detail: row.detail
  }));
}

export async function queueRowsFor(env) {
  if (!(await ensureDatabase(env))) return QUEUE_ROWS;
  const { results = [] } = await env.DB.prepare(
    `SELECT status, email, template, rule, campaign_step, next_send_at, detail
     FROM contacts
     ORDER BY created_at ASC, email ASC`
  ).all();
  return results;
}

export async function flowStepsFor(env) {
  if (!(await ensureDatabase(env))) return FLOW_STEPS;
  const { results = [] } = await env.DB.prepare(
    `SELECT
       id,
       sort_order AS "order",
       stage_label,
       priority,
       audience,
       template,
       subject,
       text_body,
       next_send_after_days,
       next_step,
       status_after,
       send_after_label
     FROM funnel_steps
     ORDER BY sort_order ASC, id ASC`
  ).all();
  return results.length ? results : FLOW_STEPS;
}

export async function saveFlowSteps(env, steps) {
  if (!(await ensureDatabase(env))) return Array.isArray(steps) && steps.length ? steps : FLOW_STEPS;
  const rows = Array.isArray(steps) ? steps : [];
  for (let index = 0; index < rows.length; index += 1) {
    await upsertFlowStep(env, { ...rows[index], order: rows[index].order || index + 1 });
  }
  return flowStepsFor(env);
}

export async function upsertFlowStep(env, step) {
  await env.DB.prepare(
    `INSERT INTO funnel_steps
      (id, sort_order, stage_label, priority, audience, template, subject, text_body,
       next_send_after_days, next_step, status_after, send_after_label, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET
       sort_order = excluded.sort_order,
       stage_label = excluded.stage_label,
       priority = excluded.priority,
       audience = excluded.audience,
       template = excluded.template,
       subject = excluded.subject,
       text_body = excluded.text_body,
       next_send_after_days = excluded.next_send_after_days,
       next_step = excluded.next_step,
       status_after = excluded.status_after,
       send_after_label = excluded.send_after_label,
       updated_at = CURRENT_TIMESTAMP`
  )
    .bind(
      String(step.id || step.template || crypto.randomUUID()),
      Number(step.order || 0),
      String(step.stage_label || ""),
      Number(step.priority || 0),
      String(step.audience || ""),
      String(step.template || ""),
      String(step.subject || ""),
      String(step.text_body || ""),
      String(step.next_send_after_days || ""),
      String(step.next_step || ""),
      String(step.status_after || ""),
      String(step.send_after_label || "")
    )
    .run();
}

export async function templatesFor(env) {
  const steps = await flowStepsFor(env);
  return steps.map((step) => ({
    name: step.template,
    subject: step.subject,
    text_body: step.text_body,
    html_body: ""
  }));
}

export async function prepareApprovalRowsFor(env) {
  const rows = (await queueRowsFor(env))
    .filter((row) => row.status === "ready")
    .map((row) => ({
      approved: "no",
      email: row.email,
      template: row.template,
      rule: row.rule,
      campaign_step: row.campaign_step,
      next_send_at: row.next_send_at,
      detail: row.detail
    }));

  if (!(await ensureDatabase(env))) return rows;

  for (const row of rows) {
    const existing = await env.DB.prepare("SELECT approved FROM approvals WHERE email = ? AND template = ?")
      .bind(row.email, row.template)
      .first();
    await upsertApproval(env, { ...row, approved: existing?.approved || row.approved });
  }
  return approvalRowsFor(env);
}

export async function approvalRowsFor(env) {
  if (!(await ensureDatabase(env))) return approvalRows();
  const { results = [] } = await env.DB.prepare(
    `SELECT approved, email, template, rule, campaign_step, next_send_at, detail
     FROM approvals
     ORDER BY updated_at DESC, email ASC`
  ).all();
  return results.length ? results : approvalRows();
}

export async function saveApprovalRows(env, rows) {
  if (!(await ensureDatabase(env))) return Array.isArray(rows) ? rows : [];
  for (const row of Array.isArray(rows) ? rows : []) {
    await upsertApproval(env, row);
  }
  return approvalRowsFor(env);
}

async function upsertApproval(env, row) {
  await env.DB.prepare(
    `INSERT INTO approvals
      (email, template, approved, rule, campaign_step, next_send_at, detail, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(email, template) DO UPDATE SET
       approved = excluded.approved,
       rule = excluded.rule,
       campaign_step = excluded.campaign_step,
       next_send_at = excluded.next_send_at,
       detail = excluded.detail,
       updated_at = CURRENT_TIMESTAMP`
  )
    .bind(
      String(row.email || ""),
      String(row.template || ""),
      String(row.approved || "no"),
      String(row.rule || ""),
      String(row.campaign_step || ""),
      String(row.next_send_at || ""),
      String(row.detail || "")
    )
    .run();
}

export async function gmailRowsFor(env) {
  if (!(await ensureDatabase(env))) return GMAIL_ROWS;
  const { results = [] } = await env.DB.prepare(
    `SELECT review_status, email, gmail_status, template, lead_status, detail
     FROM gmail_results
     ORDER BY updated_at DESC, email ASC`
  ).all();
  return results.length ? results : GMAIL_ROWS;
}

export async function saveGmailRows(env, rows) {
  if (!(await ensureDatabase(env))) return Array.isArray(rows) ? rows : [];
  for (const row of Array.isArray(rows) ? rows : []) {
    await env.DB.prepare(
      `INSERT INTO gmail_results
        (email, template, review_status, gmail_status, lead_status, detail, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(email, template) DO UPDATE SET
         review_status = excluded.review_status,
         gmail_status = excluded.gmail_status,
         lead_status = excluded.lead_status,
         detail = excluded.detail,
         updated_at = CURRENT_TIMESTAMP`
    )
      .bind(
        String(row.email || ""),
        String(row.template || ""),
        String(row.review_status || "pending"),
        String(row.gmail_status || "pending"),
        String(row.lead_status || ""),
        String(row.detail || "")
      )
      .run();
  }
  return gmailRowsFor(env);
}

export async function logGmailSend(env, row) {
  if (!(await ensureDatabase(env))) return false;
  await env.DB.prepare(
    `INSERT INTO gmail_send_logs
      (id, recipient, subject, mode, status, message_id, error, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(
      String(row.id || crypto.randomUUID()),
      String(row.recipient || ""),
      String(row.subject || ""),
      String(row.mode || "test"),
      String(row.status || "pending"),
      String(row.message_id || ""),
      String(row.error || "")
    )
    .run();
  return true;
}

export function countApproval(rows) {
  const approved = rows.filter((row) => String(row.approved || "").toLowerCase() === "yes").length;
  return { ready: rows.length, approved, waiting: rows.length - approved };
}

export function templates() {
  return FLOW_STEPS.map((step) => ({
    name: step.template,
    subject: step.subject,
    text_body: step.text_body,
    html_body: ""
  }));
}

export function gmailCounts() {
  return gmailCountsForRows(GMAIL_ROWS);
}

export function gmailCountsForRows(rows) {
  return {
    matched: rows.filter((row) => row.review_status === "matched").length,
    needs_review: rows.filter((row) => row.review_status === "needs_review").length,
    pending: rows.filter((row) => row.review_status === "pending").length
  };
}
