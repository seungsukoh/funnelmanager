import { formAutoSendSettings, json, readBody, saveFormAutoSendSettings } from "../../_shared/cloud-api.js";

export async function onRequestGet({ env }) {
  const settings = await formAutoSendSettings(env);
  return json({
    settings,
    message: autoSendMessage(settings)
  }, 200, env);
}

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const settings = await saveFormAutoSendSettings(env, body);
  return json({
    settings,
    message: autoSendMessage(settings)
  }, 200, env);
}

function autoSendMessage(settings) {
  const first = settings.enabled
    ? `첫 메일 자동 발송 켜짐: 오늘 ${settings.sent_today}/${settings.daily_limit}건`
    : "첫 메일 자동 발송 꺼짐";
  const followup = settings.followups_enabled
    ? `후속 자동 발송 켜짐: 오늘 ${settings.followup_sent_today}/${settings.followup_daily_limit}건`
    : "후속 자동 발송 꺼짐";
  return `${first}. ${followup}.`;
}
