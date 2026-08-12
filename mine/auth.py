import bcrypt
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, EqualTo, Length

from mine.auth_utils import load_current_user, login_required, safe_login_next
from mine.db import get_db
from mine.security_questions import (
    REQUIRED_ANSWERS,
    catalog_choices,
    list_user_answers,
    pick_challenge_question,
    question_prompt,
    save_user_answers,
    user_has_security_answers,
    verify_user_answer,
)
from mine.services import log_audit

bp = Blueprint("auth", __name__)

_FORGOT_MAX_ATTEMPTS = 5


def post_login_redirect_url(user=None) -> str:
    """Default landing path after sign-in (used when ?next= is not set)."""
    if user is not None and (user["role"] or "").strip().lower() == "guest":
        return url_for("main.knowledge")
    return url_for("main.dashboard")


def _clear_forgot_session() -> None:
    for key in (
        "forgot_user_id",
        "forgot_username",
        "forgot_question_id",
        "forgot_verified",
        "forgot_attempts",
    ):
        session.pop(key, None)


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


class ForgotUsernameForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=120)])


class ForgotChallengeForm(FlaskForm):
    answer = StringField("Your answer", validators=[DataRequired(), Length(min=1, max=200)])


class ForgotResetForm(FlaskForm):
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=8, max=128, message="Use at least 8 characters.")],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="New passwords must match.")],
    )


class SecurityQuestionsForm(FlaskForm):
    question_1 = SelectField("Question 1", validators=[DataRequired()], choices=[])
    answer_1 = StringField("Answer 1", validators=[DataRequired(), Length(min=2, max=200)])
    question_2 = SelectField("Question 2", validators=[DataRequired()], choices=[])
    answer_2 = StringField("Answer 2", validators=[DataRequired(), Length(min=2, max=200)])
    question_3 = SelectField("Question 3", validators=[DataRequired()], choices=[])
    answer_3 = StringField("Answer 3", validators=[DataRequired(), Length(min=2, max=200)])

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if not ok:
            return False
        ids = [self.question_1.data, self.question_2.data, self.question_3.data]
        if len(set(ids)) != REQUIRED_ANSWERS:
            self.question_2.errors.append("Choose three different questions.")
            return False
        return True


def _security_questions_form(existing: list[dict] | None = None) -> SecurityQuestionsForm:
    form = SecurityQuestionsForm()
    choices = [("", "Select a question…")] + catalog_choices()
    form.question_1.choices = choices
    form.question_2.choices = choices
    form.question_3.choices = choices
    if existing and len(existing) >= REQUIRED_ANSWERS and request.method == "GET":
        form.question_1.data = existing[0]["question_id"]
        form.question_2.data = existing[1]["question_id"]
        form.question_3.data = existing[2]["question_id"]
    return form


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
        if uname == "guest":
            flash("Use Continue as Guest below for the read-only guest account.", "info")
            return render_template("auth/login.html", form=form)
        user = db.execute(
            "SELECT * FROM users WHERE lower(trim(username)) = ? AND is_active = 1",
            (uname,),
        ).fetchone()
        if user and (user["role"] or "").strip().lower() == "guest":
            flash("Use Continue as Guest below for the read-only guest account.", "info")
            return render_template("auth/login.html", form=form)
        if user and bcrypt.checkpw(
            form.password.data.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            session.clear()
            session["user_id"] = user["id"]
            log_audit(user["id"], "login", "user", user["id"], None)
            db.commit()
            nxt = safe_login_next(request.form.get("next") or request.args.get("next"))
            # First-time (or never enrolled): force security-question setup before portal use.
            if (user["role"] or "").strip().lower() != "guest":
                if user_has_security_answers(db, user["id"]):
                    session["security_questions_ok"] = True
                else:
                    session["force_security_questions"] = True
                    if nxt:
                        session["post_login_next"] = nxt
                    flash(
                        "Set up three security questions to protect your account. This is required once.",
                        "warning",
                    )
                    return redirect(url_for("auth.account_security_questions", setup=1))
            if user["role"] in ("admin", "moderator"):
                pending = int(
                    db.execute(
                        "SELECT COUNT(*) AS c FROM content WHERE status = 'pending'"
                    ).fetchone()["c"]
                    or 0
                )
                if pending:
                    flash(
                        f"{pending} knowledge submission{'s' if pending != 1 else ''} waiting for approval. Open Governance to review.",
                        "warning",
                    )
                    if not nxt:
                        return redirect(url_for("admin.moderation"))
            return redirect(nxt or post_login_redirect_url(user))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/login/guest", methods=["POST"])
def login_guest():
    """Read-only guest session — browse Knowledge, Domain Knowledge, Journey, and KYC only."""
    from mine.guest import GUEST_USERNAME, ensure_guest_user, guest_may_visit_path

    if load_current_user():
        return redirect(post_login_redirect_url(load_current_user()))

    ensure_guest_user()
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE lower(trim(username)) = ? AND role = 'guest' AND is_active = 1",
        (GUEST_USERNAME,),
    ).fetchone()
    if not user:
        flash("Guest access is not available right now.", "danger")
        return redirect(url_for("auth.login"))

    session.clear()
    session["user_id"] = user["id"]
    log_audit(user["id"], "login_guest", "user", user["id"], None)
    db.commit()
    flash("Signed in as Guest — view-only access to selected knowledge pages.", "success")
    nxt = safe_login_next(request.form.get("next") or request.args.get("next"))
    if nxt and not guest_may_visit_path(nxt):
        nxt = None
    return redirect(nxt or post_login_redirect_url(user))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    user = load_current_user()
    log_audit(user["id"], "logout", "user", user["id"], None)
    get_db().commit()
    session.pop("user_id", None)
    session.pop("security_questions_ok", None)
    session.pop("force_security_questions", None)
    session.pop("post_login_next", None)
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Step 1: identify account by username."""
    if load_current_user():
        return redirect(post_login_redirect_url(load_current_user()))
    _clear_forgot_session()
    form = ForgotUsernameForm()
    if form.validate_on_submit():
        db = get_db()
        uname = form.username.data.strip().lower()
        user = db.execute(
            "SELECT id, username, role, is_active FROM users WHERE lower(trim(username)) = ?",
            (uname,),
        ).fetchone()
        # Generic messaging — avoid confirming whether the username exists.
        generic = (
            "If this account has security questions set up, you’ll be asked one next. "
            "Otherwise contact an admin to reset your password."
        )
        if (
            not user
            or not user["is_active"]
            or (user["role"] or "").strip().lower() == "guest"
            or not user_has_security_answers(db, user["id"])
        ):
            flash(generic, "info")
            return redirect(url_for("auth.login"))
        challenge = pick_challenge_question(db, user["id"])
        if not challenge:
            flash(generic, "info")
            return redirect(url_for("auth.login"))
        session["forgot_user_id"] = int(user["id"])
        session["forgot_username"] = user["username"]
        session["forgot_question_id"] = challenge["question_id"]
        session["forgot_verified"] = False
        session["forgot_attempts"] = 0
        log_audit(user["id"], "password_reset_requested", "user", user["id"], None)
        db.commit()
        return redirect(url_for("auth.forgot_password_challenge"))
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/forgot-password/challenge", methods=["GET", "POST"])
def forgot_password_challenge():
    """Step 2: answer one security question (1 of 3 is enough)."""
    if load_current_user():
        return redirect(post_login_redirect_url(load_current_user()))
    uid = session.get("forgot_user_id")
    qid = session.get("forgot_question_id")
    if not uid or not qid or session.get("forgot_verified"):
        flash("Start password recovery again.", "warning")
        return redirect(url_for("auth.forgot_password"))

    attempts = int(session.get("forgot_attempts") or 0)
    if attempts >= _FORGOT_MAX_ATTEMPTS:
        _clear_forgot_session()
        flash("Too many incorrect attempts. Try again later or contact an admin.", "danger")
        return redirect(url_for("auth.login"))

    form = ForgotChallengeForm()
    prompt = question_prompt(qid)
    if form.validate_on_submit():
        db = get_db()
        if verify_user_answer(db, int(uid), qid, form.answer.data or ""):
            session["forgot_verified"] = True
            session.pop("forgot_question_id", None)
            session["forgot_attempts"] = 0
            log_audit(int(uid), "password_reset_verified", "user", int(uid), None)
            db.commit()
            flash("Answer verified. Choose a new password.", "success")
            return redirect(url_for("auth.forgot_password_reset"))
        attempts += 1
        session["forgot_attempts"] = attempts
        remaining = _FORGOT_MAX_ATTEMPTS - attempts
        # Rotate to another question after a miss.
        nxt = pick_challenge_question(db, int(uid), avoid_id=qid)
        if nxt:
            session["forgot_question_id"] = nxt["question_id"]
            prompt = nxt["prompt"]
        if remaining <= 0:
            _clear_forgot_session()
            flash("Too many incorrect attempts. Try again later or contact an admin.", "danger")
            return redirect(url_for("auth.login"))
        flash(f"That answer didn’t match. {remaining} attempt{'s' if remaining != 1 else ''} left.", "danger")
        form = ForgotChallengeForm()
    return render_template(
        "auth/forgot_password_challenge.html",
        form=form,
        prompt=prompt,
        username=session.get("forgot_username") or "",
    )


@bp.route("/forgot-password/reset", methods=["GET", "POST"])
def forgot_password_reset():
    """Step 3: set a new password after a correct security answer."""
    if load_current_user():
        return redirect(post_login_redirect_url(load_current_user()))
    uid = session.get("forgot_user_id")
    if not uid or not session.get("forgot_verified"):
        flash("Verify a security question before resetting your password.", "warning")
        return redirect(url_for("auth.forgot_password"))

    form = ForgotResetForm()
    if form.validate_on_submit():
        db = get_db()
        user = db.execute(
            "SELECT id, is_active, role FROM users WHERE id = ?",
            (int(uid),),
        ).fetchone()
        if not user or not user["is_active"] or (user["role"] or "").strip().lower() == "guest":
            _clear_forgot_session()
            flash("This account cannot be reset.", "danger")
            return redirect(url_for("auth.login"))
        new_hash = bcrypt.hashpw(form.new_password.data.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, int(uid)))
        log_audit(int(uid), "password_reset_completed", "user", int(uid), None)
        db.commit()
        _clear_forgot_session()
        flash("Password updated. Sign in with your new password.", "success")
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/forgot_password_reset.html",
        form=form,
        username=session.get("forgot_username") or "",
    )


@bp.route("/account/security-questions", methods=["GET", "POST"])
@login_required
def account_security_questions():
    """Enroll or update the three security questions used for password recovery."""
    user = load_current_user()
    if user and (user["role"] or "").strip().lower() == "guest":
        flash("Guest accounts cannot set security questions.", "warning")
        return redirect(url_for("main.knowledge"))

    db = get_db()
    existing = list_user_answers(db, user["id"])
    enrolled = user_has_security_answers(db, user["id"])
    forced = bool(session.get("force_security_questions")) or (
        request.args.get("setup") == "1" and not enrolled
    )
    form = _security_questions_form(existing if enrolled and not forced else None)
    if form.validate_on_submit():
        try:
            pairs = [
                (form.question_1.data, form.answer_1.data),
                (form.question_2.data, form.answer_2.data),
                (form.question_3.data, form.answer_3.data),
            ]
            save_user_answers(db, user["id"], pairs)
            log_audit(user["id"], "security_questions_saved", "user", user["id"], None)
            db.commit()
            session["security_questions_ok"] = True
            session.pop("force_security_questions", None)
            flash("Security questions saved. You can use Forgot password on the sign-in page.", "success")
            nxt = safe_login_next(session.pop("post_login_next", None))
            if nxt:
                return redirect(nxt)
            if forced:
                return redirect(post_login_redirect_url(user))
            if user["role"] == "admin":
                return redirect(url_for("admin.settings"))
            return redirect(url_for("auth.account_settings"))
        except ValueError as exc:
            flash(str(exc), "danger")
    enrolled = user_has_security_answers(db, user["id"])
    return render_template(
        "auth/security_questions.html",
        form=form,
        enrolled=enrolled,
        forced=forced and not enrolled,
        is_admin=(user["role"] == "admin"),
    )


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
    db = get_db()
    enrolled = user_has_security_answers(db, user["id"]) if user else False
    return render_template("auth/account_settings.html", security_enrolled=enrolled)


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
