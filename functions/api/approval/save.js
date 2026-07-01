import { cloudNotice, countApproval, json, readBody, saveApprovalRows } from "../../_shared/cloud-api.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const rows = await saveApprovalRows(env, Array.isArray(body.rows) ? body.rows : []);
  return json({
    rows,
    counts: countApproval(rows),
    path: "cloud/preview-approval",
    message: `승인 ${countApproval(rows).approved}건을 저장했습니다. ${cloudNotice(env)}`
  }, 200, env);
}
