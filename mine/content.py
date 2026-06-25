import ipaddress
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    has_request_context,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from itsdangerous import BadSignature, URLSafeTimedSerializer
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from mine.auth_utils import load_current_user, login_required, roles_required
from mine.catalog_modules import (
    CASE_STUDY_MODULE,
    KNOWLEDGE_SERIES_MODULE_KEYS,
    KNOWLEDGE_SERIES_MODULES,
    STANDALONE_MODULE_TO_SEGMENT,
    STANDALONE_REPO_MODULES,
    STANDALONE_REPO_UI,
)
from mine.config import Config
from mine.db import get_db
from mine.fts import rebuild_content_fts
from mine.services import (
    content_visible,
    get_tags,
    log_audit,
    moderation_entry,
    notify,
    set_tags,
)
from mine.upload_extract import suggest_from_upload
from mine.upload_paths import resolve_stored_upload_path

bp = Blueprint("content", __name__)

_OFFICE_PREVIEW_MAX_AGE = 15 * 60
_OFFICE_PREVIEW_SALT = "mine-attachment-office-preview-v1"

_ALLOWED_UPLOAD_EXTS = sorted(Config.ALLOWED_EXTENSIONS)


def _office_preview_serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt=_OFFICE_PREVIEW_SALT)


def _office_cloud_can_fetch_document_url(file_url: str) -> bool:
    """Office Online fetches this URL from Microsoft's servers; localhost/http/private IPs cannot work."""
    try:
        parsed = urlparse(file_url)
    except Exception:
        return False
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost":
        return False
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_loopback or addr.is_private or addr.is_link_local:
            return False
        if getattr(addr, "is_reserved", False):
            return False
    except ValueError:
        pass
    return True


def _knowledge_series_form_choices(current_module: str | None) -> list[tuple[str, str]]:
    choices = list(KNOWLEDGE_SERIES_MODULES)
    mod = (current_module or "").strip()
    if mod and mod not in KNOWLEDGE_SERIES_MODULE_KEYS:
        choices.append((mod, mod.replace("_", " ").title()))
    return choices



class ContentForm(FlaskForm):
    module = SelectField(
        "Knowledge series",
        choices=[],
        validators=[DataRequired()],
    )
    title = StringField("Title", validators=[DataRequired(), Length(max=500)], render_kw={"id": "title"})
    summary = TextAreaField(
        "Summary", validators=[Optional(), Length(max=2000)], render_kw={"id": "summary", "rows": 5}
    )
    body = TextAreaField("Body", validators=[Optional()], render_kw={"id": "body"})
    business_challenge = TextAreaField(
        "Business challenge",
        validators=[Optional()],
        render_kw={"id": "business_challenge", "rows": 6},
    )
    solution = TextAreaField(
        "Solution",
        validators=[Optional()],
        render_kw={"id": "solution", "rows": 6},
    )
    tags = StringField("Tags (comma-separated)", validators=[Optional(), Length(max=500)])
    attachment = FileField(
        "Attachment",
        validators=[Optional(), FileAllowed(_ALLOWED_UPLOAD_EXTS, "Invalid file type.")],
        render_kw={"id": "content-attachment-field"},
    )


class StandaloneRepoForm(FlaskForm):
    """Articles for onboarding, innovation, training, or hall_of_fame (fixed module outside this form)."""

    title = StringField("Title", validators=[DataRequired(), Length(max=500)], render_kw={"id": "title"})
    summary = TextAreaField(
        "Summary", validators=[Optional(), Length(max=2000)], render_kw={"id": "summary", "rows": 5}
    )
    body = TextAreaField("Body", validators=[Optional()], render_kw={"id": "body"})
    tags = StringField("Tags (comma-separated)", validators=[Optional(), Length(max=500)])
    attachment = FileField(
        "Attachment",
        validators=[Optional(), FileAllowed(_ALLOWED_UPLOAD_EXTS, "Invalid file type.")],
        render_kw={"id": "content-attachment-field"},
    )


class ProjectContentForm(FlaskForm):
    """Create/edit Programs &amp; projects records (content.module is always <code>projects</code>)."""

    title = StringField("Project name", validators=[DataRequired(), Length(max=500)], render_kw={"id": "title"})
    summary = TextAreaField(
        "Summary", validators=[Optional(), Length(max=2000)], render_kw={"id": "summary", "rows": 5}
    )
    body = TextAreaField(
        "Description / context (optional)", validators=[Optional()], render_kw={"id": "body"}
    )
    tags = StringField("Tags (comma-separated)", validators=[Optional(), Length(max=500)])
    program_name = StringField("Program name", validators=[Optional(), Length(max=200)])
    project_manager = StringField("Project manager", validators=[Optional(), Length(max=200)])
    delivery_status = StringField("Delivery status", validators=[Optional(), Length(max=120)])
    region = StringField("Region", validators=[Optional(), Length(max=120)])
    attachment = FileField(
        "Attachment (optional)",
        validators=[Optional(), FileAllowed(_ALLOWED_UPLOAD_EXTS, "Invalid file type.")],
        render_kw={"id": "content-attachment-field"},
    )


def _project_field_specs() -> list[tuple[str, str]]:
    return [
        ("program_name", "Program name"),
        ("project_manager", "Project manager"),
        ("delivery_status", "Delivery status"),
        ("region", "Region"),
    ]


def _project_fields_filled_for_submit(form) -> list[str]:
    """Error messages for missing program/project fields when user clicks Submit for review."""
    out: list[str] = []
    for field_name, label in _project_field_specs():
        if not hasattr(form, field_name):
            continue
        raw = (getattr(form, field_name).data or "").strip()
        if not raw:
            out.append(
                f"{label} is required when you submit for review, or use Save draft to add it later."
            )
    return out


def _str_or_none(s: str) -> str | None:
    t = (s or "").strip()
    return t or None


def _content_summary_body_from_form(form, module: str) -> tuple[str | None, str | None]:
    if module == CASE_STUDY_MODULE:
        return _str_or_none(form.business_challenge.data), _str_or_none(form.solution.data)
    return _str_or_none(form.summary.data), _str_or_none(form.body.data)


def _case_study_submit_errors(form, action: str) -> list[str]:
    if action != "submit":
        return []
    out: list[str] = []
    if not _str_or_none(form.business_challenge.data):
        out.append("Business challenge is required when you submit for review, or use Save draft to add it later.")
    if not _str_or_none(form.solution.data):
        out.append("Solution is required when you submit for review, or use Save draft to add it later.")
    return out


def _populate_case_study_form_fields(form, row) -> None:
    if (row["module"] or "").strip() != CASE_STUDY_MODULE:
        return
    form.business_challenge.data = row["summary"] or ""
    form.solution.data = row["body"] or ""


def _insert_new_content_from_form(user, form, module: str) -> int:
    action = (request.form.get("action") or "draft").strip()
    status = "pending" if action == "submit" else "draft"
    title = (form.title.data or "").strip()
    summary, body = _content_summary_body_from_form(form, module)
    tags = form.tags.data or ""
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO content (module, title, summary, body, status, author_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (module, title, summary, body, status, user["id"]),
    )
    cid = cur.lastrowid
    set_tags(db, cid, tags)
    rebuild_content_fts(db, cid)
    if module == "projects":
        db.execute(
            """
            INSERT INTO projects (content_id, program_name, project_manager, delivery_status)
            VALUES (?, ?, ?, ?)
            """,
            (
                cid,
                _str_or_none(getattr(form, "program_name").data),
                _str_or_none(getattr(form, "project_manager").data),
                _str_or_none(getattr(form, "delivery_status").data),
            ),
        )
        reg = (getattr(form, "region").data or "").strip()
        if reg:
            db.execute(
                "INSERT INTO content_meta (content_id, meta_key, meta_value) VALUES (?, 'region', ?)",
                (cid, reg),
            )
    att = form.attachment.data
    if att and att.filename:
        _insert_attachment_from_upload(db, cid, att)
    moderation_entry(cid, user["id"], "create", None)
    log_audit(user["id"], "content_create", "content", cid, status)
    if status == "pending":
        moderation_entry(cid, user["id"], "submit", None)
        _notify_moderators(f"New submission pending review: #{cid} — {title}")
    return cid


def _update_from_form(
    user,
    old_row,
    cid: int,
    form,
    *,
    module: str,
) -> bool:
    """
    Returns True on success, False if validation failed.
    For projects + submit, program/project fields are required.
    """
    action = (request.form.get("action") or "draft").strip()
    if old_row["status"] in ("draft", "rejected"):
        new_status = "pending" if action == "submit" else "draft"
    else:
        new_status = old_row["status"]
    if module == "projects" and action == "submit":
        perrs = _project_fields_filled_for_submit(form)
        if perrs:
            for m in perrs:
                flash(m, "danger")
            return False
    title = (form.title.data or "").strip()
    summary, body = _content_summary_body_from_form(form, module)
    db = get_db()
    db.execute(
        """
        UPDATE content
        SET module = ?, title = ?, summary = ?, body = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (module, title, summary, body, new_status, cid),
    )
    set_tags(db, cid, form.tags.data or "")
    rebuild_content_fts(db, cid)
    db.execute("DELETE FROM projects WHERE content_id = ?", (cid,))
    if module == "projects":
        db.execute(
            """
            INSERT INTO projects (content_id, program_name, project_manager, delivery_status)
            VALUES (?, ?, ?, ?)
            """,
            (
                cid,
                _str_or_none(form.program_name.data),
                _str_or_none(form.project_manager.data),
                _str_or_none(form.delivery_status.data),
            ),
        )
    db.execute("DELETE FROM content_meta WHERE content_id = ? AND meta_key = 'region'", (cid,))
    reg = (getattr(form, "region", None) and (form.region.data or "").strip()) or ""
    if reg:
        db.execute(
            "INSERT INTO content_meta (content_id, meta_key, meta_value) VALUES (?, 'region', ?)",
            (cid, reg),
        )
    att = form.attachment.data
    if att and att.filename:
        _insert_attachment_from_upload(db, cid, att)
    if new_status == "pending" and old_row["status"] != "pending":
        moderation_entry(cid, user["id"], "submit", None)
        _notify_moderators(f"Submission pending review: #{cid} — {title}")
    moderation_entry(cid, user["id"], "edit", None)
    log_audit(user["id"], "content_edit", "content", cid, new_status)
    return True


def _save_upload(file_storage, upload_folder: str) -> tuple[str, str]:
    orig = file_storage.filename or "file"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", orig)
    name = f"{uuid4().hex}_{safe}"
    upload_root = Path(upload_folder).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    path = upload_root / name
    file_storage.save(str(path))
    return orig, str(path.resolve())


def _insert_attachment_from_upload(db, content_id: int, file_storage) -> None:
    """Save uploaded file, optionally build PDF + slide previews, insert attachments row."""
    upload_folder = current_app_upload_folder()
    orig, path = _save_upload(file_storage, upload_folder)
    preview_path = None
    if current_app.config.get("ENABLE_OFFICE_PDF_PREVIEW", True):
        from mine.preview_convert import convert_office_file_to_pdf

        preview_path = convert_office_file_to_pdf(path, upload_folder)
    cur = db.execute(
        """
        INSERT INTO attachments (content_id, file_name, file_path, preview_path, slide_preview_dir)
        VALUES (?, ?, ?, ?, ?)
        """,
        (content_id, orig, path, preview_path, None),
    )
    att_id = cur.lastrowid
    slide_dir = _build_slide_preview_for_attachment(att_id, path, orig, upload_folder)
    if slide_dir:
        db.execute(
            "UPDATE attachments SET slide_preview_dir = ? WHERE id = ?",
            (slide_dir, att_id),
        )


def _build_slide_preview_for_attachment(
    attachment_id: int, source_path: str, original_name: str, upload_folder: str
) -> str | None:
    if not current_app.config.get("ENABLE_SLIDE_PREVIEW", True):
        return None
    from mine.slide_preview import generate_slide_png_previews, is_slide_deck_path

    if not is_slide_deck_path(original_name or source_path):
        return None
    scale = float(current_app.config.get("SLIDE_PREVIEW_SCALE", 2.0))
    paths = generate_slide_png_previews(source_path, upload_folder, attachment_id, scale=scale)
    if not paths:
        return None
    from pathlib import Path

    return str(Path(paths[0]).parent)


def _preview_download_name(original_file_name: str) -> str:
    stem = Path(original_file_name or "attachment").stem
    return f"{stem}.pdf"


def _maybe_build_pdf_preview(db, att, source_path: str) -> str | None:
    """Generate and persist a PDF preview on first view when LibreOffice is available."""
    if not current_app.config.get("ENABLE_OFFICE_PDF_PREVIEW", True):
        return None
    from mine.preview_convert import convert_office_file_to_pdf

    preview_path = convert_office_file_to_pdf(source_path, current_app_upload_folder())
    if preview_path:
        db.execute(
            "UPDATE attachments SET preview_path = ? WHERE id = ?",
            (preview_path, att["id"]),
        )
        db.commit()
    return preview_path


def _attachment_slide_preview_dir(att) -> str | None:
    try:
        raw = att["slide_preview_dir"]
    except (TypeError, KeyError):
        raw = getattr(att, "slide_preview_dir", None)
    if not raw:
        return None
    from mine.slide_preview import list_slide_pngs

    return raw if list_slide_pngs(raw) else None


def _ensure_slide_preview_paths(db, att) -> list[str]:
    from mine.slide_preview import generate_slide_png_previews, is_slide_deck_path, list_slide_pngs

    existing_dir = _attachment_slide_preview_dir(att)
    if existing_dir:
        return list_slide_pngs(existing_dir)

    if not current_app.config.get("ENABLE_SLIDE_PREVIEW", True):
        return []

    fname = att["file_name"] or ""
    if not is_slide_deck_path(fname):
        return []

    source = resolve_stored_upload_path(att["file_path"])
    if not source:
        return []

    scale = float(current_app.config.get("SLIDE_PREVIEW_SCALE", 2.0))
    paths = generate_slide_png_previews(source, current_app_upload_folder(), att["id"], scale=scale)
    if paths:
        from pathlib import Path

        slide_dir = str(Path(paths[0]).parent)
        db.execute(
            "UPDATE attachments SET slide_preview_dir = ? WHERE id = ?",
            (slide_dir, att["id"]),
        )
        db.commit()
        return paths
    return []


def _resolved_attachment_or_404(att, key: str = "file_path") -> str:
    path = resolve_stored_upload_path(att[key])
    if not path:
        abort(404)
    return path


def _attachment_manage_href(user, row) -> str | None:
    """URL to the editor where admins/moderators can upload an attachment (None if not allowed)."""
    # load_current_user() returns sqlite3.Row — supports row["key"] but not .get()
    if not user or not row or user["role"] not in ("admin", "moderator"):
        return None
    mod = (row["module"] or "").strip()
    cid = int(row["id"])
    if mod == "projects":
        return url_for("projects.project_edit", cid=cid)
    if mod in STANDALONE_REPO_MODULES:
        seg = STANDALONE_MODULE_TO_SEGMENT[mod]
        return url_for("repo_standalone.repo_edit", segment=seg, cid=cid)
    return url_for("content.content_edit", cid=cid)


def _notify_moderators(message: str):
    db = get_db()
    rows = db.execute(
        "SELECT id FROM users WHERE role IN ('admin','moderator') AND is_active = 1"
    ).fetchall()
    for r in rows:
        notify(r["id"], message)
    try:
        from flask import current_app

        from mine.mail import notify_moderators_by_email

        notify_moderators_by_email(current_app, "MiNe — moderation notification", message)
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Moderator email notification failed", exc_info=True)


@bp.route("/content")
@login_required
def content_list():
    user = load_current_user()
    db = get_db()
    if user["role"] in ("admin", "moderator"):
        rows = db.execute(
            """
            SELECT c.*, u.display_name AS author_name
            FROM content c
            JOIN users u ON u.id = c.author_id
            ORDER BY c.updated_at DESC
            LIMIT 200
            """
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT c.*, u.display_name AS author_name
            FROM content c
            JOIN users u ON u.id = c.author_id
            WHERE c.status = 'approved'
            ORDER BY c.updated_at DESC
            LIMIT 200
            """,
        ).fetchall()
    return render_template("content/list.html", rows=rows)


@bp.route("/content/<int:cid>")
@login_required
def content_view(cid: int):
    user = load_current_user()
    db = get_db()
    row = db.execute(
        """
        SELECT c.*, u.display_name AS author_name, u.email AS author_email
        FROM content c
        JOIN users u ON u.id = c.author_id
        WHERE c.id = ?
        """,
        (cid,),
    ).fetchone()
    if not row or not content_visible(user, row):
        abort(404)
    project = db.execute("SELECT * FROM projects WHERE content_id = ?", (cid,)).fetchone()
    files = db.execute(
        "SELECT * FROM attachments WHERE content_id = ? ORDER BY id DESC", (cid,)
    ).fetchall()
    region_row = db.execute(
        "SELECT meta_value FROM content_meta WHERE content_id = ? AND meta_key = 'region' LIMIT 1",
        (cid,),
    ).fetchone()
    project_region = (region_row["meta_value"] or "").strip() if region_row else ""
    related = db.execute(
        """
        SELECT c.id, c.title, c.summary, c.module, c.updated_at
        FROM content c
        WHERE c.status = 'approved' AND c.id != ? AND c.module = ?
        ORDER BY c.updated_at DESC
        LIMIT 4
        """,
        (cid, row["module"]),
    ).fetchall()
    return render_template(
        "content/view.html",
        row=row,
        project=project,
        project_region=project_region,
        files=files,
        related_rows=related,
        attachment_manage_url=_attachment_manage_href(user, row),
    )


@bp.route("/content/create", methods=["GET", "POST"])
@login_required
@roles_required("admin", "moderator")
def content_create():
    user = load_current_user()
    req_mod = (request.args.get("module") or "").strip()
    if request.method == "GET":
        if req_mod == "projects":
            return redirect(url_for("projects.project_create"))
        if req_mod in STANDALONE_REPO_MODULES:
            seg = STANDALONE_MODULE_TO_SEGMENT[req_mod]
            return redirect(url_for("repo_standalone.repo_new", segment=seg))
    form = ContentForm()
    form.module.choices = _knowledge_series_form_choices(None)
    pre = req_mod if request.method == "GET" else (form.module.data or "").strip()
    if request.method == "GET" and pre in KNOWLEDGE_SERIES_MODULE_KEYS:
        form.module.data = pre
    if form.validate_on_submit():
        mod_sl = (form.module.data or "").strip()
        if mod_sl not in KNOWLEDGE_SERIES_MODULE_KEYS:
            flash("Choose one of the knowledge-repository series.", "danger")
            return render_template("content/form.html", form=form, mode="create")
        if mod_sl == CASE_STUDY_MODULE:
            action = (request.form.get("action") or "draft").strip()
            errs = _case_study_submit_errors(form, action)
            for msg in errs:
                flash(msg, "danger")
            if errs:
                return render_template("content/form.html", form=form, mode="create")
        cid = _insert_new_content_from_form(user, form, mod_sl)
        get_db().commit()
        flash("Content saved.", "success")
        return redirect(url_for("content.content_view", cid=cid))
    if request.method == "POST" and not form.validate_on_submit():
        flash("Please fix the highlighted errors and try again.", "danger")
    return render_template("content/form.html", form=form, mode="create")


@bp.route("/content/suggest-fields", methods=["POST"])
@login_required
@roles_required("admin", "moderator")
def content_suggest_fields():
    """Read the posted attachment and return JSON title/summary/body suggestions."""
    from flask_wtf.csrf import validate_csrf

    validate_csrf(request.form.get("csrf_token"))
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="No file selected."), 400
    fname = f.filename.strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify(ok=False, error="File type is not allowed for this portal."), 400
    max_len = int(current_app.config.get("MAX_CONTENT_LENGTH") or 10 * 1024 * 1024)
    raw = f.read()
    if not raw:
        return jsonify(ok=False, error="Empty file."), 400
    if len(raw) > max_len:
        return jsonify(ok=False, error="File is too large."), 413
    try:
        module = (request.form.get("module") or "").strip()
        fields = suggest_from_upload(fname, raw, module=module)
    except Exception:
        current_app.logger.exception("suggest_from_upload failed for %s", fname)
        return jsonify(ok=False, error="Could not read this file for suggestions."), 422
    return jsonify(
        ok=True,
        title=fields["title"],
        summary=fields["summary"],
        body=fields["body"],
        business_challenge=fields.get("business_challenge", ""),
        solution=fields.get("solution", ""),
    )


def current_app_upload_folder():
    from flask import current_app

    return current_app.config["UPLOAD_FOLDER"]


@bp.route("/content/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def content_edit(cid: int):
    user = load_current_user()
    if user["role"] == "user":
        abort(403)
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row:
        abort(404)
    if row["author_id"] != user["id"] and user["role"] not in ("admin", "moderator"):
        abort(403)
    if row["status"] == "pending" and user["role"] not in ("admin", "moderator"):
        flash("You cannot edit content while it is pending review.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    if row["status"] == "approved" and user["role"] not in ("admin", "moderator"):
        flash("Approved content is read-only for contributors.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    if row["module"] == "projects":
        return redirect(url_for("projects.project_edit", cid=cid))
    if row["module"] in STANDALONE_REPO_MODULES:
        seg = STANDALONE_MODULE_TO_SEGMENT[row["module"]]
        return redirect(url_for("repo_standalone.repo_edit", segment=seg, cid=cid))
    form = ContentForm(obj=row)
    form.module.choices = _knowledge_series_form_choices(row["module"])
    form.tags.data = ", ".join(get_tags(cid))
    _populate_case_study_form_fields(form, row)
    if form.validate_on_submit():
        new_mod = (form.module.data or "").strip()
        allowed = KNOWLEDGE_SERIES_MODULE_KEYS | {(row["module"] or "").strip()}
        if new_mod not in allowed:
            flash("That module cannot be assigned from this editor.", "danger")
            return render_template("content/form.html", form=form, mode="edit", row=row)
        if new_mod == CASE_STUDY_MODULE:
            action = (request.form.get("action") or "draft").strip()
            errs = _case_study_submit_errors(form, action)
            for msg in errs:
                flash(msg, "danger")
            if errs:
                return render_template("content/form.html", form=form, mode="edit", row=row)
        if not _update_from_form(user, row, cid, form, module=new_mod):
            return render_template("content/form.html", form=form, mode="edit", row=row)
        get_db().commit()
        flash("Content updated.", "success")
        return redirect(url_for("content.content_view", cid=cid))
    if request.method == "POST" and not form.validate_on_submit():
        flash("Please fix the highlighted errors and try again.", "danger")
    return render_template("content/form.html", form=form, mode="edit", row=row)


def run_project_create():
    """Used by the projects blueprint: dedicated create form (module is always projects)."""
    user = load_current_user()
    if user["role"] == "user":
        abort(403)
    form = ProjectContentForm()
    if form.validate_on_submit():
        action = (request.form.get("action") or "draft").strip()
        if action == "submit":
            perrs = _project_fields_filled_for_submit(form)
            if perrs:
                for m in perrs:
                    flash(m, "danger")
                return render_template("projects/form.html", form=form, mode="create", row=None)
        cid = _insert_new_content_from_form(user, form, "projects")
        get_db().commit()
        flash("Program or project saved.", "success")
        return redirect(url_for("content.content_view", cid=cid))
    if request.method == "POST" and not form.validate_on_submit():
        flash("Please fix the highlighted errors and try again.", "danger")
    return render_template("projects/form.html", form=form, mode="create", row=None)


def run_project_edit(cid: int):
    """Used by the projects blueprint: edit only when content.module is already projects."""
    user = load_current_user()
    if user["role"] == "user":
        abort(403)
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row:
        abort(404)
    if row["module"] != "projects":
        return redirect(url_for("content.content_edit", cid=cid))
    if row["author_id"] != user["id"] and user["role"] not in ("admin", "moderator"):
        abort(403)
    if row["status"] == "pending" and user["role"] not in ("admin", "moderator"):
        flash("You cannot edit content while it is pending review.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    if row["status"] == "approved" and user["role"] not in ("admin", "moderator"):
        flash("Approved content is read-only for contributors.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    form = ProjectContentForm(obj=row)
    form.tags.data = ", ".join(get_tags(cid))
    proj = db.execute("SELECT * FROM projects WHERE content_id = ?", (cid,)).fetchone()
    if proj:
        form.program_name.data = proj["program_name"] or ""
        form.project_manager.data = proj["project_manager"] or ""
        form.delivery_status.data = proj["delivery_status"] or ""
    reg = db.execute(
        "SELECT meta_value FROM content_meta WHERE content_id = ? AND meta_key = 'region' LIMIT 1",
        (cid,),
    ).fetchone()
    if reg:
        form.region.data = reg["meta_value"]
    if form.validate_on_submit():
        if not _update_from_form(user, row, cid, form, module="projects"):
            return render_template("projects/form.html", form=form, mode="edit", row=row)
        get_db().commit()
        flash("Project updated.", "success")
        return redirect(url_for("content.content_view", cid=cid))
    if request.method == "POST" and not form.validate_on_submit():
        flash("Please fix the highlighted errors and try again.", "danger")
    return render_template("projects/form.html", form=form, mode="edit", row=row)


def run_standalone_repo_create(module: str):
    user = load_current_user()
    if user["role"] == "user":
        abort(403)
    if module not in STANDALONE_REPO_MODULES:
        abort(404)
    ui = STANDALONE_REPO_UI[module]
    form = StandaloneRepoForm()
    if form.validate_on_submit():
        cid = _insert_new_content_from_form(user, form, module)
        get_db().commit()
        flash(ui["create_flash"], "success")
        return redirect(url_for("content.content_view", cid=cid))
    if request.method == "POST" and not form.validate_on_submit():
        flash("Please fix the highlighted errors and try again.", "danger")
    return render_template(
        "standalone_repo/form.html",
        form=form,
        mode="create",
        row=None,
        repo_ui=ui,
        repo_module=module,
    )


def run_standalone_repo_edit(module: str, cid: int):
    user = load_current_user()
    if user["role"] == "user":
        abort(403)
    if module not in STANDALONE_REPO_MODULES:
        abort(404)
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row:
        abort(404)
    if row["module"] != module:
        if row["module"] in STANDALONE_REPO_MODULES:
            seg = STANDALONE_MODULE_TO_SEGMENT[row["module"]]
            return redirect(url_for("repo_standalone.repo_edit", segment=seg, cid=cid))
        return redirect(url_for("content.content_edit", cid=cid))
    if row["author_id"] != user["id"] and user["role"] not in ("admin", "moderator"):
        abort(403)
    if row["status"] == "pending" and user["role"] not in ("admin", "moderator"):
        flash("You cannot edit content while it is pending review.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    if row["status"] == "approved" and user["role"] not in ("admin", "moderator"):
        flash("Approved content is read-only for contributors.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    ui = STANDALONE_REPO_UI[module]
    form = StandaloneRepoForm(obj=row)
    form.tags.data = ", ".join(get_tags(cid))
    if form.validate_on_submit():
        if not _update_from_form(user, row, cid, form, module=module):
            return render_template(
                "standalone_repo/form.html",
                form=form,
                mode="edit",
                row=row,
                repo_ui=ui,
                repo_module=module,
            )
        get_db().commit()
        flash(ui["edit_flash"], "success")
        return redirect(url_for("content.content_view", cid=cid))
    if request.method == "POST" and not form.validate_on_submit():
        flash("Please fix the highlighted errors and try again.", "danger")
    return render_template(
        "standalone_repo/form.html",
        form=form,
        mode="edit",
        row=row,
        repo_ui=ui,
        repo_module=module,
    )


@bp.route("/content/<int:cid>/delete", methods=["POST"])
@login_required
def content_delete(cid: int):
    user = load_current_user()
    if user["role"] == "user":
        abort(403)
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row:
        abort(404)
    if row["author_id"] != user["id"] and user["role"] != "admin":
        abort(403)
    files = db.execute(
        "SELECT file_path, preview_path, slide_preview_dir FROM attachments WHERE content_id = ?", (cid,)
    ).fetchall()
    for f in files:
        for key in ("file_path", "preview_path"):
            p = resolve_stored_upload_path(f[key])
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass
        from mine.slide_preview import remove_slide_preview_dir

        try:
            slide_dir = f["slide_preview_dir"]
        except (TypeError, KeyError):
            slide_dir = None
        remove_slide_preview_dir(slide_dir)
    db.execute("DELETE FROM content WHERE id = ?", (cid,))
    log_audit(user["id"], "content_delete", "content", cid, None)
    db.commit()
    flash("Content deleted.", "info")
    return redirect(url_for("content.content_list"))


@bp.route("/files/<int:aid>/office-source")
def office_attachment_source(aid: int):
    """Short-lived signed URL so Microsoft Office Online can fetch Office files without a session cookie."""
    token = (request.args.get("token") or "").strip()
    if not token:
        abort(403)
    try:
        data = _office_preview_serializer(current_app.config["SECRET_KEY"]).loads(
            token, max_age=_OFFICE_PREVIEW_MAX_AGE
        )
    except BadSignature:
        abort(403)
    if int(data.get("aid", 0)) != aid:
        abort(403)
    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    fname = (att["file_name"] or "").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ("ppt", "pptx", "xlsx", "xls"):
        abort(404)
    path = _resolved_attachment_or_404(att)
    mime, _ = mimetypes.guess_type(fname)
    default_name = fname or ("workbook.xlsx" if ext == "xlsx" else "workbook.xls" if ext == "xls" else "presentation.pptx")
    return send_file(
        path,
        mimetype=mime or None,
        as_attachment=False,
        download_name=default_name,
    )


@bp.record_once
def _register_office_embed_template_global(state):
    app = state.app

    @app.template_global()
    def office_embed_src(aid: int):
        if not app.config.get("ENABLE_OFFICE_EMBED_PREVIEW", True):
            return None
        if not has_request_context():
            return None
        token = _office_preview_serializer(app.config["SECRET_KEY"]).dumps({"aid": int(aid)})
        file_url = url_for("content.office_attachment_source", aid=aid, token=token, _external=True)
        if not app.config.get("OFFICE_EMBED_SKIP_REACHABILITY_CHECK", False):
            if not _office_cloud_can_fetch_document_url(file_url):
                return None
        return "https://view.officeapps.live.com/op/embed.aspx?src=" + quote(file_url, safe="")

    @app.template_global()
    def attachment_has_pdf_preview(att) -> bool:
        try:
            prev = att["preview_path"]
        except (TypeError, KeyError):
            prev = getattr(att, "preview_path", None)
        if not prev:
            return False
        return resolve_stored_upload_path(prev) is not None

    @app.template_global()
    def attachment_has_slide_preview(att) -> bool:
        from mine.slide_preview import list_slide_pngs

        try:
            slide_dir = att["slide_preview_dir"]
        except (TypeError, KeyError):
            slide_dir = getattr(att, "slide_preview_dir", None)
        return bool(list_slide_pngs(slide_dir))


@bp.route("/files/<int:aid>/preview")
@login_required
def attachment_preview_pdf(aid: int):
    """Serve derived PDF for in-page preview (original upload is unchanged)."""
    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)
    prev = resolve_stored_upload_path(att["preview_path"])
    if not prev:
        source = resolve_stored_upload_path(att["file_path"])
        if source:
            prev = _maybe_build_pdf_preview(db, att, source)
    if not prev:
        abort(404)
    dl = _preview_download_name(att["file_name"] or "attachment")
    return send_file(
        prev,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=dl,
    )


@bp.route("/files/<int:aid>/preview-xlsx-html")
@login_required
def attachment_preview_xlsx_html(aid: int):
    """First-sheet table preview for .xlsx (works without LibreOffice or Office Online reachability)."""
    from mine.xlsx_preview import render_xlsx_preview_html

    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)
    fname = (att["file_name"] or "").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext != "xlsx":
        abort(404)
    path = _resolved_attachment_or_404(att)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        abort(404)
    html = render_xlsx_preview_html(data, workbook_title=fname)
    if not html:
        abort(404)
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


@bp.route("/files/<int:aid>/slides/<int:slide_num>")
@login_required
def attachment_slide_image(aid: int, slide_num: int):
    """Serve one rasterized slide PNG from a deck preview."""
    if slide_num < 1 or slide_num > 999:
        abort(404)
    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)

    paths = _ensure_slide_preview_paths(db, att)
    if not paths or slide_num > len(paths):
        abort(404)

    path = paths[slide_num - 1]
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="image/png", as_attachment=False, download_name=f"slide-{slide_num:03d}.png")


@bp.route("/files/<int:aid>/preview-slides")
@login_required
def attachment_preview_slides(aid: int):
    """Full-fidelity slide carousel (PNG raster of each slide)."""
    from mine.slide_carousel import render_slide_carousel_html

    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)

    paths = _ensure_slide_preview_paths(db, att)
    if not paths:
        abort(404)

    slide_urls = [
        url_for("content.attachment_slide_image", aid=aid, slide_num=i + 1)
        for i in range(len(paths))
    ]
    html = render_slide_carousel_html(
        deck_title=att["file_name"] or "Presentation",
        slide_urls=slide_urls,
    )
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


@bp.route("/files/<int:aid>/preview-pptx-html")
@login_required
def attachment_preview_pptx_html(aid: int):
    """Visual slide preview for .pptx — embedded SVG/PNG icons and text (no LibreOffice)."""
    from mine.pptx_preview import render_pptx_preview_html
    from mine.pptx_visual_preview import render_pptx_visual_html

    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)
    fname = (att["file_name"] or "").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ("ppt", "pptx"):
        abort(404)
    path = _resolved_attachment_or_404(att)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        abort(404)

    def asset_url(media_name: str) -> str:
        return url_for("content.attachment_pptx_asset", aid=aid, filename=media_name)

    html = render_pptx_visual_html(data, deck_title=fname, asset_url_for=asset_url)
    if not html:
        html = render_pptx_preview_html(data, deck_title=fname)
    if not html:
        abort(404)
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


@bp.route("/files/<int:aid>/pptx-asset/<path:filename>")
@login_required
def attachment_pptx_asset(aid: int, filename: str):
    """Serve one embedded image/SVG from inside a .pptx archive."""
    from mine.pptx_visual_preview import is_safe_pptx_media_filename, read_pptx_media

    if not is_safe_pptx_media_filename(filename):
        abort(404)
    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)
    fname = (att["file_name"] or "").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ("ppt", "pptx"):
        abort(404)
    path = _resolved_attachment_or_404(att)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        abort(404)
    result = read_pptx_media(data, filename)
    if not result:
        abort(404)
    blob, mime = result
    resp = make_response(blob)
    resp.headers["Content-Type"] = mime
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@bp.route("/files/<int:aid>/preview-docx-html")
@login_required
def attachment_preview_docx_html(aid: int):
    """Paragraph text preview for .docx (works without LibreOffice or Office Online)."""
    from mine.docx_preview import render_docx_preview_html

    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)
    fname = (att["file_name"] or "").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext != "docx":
        abort(404)
    path = _resolved_attachment_or_404(att)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        abort(404)
    html = render_docx_preview_html(data, doc_title=fname)
    if not html:
        abort(404)
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


@bp.route("/files/<int:aid>")
@login_required
def download_attachment(aid: int):
    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not att:
        abort(404)
    row = db.execute("SELECT * FROM content WHERE id = ?", (att["content_id"],)).fetchone()
    if not content_visible(load_current_user(), row):
        abort(404)
    path = _resolved_attachment_or_404(att)
    fname = att["file_name"] or "file"
    mime, _ = mimetypes.guess_type(fname)
    inline = (request.args.get("inline") or "").strip().lower() in ("1", "true", "yes")
    return send_file(
        path,
        mimetype=mime or None,
        as_attachment=not inline,
        download_name=fname,
    )


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    """Attach a file to existing content (expects content_id in form)."""
    from flask_wtf.csrf import validate_csrf

    validate_csrf(request.form.get("csrf_token"))
    cid = int(request.form.get("content_id", "0"))
    user = load_current_user()
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row or (row["author_id"] != user["id"] and user["role"] not in ("admin", "moderator")):
        abort(403)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("content.content_view", cid=cid))
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    allowed = current_app.config.get("ALLOWED_EXTENSIONS") or Config.ALLOWED_EXTENSIONS
    if ext not in allowed:
        flash("File type not allowed.", "danger")
        return redirect(url_for("content.content_view", cid=cid))
    orig = f.filename or "file"
    _insert_attachment_from_upload(db, cid, f)
    log_audit(user["id"], "attachment_upload", "content", cid, orig)
    db.commit()
    flash("File uploaded.", "success")
    return redirect(url_for("content.content_view", cid=cid))
