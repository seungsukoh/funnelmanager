import { countApproval, json, readBody } from "../../_shared/cloud-api.js";

export async function onRequestPost({ request }) {
  const body = await readBody(request);
  const rows = Array.isArray(body.rows) ? body.rows : [];
  return json({
    rows,
    counts: countApproval(rows),
    path: "cloud/preview-approval",
    message: `클라우드 미리보기 승인 ${countApproval(rows).approved}건입니다. 실제 저장은 다음 단계에서 연결합니다.`
  });
}
