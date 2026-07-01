import { json } from "../../_shared/cloud-api.js";

export function onRequestPost({ env }) {
  return json({
    auth_url: "",
    message: "Google OAuth는 Cloudflare Secret과 토큰 저장소를 연결한 뒤 활성화됩니다."
  }, 200, env);
}
