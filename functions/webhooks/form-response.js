import { countBy, json, queueRowsFor, readBody, saveFormResponse } from "../_shared/cloud-api.js";

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
    const rows = await queueRowsFor(env);
    return json({
      ...result,
      rows,
      counts: countBy(rows, "status"),
      message: result.duplicate
        ? "이미 처리한 폼 응답입니다."
        : result.imported
          ? "폼 응답을 명단에 추가했습니다."
          : "폼 응답을 받았지만 발송 가능한 이메일을 찾지 못했습니다."
    }, result.duplicate ? 200 : 201, env);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return json({ error: message }, message.includes("D1 binding") ? 503 : 500, env);
  }
}

export function onRequestGet({ env }) {
  return json({
    message: "POST Google Forms webhook payloads to this endpoint.",
    required_header: "X-Automailer-Token"
  }, 200, env);
}
