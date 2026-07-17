"""Keep content_fts in sync and repair broken indexes/triggers."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Standalone FTS5 index (stores its own column values). Do NOT use content='content'
# — that mode requires a matching tags column on the content table, which we do not have.
_FTS_CREATE_SQL = """
CREATE VIRTUAL TABLE content_fts USING fts5(
  title,
  summary,
  body,
  tags,
  tokenize = 'porter unicode61'
);
"""

# Use DELETE FROM … WHERE rowid=… — the FTS5 INSERT 'delete' command raises
# "SQL logic error" on some SQLite builds (observed with 3.43.x on Windows/Azure).
_TRIGGER_SQL = """
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
"""


def _fts_definition(db) -> str:
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'content_fts'"
    ).fetchone()
    if not row:
        return ""
    return (row[0] if not isinstance(row, sqlite3.Row) else row["sql"]) or ""


def _fts_is_broken(db) -> bool:
    """True when FTS is missing, uses external content, or cannot be queried."""
    sql = _fts_definition(db).lower().replace(" ", "")
    if not sql:
        return True
    if "content='content'" in sql or 'content="content"' in sql:
        return True
    try:
        db.execute("SELECT COUNT(*) FROM content_fts").fetchone()
    except sqlite3.Error:
        return True
    return False


def _triggers_use_legacy_delete(db) -> bool:
    """True when content_au still uses the broken INSERT … 'delete' command."""
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'content_au'"
    ).fetchone()
    if not row:
        return True
    sql = (row[0] if not isinstance(row, sqlite3.Row) else row["sql"]) or ""
    return "values('delete'" in sql.lower().replace(" ", "") or "'delete'" in sql.lower()


def _fts_update_probe_fails(db) -> bool:
    """True when updating a content row fails (usually a bad FTS trigger)."""
    row = db.execute("SELECT id FROM content ORDER BY id LIMIT 1").fetchone()
    if not row:
        return False
    cid = int(row[0])
    try:
        db.execute("SAVEPOINT fts_update_probe")
        db.execute("UPDATE content SET title = title WHERE id = ?", (cid,))
        db.execute("ROLLBACK TO fts_update_probe")
        db.execute("RELEASE fts_update_probe")
        return False
    except sqlite3.Error:
        try:
            db.execute("ROLLBACK TO fts_update_probe")
        except sqlite3.Error:
            pass
        try:
            db.execute("RELEASE fts_update_probe")
        except sqlite3.Error:
            pass
        return True


def rebuild_content_fts(db, content_id: int) -> None:
    """Re-index one content row (call after tag / attachment metadata changes)."""
    row = db.execute(
        """
        SELECT id, coalesce(title,''), coalesce(summary,''), coalesce(body,'')
        FROM content WHERE id = ?
        """,
        (content_id,),
    ).fetchone()
    try:
        db.execute("DELETE FROM content_fts WHERE rowid = ?", (content_id,))
        if not row:
            return
        tags = db.execute(
            "SELECT coalesce(group_concat(meta_value, ' '), '') FROM content_meta "
            "WHERE content_id = ? AND meta_key = 'tag'",
            (content_id,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO content_fts(rowid, title, summary, body, tags) VALUES (?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], tags or ""),
        )
    except sqlite3.Error:
        logger.exception("rebuild_content_fts failed for content #%s", content_id)


def rebuild_all_content_fts(db) -> int:
    """Re-index every content row. Returns number of rows indexed."""
    try:
        db.execute("DELETE FROM content_fts")
    except sqlite3.Error:
        # Fallback if DELETE FROM is unsupported on a broken index
        try:
            db.execute("INSERT INTO content_fts(content_fts) VALUES('delete-all')")
        except sqlite3.Error:
            pass
    rows = db.execute(
        "SELECT id, coalesce(title,''), coalesce(summary,''), coalesce(body,'') FROM content"
    ).fetchall()
    n = 0
    for row in rows:
        cid = int(row[0])
        tags = db.execute(
            "SELECT coalesce(group_concat(meta_value, ' '), '') FROM content_meta "
            "WHERE content_id = ? AND meta_key = 'tag'",
            (cid,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO content_fts(rowid, title, summary, body, tags) VALUES (?, ?, ?, ?, ?)",
            (cid, row[1], row[2], row[3], tags or ""),
        )
        n += 1
    return n


def _install_fts_triggers(db) -> None:
    db.execute("DROP TRIGGER IF EXISTS content_ai")
    db.execute("DROP TRIGGER IF EXISTS content_ad")
    db.execute("DROP TRIGGER IF EXISTS content_au")
    db.executescript(_TRIGGER_SQL)


def ensure_content_fts(db) -> None:
    """
    Ensure content_fts is a healthy standalone index with working UPDATE triggers.
    Safe to call on every app startup.
    """
    needs_rebuild = False

    if _fts_is_broken(db):
        logger.warning("Repairing content_fts full-text index (broken or external-content schema)")
        db.execute("DROP TRIGGER IF EXISTS content_ai")
        db.execute("DROP TRIGGER IF EXISTS content_ad")
        db.execute("DROP TRIGGER IF EXISTS content_au")
        db.execute("DROP TABLE IF EXISTS content_fts")
        for name in (
            "content_fts_data",
            "content_fts_idx",
            "content_fts_docsize",
            "content_fts_config",
            "content_fts_content",
        ):
            try:
                db.execute(f"DROP TABLE IF EXISTS {name}")
            except sqlite3.Error:
                pass
        db.executescript(_FTS_CREATE_SQL)
        needs_rebuild = True

    # Replace legacy INSERT … 'delete' triggers (they 500 on approve/update).
    if _triggers_use_legacy_delete(db) or _fts_update_probe_fails(db):
        logger.warning("Repairing content_fts triggers so content UPDATE/approve works")
        db.execute("DROP TRIGGER IF EXISTS content_ai")
        db.execute("DROP TRIGGER IF EXISTS content_ad")
        db.execute("DROP TRIGGER IF EXISTS content_au")
        needs_rebuild = True

    _install_fts_triggers(db)

    if not needs_rebuild:
        try:
            fts_n = int(db.execute("SELECT COUNT(*) AS c FROM content_fts").fetchone()[0] or 0)
            content_n = int(db.execute("SELECT COUNT(*) AS c FROM content").fetchone()[0] or 0)
            if content_n and fts_n < content_n:
                needs_rebuild = True
        except sqlite3.Error:
            needs_rebuild = True

    # Final probe with new triggers installed
    if _fts_update_probe_fails(db):
        logger.warning("content UPDATE still failing — rebuilding content_fts from scratch")
        db.execute("DROP TRIGGER IF EXISTS content_ai")
        db.execute("DROP TRIGGER IF EXISTS content_ad")
        db.execute("DROP TRIGGER IF EXISTS content_au")
        db.execute("DROP TABLE IF EXISTS content_fts")
        db.executescript(_FTS_CREATE_SQL)
        _install_fts_triggers(db)
        needs_rebuild = True

    if needs_rebuild:
        n = rebuild_all_content_fts(db)
        db.commit()
        logger.info("content_fts rebuilt for %s content row(s)", n)
    else:
        db.commit()
