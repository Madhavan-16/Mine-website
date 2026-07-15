"""Keep content_fts in sync and repair broken external-content indexes."""

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
  INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags)
  VALUES('delete', old.id, coalesce(old.title, ''), coalesce(old.summary, ''), coalesce(old.body, ''), '');
END;

CREATE TRIGGER IF NOT EXISTS content_au AFTER UPDATE ON content BEGIN
  INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags)
  VALUES('delete', old.id, coalesce(old.title, ''), coalesce(old.summary, ''), coalesce(old.body, ''), '');
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
        if not row:
            db.execute(
                "INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags) "
                "VALUES('delete', ?, '', '', '', '')",
                (content_id,),
            )
            return
        tags = db.execute(
            "SELECT coalesce(group_concat(meta_value, ' '), '') FROM content_meta "
            "WHERE content_id = ? AND meta_key = 'tag'",
            (content_id,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags) "
            "VALUES('delete', ?, '', '', '', '')",
            (content_id,),
        )
        db.execute(
            "INSERT INTO content_fts(rowid, title, summary, body, tags) VALUES (?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], tags or ""),
        )
    except sqlite3.Error:
        logger.exception("rebuild_content_fts failed for content #%s", content_id)


def rebuild_all_content_fts(db) -> int:
    """Re-index every content row. Returns number of rows indexed."""
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
        try:
            db.execute(
                "INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags) "
                "VALUES('delete', ?, '', '', '', '')",
                (cid,),
            )
        except sqlite3.Error:
            pass
        db.execute(
            "INSERT INTO content_fts(rowid, title, summary, body, tags) VALUES (?, ?, ?, ?, ?)",
            (cid, row[1], row[2], row[3], tags or ""),
        )
        n += 1
    return n


def ensure_content_fts(db) -> None:
    """
    Ensure content_fts is a healthy standalone index and rebuild if needed.
    Safe to call on every app startup.
    """
    needs_rebuild = False
    if _fts_is_broken(db):
        logger.warning("Repairing content_fts full-text index (broken or external-content schema)")
        db.execute("DROP TABLE IF EXISTS content_fts")
        # Drop orphaned fts5 shadow tables if any linger with old names
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
        db.execute("DROP TRIGGER IF EXISTS content_ai")
        db.execute("DROP TRIGGER IF EXISTS content_ad")
        db.execute("DROP TRIGGER IF EXISTS content_au")
        db.executescript(_FTS_CREATE_SQL)
        db.executescript(_TRIGGER_SQL)
        needs_rebuild = True
    else:
        # Index may be empty after bulk imports that skipped triggers
        try:
            fts_n = int(db.execute("SELECT COUNT(*) AS c FROM content_fts").fetchone()[0] or 0)
            content_n = int(db.execute("SELECT COUNT(*) AS c FROM content").fetchone()[0] or 0)
            if content_n and fts_n < content_n:
                needs_rebuild = True
        except sqlite3.Error:
            needs_rebuild = True

    if needs_rebuild:
        n = rebuild_all_content_fts(db)
        db.commit()
        logger.info("content_fts rebuilt for %s content row(s)", n)
