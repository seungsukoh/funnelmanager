import { html, json } from "../../_shared/cloud-api.js";
import { completeAuthorization } from "../../_shared/google.js";

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const error = url.searchParams.get("error");
  if (error) return resultHtml(false, `Google 연결 실패: ${error}`);

  try {
    const code = url.searchParams.get("code") || "";
    const state = url.searchParams.get("state") || "";
    if (!code || !state) throw new Error("Google 연결 코드가 없습니다.");
    await completeAuthorization(env, { code, state });
    return resultHtml(true, "Google 연결이 완료됐습니다. 앱으로 돌아가 Google 상태를 다시 확인하세요.");
  } catch (errorValue) {
    return resultHtml(false, errorValue.message || "Google 연결에 실패했습니다.");
  }
}

export function onRequestPost() {
  return json({ error: "method not allowed" }, 405);
}

function resultHtml(ok, message) {
  return html(`<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Google 연결</title>
    <style>
      body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f8fb; color: #172033; }
      main { width: min(680px, calc(100% - 32px)); margin: 12vh auto; padding: 28px; border: 1px solid #d8e0ea; border-radius: 8px; background: #fff; }
      h1 { margin: 0 0 12px; font-size: 1.5rem; }
      p { margin: 0 0 20px; line-height: 1.6; color: #46566a; }
      .badge { display: inline-flex; margin-bottom: 16px; padding: 6px 10px; border-radius: 6px; font-weight: 800; background: ${ok ? "#e5f4ea" : "#fff1f2"}; color: ${ok ? "#166534" : "#9f1239"}; }
      button { min-height: 40px; padding: 0 14px; border: 1px solid #224f8a; border-radius: 6px; background: #224f8a; color: #fff; font-weight: 800; cursor: pointer; }
    </style>
  </head>
  <body>
    <main>
      <span class="badge">${ok ? "완료" : "확인 필요"}</span>
      <h1>Google 연결</h1>
      <p>${escapeHtml(message)}</p>
      <button type="button" onclick="window.close()">창 닫기</button>
    </main>
  </body>
</html>`);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
