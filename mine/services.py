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
    """Personal notification — visible only to the given user account."""
    db = get_db()
    db.execute(
        """
        INSERT INTO notifications (user_id, message, scope)
        VALUES (?, ?, 'personal')
        """,
        (user_id, message),
    )


def notify_common(message: str):
    """Broadcast notification — visible to every signed-in account."""
    db = get_db()
    db.execute(
        """
        INSERT INTO notifications (user_id, message, scope)
        VALUES (NULL, ?, 'common')
        """,
        (message,),
    )


def _visible_notifications_sql():
    return """
        SELECT
            n.id,
            n.message,
            n.scope,
            n.created_at,
            CASE
                WHEN n.scope = 'common' THEN COALESCE(s.is_read, 0)
                ELSE n.is_read
            END AS is_read
        FROM notifications n
        LEFT JOIN notification_user_state s
            ON n.scope = 'common'
           AND s.notification_id = n.id
           AND s.user_id = ?
        WHERE (n.scope = 'personal' AND n.user_id = ?)
           OR (n.scope = 'common' AND COALESCE(s.is_cleared, 0) = 0)
        ORDER BY n.id DESC
        LIMIT ?
    """


def get_user_notifications(user_id: int, *, limit: int = 6):
    db = get_db()
    return db.execute(_visible_notifications_sql(), (user_id, user_id, limit)).fetchall()


def count_unread_notifications(user_id: int) -> int:
    db = get_db()
    row = db.execute(
        """
        SELECT COUNT(*) AS c FROM (
            SELECT n.id
            FROM notifications n
            WHERE n.scope = 'personal' AND n.user_id = ? AND n.is_read = 0
            UNION ALL
            SELECT n.id
            FROM notifications n
            LEFT JOIN notification_user_state s
                ON s.notification_id = n.id AND s.user_id = ?
            WHERE n.scope = 'common'
              AND COALESCE(s.is_cleared, 0) = 0
              AND COALESCE(s.is_read, 0) = 0
        )
        """,
        (user_id, user_id),
    ).fetchone()
    return int(row["c"] or 0)


def count_read_notifications(user_id: int) -> int:
    db = get_db()
    row = db.execute(
        """
        SELECT COUNT(*) AS c FROM (
            SELECT n.id
            FROM notifications n
            WHERE n.scope = 'personal' AND n.user_id = ? AND n.is_read = 1
            UNION ALL
            SELECT n.id
            FROM notifications n
            INNER JOIN notification_user_state s
                ON s.notification_id = n.id AND s.user_id = ?
            WHERE n.scope = 'common'
              AND COALESCE(s.is_cleared, 0) = 0
              AND s.is_read = 1
        )
        """,
        (user_id, user_id),
    ).fetchone()
    return int(row["c"] or 0)


def _upsert_common_state(db, notification_id: int, user_id: int, *, is_read: int | None = None, is_cleared: int | None = None):
    db.execute(
        """
        INSERT INTO notification_user_state (notification_id, user_id, is_read, is_cleared)
        VALUES (?, ?, COALESCE(?, 0), COALESCE(?, 0))
        ON CONFLICT(notification_id, user_id) DO UPDATE SET
            is_read = CASE WHEN ? IS NOT NULL THEN ? ELSE notification_user_state.is_read END,
            is_cleared = CASE WHEN ? IS NOT NULL THEN ? ELSE notification_user_state.is_cleared END
        """,
        (
            notification_id,
            user_id,
            is_read,
            is_cleared,
            is_read,
            is_read,
            is_cleared,
            is_cleared,
        ),
    )


def mark_all_notifications_read(user_id: int):
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND scope = 'personal'",
        (user_id,),
    )
    common_rows = db.execute("SELECT id FROM notifications WHERE scope = 'common'").fetchall()
    for row in common_rows:
        _upsert_common_state(db, int(row["id"]), user_id, is_read=1)


def clear_notification(user_id: int, notification_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT id, scope, user_id, is_read FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    if not row:
        return False
    if row["scope"] == "personal":
        if int(row["user_id"]) != user_id or not row["is_read"]:
            return False
        db.execute("DELETE FROM notifications WHERE id = ? AND user_id = ?", (notification_id, user_id))
        return True
    state = db.execute(
        """
        SELECT is_read FROM notification_user_state
        WHERE notification_id = ? AND user_id = ?
        """,
        (notification_id, user_id),
    ).fetchone()
    if not state or not state["is_read"]:
        return False
    _upsert_common_state(db, notification_id, user_id, is_cleared=1)
    return True


def clear_all_read_notifications(user_id: int):
    db = get_db()
    db.execute(
        "DELETE FROM notifications WHERE user_id = ? AND scope = 'personal' AND is_read = 1",
        (user_id,),
    )
    common_read = db.execute(
        """
        SELECT notification_id
        FROM notification_user_state
        WHERE user_id = ? AND is_read = 1 AND is_cleared = 0
        """,
        (user_id,),
    ).fetchall()
    for row in common_read:
        _upsert_common_state(db, int(row["notification_id"]), user_id, is_cleared=1)


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
