import { json } from "../../_shared/cloud-api.js";

export function onRequestPost({ env }) {
  return json({
    summary: {
      rows: 1,
      columns: ["approved", "status", "email", "subject", "text_body"],
      spreadsheet_id: "cloud-preview",
      sheet_name: "GmailQueue",
      updated_rows: 0,
      updated_cells: 0
    },
    message: "클라우드 미리보기입니다. 실제 Google Sheet 업로드는 OAuth와 Sheets API 연결 후 실행됩니다."
  }, 200, env);
}
