"""Resolve stored attachment paths to absolute files on disk."""

from __future__ import annotations

import os
from pathlib import Path

from flask import current_app


def config_upload_folder() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]).resolve()


def config_base_dir() -> Path:
    return Path(current_app.config.get("BASE_DIR", Path.cwd())).resolve()


def resolve_stored_upload_path(stored: str | None) -> str | None:
    """
    Turn a DB-stored file_path / preview_path into an absolute path that exists.

    Legacy rows may store relative paths like ``uploads/<uuid>_file.pptx`` while
    Werkzeug resolves relatives from the blueprint package dir — normalize here.
    """
    if not stored or not str(stored).strip():
        return None

    raw = str(stored).strip()
    p = Path(raw)
    upload_root = config_upload_folder()
    base_dir = config_base_dir()

    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.extend(
            [
                Path.cwd() / p,
                base_dir / p,
                upload_root / p.name,
                upload_root / p,
            ]
        )

    seen: set[str] = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return str(resolved)
    return None


def normalize_stored_upload_path(stored: str | None) -> str | None:
    """Return canonical absolute path for DB storage, or None if missing."""
    resolved = resolve_stored_upload_path(stored)
    if resolved:
        return resolved
    if not stored or not str(stored).strip():
        return None
    p = Path(str(stored).strip())
    if p.is_absolute():
        return str(p)
    return str((config_base_dir() / p).resolve())


def normalize_attachment_paths_in_db(db) -> int:
    """Fix legacy relative attachment paths in SQLite. Returns rows updated."""
    rows = db.execute("SELECT id, file_path, preview_path FROM attachments").fetchall()
    updated = 0
    for row in rows:
        changes: dict[str, str] = {}
        for col in ("file_path", "preview_path"):
            raw = row[col]
            if not raw:
                continue
            canonical = normalize_stored_upload_path(raw)
            if canonical and canonical != raw and os.path.isfile(canonical):
                changes[col] = canonical
        if changes:
            if "file_path" in changes:
                db.execute(
                    "UPDATE attachments SET file_path = ? WHERE id = ?",
                    (changes["file_path"], row["id"]),
                )
            if "preview_path" in changes:
                db.execute(
                    "UPDATE attachments SET preview_path = ? WHERE id = ?",
                    (changes["preview_path"], row["id"]),
                )
            updated += 1
    if updated:
        db.commit()
    return updated
