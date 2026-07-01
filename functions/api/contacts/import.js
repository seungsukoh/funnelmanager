import { cloudNotice, countBy, json, queueRowsFor, readBody, saveContactRows } from "../../_shared/cloud-api.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const rows = Array.isArray(body.rows) ? body.rows : [];
  if (!rows.length) {
    return json({ error: "엑셀 또는 CSV에서 읽은 명단이 없습니다." }, 400, env);
  }

  const imported = await saveContactRows(env, rows);
  const queueRows = await queueRowsFor(env);
  return json({
    imported,
    rows: queueRows,
    counts: countBy(queueRows, "status"),
    summary: {
      received: rows.length,
      imported: imported.length
    },
    message: `명단 ${imported.length}건을 불러왔습니다. 발송 승인에서 보낼 사람을 선택하세요. ${cloudNotice(env)}`
  }, 200, env);
}
