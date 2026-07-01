import { applyGmailResultsToContacts, countBy, json, queueRowsFor } from "../../_shared/cloud-api.js";

export async function onRequestPost({ env }) {
  const summary = await applyGmailResultsToContacts(env);
  const rows = await queueRowsFor(env);
  return json({
    summary,
    rows,
    counts: countBy(rows, "status"),
    message: `Gmail 결과를 반영했습니다. 다음 메일 예약 ${summary.scheduled}건, 바로 보낼 수 있는 메일 ${summary.ready}건, 완료 ${summary.completed}건입니다.`
  }, 200, env);
}
