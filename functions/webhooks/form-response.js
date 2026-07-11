import {
  checkFormAutoSendAllowed,
  countBy,
  json,
  queueRowsFor,
  readBody,
  recordFormAutoSend,
  saveFormResponse
} from "../_shared/cloud-api.js";
import { googleSetup, sendWorkflowEmail } from "../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const expectedToken = env.FORM_WEBHOOK_TOKEN || env.AUTOMAILER_WEBHOOK_TOKEN || "";
  if (!expectedToken) {
    return json({
      error: "Cloudflare Secret FORM_WEBHOOK_TOKEN is not configured."
    }, 500, env);
  }

  const actualToken = request.headers.get("X-Automailer-Token") || "";
  if (actualToken !== expectedToken) {
    return json({ error: "Unauthorized webhook request." }, 401, env);
  }

  const payload = await readBody(request);
  try {
    const result = await saveFormResponse(env, payload);
    const autoSend = await maybeAutoSendFormResponse(env, result, payload);
    const rows = await queueRowsFor(env);
    return json({
      ...result,
      auto_send: autoSend,
      rows,
      counts: countBy(rows, "status"),
      message: result.duplicate
        ? "이미 처리한 폼 응답입니다."
        : autoSend.sent
          ? "폼 응답을 명단에 추가하고 첫 메일을 자동 발송했습니다."
        : result.imported
          ? "폼 응답을 명단에 추가했습니다."
          : "폼 응답을 받았지만 발송 가능한 이메일을 찾지 못했습니다."
    }, result.duplicate ? 200 : 201, env);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return json({ error: message }, message.includes("D1 binding") ? 503 : 500, env);
  }
}

async function maybeAutoSendFormResponse(env, result, payload) {
  const skipped = (reason, extra = {}) => ({
    enabled: Boolean(extra.settings?.enabled),
    attempted: false,
    sent: false,
    reason,
    ...extra
  });

  if (result.duplicate) return skipped("중복 응답은 자동 발송하지 않습니다.");
  if (result.existing_contact) return skipped("이미 등록된 고객은 자동 발송하지 않습니다.");
  if (!result.imported || !result.contact?.email) return skipped("발송 가능한 이메일이 없습니다.");

  const allowed = await checkFormAutoSendAllowed(env);
  if (!allowed.allowed) {
    return skipped(allowed.reason, { settings: allowed.settings });
  }

  const setup = await googleSetup(env, "");
  if (!setup.sendReady) {
    return {
      enabled: true,
      attempted: false,
      sent: false,
      reason: "Gmail API 발송 준비가 완료되지 않았습니다.",
      blockers: setupSteps(setup),
      settings: allowed.settings
    };
  }

  try {
    const sent = await sendWorkflowEmail(env, {
      contact: result.contact,
      fields: payload.fields || {},
      mode: "form_auto"
    });
    const settings = await recordFormAutoSend(env);
    return {
      enabled: true,
      attempted: true,
      sent: true,
      recipient: sent.recipient,
      subject: sent.subject,
      template: sent.template,
      message_id: sent.message_id,
      sent_at: sent.sent_at,
      settings
    };
  } catch (error) {
    return {
      enabled: true,
      attempted: true,
      sent: false,
      error: friendlyAutoSendError(error),
      settings: allowed.settings
    };
  }
}

function setupSteps(setup) {
  const steps = [];
  if (!setup.databaseReady) steps.push("D1 저장소");
  if (!setup.hasClient) steps.push("Google OAuth Secret");
  if (!setup.tokenValid) steps.push("Google 연결");
  return steps;
}

function friendlyAutoSendError(error) {
  const message = error.message || "자동 발송 중 오류가 발생했습니다.";
  if (/already/i.test(message) || /이미/.test(message)) return message;
  if (/insufficient|scope|permission/i.test(message)) {
    return "Gmail 발송 권한이 부족합니다. 앱에서 Google 연결을 다시 실행하세요.";
  }
  if (/not been used|disabled|api has not/i.test(message)) {
    return "Google Cloud에서 Gmail API가 켜져 있는지 확인하세요.";
  }
  if (/invalid_grant|refresh_token/i.test(message)) {
    return "Google 연결 토큰이 만료됐습니다. 앱에서 Google 연결을 다시 실행하세요.";
  }
  return message;
}

export function onRequestGet({ env }) {
  return json({
    message: "POST Google Forms webhook payloads to this endpoint.",
    required_header: "X-Automailer-Token"
  }, 200, env);
}
