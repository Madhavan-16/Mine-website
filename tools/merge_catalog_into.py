#!/usr/bin/env python3
"""
Merge catalogue content from a SOURCE database into a TARGET database.

Use cases
---------
1) Merge knowledge artefacts only (recommended for Azure ↔ local):
     python tools/merge_catalog_into.py --source mine.db --target azure-mine.db ^
         --source-uploads uploads --target-uploads azure-uploads --modules knowledge

2) Publish full local catalogue onto a downloaded Azure DB (then upload that DB back):
     python tools/merge_catalog_into.py --source mine.db --target azure-mine.db ^
         --source-uploads uploads --target-uploads azure-uploads

3) Merge a backup into your local DB without wiping either side:
     python tools/merge_catalog_into.py --source backup.db --target mine.db ^
         --source-uploads backup-uploads --target-uploads uploads

Rules
-----
- Users are matched by email / username (never wipe target users).
- Content is skipped when the same module + title already exists on the target.
- Attachment files are copied when missing on the target upload folder.
- Does not delete anything on the target.
- Prefer --modules knowledge: UI and non-knowledge content should come from local git push.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CONTENT_COLS = (
    "module",
    "title",
    "summary",
    "body",
    "status",
    "author_id",
    "created_at",
    "updated_at",
)


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SystemExit(f"Database not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _map_author(src: sqlite3.Connection, dest: sqlite3.Connection, author_id: int) -> int:
    row = src.execute(
        "SELECT username, email, display_name, role, password_hash, is_active FROM users WHERE id = ?",
        (author_id,),
    ).fetchone()
    if not row:
        # fall back to first admin / first user on dest
        fallback = dest.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
        ).fetchone() or dest.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        if not fallback:
            raise SystemExit("Target database has no users to assign as author.")
        return int(fallback["id"])

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
            username,
            email or f"{username}@hexaware.local",
            row["password_hash"],
            row["display_name"] or username,
            row["role"] or "user",
            row["is_active"] if row["is_active"] is not None else 1,
        ),
    )
    return int(cur.lastrowid)


def _content_exists(dest: sqlite3.Connection, module: str, title: str) -> bool:
    row = dest.execute(
        """
        SELECT id FROM content
        WHERE lower(trim(module)) = lower(trim(?))
          AND lower(trim(title)) = lower(trim(?))
        LIMIT 1
        """,
        (module, title),
    ).fetchone()
    return row is not None


def _copy_file(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return False
    dest.write_bytes(src.read_bytes())
    return True


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


def merge(
    *,
    source_db: Path,
    target_db: Path,
    source_uploads: Path,
    target_uploads: Path,
    dry_run: bool,
    modules: set[str] | None = None,
) -> dict:
    src = _connect(source_db)
    dest = _connect(target_db)
    source_base = source_db.parent
    target_base = target_db.parent

    created = skipped = files_copied = 0
    rows = src.execute(
        "SELECT * FROM content ORDER BY id"
    ).fetchall()

    for row in rows:
        module = row["module"] or ""
        title = row["title"] or ""
        if modules is not None and module not in modules:
            continue
        if _content_exists(dest, module, title):
            skipped += 1
            continue

        author_id = _map_author(src, dest, int(row["author_id"]))
        if dry_run:
            created += 1
            continue

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
        new_cid = int(cur.lastrowid)

        # tags / meta
        for meta in src.execute(
            "SELECT meta_key, meta_value FROM content_meta WHERE content_id = ?",
            (row["id"],),
        ).fetchall():
            dest.execute(
                "INSERT INTO content_meta (content_id, meta_key, meta_value) VALUES (?, ?, ?)",
                (new_cid, meta["meta_key"], meta["meta_value"]),
            )

        # projects extension
        proj = src.execute(
            "SELECT * FROM projects WHERE content_id = ?", (row["id"],)
        ).fetchone()
        if proj:
            cols = [k for k in proj.keys() if k not in ("id", "content_id")]
            placeholders = ", ".join("?" for _ in cols)
            dest.execute(
                f"INSERT INTO projects (content_id, {', '.join(cols)}) VALUES (?, {placeholders})",
                (new_cid, *[proj[c] for c in cols]),
            )

        for att in src.execute(
            "SELECT * FROM attachments WHERE content_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall():
            stored = att["file_path"]
            src_file = _resolve_upload(stored, source_uploads, source_base)
            new_stored = stored
            if src_file:
                rel_name = src_file.name
                # keep under uploads/<name> portable form
                dest_file = target_uploads / rel_name
                if _copy_file(src_file, dest_file):
                    files_copied += 1
                new_stored = f"uploads/{rel_name}"

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
                    new_cid,
                    att["file_name"],
                    new_stored,
                    preview_stored,
                    None,  # slide previews rebuild on demand
                ),
            )

        created += 1

    if not dry_run:
        # refresh FTS if present
        try:
            dest.execute("INSERT INTO content_fts(content_fts) VALUES('rebuild')")
        except sqlite3.Error:
            pass
        dest.commit()

    src.close()
    dest.close()
    return {"created": created, "skipped": skipped, "files_copied": files_copied, "dry_run": dry_run}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="Source SQLite DB (e.g. local mine.db)")
    parser.add_argument("--target", type=Path, required=True, help="Target SQLite DB (will be updated)")
    parser.add_argument("--source-uploads", type=Path, default=None, help="Source uploads folder")
    parser.add_argument("--target-uploads", type=Path, default=None, help="Target uploads folder")
    parser.add_argument(
        "--modules",
        default="",
        help="Comma-separated modules to merge, or 'knowledge' for knowledge-repository series only",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write")
    args = parser.parse_args()

    source_uploads = (args.source_uploads or (args.source.parent / "uploads")).resolve()
    target_uploads = (args.target_uploads or (args.target.parent / "uploads")).resolve()
    target_uploads.mkdir(parents=True, exist_ok=True)

    modules = None
    raw_modules = (args.modules or "").strip().lower()
    if raw_modules:
        if raw_modules in ("knowledge", "knowledge-series", "knowledge_series"):
            from mine.catalog_modules import KNOWLEDGE_SERIES_MODULE_KEYS

            modules = set(KNOWLEDGE_SERIES_MODULE_KEYS)
        else:
            modules = {m.strip() for m in raw_modules.split(",") if m.strip()}

    result = merge(
        source_db=args.source.resolve(),
        target_db=args.target.resolve(),
        source_uploads=source_uploads,
        target_uploads=target_uploads,
        dry_run=args.dry_run,
        modules=modules,
    )
    mode = "DRY-RUN" if result["dry_run"] else "DONE"
    print(
        f"{mode}: created={result['created']} skipped_existing={result['skipped']} "
        f"files_copied={result['files_copied']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
