from mine.db import get_db


def log_audit(user_id, action, entity_type=None, entity_id=None, detail=None):
    db = get_db()
    db.execute(
        """
        INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, action, entity_type, entity_id, detail),
    )


def notify(user_id: int, message: str):
    db = get_db()
    db.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, message),
    )


def moderation_entry(content_id, performed_by, action, note=None):
    db = get_db()
    db.execute(
        """
        INSERT INTO moderation_log (content_id, action, performed_by, note)
        VALUES (?, ?, ?, ?)
        """,
        (content_id, action, performed_by, note),
    )


def get_tags(content_id: int):
    rows = get_db().execute(
        "SELECT meta_value FROM content_meta WHERE content_id = ? AND meta_key = 'tag' ORDER BY id",
        (content_id,),
    ).fetchall()
    return [r["meta_value"] for r in rows]


def set_tags(db, content_id: int, tags_csv: str):
    db.execute("DELETE FROM content_meta WHERE content_id = ? AND meta_key = 'tag'", (content_id,))
    for raw in (tags_csv or "").split(","):
        t = raw.strip()
        if t:
            db.execute(
                "INSERT INTO content_meta (content_id, meta_key, meta_value) VALUES (?, 'tag', ?)",
                (content_id, t),
            )


def content_visible(user, row) -> bool:
    if not row:
        return False
    if row["status"] == "approved":
        return True
    if not user:
        return False
    if user["role"] in ("admin", "moderator"):
        return True
    return row["author_id"] == user["id"]
