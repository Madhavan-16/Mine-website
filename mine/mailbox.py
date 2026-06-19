from __future__ import annotations

import base64
import secrets
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from mine.auth_utils import load_current_user, login_required, roles_required
from mine.db import get_db
from mine.forms_mailbox import GraphComposeForm
from mine.graph_mail import FOLDER_MAP, GraphError, build_authorization_url, disconnect_user, exchange_code_for_token
from mine.graph_mail import get_folder_messages, get_message, get_valid_access_token, graph_ready, persist_oauth_result, send_mail
from mine.services import log_audit

bp = Blueprint("mailbox", __name__, url_prefix="/admin/mailbox")

STATE_KEY = "ms_oauth_state"
TOKEN_MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB simple attachment limit


def _redirect_uri() -> str:
    path = (current_app.config.get("MS_REDIRECT_PATH") or "/admin/mailbox/oauth/callback").strip()
    path = path if path.startswith("/") else f"/{path}"
    root = request.url_root.rstrip("/")
    return f"{root}{path}"


def _safe_next_url() -> str:
    nxt = (request.args.get("next") or "").strip()
    if not nxt:
        return url_for("mailbox.inbox")
    p = urlparse(nxt)
    if p.scheme or p.netloc:
        return url_for("mailbox.inbox")
    if not nxt.startswith("/"):
        return url_for("mailbox.inbox")
    return nxt


def _require_graph() -> bool:
    if graph_ready(current_app):
        return True
    flash(
        "Outlook integration is not configured. Set MS_GRAPH_ENABLED=1, MS_CLIENT_ID, MS_CLIENT_SECRET, and MS_TOKEN_ENCRYPTION_KEY.",
        "danger",
    )
    return False


def _clear_mailbox_token_if_needed(db, user_id: int, err: GraphError) -> None:
    if err.needs_reconnect:
        disconnect_user(db, user_id)
        db.commit()


def _folder_page(folder_key: str, title: str):
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    user = load_current_user()
    db = get_db()
    try:
        access_token, token_row = get_valid_access_token(db, current_app, int(user["id"]))
        messages = get_folder_messages(access_token, folder_key)
        db.commit()
    except GraphError as exc:
        _clear_mailbox_token_if_needed(db, int(user["id"]), exc)
        flash(str(exc), "danger")
        if exc.needs_reconnect:
            return redirect(url_for("mailbox.connect"))
        return redirect(url_for("admin.settings"))

    return render_template(
        "mailbox/folder_list.html",
        folder_key=folder_key,
        folder_title=title,
        rows=messages,
        account_email=token_row.get("account_email") or "",
        account_display_name=token_row.get("account_display_name") or "",
    )


@bp.route("/")
@login_required
@roles_required("admin")
def home():
    return redirect(url_for("mailbox.inbox"))


@bp.route("/connect", methods=["GET"])
@login_required
@roles_required("admin")
def connect():
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    user = load_current_user()
    db = get_db()
    token = None
    try:
        token = get_valid_access_token(db, current_app, int(user["id"]))[1]
        db.commit()
    except GraphError as exc:
        _clear_mailbox_token_if_needed(db, int(user["id"]), exc)
    return render_template("mailbox/connect.html", token=token, graph_ready=True)


@bp.route("/connect/start", methods=["POST"])
@login_required
@roles_required("admin")
def connect_start():
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    state = secrets.token_urlsafe(24)
    session[STATE_KEY] = state
    session["ms_oauth_next"] = _safe_next_url()
    try:
        auth_url = build_authorization_url(current_app, _redirect_uri(), state)
    except GraphError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("mailbox.connect"))
    return redirect(auth_url)


@bp.route("/oauth/callback", methods=["GET"])
@login_required
@roles_required("admin")
def oauth_callback():
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    expected = session.pop(STATE_KEY, None)
    got = (request.args.get("state") or "").strip()
    if not expected or not got or expected != got:
        flash("OAuth state check failed. Please try connecting Outlook again.", "danger")
        return redirect(url_for("mailbox.connect"))
    code = (request.args.get("code") or "").strip()
    if not code:
        detail = (request.args.get("error_description") or request.args.get("error") or "").strip()
        flash(f"Microsoft sign-in failed: {detail or 'no authorization code returned'}", "danger")
        return redirect(url_for("mailbox.connect"))

    db = get_db()
    user = load_current_user()
    try:
        token_result = exchange_code_for_token(current_app, code, _redirect_uri())
        persist_oauth_result(db, current_app, int(user["id"]), token_result)
        log_audit(int(user["id"]), "graph_mail_connect", "mailbox", int(user["id"]), "provider=microsoft_graph")
        db.commit()
    except GraphError as exc:
        db.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("mailbox.connect"))
    flash("Outlook mailbox connected successfully.", "success")
    nxt = session.pop("ms_oauth_next", "") or url_for("mailbox.inbox")
    return redirect(nxt)


@bp.route("/disconnect", methods=["POST"])
@login_required
@roles_required("admin")
def disconnect():
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    db = get_db()
    user = load_current_user()
    disconnect_user(db, int(user["id"]))
    log_audit(int(user["id"]), "graph_mail_disconnect", "mailbox", int(user["id"]), "provider=microsoft_graph")
    db.commit()
    flash("Outlook mailbox disconnected.", "info")
    return redirect(url_for("mailbox.connect"))


@bp.route("/inbox")
@login_required
@roles_required("admin")
def inbox():
    return _folder_page("inbox", "Inbox")


@bp.route("/sent")
@login_required
@roles_required("admin")
def sent():
    return _folder_page("sent", "Sent")


@bp.route("/drafts")
@login_required
@roles_required("admin")
def drafts():
    return _folder_page("drafts", "Drafts")


@bp.route("/trash")
@login_required
@roles_required("admin")
def trash():
    return _folder_page("trash", "Trash")


@bp.route("/message/<mid>")
@login_required
@roles_required("admin")
def message_detail(mid: str):
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    db = get_db()
    user = load_current_user()
    try:
        access_token, token_row = get_valid_access_token(db, current_app, int(user["id"]))
        row = get_message(access_token, mid)
        db.commit()
    except GraphError as exc:
        _clear_mailbox_token_if_needed(db, int(user["id"]), exc)
        flash(str(exc), "danger")
        if exc.needs_reconnect:
            return redirect(url_for("mailbox.connect"))
        return redirect(url_for("mailbox.inbox"))
    return render_template(
        "mailbox/message_detail.html",
        row=row,
        account_email=token_row.get("account_email") or "",
        folders=FOLDER_MAP,
    )


def _build_attachment_payload(files) -> tuple[list[dict[str, str]], str | None]:
    payload: list[dict[str, str]] = []
    allowed = current_app.config.get("ALLOWED_EXTENSIONS") or set()
    for f in files:
        if not f or not (f.filename or "").strip():
            continue
        safe_name = secure_filename(f.filename)
        if not safe_name:
            return [], "Attachment filename is invalid."
        ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if ext not in allowed:
            return [], f"Attachment type .{ext or '(none)'} is not allowed."
        blob = f.read() or b""
        if len(blob) > TOKEN_MAX_FILE_SIZE:
            return [], f"Attachment {safe_name!r} is larger than 3MB; please use a smaller file."
        payload.append(
            {
                "name": safe_name,
                "content_type": (f.mimetype or "application/octet-stream"),
                "content_b64": base64.b64encode(blob).decode("ascii"),
            }
        )
    return payload, None


@bp.route("/compose", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def compose():
    if not _require_graph():
        return redirect(url_for("admin.settings"))
    form = GraphComposeForm()
    if request.method == "GET":
        pre = (request.args.get("to") or "").strip()
        if pre:
            form.to_addresses.data = pre
        return render_template("mailbox/compose.html", form=form)

    if not form.validate_on_submit():
        flash("Please fix the errors in the mail form.", "danger")
        return render_template("mailbox/compose.html", form=form)

    files = request.files.getlist(form.attachments.name)
    attachments, attachment_err = _build_attachment_payload(files)
    if attachment_err:
        flash(attachment_err, "danger")
        return render_template("mailbox/compose.html", form=form)

    db = get_db()
    user = load_current_user()
    try:
        access_token, _ = get_valid_access_token(db, current_app, int(user["id"]))
        send_mail(
            access_token,
            to_raw=form.to_addresses.data or "",
            cc_raw=form.cc_addresses.data or "",
            bcc_raw=form.bcc_addresses.data or "",
            subject=form.subject.data or "",
            body_text=form.body.data or "",
            attachments=attachments,
        )
        log_audit(
            int(user["id"]),
            "graph_mail_send",
            "mailbox",
            int(user["id"]),
            f"to={form.to_addresses.data!r} subject={(form.subject.data or '')[:120]!r} attachments={len(attachments)}",
        )
        db.commit()
    except GraphError as exc:
        _clear_mailbox_token_if_needed(db, int(user["id"]), exc)
        flash(str(exc), "danger")
        if exc.needs_reconnect:
            return redirect(url_for("mailbox.connect"))
        return render_template("mailbox/compose.html", form=form)

    flash("Message accepted by Microsoft Graph and queued for delivery.", "success")
    return redirect(url_for("mailbox.sent"))
