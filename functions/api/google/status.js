import { json, readBody } from "../../_shared/cloud-api.js";
import { googleSetup } from "../../_shared/google.js";

export async function onRequestGet({ request, env }) {
  return statusResponse({ body: bodyFromUrl(request), env });
}

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  return statusResponse({ body, env });
}

async function statusResponse({ body, env }) {
  const setup = await googleSetup(env, body.gmail_source || "");
  return json({
    redirect_uri: "Cloudflare Functions OAuth callback",
    sheet_name: body.gmail_sheet_name || "GmailQueue",
    steps: [
      {
        id: "database",
        label: "D1 저장소",
        done: setup.hasDb,
        detail: setup.hasDb ? "D1 저장소가 연결됐습니다." : "Cloudflare Pages Functions에 D1 바인딩 DB를 연결하세요."
      },
      {
        id: "cloud",
        label: "Google OAuth Secret",
        done: setup.hasClient,
        detail: setup.hasClient ? "Google OAuth Secret이 준비됐습니다." : "GOOGLE_OAUTH_CLIENT Secret 또는 GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET이 필요합니다."
      },
      {
        id: "sheet",
        label: "비공개 시트 입력",
        done: setup.sheetReady,
        detail: setup.sheetReady ? "Gmail 시트 링크가 입력됐습니다." : "운영 Google Sheet 링크를 입력하세요."
      },
      {
        id: "connect",
        label: "Google 연결",
        done: setup.tokenValid,
        detail: setup.tokenValid
          ? "Google Sheets/Gmail 발송 권한 토큰이 D1에 저장됐습니다."
          : !setup.hasToken
            ? "Google 연결을 눌러 권한을 승인하세요."
            : setup.tokenHasRequiredScopes
              ? "Google 연결을 눌러 권한을 다시 승인하세요."
              : "기존 Google 연결에 Gmail 발송 권한이 없습니다. Google 연결을 다시 실행하세요."
      },
      {
        id: "gmail_send",
        label: "Gmail 테스트 발송",
        done: setup.sendReady,
        detail: setup.sendReady ? "테스트 수신자 1명에게 Gmail API 발송을 실행할 수 있습니다." : "Gmail 발송 권한까지 승인하면 테스트 발송을 실행할 수 있습니다."
      },
      {
        id: "fetch",
        label: "Sheet 실행 준비",
        done: setup.ready,
        detail: setup.ready
          ? "비공개 시트 업로드/가져오기를 실행할 수 있습니다."
          : "Gmail 시트 링크까지 입력하면 실제 Google Sheet 연동이 가능합니다."
      }
    ],
    message: setup.ready ? "Google Sheet 연동 준비가 완료됐습니다." : "Google Sheet 연동 준비 상태를 확인했습니다."
  }, 200, env);
}

function bodyFromUrl(request) {
  const params = new URL(request.url).searchParams;
  return {
    gmail_source: params.get("gmail_source") || "",
    gmail_sheet_name: params.get("gmail_sheet_name") || "GmailQueue"
  };
}
