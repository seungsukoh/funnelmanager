import { cloudNotice, flowStepsFor, json, templatesFor } from "../_shared/cloud-api.js";

export async function onRequestGet({ env }) {
  const steps = await flowStepsFor(env);
  return json({
    path: "cloud/sample-funnel",
    steps,
    templates: await templatesFor(env),
    message: `메일 흐름 ${steps.length}개를 불러왔습니다. ${cloudNotice(env)}`
  }, 200, env);
}
