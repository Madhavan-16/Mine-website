import os
from datetime import timedelta
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent


def _default_data_path(env_key: str) -> Path:
    """Local and Azure defaults: project root (wwwroot on App Service = git deploy)."""
    if env_key == "DATABASE_PATH":
        return _BASE_DIR / "mine.db"
    return _BASE_DIR / "uploads"


def _resolve_path(env_key: str, default: Path) -> str:
    """Honor DATABASE_PATH / UPLOAD_FOLDER when set; ignore legacy /home/data/mine paths on Azure."""
    raw = (os.environ.get(env_key) or "").strip()
    try:
        from mine.azure_persist import is_azure_app_service, is_legacy_home_data_path
    except ImportError:
        is_azure_app_service = lambda: False  # noqa: E731
        is_legacy_home_data_path = lambda _p: False  # noqa: E731

    if is_azure_app_service() and is_legacy_home_data_path(raw):
        # Old portal settings pointed the whole site at /home/data — ignore so local push wins.
        p = default
    else:
        p = Path(raw) if raw else default
    if not p.is_absolute():
        p = (_BASE_DIR / p).resolve()
    else:
        p = p.resolve()
    return str(p)


class Config:
    BASE_DIR = _BASE_DIR
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    # Used when "Remember me" is checked on sign-in.
    PERMANENT_SESSION_LIFETIME = timedelta(
        days=int(os.environ.get("PERMANENT_SESSION_DAYS", "30"))
    )
    DATABASE = _resolve_path("DATABASE_PATH", _default_data_path("DATABASE_PATH"))
    UPLOAD_FOLDER = _resolve_path("UPLOAD_FOLDER", _default_data_path("UPLOAD_FOLDER"))
    _team_roster = (os.environ.get("TEAM_ROSTER_XLSX") or "").strip()
    TEAM_ROSTER_XLSX = _team_roster or str(_BASE_DIR / "data" / "Freeport active resource Tracker - Updated.xlsx")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
    ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "png", "jpg", "jpeg", "ppt", "pptx"}
    # PowerPoint in-browser preview uses Microsoft Office Online; the signed file URL must be HTTPS and reachable from the internet.
    ENABLE_OFFICE_EMBED_PREVIEW = os.environ.get("ENABLE_OFFICE_EMBED_PREVIEW", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    # If true, still build Office embed URLs on localhost/http/private hosts (usually broken in the iframe).
    OFFICE_EMBED_SKIP_REACHABILITY_CHECK = os.environ.get(
        "OFFICE_EMBED_SKIP_REACHABILITY_CHECK", "0"
    ).lower() in ("1", "true", "yes")
    # When LibreOffice is installed (soffice), convert Office uploads to PDF for in-browser preview.
    # Original files are always kept; downloads serve the uploaded file.
    ENABLE_OFFICE_PDF_PREVIEW = os.environ.get("ENABLE_OFFICE_PDF_PREVIEW", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    ENABLE_SLIDE_PREVIEW = os.environ.get("ENABLE_SLIDE_PREVIEW", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    SLIDE_PREVIEW_SCALE = float(os.environ.get("SLIDE_PREVIEW_SCALE", "2.0"))
    # On startup, convert existing Office attachments to PDF when LibreOffice is available.
    BACKFILL_ATTACHMENT_PREVIEWS = os.environ.get("BACKFILL_ATTACHMENT_PREVIEWS", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None

    # --- Outbound email (SMTP). Disabled by default. ---
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "0").lower() in ("1", "true", "yes")
    # When true, send_email appends to MAIL_DUMMY_PATH instead of using SMTP (local/dev only).
    MAIL_DUMMY = os.environ.get("MAIL_DUMMY", "0").lower() in ("1", "true", "yes")
    _mail_dummy_path = (os.environ.get("MAIL_DUMMY_PATH") or "").strip()
    MAIL_DUMMY_PATH = _mail_dummy_path or str(BASE_DIR / "logs" / "mail-outbox.log")
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    # Implicit TLS (e.g. port 465). If true, STARTTLS is not used.
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "0").lower() in ("1", "true", "yes")
    # STARTTLS after connect (typical on port 587). Ignored when MAIL_USE_SSL is true.
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1").lower() not in ("0", "false", "no")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "").strip()
    MAIL_SMTP_TIMEOUT = int(os.environ.get("MAIL_SMTP_TIMEOUT", "30"))
    # When true, pending submissions also email admins/moderators (in addition to in-app notifications).
    MAIL_NOTIFY_ON_PENDING = os.environ.get("MAIL_NOTIFY_ON_PENDING", "0").lower() in ("1", "true", "yes")
    # Optional extra allowed recipients for the admin "Send email" screen (comma-separated), e.g. team aliases.
    MAIL_EXTRA_ALLOWLIST = frozenset(
        x.strip().lower()
        for x in (os.environ.get("MAIL_EXTRA_ALLOWLIST", "") or "").split(",")
        if x.strip()
    )
    # When true (default), admin "Send email" accepts any syntactically valid address (like a normal mail client).
    # Set MAIL_OPEN_RECIPIENTS=0 to restrict to active MiNe users plus MAIL_EXTRA_ALLOWLIST only.
    MAIL_OPEN_RECIPIENTS = os.environ.get("MAIL_OPEN_RECIPIENTS", "1").lower() not in ("0", "false", "no")
    # Verbose SMTP protocol log to stderr (development only).
    MAIL_SMTP_DEBUG = os.environ.get("MAIL_SMTP_DEBUG", "0").lower() in ("1", "true", "yes")

    # --- Microsoft Graph / Outlook mailbox integration (OAuth2 Authorization Code) ---
    # Enable Graph mailbox routes and OAuth connect flow.
    MS_GRAPH_ENABLED = os.environ.get("MS_GRAPH_ENABLED", "0").lower() in ("1", "true", "yes")
    # App registration details from Microsoft Entra ID.
    MS_CLIENT_ID = (os.environ.get("MS_CLIENT_ID") or "").strip()
    MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")
    # Use "common" for org + personal Microsoft accounts.
    MS_TENANT = (os.environ.get("MS_TENANT") or "common").strip()
    # OAuth callback route path (must match app registration redirect URI path).
    MS_REDIRECT_PATH = (os.environ.get("MS_REDIRECT_PATH") or "/admin/mailbox/oauth/callback").strip()
    # Encryption key for token at-rest protection (Fernet base64 key).
    MS_TOKEN_ENCRYPTION_KEY = (os.environ.get("MS_TOKEN_ENCRYPTION_KEY") or "").strip()
    # Optional comma-separated scope override; defaults are delegated mailbox scopes.
    _ms_scopes_raw = (os.environ.get("MS_GRAPH_SCOPES") or "").strip()
    MS_GRAPH_SCOPES = tuple(
        s.strip()
        for s in (_ms_scopes_raw.split(",") if _ms_scopes_raw else [])
        if s.strip()
    ) or (
        "openid",
        "profile",
        "offline_access",
        "User.Read",
        "Mail.ReadWrite",
        "Mail.Send",
    )
    # Optional Graph API override; defaults to v1 endpoint.
    MS_GRAPH_BASE_URL = (os.environ.get("MS_GRAPH_BASE_URL") or "https://graph.microsoft.com/v1.0").strip()

    # SharePoint / Teams training folder → Ask MiNe knowledge (app-only Graph).
    SHAREPOINT_KB_ENABLED = os.environ.get("SHAREPOINT_KB_ENABLED", "0").lower() in ("1", "true", "yes")
    SHAREPOINT_KB_FOLDER_URL = (os.environ.get("SHAREPOINT_KB_FOLDER_URL") or "").strip()
    SHAREPOINT_KB_SYNC_ON_STARTUP = os.environ.get("SHAREPOINT_KB_SYNC_ON_STARTUP", "0").lower() in (
        "1",
        "true",
        "yes",
    )
    SHAREPOINT_KB_SYNC_INTERVAL_HOURS = float(os.environ.get("SHAREPOINT_KB_SYNC_INTERVAL_HOURS", "6") or 6)
    SHAREPOINT_KB_MAX_FILES = int(os.environ.get("SHAREPOINT_KB_MAX_FILES", "200") or 200)
    SHAREPOINT_KB_MAX_FILE_MB = float(os.environ.get("SHAREPOINT_KB_MAX_FILE_MB", "25") or 25)
    # Optional local mirror of the Teams folder (indexed without Graph).
    SHAREPOINT_KB_LOCAL_DIR = (os.environ.get("SHAREPOINT_KB_LOCAL_DIR") or "data/teams_training").strip()

    # Knowledge chatbot (FTS + optional free-tier LLM: Groq or Gemini).
    CHATBOT_ENABLED = os.environ.get("CHATBOT_ENABLED", "1").lower() not in ("0", "false", "no")
    # Provider: auto | groq | gemini | none
    CHATBOT_LLM_PROVIDER = (os.environ.get("CHATBOT_LLM_PROVIDER") or "auto").strip().lower()
    GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
    GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
    # Defaults: Groq llama-3.1-8b-instant · Gemini gemini-2.0-flash
    CHATBOT_LLM_MODEL = (os.environ.get("CHATBOT_LLM_MODEL") or "").strip()
    CHATBOT_LLM_TIMEOUT = float(os.environ.get("CHATBOT_LLM_TIMEOUT", "60") or 60)
