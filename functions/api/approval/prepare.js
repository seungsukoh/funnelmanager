import { approvalRows, countApproval, countBy, json, QUEUE_ROWS } from "../../_shared/cloud-api.js";

export function onRequestPost() {
  const rows = approvalRows();
  return json({
    rows,
    counts: countApproval(rows),
    queue_counts: countBy(QUEUE_ROWS, "status"),
    path: "cloud/preview-approval",
    message: `클라우드 미리보기 승인 목록 ${rows.length}건을 만들었습니다. 실제 저장은 D1/R2 연결 후 활성화됩니다.`
  });
}
