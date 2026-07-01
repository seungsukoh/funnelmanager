import { json, readBody } from "../../_shared/cloud-api.js";
import { googleSetup } from "../../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
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
        detail: setup.tokenValid ? "Google 연결 토큰이 D1에 저장됐습니다." : "Google 연결을 눌러 권한을 승인하세요."
      },
      {
        id: "fetch",
        label: "결과 가져오기 준비",
        done: setup.ready,
        detail: setup.ready ? "비공개 시트 업로드/가져오기를 실행할 수 있습니다." : "위 항목을 완료하면 실제 Google Sheet 연동이 가능합니다."
      }
    ],
    message: setup.ready ? "Google Sheet 연동 준비가 완료됐습니다." : "Google Sheet 연동 준비 상태를 확인했습니다."
  }, 200, env);
}
