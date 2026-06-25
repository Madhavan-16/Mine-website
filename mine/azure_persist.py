"""Azure App Service: ensure git-deployed data directories exist."""

from __future__ import annotations

import os
from pathlib import Path

_AZURE_WWWROOT = Path("/home/site/wwwroot")


def is_azure_app_service() -> bool:
    return bool((os.environ.get("WEBSITE_SITE_NAME") or "").strip())


def ensure_azure_persistent_storage(app) -> None:
    """On Azure App Service, ensure mine.db and uploads/ directories exist under wwwroot."""
    if not is_azure_app_service():
        return

    db_path = Path(app.config["DATABASE"])
    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ignored = []
    for key in ("DATABASE_PATH", "UPLOAD_FOLDER"):
        portal_val = (os.environ.get(key) or "").strip()
        if portal_val and portal_val.replace("\\", "/") != str(
            db_path if key == "DATABASE_PATH" else upload_dir
        ).replace("\\", "/"):
            ignored.append(f"{key}={portal_val}")

    if ignored:
        app.logger.warning(
            "Azure git-deploy mode: ignoring portal data path(s) %s — using DATABASE=%s UPLOAD_FOLDER=%s",
            ", ".join(ignored),
            db_path,
            upload_dir,
        )
    else:
        app.logger.info(
            "Azure data paths: DATABASE=%s UPLOAD_FOLDER=%s",
            db_path,
            upload_dir,
        )
