"""
Knowledge-artefact persistence on Azure App Service.

Policy
------
- UI, static images, projects config, users, and non-knowledge content come from
  the git deploy (wwwroot). Local push is the source of truth for those.
- Knowledge-repository series (KYC, KYA, term of the week, newsletter, case
  studies, RFP snippets, blogs) are bidirectional: website uploads are mirrored
  under /home/data/mine/knowledge and re-merged into live wwwroot after each deploy.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from pathlib import Path

from mine.catalog_modules import KNOWLEDGE_SERIES_MODULE_KEYS

logger = logging.getLogger(__name__)

_LEGACY_FULL_DB = Path("/home/data/mine/mine.db")
_LEGACY_FULL_UPLOADS = Path("/home/data/mine/uploads")


def is_azure_app_service() -> bool:
    return bool((os.environ.get("WEBSITE_SITE_NAME") or "").strip())


def knowledge_persist_enabled() -> bool:
    if (os.environ.get("MINE_KNOWLEDGE_PERSIST") or "1").strip().lower() in ("0", "false", "no"):
        return False
    return is_azure_app_service()


def knowledge_persist_root() -> Path:
    raw = (os.environ.get("MINE_KNOWLEDGE_PERSIST_ROOT") or "").strip()
    if raw:
        return Path(raw)
    return Path("/home/data/mine/knowledge")


def knowledge_persist_db_path() -> Path:
    return knowledge_persist_root() / "knowledge.db"


def knowledge_persist_uploads_path() -> Path:
    return knowledge_persist_root() / "uploads"


def is_knowledge_module(module: str | None) -> bool:
    return (module or "").strip() in KNOWLEDGE_SERIES_MODULE_KEYS


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_mirror_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          role TEXT DEFAULT 'user',
          is_active INTEGER DEFAULT 1,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS content (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          module TEXT,
          title TEXT,
          summary TEXT,
          body TEXT,
          status TEXT,
          author_id INTEGER,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS content_meta (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          content_id INTEGER,
          meta_key TEXT,
          meta_value TEXT
        );
        CREATE TABLE IF NOT EXISTS attachments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          content_id INTEGER,
          file_name TEXT,
          file_path TEXT,
          preview_path TEXT,
          slide_preview_dir TEXT,
          uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    try:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_mirror_module_title
              ON content (module, title)
            """
        )
    except sqlite3.Error:
        pass
    conn.commit()


def ensure_knowledge_persist_dirs() -> None:
    if not knowledge_persist_enabled():
        return
    knowledge_persist_root().mkdir(parents=True, exist_ok=True)
    knowledge_persist_uploads_path().mkdir(parents=True, exist_ok=True)
    with _connect(knowledge_persist_db_path()) as conn:
        _ensure_mirror_schema(conn)


def _map_author(src: sqlite3.Connection, dest: sqlite3.Connection, author_id: int | None) -> int:
    if author_id:
        row = src.execute(
            "SELECT username, email, password_hash, display_name, role, is_active FROM users WHERE id = ?",
            (author_id,),
        ).fetchone()
    else:
        row = None
    if row:
        email = (row["email"] or "").strip().lower()
        username = (row["username"] or "").strip()
        existing = None
        if email:
            existing = dest.execute(
                "SELECT id FROM users WHERE lower(trim(email)) = ?", (email,)
            ).fetchone()
        if not existing and username:
            existing = dest.execute(
                "SELECT id FROM users WHERE lower(trim(username)) = ?", (username.lower(),)
            ).fetchone()
        if existing:
            return int(existing["id"])
        cur = dest.execute(
            """
            INSERT INTO users (username, email, password_hash, display_name, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username or f"user{author_id}",
                email or f"user{author_id}@hexaware.local",
                row["password_hash"] or "!",
                row["display_name"] or username or "Knowledge author",
                row["role"] or "user",
                row["is_active"] if row["is_active"] is not None else 1,
            ),
        )
        return int(cur.lastrowid)

    fallback = dest.execute(
        "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
    ).fetchone() or dest.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    if not fallback:
        cur = dest.execute(
            """
            INSERT INTO users (username, email, password_hash, display_name, role, is_active)
            VALUES ('knowledge-mirror', 'knowledge-mirror@local', '!', 'Knowledge mirror', 'admin', 1)
            """
        )
        return int(cur.lastrowid)
    return int(fallback["id"])


def _find_content(conn: sqlite3.Connection, module: str, title: str):
    return conn.execute(
        """
        SELECT * FROM content
        WHERE lower(trim(module)) = lower(trim(?))
          AND lower(trim(title)) = lower(trim(?))
        LIMIT 1
        """,
        (module, title),
    ).fetchone()


def _resolve_upload(stored: str | None, upload_root: Path, base: Path) -> Path | None:
    if not stored:
        return None
    raw = str(stored).strip().replace("\\", "/")
    p = Path(raw)
    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        rel = raw.lstrip("./")
        if rel.startswith("uploads/"):
            candidates.append(upload_root / rel[len("uploads/") :])
        candidates.extend([base / rel, upload_root / Path(rel).name, upload_root / rel])
    for c in candidates:
        if c.is_file():
            return c
    return None


def _copy_file(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size == src.stat().st_size:
        return False
    shutil.copy2(src, dest)
    return True


def _ts(value) -> str:
    return str(value or "")


def _should_replace(live_updated, persist_updated) -> bool:
    """Prefer newer timestamp; fill empty live if persist has a date."""
    a = _ts(live_updated)
    b = _ts(persist_updated)
    if not b:
        return False
    if not a:
        return True
    return b > a


def _replace_attachments(
    *,
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    src_cid: int,
    dest_cid: int,
    source_uploads: Path,
    target_uploads: Path,
    source_base: Path,
) -> int:
    files_copied = 0
    dest.execute("DELETE FROM attachments WHERE content_id = ?", (dest_cid,))
    for att in src.execute(
        "SELECT * FROM attachments WHERE content_id = ? ORDER BY id",
        (src_cid,),
    ).fetchall():
        stored = att["file_path"]
        src_file = _resolve_upload(stored, source_uploads, source_base)
        new_stored = stored
        if src_file:
            dest_file = target_uploads / src_file.name
            if _copy_file(src_file, dest_file):
                files_copied += 1
            new_stored = f"uploads/{src_file.name}"

        preview_stored = att["preview_path"]
        if preview_stored:
            prev_src = _resolve_upload(preview_stored, source_uploads, source_base)
            if prev_src:
                dest_prev = target_uploads / prev_src.name
                if _copy_file(prev_src, dest_prev):
                    files_copied += 1
                preview_stored = f"uploads/{prev_src.name}"

        dest.execute(
            """
            INSERT INTO attachments (content_id, file_name, file_path, preview_path, slide_preview_dir)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                dest_cid,
                att["file_name"],
                new_stored,
                preview_stored,
                None,
            ),
        )
    return files_copied


def _upsert_knowledge_row(
    *,
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    row,
    source_uploads: Path,
    target_uploads: Path,
    source_base: Path,
    overwrite_existing: bool,
) -> tuple[str, int]:
    """Returns (action, files_copied) where action is created|updated|skipped."""
    module = row["module"] or ""
    title = row["title"] or ""
    if not is_knowledge_module(module) or not title.strip():
        return "skipped", 0

    existing = _find_content(dest, module, title)
    author_id = _map_author(src, dest, row["author_id"] if "author_id" in row.keys() else None)

    if existing and not overwrite_existing and not _should_replace(existing["updated_at"], row["updated_at"]):
        return "skipped", 0

    if existing:
        dest_cid = int(existing["id"])
        dest.execute(
            """
            UPDATE content
            SET summary = ?, body = ?, status = ?, author_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                row["summary"],
                row["body"],
                row["status"] or existing["status"],
                author_id,
                row["updated_at"] or existing["updated_at"],
                dest_cid,
            ),
        )
        action = "updated"
    else:
        cur = dest.execute(
            """
            INSERT INTO content (module, title, summary, body, status, author_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                module,
                title,
                row["summary"],
                row["body"],
                row["status"] or "draft",
                author_id,
                row["created_at"],
                row["updated_at"],
            ),
        )
        dest_cid = int(cur.lastrowid)
        action = "created"

    dest.execute("DELETE FROM content_meta WHERE content_id = ?", (dest_cid,))
    for meta in src.execute(
        "SELECT meta_key, meta_value FROM content_meta WHERE content_id = ?",
        (row["id"],),
    ).fetchall():
        dest.execute(
            "INSERT INTO content_meta (content_id, meta_key, meta_value) VALUES (?, ?, ?)",
            (dest_cid, meta["meta_key"], meta["meta_value"]),
        )

    files_copied = _replace_attachments(
        src=src,
        dest=dest,
        src_cid=int(row["id"]),
        dest_cid=dest_cid,
        source_uploads=source_uploads,
        target_uploads=target_uploads,
        source_base=source_base,
    )
    return action, files_copied


def _module_placeholders() -> tuple[str, tuple[str, ...]]:
    mods = tuple(sorted(KNOWLEDGE_SERIES_MODULE_KEYS))
    return ",".join("?" * len(mods)), mods


def seed_knowledge_mirror_from_legacy_full_store() -> None:
    """One-time: pull knowledge rows out of the old full /home/data/mine DB."""
    if not knowledge_persist_enabled():
        return
    mirror_db = knowledge_persist_db_path()
    if mirror_db.is_file() and mirror_db.stat().st_size > 0:
        with _connect(mirror_db) as conn:
            n = conn.execute(
                f"SELECT COUNT(*) AS c FROM content WHERE module IN ({','.join('?' * len(KNOWLEDGE_SERIES_MODULE_KEYS))})",
                tuple(KNOWLEDGE_SERIES_MODULE_KEYS),
            ).fetchone()["c"]
            if n:
                return
    if not _LEGACY_FULL_DB.is_file():
        return

    ensure_knowledge_persist_dirs()
    src = _connect(_LEGACY_FULL_DB)
    dest = _connect(mirror_db)
    try:
        _ensure_mirror_schema(dest)
        ph, mods = _module_placeholders()
        rows = src.execute(
            f"SELECT * FROM content WHERE module IN ({ph}) ORDER BY id",
            mods,
        ).fetchall()
        created = 0
        for row in rows:
            action, _ = _upsert_knowledge_row(
                src=src,
                dest=dest,
                row=row,
                source_uploads=_LEGACY_FULL_UPLOADS,
                target_uploads=knowledge_persist_uploads_path(),
                source_base=_LEGACY_FULL_DB.parent,
                overwrite_existing=True,
            )
            if action == "created":
                created += 1
        dest.commit()
        if created:
            logger.info("Seeded knowledge mirror with %s item(s) from legacy /home/data/mine", created)
    finally:
        src.close()
        dest.close()


def merge_knowledge_persist_into_live(app) -> dict:
    """After git deploy, restore website knowledge artefacts into wwwroot live DB."""
    if not knowledge_persist_enabled():
        return {"enabled": False}

    ensure_knowledge_persist_dirs()
    seed_knowledge_mirror_from_legacy_full_store()

    mirror_db = knowledge_persist_db_path()
    if not mirror_db.is_file() or mirror_db.stat().st_size == 0:
        return {"enabled": True, "created": 0, "updated": 0, "skipped": 0, "files_copied": 0}

    live_db = Path(app.config["DATABASE"])
    live_uploads = Path(app.config["UPLOAD_FOLDER"])
    live_uploads.mkdir(parents=True, exist_ok=True)

    src = _connect(mirror_db)
    dest = _connect(live_db)
    created = updated = skipped = files_copied = 0
    try:
        ph, mods = _module_placeholders()
        rows = src.execute(
            f"SELECT * FROM content WHERE module IN ({ph}) ORDER BY id",
            mods,
        ).fetchall()
        for row in rows:
            action, n_files = _upsert_knowledge_row(
                src=src,
                dest=dest,
                row=row,
                source_uploads=knowledge_persist_uploads_path(),
                target_uploads=live_uploads,
                source_base=mirror_db.parent,
                overwrite_existing=False,
            )
            files_copied += n_files
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
        try:
            dest.execute("INSERT INTO content_fts(content_fts) VALUES('rebuild')")
        except sqlite3.Error:
            pass
        dest.commit()
    finally:
        src.close()
        dest.close()

    if created or updated or files_copied:
        logger.info(
            "Knowledge persist → live: created=%s updated=%s skipped=%s files=%s",
            created,
            updated,
            skipped,
            files_copied,
        )
    return {
        "enabled": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "files_copied": files_copied,
    }


def sync_knowledge_item_to_persist(app, content_id: int) -> None:
    """Mirror one live knowledge record into the durable store (create/update)."""
    if not knowledge_persist_enabled():
        return

    ensure_knowledge_persist_dirs()
    live_db = Path(app.config["DATABASE"])
    live_uploads = Path(app.config["UPLOAD_FOLDER"])
    src = _connect(live_db)
    dest = _connect(knowledge_persist_db_path())
    try:
        _ensure_mirror_schema(dest)
        row = src.execute("SELECT * FROM content WHERE id = ?", (content_id,)).fetchone()
        if not row or not is_knowledge_module(row["module"]):
            return
        _upsert_knowledge_row(
            src=src,
            dest=dest,
            row=row,
            source_uploads=live_uploads,
            target_uploads=knowledge_persist_uploads_path(),
            source_base=live_db.parent,
            overwrite_existing=True,
        )
        dest.commit()
    except Exception:
        logger.exception("Failed syncing knowledge content #%s to persist store", content_id)
    finally:
        src.close()
        dest.close()


def delete_knowledge_from_persist(module: str | None, title: str | None) -> None:
    if not knowledge_persist_enabled() or not is_knowledge_module(module) or not (title or "").strip():
        return
    mirror_db = knowledge_persist_db_path()
    if not mirror_db.is_file():
        return
    conn = _connect(mirror_db)
    try:
        row = _find_content(conn, module or "", title or "")
        if not row:
            return
        cid = int(row["id"])
        conn.execute("DELETE FROM attachments WHERE content_id = ?", (cid,))
        conn.execute("DELETE FROM content_meta WHERE content_id = ?", (cid,))
        conn.execute("DELETE FROM content WHERE id = ?", (cid,))
        conn.commit()
    finally:
        conn.close()
