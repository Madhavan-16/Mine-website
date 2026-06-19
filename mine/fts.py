"""Keep FTS index in sync when tags (content_meta) change without touching content row."""


def rebuild_content_fts(db, content_id: int):
    row = db.execute(
        """
        SELECT id, coalesce(title,''), coalesce(summary,''), coalesce(body,'')
        FROM content WHERE id = ?
        """,
        (content_id,),
    ).fetchone()
    if not row:
        db.execute("INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags) VALUES('delete', ?, '', '', '', '')", (content_id,))
        return
    tags = db.execute(
        "SELECT coalesce(group_concat(meta_value, ' '), '') FROM content_meta WHERE content_id = ? AND meta_key = 'tag'",
        (content_id,),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO content_fts(content_fts, rowid, title, summary, body, tags) VALUES('delete', ?, '', '', '', '')",
        (content_id,),
    )
    db.execute(
        "INSERT INTO content_fts(rowid, title, summary, body, tags) VALUES (?, ?, ?, ?, ?)",
        (row[0], row[1], row[2], row[3], tags or ""),
    )
