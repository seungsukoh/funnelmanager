import { json, readBody } from "../../_shared/cloud-api.js";
import { buildAuthorization } from "../../_shared/google.js";

export async function onRequestPost({ request, env }) {
  const body = await readBody(request);
  const origin = new URL(request.url).origin;
  const redirectUri = String(body.redirect_uri || `${origin}/oauth/google/callback`);
  const result = await buildAuthorization(env, redirectUri);
  return json(result, 200, env);
}
