"""Guest account: read-only browse of selected knowledge pages."""

from __future__ import annotations

import bcrypt

from mine.db import get_db

GUEST_USERNAME = "guest"
GUEST_EMAIL = "guest@mine.local"
GUEST_DISPLAY_NAME = "Guest"

# Endpoints a guest may hit (everything else redirects to Knowledge).
GUEST_ALLOWED_ENDPOINTS = frozenset(
    {
        "auth.login",
        "auth.login_guest",
        "auth.logout",
        "main.knowledge",
        "main.journey",
        "main.journey_autonomous_mining_revolution_image",
        "main.journey_autonomous_mining_revolution_image_2x",
        "main.open_pit_copper_domain",
        "main.open_pit_copper_domain_raw",
        "main.open_pit_copper_domain_lifecycle_image",
        "main.open_pit_copper_domain_value_chain_image",
        "main.open_pit_copper_domain_digital_enablement_image",
        "main.open_pit_copper_domain_service_map_image",
        "main.open_pit_copper_domain_measurement_hierarchy_image",
        "main.open_pit_copper_domain_pa_process_image",
        "reference.index",
        "reference.fmi_kyc",
        "reference.background",
        "content.content_view",
        "content.download_attachment",
        "content.attachment_preview_pdf",
        "content.attachment_preview_xlsx_html",
        "content.attachment_slide_image",
        "content.attachment_preview_slides",
        "content.attachment_preview_pptx_html",
        "content.attachment_pptx_asset",
        "content.attachment_preview_docx_html",
        "content.office_attachment_source",
        "static",
    }
)


def is_guest_user(user) -> bool:
    if not user:
        return False
    return (user["role"] or "").strip().lower() == "guest"


def guest_may_visit_path(path: str | None) -> bool:
    """True when a relative URL resolves to an endpoint on the guest allowlist."""
    from flask import current_app
    from werkzeug.exceptions import MethodNotAllowed, NotFound

    from mine.auth_utils import safe_login_next

    target = safe_login_next(path)
    if not target:
        return False
    path_only = target.split("?", 1)[0]
    try:
        endpoint, _ = current_app.url_map.bind("").match(path_only)
    except (NotFound, MethodNotAllowed):
        return False
    except Exception:
        return False
    if not endpoint:
        return False
    if endpoint.startswith("static"):
        return True
    return endpoint in GUEST_ALLOWED_ENDPOINTS


def ensure_users_guest_role(db=None) -> None:
    """Allow role='guest' on existing SQLite DBs that still have the old CHECK."""
    db = db or get_db()
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    sql = (row[0] if row else "") or ""
    if "guest" in sql.lower():
        return

    db.execute("PRAGMA foreign_keys = OFF")
    db.executescript(
        """
        CREATE TABLE users__guest_mig (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          role TEXT CHECK(role IN ('admin','moderator','user','guest')) DEFAULT 'user',
          is_active INTEGER DEFAULT 1,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO users__guest_mig (
          id, username, email, password_hash, display_name, role, is_active, created_at
        )
        SELECT id, username, email, password_hash, display_name, role, is_active, created_at
        FROM users;
        DROP TABLE users;
        ALTER TABLE users__guest_mig RENAME TO users;
        """
    )
    db.execute("PRAGMA foreign_keys = ON")
    db.commit()


def ensure_guest_user(db=None) -> None:
    """Create the shared Guest account if missing."""
    db = db or get_db()
    ensure_users_guest_role(db)
    existing = db.execute(
        "SELECT id, role FROM users WHERE lower(trim(username)) = ?",
        (GUEST_USERNAME,),
    ).fetchone()
    if existing:
        if (existing["role"] or "").strip().lower() != "guest":
            db.execute(
                "UPDATE users SET role = 'guest', is_active = 1, display_name = ? WHERE id = ?",
                (GUEST_DISPLAY_NAME, existing["id"]),
            )
            db.commit()
        return
    # Unusable password — guest signs in only via Login as Guest.
    pw_hash = bcrypt.hashpw(b"__guest_no_password__", bcrypt.gensalt()).decode("utf-8")
    db.execute(
        """
        INSERT INTO users (username, email, password_hash, display_name, role, is_active)
        VALUES (?, ?, ?, ?, 'guest', 1)
        """,
        (GUEST_USERNAME, GUEST_EMAIL, pw_hash, GUEST_DISPLAY_NAME),
    )
    db.commit()
