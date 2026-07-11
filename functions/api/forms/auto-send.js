import { formAutoSendSettings, json, readBody, saveFormAutoSendSettings } from "../../_shared/cloud-api.js";

export async function onRequestGet({ env }) {
  const settings = await formAutoSendSettings(env);
  return json({
    settings,
    message: settings.enabled
      ? `폼 자동 발송이 켜져 있습니다. 오늘 ${settings.sent_today}/${settings.daily_limit}건을 발송했습니다.`
      : "폼 자동 발송이 꺼져 있습니다. 폼 응답은 명단에만 등록됩니다."
  }, 200, env);
}

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const settings = await saveFormAutoSendSettings(env, body);
  return json({
    settings,
    message: settings.enabled
      ? `폼 자동 발송을 켰습니다. 일일 제한은 ${settings.daily_limit}건입니다.`
      : "폼 자동 발송을 껐습니다. 폼 응답은 명단에만 등록됩니다."
  }, 200, env);
}
