import { DEFAULTS, cloudNotice, json } from "../_shared/cloud-api.js";

export function onRequestGet({ env }) {
  return json({
    ...DEFAULTS,
    message: cloudNotice(env)
  }, 200, env);
}
