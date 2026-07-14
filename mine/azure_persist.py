"""Azure App Service layout: wwwroot from git push; knowledge artefacts dual-persisted.

UI, static assets, images, projects config, and the live wwwroot DB/uploads come
from local ``git push``. Knowledge-repository artefacts also mirror under
``/home/data/mine/knowledge`` so website uploads survive the next deploy.
"""

from __future__ import annotations

import os
from pathlib import Path

_AZURE_WWWROOT = Path("/home/site/wwwroot")
_LEGACY_HOME_DATA_PREFIXES = (
    "/home/data/mine",
    "/home/data/mine/",
)


def is_azure_app_service() -> bool:
    return bool((os.environ.get("WEBSITE_SITE_NAME") or "").strip())


def is_legacy_home_data_path(raw: str | None) -> bool:
    """True when portal still points at the old full-store under /home/data/mine."""
    text = (raw or "").strip().replace("\\", "/").rstrip("/")
    if not text:
        return False
    lowered = text.lower()
    return lowered == "/home/data/mine" or lowered.startswith("/home/data/mine/")


def wwwroot_database_path() -> Path:
    return _AZURE_WWWROOT / "mine.db"


def wwwroot_upload_folder() -> Path:
    return _AZURE_WWWROOT / "uploads"


def ensure_azure_persistent_storage(app) -> None:
    """Prepare knowledge sidecar dirs; live DB/uploads stay on wwwroot (git)."""
    if not is_azure_app_service():
        return

    from mine.knowledge_persist import ensure_knowledge_persist_dirs, knowledge_persist_root

    ensure_knowledge_persist_dirs()
    app.logger.info(
        "Azure data policy: live DATABASE=%s UPLOAD_FOLDER=%s (from git deploy); "
        "knowledge artefacts also mirrored at %s",
        app.config.get("DATABASE"),
        app.config.get("UPLOAD_FOLDER"),
        knowledge_persist_root(),
    )
