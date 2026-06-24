import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    db.executescript(schema)
    db.commit()


def ensure_attachment_preview_column():
    """Existing DBs: add preview_path for derived PDF previews."""
    db = get_db()
    cols = [row[1] for row in db.execute("PRAGMA table_info(attachments)").fetchall()]
    if "preview_path" not in cols:
        db.execute("ALTER TABLE attachments ADD COLUMN preview_path TEXT")
        db.commit()


def ensure_attachment_slide_preview_column():
    """Existing DBs: add slide_preview_dir for rasterized slide PNG previews."""
    db = get_db()
    cols = [row[1] for row in db.execute("PRAGMA table_info(attachments)").fetchall()]
    if "slide_preview_dir" not in cols:
        db.execute("ALTER TABLE attachments ADD COLUMN slide_preview_dir TEXT")
        db.commit()


def ensure_user_mail_tokens_table():
    """Existing DBs: create/upgrade Graph OAuth token table."""
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_mail_tokens (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          provider TEXT NOT NULL DEFAULT 'microsoft_graph',
          access_token_enc TEXT NOT NULL DEFAULT '',
          refresh_token_enc TEXT NOT NULL DEFAULT '',
          expires_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          scope TEXT,
          tenant_hint TEXT,
          account_email TEXT,
          account_display_name TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          UNIQUE(user_id, provider)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_mail_tokens_user ON user_mail_tokens(user_id)")

    cols = {row[1] for row in db.execute("PRAGMA table_info(user_mail_tokens)").fetchall()}
    wanted = {
        "provider": "TEXT NOT NULL DEFAULT 'microsoft_graph'",
        "access_token_enc": "TEXT NOT NULL DEFAULT ''",
        "refresh_token_enc": "TEXT NOT NULL DEFAULT ''",
        "expires_at_utc": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "scope": "TEXT",
        "tenant_hint": "TEXT",
        "account_email": "TEXT",
        "account_display_name": "TEXT",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    }
    for name, ddl in wanted.items():
        if name not in cols:
            db.execute(f"ALTER TABLE user_mail_tokens ADD COLUMN {name} {ddl}")

    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create tables and seed default admin."""
    init_db()
    from mine.seed import seed_if_empty

    seed_if_empty()
    click.echo("Initialized database.")
