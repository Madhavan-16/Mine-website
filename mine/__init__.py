from pathlib import Path

from dotenv import load_dotenv

# Load `.env` before `Config` is imported — class attributes read os.environ at import time.
load_dotenv()

from flask import Flask
from flask_wtf.csrf import CSRFProtect, generate_csrf

from mine.config import Config
from mine.db import (
    ensure_attachment_preview_column,
    ensure_attachment_slide_preview_column,
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
    from mine.azure_persist import ensure_azure_persistent_storage

    ensure_azure_persistent_storage(app)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db_init_app(app)
    csrf.init_app(app)
    app.jinja_env.globals["csrf_token"] = generate_csrf

    from mine import admin, auth, content, main, projects, reference, repo_standalone, search

    app.register_blueprint(auth.bp)
    app.register_blueprint(reference.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(content.bp)
    app.register_blueprint(repo_standalone.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(admin.bp)
    if app.config.get("MS_GRAPH_ENABLED"):
        from mine import mailbox

        app.register_blueprint(mailbox.bp)

    @app.context_processor
    def inject_nav():
        from mine.auth_utils import load_current_user

        user = load_current_user()
        notifs = []
        n_unread = 0
        if user:
            db = get_db()
            n_unread = db.execute(
                "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
                (user["id"],),
            ).fetchone()["c"]
            notifs = db.execute(
                """
                SELECT * FROM notifications
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 6
                """,
                (user["id"],),
            ).fetchall()
        return dict(current_user=user, notif_count=n_unread, notifs_recent=notifs)

    with app.app_context():
        if not Path(app.config["DATABASE"]).exists():
            init_db()
        from mine.seed import seed_if_empty

        # Ensure default admin exists whenever the users table is empty (not only on first DB file creation).
        seed_if_empty()
        ensure_attachment_preview_column()
        ensure_attachment_slide_preview_column()
        ensure_user_mail_tokens_table()
        from mine.upload_paths import normalize_attachment_paths_in_db

        try:
            normalize_attachment_paths_in_db(get_db())
        except Exception:
            app.logger.exception("Attachment path normalization failed on startup")

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
