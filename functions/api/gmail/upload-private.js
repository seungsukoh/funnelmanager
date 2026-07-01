import { json, readBody } from "../../_shared/cloud-api.js";
import { googleSetup, uploadQueueToSheet } from "../../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const setup = await googleSetup(env, body.gmail_source || "");
  if (!setup.ready) {
    return json({
      summary: {
        rows: 1,
        columns: ["approved", "status", "email", "subject", "text_body"],
        spreadsheet_id: "cloud-preview",
        sheet_name: body.gmail_sheet_name || "GmailQueue",
        updated_rows: 0,
        updated_cells: 0
      },
      message: "Google Sheet 업로드 준비가 아직 완료되지 않았습니다. D1, OAuth Secret, Google 연결, 시트 링크를 확인하세요."
    }, 200, env);
  }

  const summary = await uploadQueueToSheet(env, {
    source: body.gmail_source,
    sheetName: body.gmail_sheet_name || "GmailQueue",
    campaignId: body.campaign_id || "cloud-preview"
  });
  return json({
    summary,
    message: `비공개 Google Sheet에 ${summary.rows}건을 업로드했습니다.`
  }, 200, env);
}
