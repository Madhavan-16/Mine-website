import re

from flask import Blueprint, render_template, request

from mine.auth_utils import login_required
from mine.db import get_db

bp = Blueprint("search", __name__)


def _fts_query(raw: str) -> str | None:
    parts = [p for p in re.split(r"\s+", raw.strip()) if p]
    if not parts:
        return None
    cleaned = []
    for p in parts:
        p = p.replace('"', "").replace("'", "")
        if not p:
            continue
        cleaned.append(p)
    if not cleaned:
        return None
    return " AND ".join(f'"{t}"' for t in cleaned)


@bp.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    module = (request.args.get("module") or "").strip() or None
    rows = []
    if q:
        fts = _fts_query(q)
        db = get_db()
        if fts:
            sql = """
                SELECT c.*, u.display_name AS author_name,
                       bm25(content_fts) AS rank
                FROM content_fts
                JOIN content c ON c.id = content_fts.rowid
                JOIN users u ON u.id = c.author_id
                WHERE content_fts MATCH ?
                  AND c.status = 'approved'
            """
            args: list = [fts]
            if module:
                sql += " AND c.module = ?"
                args.append(module)
            sql += " ORDER BY rank LIMIT 50"
            try:
                rows = db.execute(sql, args).fetchall()
            except Exception:
                rows = []
    return render_template("search.html", q=q, module=module, rows=rows)
