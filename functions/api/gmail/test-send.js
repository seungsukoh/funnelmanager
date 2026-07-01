import { json, readBody } from "../../_shared/cloud-api.js";
import { googleSetup, sendTestEmail } from "../../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const testEmail = String(body.test_email || "").trim();
  if (!testEmail) {
    return json({ error: "테스트 수신자 이메일을 입력하세요." }, 400, env);
  }

  const setup = await googleSetup(env, body.gmail_source || "");
  if (!setup.sendReady) {
    return json({
      summary: {
        sent: false,
        recipient: testEmail,
        mode: "test"
      },
      message: "테스트 발송 준비가 아직 완료되지 않았습니다. D1, Google OAuth Secret, Google 연결 권한을 확인하세요."
    }, 200, env);
  }

  let result;
  try {
    result = await sendTestEmail(env, {
      to: testEmail,
      subject: "[테스트] Funnel Manager Gmail API 연결 확인",
      textBody:
        "Funnel Manager Gmail API 테스트 메일입니다.\n\n이 메일은 테스트 수신자 1명에게만 발송됐습니다.\n승인 명단 전체 발송 기능은 아직 열려 있지 않습니다."
    });
  } catch (error) {
    return json({
      error: error.message || "테스트 메일 발송 중 오류가 발생했습니다."
    }, 400, env);
  }

  return json({
    summary: {
      sent: result.sent,
      recipient: result.recipient,
      subject: result.subject,
      message_id: result.message_id,
      mode: "test"
    },
    message: `테스트 메일을 ${result.recipient} 주소로 발송했습니다.`
  }, 200, env);
}
