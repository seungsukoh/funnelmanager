import { json } from "../../_shared/cloud-api.js";

export function onRequestPost() {
  return json({
    summary: {
      output_path: "cloud/gmail-send-queue",
      pending: 1
    },
    message: "클라우드 미리보기 Gmail 발송 준비 1건입니다. 실제 파일 생성은 저장소 연결 후 활성화됩니다."
  });
}
