import { json, queueRowsFor } from "../_shared/cloud-api.js";

export async function onRequestPost({ env }) {
  const queueRows = await queueRowsFor(env);
  const reportRows = queueRows.map((row) => ({
    status: row.status === "ready" ? "sent" : "skipped",
    email: row.email,
    template: row.template,
    rule: row.rule,
    detail: row.status === "ready" ? "샘플 미리보기를 만들었습니다." : row.detail,
    error: ""
  }));
  return json({
    summary: {
      processed: reportRows.length,
      sent: reportRows.filter((row) => row.status === "sent").length,
      skipped: reportRows.filter((row) => row.status === "skipped").length,
      failed: 0,
      report_path: "cloud/preview-report",
      errors: []
    },
    report_rows: reportRows,
    message: "클라우드 미리보기 메일 결과입니다. 실제 메일은 발송하지 않았습니다."
  }, 200, env);
}
