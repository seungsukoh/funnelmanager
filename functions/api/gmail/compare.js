import { gmailCountsForRows, gmailRowsFor, json } from "../../_shared/cloud-api.js";

export async function onRequestPost({ env }) {
  const rows = await gmailRowsFor(env);
  return json({
    rows,
    counts: gmailCountsForRows(rows),
    message: "클라우드 미리보기 Gmail 결과 확인입니다."
  }, 200, env);
}
