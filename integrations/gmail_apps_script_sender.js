const GMAIL_QUEUE_SHEET = "GmailQueue";
const DAILY_SEND_LIMIT = 90;
const SENDER_NAME = "Event Team";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Funnel Mail")
    .addItem("Setup GmailQueue sheet", "setupGmailQueueSheet")
    .addItem("Send approved emails", "sendApprovedEmails")
    .addItem("Install daily trigger", "installDailyTrigger")
    .addToUi();
}

function setupGmailQueueSheet() {
  const sheet = getOrCreateQueueSheet_();
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      "approved",
      "status",
      "email",
      "name",
      "campaign_id",
      "template",
      "rule",
      "subject",
      "text_body",
      "html_body",
      "dedupe_key",
      "sent_at",
      "error"
    ]);
  }
  sheet.setFrozenRows(1);
}

function sendApprovedEmails() {
  const sheet = getOrCreateQueueSheet_();
  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return;

  const headers = values[0].map(String);
  const indexes = indexHeaders_(headers);
  const quota = MailApp.getRemainingDailyQuota();
  const limit = Math.min(DAILY_SEND_LIMIT, quota);
  let sent = 0;

  for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
    if (sent >= limit) break;

    const row = values[rowIndex];
    const approved = getCell_(row, indexes, "approved").toLowerCase();
    const status = getCell_(row, indexes, "status").toLowerCase();
    const email = getCell_(row, indexes, "email");
    const subject = getCell_(row, indexes, "subject");
    const textBody = getCell_(row, indexes, "text_body") || " ";
    const htmlBody = getCell_(row, indexes, "html_body");
    const name = getCell_(row, indexes, "name");

    if (!["yes", "true", "1", "on"].includes(approved)) continue;
    if (status === "sent") continue;
    if (!email || !subject) {
      setCell_(sheet, rowIndex, indexes, "status", "failed");
      setCell_(sheet, rowIndex, indexes, "error", "missing email or subject");
      continue;
    }

    try {
      MailApp.sendEmail({
        to: email,
        subject,
        body: textBody,
        htmlBody: htmlBody || undefined,
        name: SENDER_NAME || undefined
      });
      setCell_(sheet, rowIndex, indexes, "status", "sent");
      setCell_(sheet, rowIndex, indexes, "sent_at", new Date().toISOString());
      setCell_(sheet, rowIndex, indexes, "error", "");
      sent += 1;
    } catch (error) {
      setCell_(sheet, rowIndex, indexes, "status", "failed");
      setCell_(sheet, rowIndex, indexes, "error", String(error && error.message ? error.message : error));
    }
  }
}

function installDailyTrigger() {
  ScriptApp.newTrigger("sendApprovedEmails")
    .timeBased()
    .everyDays(1)
    .atHour(9)
    .create();
}

function getOrCreateQueueSheet_() {
  const spreadsheet = SpreadsheetApp.getActive();
  return spreadsheet.getSheetByName(GMAIL_QUEUE_SHEET) || spreadsheet.insertSheet(GMAIL_QUEUE_SHEET);
}

function indexHeaders_(headers) {
  const indexes = {};
  headers.forEach((header, index) => {
    indexes[String(header).trim()] = index;
  });
  return indexes;
}

function getCell_(row, indexes, name) {
  const index = indexes[name];
  return index === undefined ? "" : String(row[index] || "").trim();
}

function setCell_(sheet, zeroBasedDataRowIndex, indexes, name, value) {
  const index = indexes[name];
  if (index === undefined) return;
  sheet.getRange(zeroBasedDataRowIndex + 1, index + 1).setValue(value);
}
