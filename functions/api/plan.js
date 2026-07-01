import { cloudNotice, countBy, json, queueRowsFor, readBody } from "../_shared/cloud-api.js";

export async function onRequestPost({ request, env }) {
  await readBody(request);
  const rows = await queueRowsFor(env);
  return json({
    rows,
    counts: countBy(rows, "status"),
    queue_path: "cloud/preview-queue",
    message: `명단 ${rows.length}건을 확인했습니다. ${cloudNotice(env)}`
  }, 200, env);
}
