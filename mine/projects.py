from flask import Blueprint, render_template, request

from mine.auth_utils import login_required
from mine.content import run_project_create, run_project_edit
from mine.db import get_db
from mine.project_catalog import PROJECT_SECTION_ICONS, PROJECT_SECTIONS, enrich_project_rows

bp = Blueprint("projects", __name__)


@bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_create():
    return run_project_create()


@bp.route("/projects/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def project_edit(cid: int):
    return run_project_edit(cid)


@bp.route("/projects")
@login_required
def project_list():
    program = (request.args.get("program") or "").strip()
    status = (request.args.get("status") or "").strip()
    region = (request.args.get("region") or "").strip()
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "recent").strip()
    db = get_db()

    program_options = [
        r["n"]
        for r in db.execute(
            """
            SELECT DISTINCT trim(p.program_name) AS n
            FROM projects p
            JOIN content c ON c.id = p.content_id
            WHERE c.status = 'approved' AND c.module = 'projects'
              AND p.program_name IS NOT NULL AND trim(p.program_name) != ''
            ORDER BY n COLLATE NOCASE
            """
        ).fetchall()
        if r["n"]
    ]

    status_options = [
        r["n"]
        for r in db.execute(
            """
            SELECT DISTINCT trim(p.delivery_status) AS n
            FROM projects p
            JOIN content c ON c.id = p.content_id
            WHERE c.status = 'approved' AND c.module = 'projects'
              AND p.delivery_status IS NOT NULL AND trim(p.delivery_status) != ''
            ORDER BY n COLLATE NOCASE
            """
        ).fetchall()
        if r["n"]
    ]

    sql = """
        SELECT c.*, u.display_name AS author_name,
               p.program_name, p.project_manager, p.delivery_status,
               (SELECT meta_value FROM content_meta m WHERE m.content_id = c.id AND m.meta_key = 'region' LIMIT 1) AS region
        FROM content c
        JOIN users u ON u.id = c.author_id
        JOIN projects p ON p.content_id = c.id
        WHERE c.module = 'projects' AND c.status = 'approved'
    """
    args: list = []
    if program:
        sql += " AND trim(p.program_name) = ?"
        args.append(program)
    if status:
        sql += " AND trim(p.delivery_status) = ?"
        args.append(status)
    if region:
        sql += " AND EXISTS (SELECT 1 FROM content_meta m WHERE m.content_id = c.id AND m.meta_key = 'region' AND m.meta_value LIKE ?)"
        args.append(f"%{region}%")
    if q:
        sql += " AND (c.title LIKE ? OR COALESCE(c.summary,'') LIKE ?)"
        like = f"%{q}%"
        args.extend([like, like])
    if sort == "alpha":
        sql += " ORDER BY c.title COLLATE NOCASE ASC"
    else:
        sql += " ORDER BY c.updated_at DESC"
    rows = db.execute(sql, args).fetchall()
    enriched = enrich_project_rows(rows)
    if q:
        ql = q.lower()
        enriched = [
            r
            for r in enriched
            if ql in (r.get("title") or "").lower()
            or ql in (r.get("summary") or "").lower()
        ]
    if sort == "alpha":
        enriched.sort(key=lambda r: (r.get("title") or "").lower())
    return render_template(
        "projects/list.html",
        rows=enriched,
        project_sections=PROJECT_SECTIONS,
        project_section_icons=PROJECT_SECTION_ICONS,
        program=program,
        status=status,
        region=region,
        q=q,
        sort=sort,
        program_options=program_options,
        status_options=status_options,
    )


@bp.route("/projects/<int:cid>")
@login_required
def project_detail(cid: int):
    from flask import abort

    from mine.auth_utils import load_current_user
    from mine.services import content_visible

    user = load_current_user()
    db = get_db()
    row = db.execute(
        """
        SELECT c.*, u.display_name AS author_name,
               p.program_name, p.project_manager, p.delivery_status
        FROM content c
        JOIN users u ON u.id = c.author_id
        JOIN projects p ON p.content_id = c.id
        WHERE c.id = ? AND c.module = 'projects'
        """,
        (cid,),
    ).fetchone()
    if not row or not content_visible(user, row):
        abort(404)
    region = db.execute(
        "SELECT meta_value FROM content_meta WHERE content_id = ? AND meta_key = 'region' LIMIT 1",
        (cid,),
    ).fetchone()
    files = db.execute(
        "SELECT * FROM attachments WHERE content_id = ? ORDER BY id DESC", (cid,)
    ).fetchall()
    ds = (row["delivery_status"] or "").lower()
    status_class = "status-dot--risk" if "risk" in ds or "amber" in ds or "yellow" in ds else "status-dot--ok"
    if not row["delivery_status"]:
        status_class = "status-dot--na"
    from mine.content import _attachment_manage_href

    return render_template(
        "projects/detail.html",
        row=row,
        region=region["meta_value"] if region else "",
        files=files,
        status_class=status_class,
        attachment_manage_url=_attachment_manage_href(user, row),
    )
