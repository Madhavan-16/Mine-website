PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT CHECK(role IN ('admin','moderator','user')) DEFAULT 'user',
  is_active INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module TEXT,
  title TEXT,
  summary TEXT,
  body TEXT,
  status TEXT,
  author_id INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER,
  program_name TEXT,
  project_manager TEXT,
  delivery_status TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_meta (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER,
  meta_key TEXT,
  meta_value TEXT,
  FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER,
  file_name TEXT,
  file_path TEXT,
  preview_path TEXT,
  slide_preview_dir TEXT,
  uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS moderation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER,
  action TEXT,
  performed_by INTEGER,
  note TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE SET NULL,
  FOREIGN KEY (performed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  action TEXT,
  entity_type TEXT,
  entity_id INTEGER,
  detail TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  message TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'personal',
  is_read INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notification_user_state (
  notification_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  is_read INTEGER DEFAULT 0,
  is_cleared INTEGER DEFAULT 0,
  PRIMARY KEY (notification_id, user_id),
  FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_mail_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  provider TEXT NOT NULL DEFAULT 'microsoft_graph',
  access_token_enc TEXT NOT NULL,
  refresh_token_enc TEXT NOT NULL,
  expires_at_utc DATETIME NOT NULL,
  scope TEXT,
  tenant_hint TEXT,
  account_email TEXT,
  account_display_name TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE(user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);
CREATE INDEX IF NOT EXISTS idx_content_module ON content(module);
CREATE INDEX IF NOT EXISTS idx_content_author ON content(author_id);
CREATE INDEX IF NOT EXISTS idx_meta_content ON content_meta(content_id);
CREATE INDEX IF NOT EXISTS idx_user_mail_tokens_user ON user_mail_tokens(user_id);

CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
  title,
  summary,
  body,
  tags,
  tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS content_ai AFTER INSERT ON content BEGIN
  INSERT INTO content_fts(rowid, title, summary, body, tags)
  VALUES (
    new.id,
    coalesce(new.title, ''),
    coalesce(new.summary, ''),
    coalesce(new.body, ''),
    (SELECT coalesce(group_concat(meta_value, ' '), '') FROM content_meta WHERE content_id = new.id AND meta_key = 'tag')
  );
END;

CREATE TRIGGER IF NOT EXISTS content_ad AFTER DELETE ON content BEGIN
  DELETE FROM content_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS content_au AFTER UPDATE ON content BEGIN
  DELETE FROM content_fts WHERE rowid = old.id;
  INSERT INTO content_fts(rowid, title, summary, body, tags)
  VALUES (
    new.id,
    coalesce(new.title, ''),
    coalesce(new.summary, ''),
    coalesce(new.body, ''),
    (SELECT coalesce(group_concat(meta_value, ' '), '') FROM content_meta WHERE content_id = new.id AND meta_key = 'tag')
  );
END;
