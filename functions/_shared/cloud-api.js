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

export function json(payload = {}, status = 200) {
  return new Response(
    JSON.stringify(
      {
        ok: status < 400,
        cloud_mode: CLOUD_MODE,
        cloud_notice: CLOUD_NOTICE,
        ...payload
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
  return {
    matched: GMAIL_ROWS.filter((row) => row.review_status === "matched").length,
    needs_review: GMAIL_ROWS.filter((row) => row.review_status === "needs_review").length,
    pending: GMAIL_ROWS.filter((row) => row.review_status === "pending").length
  };
}
