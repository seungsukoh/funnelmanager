import { GMAIL_ROWS, gmailCounts, json } from "../../_shared/cloud-api.js";

export function onRequestPost() {
  return json({
    rows: GMAIL_ROWS,
    counts: gmailCounts(),
    message: "클라우드 미리보기 Gmail 결과 확인입니다."
  });
}
