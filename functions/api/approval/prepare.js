import { cloudNotice, countApproval, countBy, json, prepareApprovalRowsFor, queueRowsFor, readBody } from "../../_shared/cloud-api.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const selectedEmails = Array.isArray(body.selected_emails) ? body.selected_emails : [];
  const rows = await prepareApprovalRowsFor(env, {
    emails: selectedEmails,
    approve_selected: Boolean(body.approve_selected)
  });
  const queueRows = await queueRowsFor(env);
  const selectedText = selectedEmails.length ? `선택한 명단 ${rows.length}건만 승인 목록에 올렸습니다.` : `승인 목록 ${rows.length}건을 만들었습니다.`;
  return json({
    rows,
    counts: countApproval(rows),
    queue_counts: countBy(queueRows, "status"),
    path: "cloud/preview-approval",
    message: `${selectedText} ${cloudNotice(env)}`
  }, 200, env);
}
