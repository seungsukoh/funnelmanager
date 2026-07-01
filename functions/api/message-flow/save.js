import { CLOUD_NOTICE, FLOW_STEPS, json, readBody, templates } from "../../_shared/cloud-api.js";

export async function onRequestPost({ request }) {
  const body = await readBody(request);
  const steps = Array.isArray(body.steps) && body.steps.length ? body.steps : FLOW_STEPS;
  return json({
    path: "cloud/sample-funnel",
    steps,
    templates: templates(),
    message: `클라우드 미리보기에서는 저장하지 않고 화면에만 반영합니다. ${CLOUD_NOTICE}`
  });
}
