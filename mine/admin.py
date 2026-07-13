import bcrypt
from urllib.parse import urlparse
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length

from mine.auth_utils import load_current_user, login_required, roles_required
from mine.db import get_db
from mine.services import clear_all_read_notifications, clear_notification, log_audit, mark_all_notifications_read, moderation_entry, notify
from mine.team_roster import import_roster_users, load_team_roster, save_roster_workbook

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _safe_post_redirect(default_endpoint: str, **default_kwargs):
    raw = (request.form.get("next") or request.args.get("next") or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        parsed = urlparse(raw)
        if not parsed.scheme and not parsed.netloc:
            return redirect(raw)
    return redirect(url_for(default_endpoint, **default_kwargs))


class RejectForm(FlaskForm):
    note = TextAreaField("Reason for rejection", validators=[DataRequired(), Length(min=1, max=2000)])


class UserCreateForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=200)])
    display_name = StringField("Display name", validators=[DataRequired(), Length(max=200)])
    password = PasswordField("Temporary password", validators=[DataRequired(), Length(min=8, max=128)])
    role = SelectField(
        "Role",
        choices=[("user", "User"), ("moderator", "Moderator"), ("admin", "Admin")],
        validators=[DataRequired()],
    )


class UserUpdateForm(FlaskForm):
    user_id = StringField("User ID", validators=[DataRequired()])
    role = SelectField(
        "Role",
        choices=[("user", "User"), ("moderator", "Moderator"), ("admin", "Admin")],
        validators=[DataRequired()],
    )


class AdminPasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=8, max=128, message="Use at least 8 characters.")],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="New passwords must match.")],
    )


class SendMailForm(FlaskForm):
    smtp_username = StringField("Your Outlook email", validators=[DataRequired(), Email(), Length(max=200)])
    smtp_password = PasswordField("Your Outlook password / app password", validators=[DataRequired(), Length(max=300)])
    to_addresses = TextAreaField(
        "To (email addresses)",
        validators=[DataRequired(), Length(max=4000)],
        description="Comma or space separated. Any syntactically valid address is allowed unless the server sets MAIL_OPEN_RECIPIENTS=0 (then only active MiNe users and MAIL_EXTRA_ALLOWLIST).",
    )
    subject = StringField("Subject", validators=[DataRequired(), Length(max=300)])
    body = TextAreaField("Message", validators=[DataRequired(), Length(max=20000)])


@bp.route("/moderator-profile")
@login_required
@roles_required("moderator")
def moderator_profile():
    user = load_current_user()
    return render_template("admin/moderator_profile.html", user=user)


@bp.route("/admin-profile")
@login_required
@roles_required("admin")
def admin_profile():
    user = load_current_user()
    return render_template("admin/admin_profile.html", user=user)


@bp.route("/moderation")
@login_required
@roles_required("admin", "moderator")
def moderation():
    db = get_db()
    rows = db.execute(
        """
        SELECT c.*,
               COALESCE(u.display_name, '(unknown author)') AS author_name,
               COALESCE(u.email, '') AS author_email
        FROM content c
        LEFT JOIN users u ON u.id = c.author_id
        WHERE lower(trim(COALESCE(c.status, ''))) = 'pending'
        ORDER BY c.updated_at ASC
        """
    ).fetchall()

    attachments_by_content = {}
    if rows:
        ids = [int(r["id"]) for r in rows]
        placeholders = ",".join("?" * len(ids))
        att_rows = db.execute(
            f"SELECT * FROM attachments WHERE content_id IN ({placeholders}) ORDER BY id DESC",
            ids,
        ).fetchall()
        for att in att_rows:
            cid = int(att["content_id"])
            attachments_by_content.setdefault(cid, []).append(att)

    return render_template(
        "admin/moderation.html",
        rows=rows,
        attachments_by_content=attachments_by_content,
    )


@bp.route("/approve/<int:cid>", methods=["POST"])
@login_required
@roles_required("admin", "moderator")
def approve(cid: int):
    user = load_current_user()
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row or (row["status"] or "").strip().lower() != "pending":
        abort(404)
    db.execute(
        "UPDATE content SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (cid,),
    )
    moderation_entry(cid, user["id"], "approve", None)
    log_audit(user["id"], "moderation_approve", "content", cid, None)
    notify(row["author_id"], f"Your submission was approved: #{cid} — {row['title']}")
    db.commit()
    flash("Content approved.", "success")
    return _safe_post_redirect("admin.moderation")


@bp.route("/reject/<int:cid>", methods=["POST"])
@login_required
@roles_required("admin", "moderator")
def reject(cid: int):
    user = load_current_user()
    form = RejectForm()
    if not form.validate_on_submit():
        flash("A rejection reason is required.", "danger")
        return _safe_post_redirect("admin.moderation")
    db = get_db()
    row = db.execute("SELECT * FROM content WHERE id = ?", (cid,)).fetchone()
    if not row or (row["status"] or "").strip().lower() != "pending":
        abort(404)
    note = (form.note.data or "").strip()
    db.execute(
        "UPDATE content SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (cid,),
    )
    moderation_entry(cid, user["id"], "reject", note)
    log_audit(user["id"], "moderation_reject", "content", cid, note)
    msg = f"Your submission needs changes: #{cid} — {row['title']}"
    if note:
        msg += f" — Note: {note}"
    notify(row["author_id"], msg)
    db.commit()
    flash("Content rejected and returned to author.", "info")
    return _safe_post_redirect("admin.moderation")


@bp.route("/users")
@login_required
@roles_required("admin")
def users():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    create_form = UserCreateForm()
    update_form = UserUpdateForm()
    roster_preview = load_team_roster()
    return render_template(
        "admin/users.html",
        rows=rows,
        create_form=create_form,
        update_form=update_form,
        roster_preview=roster_preview,
    )


@bp.route("/team-roster/upload", methods=["POST"])
@login_required
@roles_required("admin")
def team_roster_upload():
    upload = request.files.get("roster_file")
    if not upload or not upload.filename:
        flash("Choose an Excel file to upload.", "danger")
        return redirect(request.referrer or url_for("main.team_roster"))
    if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        flash("Upload an Excel workbook (.xlsx).", "danger")
        return redirect(request.referrer or url_for("main.team_roster"))
    try:
        save_roster_workbook(upload)
        roster = load_team_roster()
        if not roster:
            flash("File saved, but no Name/TSR columns were found. Check the workbook layout.", "warning")
        else:
            flash(f"Resource tracker uploaded — {len(roster)} team members loaded.", "success")
    except Exception:
        flash("Could not save the workbook.", "danger")
    return redirect(request.referrer or url_for("main.team_roster"))


@bp.route("/users/import-roster", methods=["POST"])
@login_required
@roles_required("admin")
def users_import_roster():
    db = get_db()
    result = import_roster_users(db, actor_id=load_current_user()["id"])
    if result.get("error"):
        flash(result["error"], "danger")
    elif result["created"]:
        db.commit()
        msg = f"Created {result['created']} MiNe account(s) from the roster."
        if result.get("credentials_file"):
            msg += " Passwords saved to logs/team-roster-import.csv — distribute securely."
        if result["skipped"]:
            msg += f" Skipped {result['skipped']} (already exist)."
        flash(msg, "success")
    else:
        flash("No new accounts to create — roster users may already exist.", "info")
    next_url = (request.form.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for("admin.users"))


@bp.route("/users/create", methods=["POST"])
@login_required
@roles_required("admin")
def users_create():
    form = UserCreateForm()
    if not form.validate_on_submit():
        flash("Please fix the errors and try again.", "danger")
        return redirect(url_for("admin.users"))
    db = get_db()
    pw_hash = bcrypt.hashpw(form.password.data.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        db.execute(
            """
            INSERT INTO users (username, email, password_hash, display_name, role, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                form.username.data.strip(),
                form.email.data.strip().lower(),
                pw_hash,
                form.display_name.data.strip(),
                form.role.data,
            ),
        )
        log_audit(load_current_user()["id"], "user_create", "user", None, form.username.data.strip())
        db.commit()
        flash("User created.", "success")
    except Exception:
        flash("Could not create user (duplicate username/email?).", "danger")
    return redirect(url_for("admin.users"))


@bp.route("/users/update", methods=["POST"])
@login_required
@roles_required("admin")
def users_update():
    form = UserUpdateForm()
    if not form.validate_on_submit():
        flash("Invalid update request.", "danger")
        return redirect(url_for("admin.users"))
    uid = int(form.user_id.data)
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (form.role.data, uid))
    log_audit(load_current_user()["id"], "user_role_update", "user", uid, form.role.data)
    notify(uid, f"Your role was updated to: {form.role.data}")
    db.commit()
    flash("User role updated.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/deactivate", methods=["POST"])
@login_required
@roles_required("admin")
def users_deactivate():
    uid = int(request.form.get("user_id", "0"))
    if not uid:
        abort(400)
    if uid == load_current_user()["id"]:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("admin.users"))
    db = get_db()
    db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
    log_audit(load_current_user()["id"], "user_deactivate", "user", uid, None)
    db.commit()
    flash("User deactivated.", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/delete", methods=["POST"])
@login_required
@roles_required("admin")
def users_delete():
    """Permanently remove a user; reassigns their content to the deleting admin."""
    import sqlite3

    uid = int(request.form.get("user_id", "0"))
    if not uid:
        abort(400)
    admin = load_current_user()
    admin_id = int(admin["id"])
    if uid == admin_id:
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for("admin.users"))

    db = get_db()
    target = db.execute("SELECT id, username, role, is_active FROM users WHERE id = ?", (uid,)).fetchone()
    if not target:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))

    if target["role"] == "admin" and target["is_active"]:
        others = db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
            (uid,),
        ).fetchone()["c"]
        if int(others or 0) == 0:
            flash("Cannot delete the last active administrator.", "danger")
            return redirect(url_for("admin.users"))

    try:
        db.execute("BEGIN")
        db.execute(
            "UPDATE content SET author_id = ?, updated_at = CURRENT_TIMESTAMP WHERE author_id = ?",
            (admin_id, uid),
        )
        db.execute("DELETE FROM notifications WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM notification_user_state WHERE user_id = ?", (uid,))
        db.execute("UPDATE moderation_log SET performed_by = NULL WHERE performed_by = ?", (uid,))
        db.execute("UPDATE audit_log SET user_id = NULL WHERE user_id = ?", (uid,))
        log_audit(
            admin_id,
            "user_delete",
            "user",
            uid,
            f"username={target['username']!r} content_reassigned_to={admin_id}",
        )
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f"Could not delete user (database constraint): {e}", "danger")
        return redirect(url_for("admin.users"))

    flash(
        f"User “{target['username']}” was permanently deleted. Their catalogue content is now attributed to you.",
        "success",
    )
    return redirect(url_for("admin.users"))


@bp.route("/analytics")
@login_required
@roles_required("admin", "moderator")
def analytics():
    db = get_db()
    stats = {
        "users": db.execute("SELECT COUNT(*) AS c FROM users WHERE is_active = 1").fetchone()["c"],
        "content": db.execute("SELECT COUNT(*) AS c FROM content").fetchone()["c"],
        "approved": db.execute("SELECT COUNT(*) AS c FROM content WHERE status='approved'").fetchone()[
            "c"
        ],
        "pending": db.execute(
            "SELECT COUNT(*) AS c FROM content WHERE lower(trim(COALESCE(status,''))) = 'pending'"
        ).fetchone()["c"],
    }
    by_module = db.execute(
        """
        SELECT module, COUNT(*) AS c
        FROM content
        WHERE status = 'approved'
        GROUP BY module
        ORDER BY c DESC
        """
    ).fetchall()
    return render_template("admin/analytics.html", stats=stats, by_module=by_module)


@bp.route("/notifications/read", methods=["POST"])
@login_required
def notifications_read():
    """Mark all notifications read for current user."""
    user = load_current_user()
    mark_all_notifications_read(user["id"])
    get_db().commit()
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/notifications/clear-read", methods=["POST"])
@login_required
def notifications_clear_read():
    """Delete/dismiss all read notifications for current user."""
    user = load_current_user()
    clear_all_read_notifications(user["id"])
    get_db().commit()
    flash("Read notifications cleared.", "success")
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/notifications/<int:nid>/clear", methods=["POST"])
@login_required
def notifications_clear(nid: int):
    """Delete one read notification for current user."""
    user = load_current_user()
    if not clear_notification(user["id"], nid):
        abort(404)
    get_db().commit()
    return redirect(request.referrer or url_for("main.dashboard"))


def _render_password_form(form=None):
    return render_template("admin/settings_password.html", form=form or AdminPasswordChangeForm())


@bp.route("/settings")
@login_required
@roles_required("admin")
def settings():
    from mine import mail as mailmod

    return render_template("admin/settings.html", mail_ready=mailmod.mail_ready(current_app))


@bp.route("/mail", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def mail_compose():
    import re

    from mine import mail as mailmod

    current_user_row = load_current_user()
    admin_sender_candidate = ""
    if current_user_row:
        try:
            admin_sender_candidate = ((current_user_row["email"] or "")).strip()
        except Exception:
            admin_sender_candidate = ""
    admin_sender_norm = mailmod.normalize_email(admin_sender_candidate) if admin_sender_candidate else None
    sender_preview = admin_sender_norm or ((current_app.config.get("MAIL_DEFAULT_SENDER") or "").strip()[:100])

    mail_ctx = {
        "smtp_server": (current_app.config.get("MAIL_SERVER") or "").strip(),
        "smtp_port": int(current_app.config.get("MAIL_PORT") or 587),
        "smtp_ssl": bool(current_app.config.get("MAIL_USE_SSL")),
        "smtp_starttls": bool(current_app.config.get("MAIL_USE_TLS")),
        "smtp_auth": bool((current_app.config.get("MAIL_USERNAME") or "").strip()),
        "open_recipients": bool(current_app.config.get("MAIL_OPEN_RECIPIENTS")),
        "sender_preview": sender_preview,
        "mail_dummy": bool(current_app.config.get("MAIL_DUMMY")),
        "mail_dummy_path": (current_app.config.get("MAIL_DUMMY_PATH") or "").strip(),
        "smtp_placeholder": any(
            "replace_with_" in (str(x or "").lower())
            for x in (
                current_app.config.get("MAIL_USERNAME"),
                current_app.config.get("MAIL_PASSWORD"),
                current_app.config.get("MAIL_DEFAULT_SENDER"),
            )
        ),
    }

    form = SendMailForm()
    ready = mailmod.mail_ready(current_app)
    if request.method == "GET":
        if admin_sender_norm:
            form.smtp_username.data = admin_sender_norm
        pre = (request.args.get("to") or "").strip()
        if pre:
            form.to_addresses.data = pre
        return render_template("admin/mail.html", form=form, mail_ready=ready, mail_ctx=mail_ctx)

    if not form.validate_on_submit():
        flash("Please fix the errors below.", "danger")
        return render_template("admin/mail.html", form=form, mail_ready=ready, mail_ctx=mail_ctx)

    host_ok = bool((current_app.config.get("MAIL_SERVER") or "").strip())
    sender_input_raw = (form.smtp_username.data or "").strip()
    sender_input = mailmod.normalize_email(sender_input_raw)
    if not sender_input:
        flash("Enter a valid Outlook mailbox email in the SMTP credentials section.", "danger")
        return render_template("admin/mail.html", form=form, mail_ready=ready, mail_ctx=mail_ctx)

    if not host_ok:
        flash(
            "Mail is not configured. Set MAIL_ENABLED=1 and MAIL_SERVER. "
            "For local testing without SMTP, add MAIL_DUMMY=1 (messages go to a log file). "
            "For production, set MAIL_SERVER and usually MAIL_USERNAME / MAIL_PASSWORD.",
            "warning",
        )
        return render_template("admin/mail.html", form=form, mail_ready=False, mail_ctx=mail_ctx)

    raw = (form.to_addresses.data or "").strip()
    pieces = [p for p in re.split(r"[\s,;]+", raw) if p.strip()]
    addrs: list[str] = []
    for p in pieces:
        n = mailmod.normalize_email(p)
        if not n:
            flash(f"Invalid email address: “{p}”.", "danger")
            return render_template("admin/mail.html", form=form, mail_ready=ready, mail_ctx=mail_ctx)
        addrs.append(n)

    seen: set[str] = set()
    uniq: list[str] = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    addrs = uniq

    db = get_db()
    if not current_app.config.get("MAIL_OPEN_RECIPIENTS"):
        permitted = mailmod.permitted_recipient_emails(current_app, db)
        blocked = [a for a in addrs if a not in permitted]
        if blocked:
            u = load_current_user()
            prof = (u["email"] or "").strip() if u else ""
            hint = ""
            if prof:
                pn = mailmod.normalize_email(prof)
                if pn:
                    in_dir = pn in permitted
                    hint = (
                        f" Your profile email normalizes to {pn!r}; it is in the allowed recipient set: {in_dir}. "
                        "Use that exact mailbox in To, or clear MAIL_OPEN_RECIPIENTS=0 so any valid address is allowed."
                    )
                else:
                    hint = f" Your MiNe profile email on file is: {prof!r}."
            flash(
                "These addresses are not permitted: "
                + ", ".join(blocked)
                + ". Allowed recipients are active MiNe user emails plus MAIL_EXTRA_ALLOWLIST, "
                "or remove MAIL_OPEN_RECIPIENTS=0 to allow any valid address."
                + hint,
                "danger",
            )
            return render_template("admin/mail.html", form=form, mail_ready=ready, mail_ctx=mail_ctx)

    subject = (form.subject.data or "").strip()
    body = (form.body.data or "").strip()
    ok, err = mailmod.send_email(
        current_app,
        addrs,
        subject,
        body,
        sender_override=sender_input,
        smtp_username_override=sender_input,
        smtp_password_override=form.smtp_password.data or "",
    )
    if ok:
        log_audit(load_current_user()["id"], "mail_send", "mail", None, f"to={addrs!r} subject={subject[:120]!r}")
        db.commit()
        if current_app.config.get("MAIL_DUMMY"):
            flash(
                f"Message saved to the dev mailbox file ({current_app.config.get('MAIL_DUMMY_PATH')}). "
                "No SMTP was used. For real email, set MAIL_SERVER (and unset MAIL_DUMMY).",
                "success",
            )
        else:
            flash(f"Message sent to {len(addrs)} recipient(s).", "success")
        return redirect(url_for("admin.mail_compose"))

    flash(f"Could not send mail: {err}", "danger")
    return render_template("admin/mail.html", form=form, mail_ready=ready, mail_ctx=mail_ctx)


@bp.route("/settings/password", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def settings_password():
    if request.method == "GET":
        return _render_password_form()
    form = AdminPasswordChangeForm()
    if not form.validate_on_submit():
        flash("Please fix the errors in the password form.", "danger")
        return _render_password_form(form)
    user = load_current_user()
    db = get_db()
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not row or not bcrypt.checkpw(
        form.current_password.data.encode("utf-8"),
        row["password_hash"].encode("utf-8"),
    ):
        flash("Current password is incorrect.", "danger")
        return _render_password_form()
    new_hash = bcrypt.hashpw(form.new_password.data.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    log_audit(user["id"], "password_change", "user", user["id"], None)
    db.commit()
    flash("Your password was updated.", "success")
    return redirect(url_for("admin.settings"))
