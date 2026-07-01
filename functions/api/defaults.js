import { CLOUD_NOTICE, DEFAULTS, json } from "../_shared/cloud-api.js";

export function onRequestGet() {
  return json({
    ...DEFAULTS,
    message: CLOUD_NOTICE
  });
}
