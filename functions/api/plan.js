import { CLOUD_NOTICE, QUEUE_ROWS, countBy, json, readBody } from "../_shared/cloud-api.js";

export async function onRequestPost({ request }) {
  await readBody(request);
  return json({
    rows: QUEUE_ROWS,
    counts: countBy(QUEUE_ROWS, "status"),
    queue_path: "cloud/preview-queue",
    message: `클라우드 미리보기 명단입니다. 실제 파일 처리 전 샘플 ${QUEUE_ROWS.length}건을 표시합니다. ${CLOUD_NOTICE}`
  });
}
