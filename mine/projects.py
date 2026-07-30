from flask import Blueprint, flash, redirect, render_template, request, url_for

from mine.auth_utils import login_required, roles_required
from mine.content import run_project_create, run_project_edit
from mine.db import get_db
from mine.project_catalog import (
    PROJECT_SECTION_ICONS,
    PROJECT_SECTIONS,
    build_portfolio_viz,
    enrich_project_rows,
    filter_projects_by_active,
    project_is_active,
    set_catalog_project_active,
    set_db_project_active,
)

bp = Blueprint("projects", __name__)


@bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_create():
    return run_project_create()


@bp.route("/projects/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def project_edit(cid: int):
    return run_project_edit(cid)


@bp.route("/projects/toggle-active", methods=["POST"])
@login_required
@roles_required("admin", "moderator")
def toggle_project_active():
    next_url = (request.form.get("next") or "").strip()
    if not next_url.startswith("/"):
        next_url = url_for("projects.project_list")

    is_active = request.form.get("is_active") == "1"
    catalog_key = (request.form.get("catalog_key") or "").strip() or None
    title = (request.form.get("title") or "").strip() or None
    content_id_raw = (request.form.get("content_id") or "").strip()

    db = get_db()
    ok = False
    if content_id_raw.isdigit():
        ok = set_db_project_active(db, int(content_id_raw), is_active)
        if ok:
            db.commit()
    elif catalog_key or title:
        ok = set_catalog_project_active(catalog_key=catalog_key, title=title, is_active=is_active)

    if ok:
        flash(
            "Engagement marked as active." if is_active else "Engagement marked as ended (excluded from landing active-project count).",
            "success",
        )
    else:
        flash("Could not update the active flag for this project.", "danger")
    return redirect(next_url)


@bp.route("/projects")
@login_required
def project_list():
    program = (request.args.get("program") or "").strip()
    status = (request.args.get("status") or "").strip()
    region = (request.args.get("region") or "").strip()
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "recent").strip()
    active = (request.args.get("active") or "1").strip().lower()
    if active not in ("1", "0", "all"):
        active = "1"
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
               COALESCE(p.is_active, 1) AS is_active,
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
    try:
        rows = db.execute(sql, args).fetchall()
    except Exception:
        sql = sql.replace("COALESCE(p.is_active, 1) AS is_active", "1 AS is_active")
        rows = db.execute(sql, args).fetchall()
    enriched_all = enrich_project_rows(rows)
    active_count = sum(1 for r in enriched_all if project_is_active(r))
    ended_count = len(enriched_all) - active_count
    all_count = len(enriched_all)

    enriched = filter_projects_by_active(enriched_all, active)
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
    portfolio_viz = build_portfolio_viz(enriched)
    return render_template(
        "projects/list.html",
        rows=enriched,
        portfolio_viz=portfolio_viz,
        project_sections=PROJECT_SECTIONS,
        project_section_icons=PROJECT_SECTION_ICONS,
        program=program,
        status=status,
        region=region,
        q=q,
        sort=sort,
        active=active,
        active_count=active_count,
        ended_count=ended_count,
        all_count=all_count,
        program_options=program_options,
        status_options=status_options,
        project_is_active=project_is_active,
    )


@bp.route("/projects/<int:cid>")
@login_required
def project_detail(cid: int):
    from flask import abort

    from mine.auth_utils import load_current_user
    from mine.services import content_visible

    user = load_current_user()
    db = get_db()
    row = None
    try:
        row = db.execute(
            """
            SELECT c.*, u.display_name AS author_name,
                   p.program_name, p.project_manager, p.delivery_status,
                   COALESCE(p.is_active, 1) AS is_active
            FROM content c
            JOIN users u ON u.id = c.author_id
            JOIN projects p ON p.content_id = c.id
            WHERE c.id = ? AND c.module = 'projects'
            """,
            (cid,),
        ).fetchone()
    except Exception:
        row = db.execute(
            """
            SELECT c.*, u.display_name AS author_name,
                   p.program_name, p.project_manager, p.delivery_status,
                   1 AS is_active
            FROM content c
            JOIN users u ON u.id = c.author_id
            JOIN projects p ON p.content_id = c.id
            WHERE c.id = ? AND c.module = 'projects'
            """,
            (cid,),
        ).fetchone()
    if not row or not content_visible(row, user):
        abort(404)
    region_row = db.execute(
        "SELECT meta_value FROM content_meta WHERE content_id = ? AND meta_key = 'region' LIMIT 1",
        (cid,),
    ).fetchone()
    region = region_row["meta_value"] if region_row else None
    ds = (row["delivery_status"] or "").lower()
    status_class = "status-ok"
    if not row["delivery_status"]:
        status_class = "status-na"
    elif "risk" in ds or "at risk" in ds:
        status_class = "status-risk"
    return render_template(
        "projects/detail.html",
        row=row,
        region=region,
        status_class=status_class,
    )
