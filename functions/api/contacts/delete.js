import {
  approvalRowsFor,
  cloudNotice,
  countApproval,
  countBy,
  deleteContactRows,
  gmailCountsForRows,
  gmailRowsFor,
  json,
  queueRowsFor,
  readBody
} from "../../_shared/cloud-api.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const all = Boolean(body.all);
  const emails = Array.isArray(body.emails) ? body.emails : [];
  if (!all && !emails.length) {
    return json({ error: "삭제할 명단을 선택하세요." }, 400, env);
  }

  const summary = await deleteContactRows(env, { emails, all });
  const rows = await queueRowsFor(env);
  const approvalRows = await approvalRowsFor(env);
  const gmailRows = await gmailRowsFor(env);
  const targetText = all ? "전체 명단" : `선택한 명단 ${summary.deleted}건`;

  return json({
    rows,
    counts: countBy(rows, "status"),
    approval_rows: approvalRows,
    approval_counts: countApproval(approvalRows),
    gmail_rows: gmailRows,
    gmail_counts: gmailCountsForRows(gmailRows),
    summary,
    message: `${targetText}을 삭제했습니다. 연결된 승인 목록과 Gmail 결과도 함께 정리했습니다. ${cloudNotice(env)}`
  }, 200, env);
}
