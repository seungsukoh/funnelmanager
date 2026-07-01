import { json } from "../../_shared/cloud-api.js";

export function onRequestPost({ env }) {
  return json({
    summary: {
      imported: 1,
      failed: 0,
      skipped: 1
    },
    message: "클라우드 미리보기 결과 반영입니다. 실제 고객 상태 저장은 D1 연결 후 활성화됩니다."
  }, 200, env);
}
