const WEBHOOK_URL = "https://your-app.example.com/webhooks/form-response";
const WEBHOOK_TOKEN = "replace-with-shared-secret";

function onFormSubmit(e) {
  const fields = {};

  Object.keys(e.namedValues).forEach((key) => {
    const value = e.namedValues[key];
    fields[key] = Array.isArray(value) ? value.join(", ") : String(value || "");
  });

  const payload = {
    source: "google_forms",
    external_response_id: `${e.range.getSheet().getSheetId()}:${e.range.getRow()}`,
    submitted_at: new Date().toISOString(),
    fields
  };

  UrlFetchApp.fetch(WEBHOOK_URL, {
    method: "post",
    contentType: "application/json",
    headers: {
      "X-Automailer-Token": WEBHOOK_TOKEN
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}
