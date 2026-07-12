import { dueFollowupSummary, formAutoSendSettings, json, readBody, saveFormAutoSendSettings } from "../../_shared/cloud-api.js";
import { googleSetup } from "../../_shared/google.js";

export async function onRequestGet({ env }) {
  const settings = await formAutoSendSettings(env);
  const status = await autoSendStatus(env, settings);
  return json({
    settings,
    status,
    message: autoSendMessage(settings)
  }, 200, env);
}

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const settings = await saveFormAutoSendSettings(env, body);
  const status = await autoSendStatus(env, settings);
  return json({
    settings,
    status,
    message: autoSendMessage(settings)
  }, 200, env);
}

async function autoSendStatus(env, settings) {
  const due = await dueFollowupSummary(env, 5);
  let setup;
  try {
    setup = await googleSetup(env, "");
  } catch (error) {
    setup = {
      sendReady: false,
      databaseReady: false,
      hasClient: false,
      tokenValid: false,
      error: error.message || "Gmail 상태를 확인하지 못했습니다."
    };
  }

  const blockers = [];
  if (!settings.followups_enabled) blockers.push("후속 자동 발송이 꺼져 있습니다.");
  if (!setup.sendReady) blockers.push("Gmail 발송 권한 연결이 필요합니다.");
  if (Number(settings.followup_remaining_today || 0) <= 0) blockers.push("오늘 후속 자동 발송 한도에 도달했습니다.");
  if (Number(due.due_count || 0) <= 0) blockers.push("지금 보낼 후속 메일 대상이 없습니다.");

  const ready = blockers.length === 0;
  return {
    first_mail: {
      enabled: Boolean(settings.enabled),
      sent_today: Number(settings.sent_today || 0),
      daily_limit: Number(settings.daily_limit || 20),
      remaining_today: Number(settings.remaining_today || 0)
    },
    followups: {
      enabled: Boolean(settings.followups_enabled),
      sent_today: Number(settings.followup_sent_today || 0),
      daily_limit: Number(settings.followup_daily_limit || 20),
      remaining_today: Number(settings.followup_remaining_today || 0),
      due_count: Number(due.due_count || 0),
      due_preview: due.due_preview || [],
      gmail_ready: Boolean(setup.sendReady),
      ready,
      blockers,
      label: ready ? "실행 가능" : "확인 필요",
      detail: ready
        ? `예약일이 지난 후속 메일 ${due.due_count}건을 발송할 수 있습니다.`
        : blockers[0] || "상태 확인이 필요합니다."
    }
  };
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
