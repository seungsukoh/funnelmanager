import { approvalRowsFor, json } from "../../_shared/cloud-api.js";

export async function onRequestPost({ env }) {
  const approvals = await approvalRowsFor(env);
  const pending = approvals.filter((row) => row.approved === "yes").length || approvals.length;
  return json({
    summary: {
      output_path: "cloud/gmail-send-queue",
      pending
    },
    message: `Gmail 발송 준비 ${pending}건입니다. 실제 Gmail 발송은 Google OAuth 연결 후 활성화됩니다.`
  }, 200, env);
}
