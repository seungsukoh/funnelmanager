import { CLOUD_NOTICE, FLOW_STEPS, json, templates } from "../_shared/cloud-api.js";

export function onRequestGet() {
  return json({
    path: "cloud/sample-funnel",
    steps: FLOW_STEPS,
    templates: templates(),
    message: `클라우드 미리보기 메일 흐름입니다. ${CLOUD_NOTICE}`
  });
}
