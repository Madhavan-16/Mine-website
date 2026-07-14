"""Resolve stored attachment paths to absolute files on disk."""

from __future__ import annotations

import os
from pathlib import Path

from flask import current_app


def config_upload_folder() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]).resolve()


def config_base_dir() -> Path:
    return Path(current_app.config.get("BASE_DIR", Path.cwd())).resolve()


def to_portable_upload_path(absolute: str | Path) -> str:
    """
    Store paths relative to the project root so the same DB works locally and on Azure.

    Examples: uploads/abc_file.pptx, uploads/.slide_previews/12
    """
    p = Path(absolute).resolve()
    base = config_base_dir()
    upload_root = config_upload_folder()
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        pass
    try:
        rel = p.relative_to(upload_root)
        return f"uploads/{rel.as_posix()}"
    except ValueError:
        return f"uploads/{p.name}"


def resolve_stored_upload_path(stored: str | None) -> str | None:
    """
    Turn a DB-stored file_path / preview_path into an absolute path that exists.

    Legacy rows may store absolute Windows paths or relative paths like
    ``uploads/<uuid>_file.pptx``.
    """
    return resolve_stored_path(stored, kind="file")


def resolve_stored_path(stored: str | None, *, kind: str = "any") -> str | None:
    """Resolve a portable or legacy stored path to an absolute file or directory."""
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
        # Prefer upload root for portable "uploads/..." paths (esp. Azure /home/data/mine/uploads).
        rel = p.as_posix().lstrip("./")
        if rel.startswith("uploads/"):
            under_upload = rel[len("uploads/") :]
            candidates.append(upload_root / under_upload)
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
        if kind == "file" and resolved.is_file():
            return str(resolved)
        if kind == "dir" and resolved.is_dir():
            return str(resolved)
        if kind == "any" and (resolved.is_file() or resolved.is_dir()):
            return str(resolved)
    return None


def normalize_stored_upload_path(stored: str | None) -> str | None:
    """Return canonical portable path for DB storage, or None if missing."""
    resolved = resolve_stored_upload_path(stored)
    if resolved:
        return to_portable_upload_path(resolved)
    if not stored or not str(stored).strip():
        return None
    raw = str(stored).strip()
    p = Path(raw)
    if p.is_absolute():
        if os.path.isfile(p):
            return to_portable_upload_path(p)
        return None
    return raw.replace("\\", "/")


def normalize_stored_dir_path(stored: str | None) -> str | None:
    """Return canonical portable directory path for DB storage."""
    resolved = resolve_stored_path(stored, kind="dir")
    if resolved:
        return to_portable_upload_path(resolved)
    if not stored or not str(stored).strip():
        return None
    raw = str(stored).strip().replace("\\", "/")
    p = Path(raw)
    if p.is_absolute():
        return None
    return raw


def normalize_attachment_paths_in_db(db) -> int:
    """Fix legacy absolute attachment paths in SQLite. Returns rows updated."""
    rows = db.execute("SELECT id, file_path, preview_path, slide_preview_dir FROM attachments").fetchall()
    updated = 0
    for row in rows:
        changes: dict[str, str] = {}
        for col in ("file_path", "preview_path"):
            raw = row[col]
            if not raw:
                continue
            canonical = normalize_stored_upload_path(raw)
            if canonical and canonical != raw:
                changes[col] = canonical
        raw_dir = row["slide_preview_dir"]
        if raw_dir:
            canonical_dir = normalize_stored_dir_path(raw_dir)
            if canonical_dir and canonical_dir != raw_dir:
                changes["slide_preview_dir"] = canonical_dir
        if changes:
            sets = ", ".join(f"{col} = ?" for col in changes)
            db.execute(
                f"UPDATE attachments SET {sets} WHERE id = ?",
                (*changes.values(), row["id"]),
            )
            updated += 1
    if updated:
        db.commit()
    return updated
