import { countBy, json, queueRowsFor, readBody } from "../../_shared/cloud-api.js";
import { sendDueFollowupEmails } from "../../_shared/google.js";

export async function onRequestPost({ request, env }) {
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
      ? `후속 메일 ${summary.sent}건을 발송했습니다.`
      : summary.reason || "지금 자동 발송할 후속 메일이 없습니다."
  }, 200, env);
}

export function onRequestGet({ env }) {
  return json({
    message: "POST to this endpoint from the app to send due follow-up emails."
  }, 200, env);
}
