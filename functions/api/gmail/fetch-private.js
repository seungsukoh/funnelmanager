import { GMAIL_ROWS, json } from "../../_shared/cloud-api.js";

export function onRequestPost() {
  return json({
    summary: {
      rows: GMAIL_ROWS.length,
      output_path: "cloud/gmail-results",
      sheet_name: "GmailQueue"
    },
    message: "클라우드 미리보기 Gmail 결과를 표시합니다. 실제 결과 가져오기는 Google 연결 후 활성화됩니다."
  });
}
