"""Azure App Service: persistent data outside wwwroot so git deploys don't wipe content."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_AZURE_WWWROOT = Path("/home/site/wwwroot")
# /home persists across App Service git/zip deploys; wwwroot is replaced.
_AZURE_PERSIST_ROOT = Path("/home/data/mine")


def is_azure_app_service() -> bool:
    return bool((os.environ.get("WEBSITE_SITE_NAME") or "").strip())


def azure_persist_root() -> Path:
    raw = (os.environ.get("MINE_AZURE_DATA_ROOT") or "").strip()
    if raw:
        return Path(raw)
    return _AZURE_PERSIST_ROOT


def azure_default_database_path() -> Path:
    return azure_persist_root() / "mine.db"


def azure_default_upload_folder() -> Path:
    return azure_persist_root() / "uploads"


def _copy_file_if_needed(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    if dest.is_file() and dest.stat().st_size > 0:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _merge_tree(src: Path, dest: Path) -> int:
    """Copy files from src into dest without overwriting existing files. Returns files copied."""
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_dir = dest / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            s = Path(root) / name
            d = target_dir / name
            if d.exists():
                continue
            shutil.copy2(s, d)
            copied += 1
    return copied


def migrate_wwwroot_data_into_persistent(app) -> None:
    """
    One-time / safe catch-up: if persistent store is empty, seed from wwwroot
    (git-deployed or previously live site data under the app folder).
    Never overwrites an existing persistent database.
    """
    if not is_azure_app_service():
        return

    db_path = Path(app.config["DATABASE"])
    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    www_db = _AZURE_WWWROOT / "mine.db"
    www_uploads = _AZURE_WWWROOT / "uploads"

    migrated = []
    if _copy_file_if_needed(www_db, db_path):
        migrated.append(f"database from {www_db}")

    n_files = _merge_tree(www_uploads, upload_dir)
    if n_files:
        migrated.append(f"{n_files} upload file(s) from {www_uploads}")

    if migrated:
        app.logger.info("Azure persistent data seeded: %s", "; ".join(migrated))


def ensure_azure_persistent_storage(app) -> None:
    """Ensure persistent directories exist and seed from wwwroot when appropriate."""
    if not is_azure_app_service():
        return

    db_path = Path(app.config["DATABASE"])
    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    migrate_wwwroot_data_into_persistent(app)

    app.logger.info(
        "Azure persistent data: DATABASE=%s UPLOAD_FOLDER=%s (survives git deploy)",
        db_path,
        upload_dir,
    )
