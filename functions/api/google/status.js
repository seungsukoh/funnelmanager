import { json } from "../../_shared/cloud-api.js";

export function onRequestPost() {
  return json({
    redirect_uri: "Cloudflare Functions OAuth callback",
    sheet_name: "GmailQueue",
    steps: [
      {
        id: "cloud",
        label: "Google Cloud 설정",
        done: false,
        detail: "Cloudflare Secret에 OAuth Client를 저장해야 합니다."
      },
      {
        id: "sheet",
        label: "비공개 시트 입력",
        done: false,
        detail: "운영 Google Sheet 링크를 연결해야 합니다."
      },
      {
        id: "connect",
        label: "Google 연결",
        done: false,
        detail: "토큰 저장소를 D1 또는 KV로 연결해야 합니다."
      },
      {
        id: "fetch",
        label: "결과 가져오기 준비",
        done: false,
        detail: "위 항목 완료 후 실제 결과 가져오기가 가능합니다."
      }
    ],
    message: "Cloudflare 미리보기에서는 Google 연결 상태만 안내합니다."
  });
}
