const FOLLOWUP_WEBHOOK_URL = "https://funnelmanager.pages.dev/webhooks/send-due-followups";
const FOLLOWUP_WEBHOOK_TOKEN = "replace-with-shared-secret";

function runDueFollowups() {
  const response = UrlFetchApp.fetch(FOLLOWUP_WEBHOOK_URL, {
    method: "post",
    contentType: "application/json",
    headers: {
      "X-Automailer-Token": FOLLOWUP_WEBHOOK_TOKEN
    },
    payload: JSON.stringify({
      limit: 20
    }),
    muteHttpExceptions: true
  });

  console.log(response.getResponseCode());
  console.log(response.getContentText());
}
