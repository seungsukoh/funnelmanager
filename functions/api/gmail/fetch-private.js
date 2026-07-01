import { gmailRowsFor, json, readBody } from "../../_shared/cloud-api.js";
import { fetchSheetResults, googleSetup } from "../../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const setup = await googleSetup(env, body.gmail_source || "");
  if (setup.ready) {
    const summary = await fetchSheetResults(env, {
      source: body.gmail_source,
      sheetName: body.gmail_sheet_name || "GmailQueue"
    });
    return json({
      summary,
      message: `비공개 Google Sheet에서 ${summary.rows}건을 가져왔습니다.`
    }, 200, env);
  }

  const rows = await gmailRowsFor(env);
  return json({
    summary: {
      rows: rows.length,
      output_path: "cloud/gmail-results",
      sheet_name: body.gmail_sheet_name || "GmailQueue"
    },
    message: "Google Sheet 가져오기 준비가 아직 완료되지 않아 저장된 미리보기 결과를 표시합니다."
  }, 200, env);
}
