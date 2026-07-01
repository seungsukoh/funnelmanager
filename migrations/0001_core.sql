CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
  email TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'ready',
  template TEXT NOT NULL DEFAULT '',
  rule TEXT NOT NULL DEFAULT '',
  campaign_step TEXT NOT NULL DEFAULT '',
  next_send_at TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS funnel_steps (
  id TEXT PRIMARY KEY,
  sort_order INTEGER NOT NULL DEFAULT 0,
  stage_label TEXT NOT NULL DEFAULT '',
  priority INTEGER NOT NULL DEFAULT 0,
  audience TEXT NOT NULL DEFAULT '',
  template TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  text_body TEXT NOT NULL DEFAULT '',
  next_send_after_days TEXT NOT NULL DEFAULT '',
  next_step TEXT NOT NULL DEFAULT '',
  status_after TEXT NOT NULL DEFAULT '',
  send_after_label TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS approvals (
  email TEXT NOT NULL,
  template TEXT NOT NULL,
  approved TEXT NOT NULL DEFAULT 'no',
  rule TEXT NOT NULL DEFAULT '',
  campaign_step TEXT NOT NULL DEFAULT '',
  next_send_at TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (email, template)
);

CREATE TABLE IF NOT EXISTS gmail_results (
  email TEXT NOT NULL,
  template TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'pending',
  gmail_status TEXT NOT NULL DEFAULT 'pending',
  lead_status TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (email, template)
);

CREATE TABLE IF NOT EXISTS gmail_send_logs (
  id TEXT PRIMARY KEY,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'test',
  status TEXT NOT NULL DEFAULT 'pending',
  message_id TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
