import bcrypt
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, Length

from mine.auth_utils import load_current_user, login_required, safe_login_next
from mine.db import get_db
from mine.services import log_audit

bp = Blueprint("auth", __name__)


def post_login_redirect_url(user=None) -> str:
    """Default landing path after sign-in (used when ?next= is not set)."""
    return url_for("main.dashboard")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class AccountPasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=8, max=128, message="Use at least 8 characters.")],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="New passwords must match.")],
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if load_current_user():
        u = load_current_user()
        nxt = safe_login_next(request.args.get("next"))
        return redirect(nxt or post_login_redirect_url(u))
    form = LoginForm()
    if form.validate_on_submit():
        db = get_db()
        uname = form.username.data.strip().lower()
        user = db.execute(
            "SELECT * FROM users WHERE lower(trim(username)) = ? AND is_active = 1",
            (uname,),
        ).fetchone()
        if user and bcrypt.checkpw(
            form.password.data.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            session.clear()
            session["user_id"] = user["id"]
            log_audit(user["id"], "login", "user", user["id"], None)
            db.commit()
            nxt = safe_login_next(request.form.get("next") or request.args.get("next"))
            return redirect(nxt or post_login_redirect_url(user))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    user = load_current_user()
    log_audit(user["id"], "logout", "user", user["id"], None)
    get_db().commit()
    session.pop("user_id", None)
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET"])
@login_required
def profile():
    user = load_current_user()
    role = user["role"] if user else "user"
    if role == "admin":
        return redirect(url_for("admin.admin_profile"))
    if role == "moderator":
        return redirect(url_for("admin.moderator_profile"))
    return render_template("auth/profile.html", user=user)


@bp.route("/account/settings", methods=["GET"])
@login_required
def account_settings():
    user = load_current_user()
    if user and user["role"] == "admin":
        return redirect(url_for("admin.settings"))
    return render_template("auth/account_settings.html")


@bp.route("/account/settings/password", methods=["GET", "POST"])
@login_required
def account_settings_password():
    user = load_current_user()
    if user and user["role"] == "admin":
        return redirect(url_for("admin.settings_password"))
    if request.method == "GET":
        return render_template(
            "auth/account_settings_password.html", form=AccountPasswordChangeForm()
        )
    form = AccountPasswordChangeForm()
    if not form.validate_on_submit():
        flash("Please fix the errors in the password form.", "danger")
        return render_template("auth/account_settings_password.html", form=form)
    db = get_db()
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not row or not bcrypt.checkpw(
        form.current_password.data.encode("utf-8"),
        row["password_hash"].encode("utf-8"),
    ):
        flash("Current password is incorrect.", "danger")
        return render_template("auth/account_settings_password.html", form=form)
    new_hash = bcrypt.hashpw(form.new_password.data.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    log_audit(user["id"], "password_change", "user", user["id"], None)
    db.commit()
    flash("Your password was updated.", "success")
    return redirect(url_for("auth.account_settings"))
