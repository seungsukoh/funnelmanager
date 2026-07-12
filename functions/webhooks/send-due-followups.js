import { countBy, json, queueRowsFor, readBody } from "../_shared/cloud-api.js";
import { sendDueFollowupEmails } from "../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const expectedToken = env.FORM_WEBHOOK_TOKEN || env.AUTOMAILER_WEBHOOK_TOKEN || "";
  if (!expectedToken) {
    return json({
      error: "Cloudflare Secret FORM_WEBHOOK_TOKEN is not configured."
    }, 500, env);
  }

  const actualToken = request.headers.get("X-Automailer-Token") || "";
  if (actualToken !== expectedToken) {
    return json({ error: "Unauthorized webhook request." }, 401, env);
  }

  const body = await readBody(request);
  const summary = await sendDueFollowupEmails(env, {
    limit: body.limit || env.FOLLOWUP_AUTO_SEND_BATCH_LIMIT || 20
  });
  const rows = await queueRowsFor(env);
  return json({
    summary,
    rows,
    counts: countBy(rows, "status"),
    message: summary.sent
      ? `후속 메일 ${summary.sent}건을 자동 발송했습니다.`
      : summary.reason || "자동 발송할 후속 메일이 없습니다."
  }, 200, env);
}

export function onRequestGet({ env }) {
  return json({
    message: "POST to this endpoint with X-Automailer-Token to send due follow-up emails.",
    required_header: "X-Automailer-Token"
  }, 200, env);
}
