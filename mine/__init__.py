from pathlib import Path
import os

from dotenv import load_dotenv

# Load `.env` before `Config` is imported — class attributes read os.environ at import time.
load_dotenv()

from flask import Flask
from flask_wtf.csrf import CSRFProtect, generate_csrf

from mine.config import Config
from mine.db import (
    ensure_attachment_preview_column,
    ensure_attachment_slide_preview_column,
    ensure_notifications_scope,
    ensure_projects_is_active_column,
    ensure_security_questions_table,
    ensure_sharepoint_docs_table,
    ensure_user_mail_tokens_table,
    get_db,
    init_app as db_init_app,
    init_db,
)

csrf = CSRFProtect()


def create_app():
    load_dotenv()
    base_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )
    app.config.from_object(Config)
    # Re-read LLM secrets from process env so Azure App Settings always win
    # (Config class attrs are fixed at first import).
    for key in (
        "CHATBOT_LLM_PROVIDER",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "CHATBOT_LLM_MODEL",
        "CHATBOT_LLM_TIMEOUT",
        "CHATBOT_ENABLED",
    ):
        if key in os.environ:
            raw = (os.environ.get(key) or "").strip()
            if key == "CHATBOT_LLM_PROVIDER":
                app.config[key] = (raw or "auto").lower()
            elif key == "CHATBOT_ENABLED":
                app.config[key] = raw.lower() not in ("0", "false", "no")
            elif key == "CHATBOT_LLM_TIMEOUT":
                try:
                    app.config[key] = float(raw or 45)
                except ValueError:
                    app.config[key] = 45.0
            else:
                app.config[key] = raw
    from mine.azure_persist import ensure_azure_persistent_storage

    ensure_azure_persistent_storage(app)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db_init_app(app)
    csrf.init_app(app)
    app.jinja_env.globals["csrf_token"] = generate_csrf

    from mine import admin, auth, chatbot, content, main, projects, reference, repo_standalone, search

    app.register_blueprint(auth.bp)
    app.register_blueprint(reference.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(content.bp)
    app.register_blueprint(repo_standalone.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(chatbot.bp)
    if app.config.get("MS_GRAPH_ENABLED"):
        from mine import mailbox

        app.register_blueprint(mailbox.bp)

    @app.context_processor
    def inject_nav():
        from mine.auth_utils import load_current_user
        from mine.catalog_modules import MODULE_LABELS, SEARCH_FILTER_MODULES, module_label
        from mine.guest import is_guest_user
        from mine.services import count_read_notifications, count_unread_notifications, get_user_notifications

        user = load_current_user()
        notifs = []
        n_unread = 0
        n_read = 0
        pending_moderation = None
        if user and not is_guest_user(user):
            uid = user["id"]
            n_unread = count_unread_notifications(uid)
            n_read = count_read_notifications(uid)
            notifs = get_user_notifications(uid, limit=6)
            if user["role"] in ("admin", "moderator"):
                pending_moderation = int(
                    get_db()
                    .execute("SELECT COUNT(*) AS c FROM content WHERE status = 'pending'")
                    .fetchone()["c"]
                    or 0
                )
        return dict(
            current_user=user,
            is_guest=is_guest_user(user),
            notif_count=n_unread,
            notif_read_count=n_read,
            notifs_recent=notifs,
            pending_moderation=pending_moderation,
            module_labels=MODULE_LABELS,
            module_label=module_label,
            search_filter_modules=SEARCH_FILTER_MODULES,
        )

    @app.before_request
    def enforce_guest_access():
        from flask import flash, redirect, request, url_for

        from mine.auth_utils import load_current_user
        from mine.guest import GUEST_ALLOWED_ENDPOINTS, is_guest_user

        user = load_current_user()
        if not is_guest_user(user):
            return None
        endpoint = request.endpoint or ""
        if endpoint in GUEST_ALLOWED_ENDPOINTS or endpoint.startswith("static"):
            return None
        flash("Guest accounts can only view Knowledge, Domain Knowledge, Journey, and Know your Customer.", "warning")
        return redirect(url_for("main.knowledge"))

    @app.before_request
    def enforce_security_questions_setup():
        """First login after feature: require 3 security questions before using the portal."""
        from flask import redirect, request, session, url_for

        from mine.auth_utils import load_current_user
        from mine.db import get_db
        from mine.guest import is_guest_user
        from mine.security_questions import user_has_security_answers

        if request.endpoint and (
            request.endpoint.startswith("static")
            or request.endpoint in (
                "auth.login",
                "auth.login_guest",
                "auth.logout",
                "auth.forgot_password",
                "auth.forgot_password_challenge",
                "auth.forgot_password_reset",
                "auth.account_security_questions",
            )
        ):
            return None

        user = load_current_user()
        if not user or is_guest_user(user):
            return None

        # Session cache so we don't hit SQLite on every request after setup.
        if session.get("security_questions_ok"):
            return None

        try:
            enrolled = user_has_security_answers(get_db(), int(user["id"]))
        except Exception:
            return None

        if enrolled:
            session["security_questions_ok"] = True
            return None

        session["force_security_questions"] = True
        return redirect(url_for("auth.account_security_questions", setup=1))

    with app.app_context():
        if not Path(app.config["DATABASE"]).exists():
            init_db()
        from mine.seed import seed_if_empty

        # Ensure default admin exists whenever the users table is empty (not only on first DB file creation).
        seed_if_empty()
        try:
            from mine.guest import ensure_guest_user

            ensure_guest_user()
        except Exception:
            app.logger.exception("Guest user ensure failed on startup")
        ensure_attachment_preview_column()
        ensure_attachment_slide_preview_column()
        ensure_notifications_scope()
        ensure_user_mail_tokens_table()
        ensure_projects_is_active_column()
        try:
            ensure_security_questions_table()
        except Exception:
            app.logger.exception("security questions table ensure failed on startup")
        try:
            ensure_sharepoint_docs_table()
        except Exception:
            app.logger.exception("sharepoint_docs table ensure failed on startup")
        from mine.fts import ensure_content_fts
        from mine.upload_paths import normalize_attachment_paths_in_db

        try:
            ensure_content_fts(get_db())
        except Exception:
            app.logger.exception("content_fts ensure/rebuild failed on startup")

        try:
            normalize_attachment_paths_in_db(get_db())
        except Exception:
            app.logger.exception("Attachment path normalization failed on startup")

        try:
            from mine.knowledge_persist import merge_knowledge_persist_into_live

            merge_knowledge_persist_into_live(app)
        except Exception:
            app.logger.exception("Knowledge persist merge failed on startup")

        if app.config.get("SHAREPOINT_KB_ENABLED") and app.config.get("SHAREPOINT_KB_SYNC_ON_STARTUP"):
            try:
                from mine.sharepoint_kb import sharepoint_kb_ready, sync_sharepoint_folder

                if sharepoint_kb_ready(app):
                    result = sync_sharepoint_folder(app, force=False)
                    app.logger.info("SharePoint KB sync on startup: %s", result)
            except Exception:
                app.logger.exception("SharePoint KB sync on startup failed")

        if app.config.get("BACKFILL_ATTACHMENT_PREVIEWS", True):
            try:
                from mine.preview_backfill import (
                    backfill_missing_pdf_previews,
                    backfill_missing_slide_previews,
                )

                pdf_result = backfill_missing_pdf_previews(get_db(), app.config["UPLOAD_FOLDER"])
                if pdf_result.get("converted"):
                    app.logger.info("Attachment PDF preview backfill: %s", pdf_result)
                if app.config.get("ENABLE_SLIDE_PREVIEW", True):
                    from mine.slide_preview import slide_export_available

                    if slide_export_available():
                        slide_result = backfill_missing_slide_previews(
                            get_db(),
                            app.config["UPLOAD_FOLDER"],
                            scale=float(app.config.get("SLIDE_PREVIEW_SCALE", 2.0)),
                        )
                        if slide_result.get("converted"):
                            app.logger.info("Attachment slide preview backfill: %s", slide_result)
            except Exception:
                app.logger.exception("Attachment preview backfill failed on startup")

    return app
