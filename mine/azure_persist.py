"""Azure App Service: persistent /home/data paths and one-time wwwroot migration."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_AZURE_WWWROOT = Path("/home/site/wwwroot")
_AZURE_DATA = Path("/home/data")
_AZURE_DATA_DB = _AZURE_DATA / "mine.db"
_AZURE_DATA_UPLOADS = _AZURE_DATA / "uploads"


def is_azure_app_service() -> bool:
    return bool((os.environ.get("WEBSITE_SITE_NAME") or "").strip())


def azure_default_database_path() -> Path:
    return _AZURE_DATA_DB


def azure_default_upload_folder() -> Path:
    return _AZURE_DATA_UPLOADS


def _copy_upload_tree(source: Path, dest: Path) -> int:
    copied = 0
    if not source.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name == ".gitkeep":
            continue
        target = dest / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        copied += 1
    return copied


def ensure_azure_persistent_storage(app) -> None:
    """
    On Azure App Service:
    - Ensure DATABASE_PATH and UPLOAD_FOLDER exist under /home/data (via Config defaults).
    - Copy legacy mine.db / uploads from wwwroot once if persistent copies are empty.
    """
    if not is_azure_app_service():
        return

    db_path = Path(app.config["DATABASE"])
    upload_dir = Path(app.config["UPLOAD_FOLDER"])

    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    legacy_db = _AZURE_WWWROOT / "mine.db"
    if legacy_db.is_file() and not db_path.is_file():
        logger.info("Azure: migrating database %s -> %s", legacy_db, db_path)
        shutil.copy2(legacy_db, db_path)

    legacy_uploads = _AZURE_WWWROOT / "uploads"
    has_persistent_uploads = any(upload_dir.iterdir()) if upload_dir.is_dir() else False
    if legacy_uploads.is_dir() and not has_persistent_uploads:
        n = _copy_upload_tree(legacy_uploads, upload_dir)
        if n:
            logger.info(
                "Azure: migrated %s upload file(s) from %s to %s",
                n,
                legacy_uploads,
                upload_dir,
            )

    app.logger.info(
        "Azure persistent storage: DATABASE_PATH=%s UPLOAD_FOLDER=%s",
        db_path,
        upload_dir,
    )
