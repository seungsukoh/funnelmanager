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
    const steps = setupSteps(setup);
    return json({
      summary: {
        sent: false,
        recipient: testEmail,
        mode: "test",
        blockers: steps.filter((step) => !step.done).map((step) => step.label)
      },
      steps,
      message: `테스트 발송 준비가 아직 완료되지 않았습니다. 먼저 확인할 항목: ${steps.filter((step) => !step.done).map((step) => step.label).join(", ")}`
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
      error: friendlyGmailError(error),
      detail: error.message || "테스트 메일 발송 중 오류가 발생했습니다."
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

function setupSteps(setup) {
  return [
    {
      id: "database",
      label: "D1 저장소",
      done: setup.databaseReady,
      detail: setup.databaseReady
        ? "D1 저장소가 연결됐습니다."
        : setup.databaseError || "Cloudflare Pages Functions에 D1 바인딩 DB를 연결하세요."
    },
    {
      id: "cloud",
      label: "Google OAuth Secret",
      done: setup.hasClient,
      detail: setup.hasClient ? "Google OAuth Secret이 준비됐습니다." : "GOOGLE_CLIENT_ID와 GOOGLE_CLIENT_SECRET을 Secret으로 추가하세요."
    },
    {
      id: "connect",
      label: "Google 연결",
      done: setup.tokenValid,
      detail: setup.tokenValid
        ? "Gmail 발송 권한까지 승인됐습니다."
        : !setup.hasToken
          ? "앱에서 Google 연결을 눌러 권한을 승인하세요."
          : "기존 Google 연결에 Gmail 발송 권한이 부족합니다. Google 연결을 다시 실행하세요."
    }
  ];
}

function friendlyGmailError(error) {
  const message = error.message || "테스트 메일 발송 중 오류가 발생했습니다.";
  if (/insufficient|scope|permission/i.test(message)) {
    return "Gmail 발송 권한이 부족합니다. 앱에서 Google 연결을 다시 눌러 Gmail 발송 권한을 승인하세요.";
  }
  if (/not been used|disabled|api has not/i.test(message)) {
    return "Google Cloud에서 Gmail API가 아직 켜져 있지 않습니다. Gmail API를 Enable 한 뒤 다시 시도하세요.";
  }
  if (/invalid_grant|refresh_token/i.test(message)) {
    return "Google 연결 토큰이 만료됐거나 맞지 않습니다. 앱에서 Google 연결을 다시 실행하세요.";
  }
  return message;
}
