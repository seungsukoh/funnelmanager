import { cloudNotice, countApproval, countBy, json, prepareApprovalRowsFor, queueRowsFor } from "../../_shared/cloud-api.js";

export async function onRequestPost({ env }) {
  const rows = await prepareApprovalRowsFor(env);
  const queueRows = await queueRowsFor(env);
  return json({
    rows,
    counts: countApproval(rows),
    queue_counts: countBy(queueRows, "status"),
    path: "cloud/preview-approval",
    message: `승인 목록 ${rows.length}건을 만들었습니다. ${cloudNotice(env)}`
  }, 200, env);
}
