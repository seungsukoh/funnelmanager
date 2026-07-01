import { cloudNotice, FLOW_STEPS, json, readBody, saveFlowSteps, templatesFor } from "../../_shared/cloud-api.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const inputSteps = Array.isArray(body.steps) && body.steps.length ? body.steps : FLOW_STEPS;
  const steps = await saveFlowSteps(env, inputSteps);
  return json({
    path: "cloud/sample-funnel",
    steps,
    templates: await templatesFor(env),
    message: `메일 흐름 ${steps.length}개를 저장했습니다. ${cloudNotice(env)}`
  }, 200, env);
}
