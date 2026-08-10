"""Sync and search SharePoint / Teams folder documents for Ask MiNe."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import click
from flask import current_app
from flask.cli import with_appcontext

from mine.db import get_db

logger = logging.getLogger(__name__)

_SUPPORTED_EXT = frozenset({"pdf", "docx", "pptx", "xlsx", "txt", "md", "csv"})
_SKIP_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})


def sharepoint_graph_ready(app=None) -> bool:
    """True when app-only Graph credentials can call SharePoint."""
    app = app or current_app
    client_id = (app.config.get("MS_CLIENT_ID") or "").strip()
    secret = (app.config.get("MS_CLIENT_SECRET") or "").strip()
    tenant = (app.config.get("MS_TENANT") or "").strip()
    if not client_id or not secret or not tenant:
        return False
    if tenant.lower() in ("common", "organizations", "consumers"):
        return False
    if client_id.upper().startswith("REPLACE_WITH_"):
        return False
    url = (app.config.get("SHAREPOINT_KB_FOLDER_URL") or "").strip()
    return bool(url)


def local_training_dir(app=None) -> "Path":
    from pathlib import Path

    app = app or current_app
    raw = (app.config.get("SHAREPOINT_KB_LOCAL_DIR") or "data/teams_training").strip()
    p = Path(raw)
    if not p.is_absolute():
        root = Path(app.root_path).resolve().parent
        p = root / p
    return p


def sharepoint_kb_ready(app=None) -> bool:
    """True when Teams/SharePoint KB sync can run (Graph and/or local folder)."""
    app = app or current_app
    if not app.config.get("SHAREPOINT_KB_ENABLED"):
        return False
    return sharepoint_graph_ready(app) or True  # local ingest always available when enabled


def sharepoint_search_enabled(app=None) -> bool:
    app = app or current_app
    if app.config.get("SHAREPOINT_KB_ENABLED"):
        return True
    try:
        return docs_count() > 0
    except Exception:
        return False


def encode_sharing_url(sharing_url: str) -> str:
    """Encode a SharePoint/OneDrive sharing URL for Graph /shares/{token}."""
    raw = (sharing_url or "").strip()
    if not raw:
        raise ValueError("Sharing URL is empty.")
    # Drop tracking query params that are not part of the share identity when possible,
    # but keep the full URL if stripping would break :f: / :u: short links.
    parsed = urlparse(raw)
    # Short folder links (:f:) need the path; email= / e= are tracking-only.
    if parsed.query and (":f:" in raw or ":u:" in raw or ":b:" in raw):
        kept = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in ("email", "e", "cid")
        ]
        cleaned = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(kept), parsed.fragment)
        )
        raw = cleaned or raw
    b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return "u!" + b64.rstrip("=").replace("/", "_").replace("+", "-")


def _msal_app(app):
    import msal

    tenant = (app.config.get("MS_TENANT") or "").strip()
    return msal.ConfidentialClientApplication(
        client_id=app.config["MS_CLIENT_ID"],
        client_credential=app.config["MS_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{tenant}",
    )


def acquire_app_token(app=None) -> str:
    """Client-credentials token for application Graph permissions (Sites/Files.Read.All)."""
    app = app or current_app
    if not sharepoint_graph_ready(app):
        raise RuntimeError(
            "SharePoint Graph is not configured. Set SHAREPOINT_KB_FOLDER_URL, MS_CLIENT_ID, "
            "MS_CLIENT_SECRET, and MS_TENANT (tenant GUID — not 'common')."
        )
    result = _msal_app(app).acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if not result or "access_token" not in result:
        err = result.get("error_description") or result.get("error") or result
        raise RuntimeError(f"Could not acquire Graph app token: {err}")
    return result["access_token"]


def _graph_request(
    access_token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    headers_extra: dict[str, str] | None = None,
    stream: bool = False,
    timeout: int = 60,
) -> Any:
    import requests

    app = current_app
    base = (app.config.get("MS_GRAPH_BASE_URL") or "https://graph.microsoft.com/v1.0").rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if headers_extra:
        headers.update(headers_extra)
    res = requests.request(
        method.upper(),
        url,
        headers=headers,
        params=params,
        timeout=timeout,
        stream=stream,
    )
    if res.status_code >= 400:
        detail = res.text[:800]
        try:
            payload = res.json()
            err = payload.get("error") or {}
            if isinstance(err, dict):
                detail = f"{err.get('code')}: {err.get('message')}"
        except Exception:
            pass
        raise RuntimeError(f"Graph {method.upper()} {path} failed ({res.status_code}): {detail}")
    if stream:
        return res
    if res.status_code == 204 or not res.content:
        return None
    return res.json()


def resolve_shared_folder(access_token: str, sharing_url: str) -> dict[str, Any]:
    token = encode_sharing_url(sharing_url)
    return _graph_request(
        access_token,
        "GET",
        f"/shares/{token}/driveItem",
        headers_extra={"Prefer": "redeemSharingLinkIfNecessary"},
    )


def _list_children(access_token: str, drive_id: str, item_id: str) -> list[dict[str, Any]]:
    import requests

    items: list[dict[str, Any]] = []
    base = (current_app.config.get("MS_GRAPH_BASE_URL") or "https://graph.microsoft.com/v1.0").rstrip("/")
    url: str | None = f"{base}/drives/{drive_id}/items/{item_id}/children"
    params: dict[str, Any] | None = {
        "$select": "id,name,size,file,folder,webUrl,eTag,cTag,lastModifiedDateTime,parentReference",
        "$top": 200,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    while url:
        res = requests.get(url, headers=headers, params=params, timeout=60)
        params = None
        if res.status_code >= 400:
            raise RuntimeError(f"Graph list children failed ({res.status_code}): {res.text[:400]}")
        payload = res.json() if res.content else {}
        items.extend(payload.get("value") or [])
        url = payload.get("@odata.nextLink")
    return items


def _walk_files(
    access_token: str,
    drive_id: str,
    item_id: str,
    *,
    prefix: str = "",
    max_files: int = 200,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stack: list[tuple[str, str]] = [(item_id, prefix)]
    while stack and len(out) < max_files:
        cur_id, cur_prefix = stack.pop()
        children = _list_children(access_token, drive_id, cur_id)
        for child in children:
            name = (child.get("name") or "").strip()
            if not name or name.lower() in _SKIP_NAMES:
                continue
            rel = f"{cur_prefix}/{name}".strip("/") if cur_prefix else name
            if child.get("folder") is not None:
                stack.append((child["id"], rel))
                continue
            if child.get("file") is None:
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in _SUPPORTED_EXT:
                continue
            child["_rel_path"] = rel
            out.append(child)
            if len(out) >= max_files:
                break
    return out


def _download_content(access_token: str, drive_id: str, item_id: str, *, max_bytes: int) -> bytes:
    import requests

    base = (current_app.config.get("MS_GRAPH_BASE_URL") or "https://graph.microsoft.com/v1.0").rstrip("/")
    url = f"{base}/drives/{drive_id}/items/{item_id}/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get(url, headers=headers, timeout=120, allow_redirects=True)
    if res.status_code >= 400:
        raise RuntimeError(f"Download failed ({res.status_code}): {res.text[:400]}")
    data = res.content or b""
    if len(data) > max_bytes:
        raise RuntimeError(f"File exceeds size limit ({len(data)} > {max_bytes} bytes).")
    return data


def ensure_sharepoint_docs_table(db=None) -> None:
    db = db or get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS sharepoint_docs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          drive_id TEXT NOT NULL,
          item_id TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          path TEXT NOT NULL DEFAULT '',
          web_url TEXT,
          mime_type TEXT,
          etag TEXT,
          last_modified TEXT,
          size_bytes INTEGER DEFAULT 0,
          title TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL DEFAULT '',
          synced_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(drive_id, item_id)
        );
        CREATE INDEX IF NOT EXISTS idx_sharepoint_docs_name ON sharepoint_docs(name);
        CREATE VIRTUAL TABLE IF NOT EXISTS sharepoint_docs_fts USING fts5(
          title,
          summary,
          body,
          name,
          path,
          content='sharepoint_docs',
          content_rowid='id',
          tokenize = 'porter unicode61'
        );
        """
    )
    db.commit()


def _rebuild_fts(db) -> None:
    db.execute("INSERT INTO sharepoint_docs_fts(sharepoint_docs_fts) VALUES('rebuild')")
    db.commit()


def _upsert_doc(
    db,
    *,
    drive_id: str,
    item_id: str,
    name: str,
    path: str,
    web_url: str,
    mime: str,
    etag: str,
    last_modified: str,
    size_bytes: int,
    title: str,
    summary: str,
    body: str,
) -> None:
    db.execute(
        """
        INSERT INTO sharepoint_docs (
          drive_id, item_id, name, path, web_url, mime_type, etag,
          last_modified, size_bytes, title, summary, body, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(drive_id, item_id) DO UPDATE SET
          name = excluded.name,
          path = excluded.path,
          web_url = excluded.web_url,
          mime_type = excluded.mime_type,
          etag = excluded.etag,
          last_modified = excluded.last_modified,
          size_bytes = excluded.size_bytes,
          title = excluded.title,
          summary = excluded.summary,
          body = excluded.body,
          synced_at = CURRENT_TIMESTAMP
        """,
        (
            drive_id,
            item_id,
            name,
            path,
            web_url,
            mime,
            etag,
            last_modified,
            size_bytes,
            (title or name)[:500],
            (summary or "")[:4000],
            (body or "")[:350_000],
        ),
    )


def _hit_from_row(row) -> dict[str, Any]:
    title = (row["title"] or row["name"] or f"Document #{row['id']}").strip()
    summary = (row["summary"] or "").strip()
    body = (row["body"] or "").strip()
    if not summary:
        summary = (body[:280] + "…") if len(body) > 280 else body
    return {
        "kind": "sharepoint",
        "id": int(row["id"]),
        "title": title,
        "summary": summary[:400],
        "url": (row["web_url"] or "").strip() or None,
        "module_label": "Teams / SharePoint training",
        "module": "sharepoint_training",
        "detail": {
            "path": row["path"] or row["name"] or "",
            "overview": (body or summary)[:2500],
            "source": "Teams / SharePoint FMI Offshore training folder",
        },
    }


def sync_local_training_dir(app=None, *, max_files: int | None = None, max_bytes: int | None = None) -> dict[str, Any]:
    """Index files copied into SHAREPOINT_KB_LOCAL_DIR (Teams folder mirror)."""
    from pathlib import Path

    from mine.upload_extract import extract_document_text

    app = app or current_app
    db = get_db()
    ensure_sharepoint_docs_table(db)
    root = local_training_dir(app)
    root.mkdir(parents=True, exist_ok=True)
    max_files = int(max_files if max_files is not None else (app.config.get("SHAREPOINT_KB_MAX_FILES") or 200))
    if max_bytes is None:
        max_mb = float(app.config.get("SHAREPOINT_KB_MAX_FILE_MB") or 25)
        max_bytes = int(max_mb * 1024 * 1024)

    drive_id = "local"
    synced = 0
    skipped = 0
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    folder_url = (app.config.get("SHAREPOINT_KB_FOLDER_URL") or "").strip()

    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.name.lower() in _SKIP_NAMES or p.name.lower() == "readme.txt":
            continue
        ext = p.suffix.lower().lstrip(".")
        if ext not in _SUPPORTED_EXT:
            continue
        files.append(p)
        if len(files) >= max_files:
            break

    for p in files:
        rel = str(p.relative_to(root)).replace("\\", "/")
        item_id = rel
        seen.add((drive_id, item_id))
        try:
            st = p.stat()
            etag = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError as exc:
            errors.append(f"{rel}: {exc}")
            continue
        existing = db.execute(
            "SELECT id, etag FROM sharepoint_docs WHERE drive_id = ? AND item_id = ?",
            (drive_id, item_id),
        ).fetchone()
        if existing and (existing["etag"] or "") == etag:
            skipped += 1
            continue
        try:
            if st.st_size > max_bytes:
                errors.append(f"{rel}: too large ({st.st_size} bytes)")
                continue
            data = p.read_bytes()
            title, summary, body = extract_document_text(p.name, data)
            if not (body or "").strip():
                title = title or p.name
                summary = summary or f"Training file: {p.name}"
                body = summary
            _upsert_doc(
                db,
                drive_id=drive_id,
                item_id=item_id,
                name=p.name,
                path=rel,
                web_url=folder_url,
                mime="",
                etag=etag,
                last_modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                size_bytes=st.st_size,
                title=title or p.name,
                summary=summary,
                body=body,
            )
            synced += 1
        except Exception as exc:
            logger.exception("Local training sync failed for %s", rel)
            errors.append(f"{rel}: {exc}")

    # Remove stale local-only rows
    rows = db.execute(
        "SELECT id, item_id FROM sharepoint_docs WHERE drive_id = ?",
        (drive_id,),
    ).fetchall()
    for row in rows:
        if (drive_id, row["item_id"]) not in seen:
            db.execute("DELETE FROM sharepoint_docs WHERE id = ?", (row["id"],))

    db.commit()
    return {
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "listed": len(files),
        "path": str(root),
    }


def sync_sharepoint_folder(app=None, *, force: bool = False) -> dict[str, Any]:
    """Sync Teams/SharePoint training docs (Graph and/or local mirror folder)."""
    app = app or current_app
    if not sharepoint_kb_ready(app):
        return {"ok": False, "error": "SharePoint KB not configured (set SHAREPOINT_KB_ENABLED=1).", "synced": 0, "skipped": 0}

    db = get_db()
    ensure_sharepoint_docs_table(db)

    interval_h = float(app.config.get("SHAREPOINT_KB_SYNC_INTERVAL_HOURS") or 6)
    if not force and interval_h > 0:
        row = db.execute("SELECT MAX(synced_at) AS t FROM sharepoint_docs").fetchone()
        last = (row["t"] if row else None) or ""
        if last:
            try:
                ts = datetime.strptime(str(last)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
                if age_h < interval_h:
                    count = db.execute("SELECT COUNT(*) AS c FROM sharepoint_docs").fetchone()["c"]
                    return {
                        "ok": True,
                        "skipped_fresh": True,
                        "age_hours": round(age_h, 2),
                        "docs": int(count or 0),
                        "synced": 0,
                        "skipped": 0,
                    }
            except Exception:
                pass

    max_files = int(app.config.get("SHAREPOINT_KB_MAX_FILES") or 200)
    max_mb = float(app.config.get("SHAREPOINT_KB_MAX_FILE_MB") or 25)
    max_bytes = int(max_mb * 1024 * 1024)
    errors: list[str] = []
    synced = 0
    skipped = 0
    listed = 0
    folder_name = ""
    graph_mode = sharepoint_graph_ready(app)

    local_result = sync_local_training_dir(app, max_files=max_files, max_bytes=max_bytes)
    synced += int(local_result.get("synced") or 0)
    skipped += int(local_result.get("skipped") or 0)
    listed += int(local_result.get("listed") or 0)
    errors.extend(local_result.get("errors") or [])

    if graph_mode:
        from mine.upload_extract import extract_document_text

        folder_url = (app.config.get("SHAREPOINT_KB_FOLDER_URL") or "").strip()
        try:
            token = acquire_app_token(app)
            root = resolve_shared_folder(token, folder_url)
            folder_name = root.get("name") or ""
            drive_id = ((root.get("parentReference") or {}).get("driveId")) or root.get("driveId")
            item_id = root.get("id")
            if not drive_id or not item_id:
                raise RuntimeError("Could not resolve SharePoint folder drive/item ids from sharing link.")

            files = _walk_files(token, drive_id, item_id, max_files=max_files)
            listed += len(files)
            seen_graph: set[tuple[str, str]] = set()

            for item in files:
                iid = item.get("id") or ""
                if not iid:
                    continue
                seen_graph.add((drive_id, iid))
                etag = (item.get("eTag") or item.get("cTag") or "").strip()
                existing = db.execute(
                    "SELECT id, etag FROM sharepoint_docs WHERE drive_id = ? AND item_id = ?",
                    (drive_id, iid),
                ).fetchone()
                if existing and etag and (existing["etag"] or "") == etag:
                    skipped += 1
                    continue
                name = item.get("name") or "document"
                size = int(item.get("size") or 0)
                if size and size > max_bytes:
                    errors.append(f"{name}: too large ({size} bytes)")
                    continue
                try:
                    data = _download_content(token, drive_id, iid, max_bytes=max_bytes)
                    title, summary, body = extract_document_text(name, data)
                    if not (body or "").strip():
                        title = title or name
                        summary = summary or f"SharePoint file: {name}"
                        body = summary
                    _upsert_doc(
                        db,
                        drive_id=drive_id,
                        item_id=iid,
                        name=name,
                        path=item.get("_rel_path") or name,
                        web_url=item.get("webUrl") or "",
                        mime=((item.get("file") or {}).get("mimeType")) or "",
                        etag=etag,
                        last_modified=item.get("lastModifiedDateTime") or "",
                        size_bytes=size or len(data),
                        title=title or name,
                        summary=summary,
                        body=body,
                    )
                    synced += 1
                except Exception as exc:
                    logger.exception("SharePoint sync failed for %s", name)
                    errors.append(f"{name}: {exc}")

            # Drop stale Graph rows only (keep local:* rows)
            rows = db.execute(
                "SELECT id, drive_id, item_id FROM sharepoint_docs WHERE drive_id != 'local'"
            ).fetchall()
            for row in rows:
                if (row["drive_id"], row["item_id"]) not in seen_graph:
                    db.execute("DELETE FROM sharepoint_docs WHERE id = ?", (row["id"],))
            db.commit()
        except Exception as exc:
            logger.exception("SharePoint Graph sync failed")
            errors.append(f"Graph sync: {exc}")
    else:
        errors.append(
            "Graph credentials not ready (need real MS_CLIENT_ID + MS_TENANT GUID). "
            f"Local mirror folder: {local_result.get('path')} — copy Teams docs there and re-sync."
        )

    try:
        _rebuild_fts(db)
    except Exception:
        logger.exception("sharepoint_docs_fts rebuild failed")

    count = db.execute("SELECT COUNT(*) AS c FROM sharepoint_docs").fetchone()["c"]
    return {
        "ok": True,
        "folder": folder_name or "local+sharepoint",
        "synced": synced,
        "skipped": skipped,
        "docs": int(count or 0),
        "errors": errors[:20],
        "listed": listed,
        "graph": graph_mode,
        "local_path": local_result.get("path"),
    }


def list_sharepoint_docs(db, *, limit: int = 8) -> list[dict[str, Any]]:
    """Recent synced Teams/SharePoint docs (for onboarding/training section lists)."""
    ensure_sharepoint_docs_table(db)
    rows = db.execute(
        """
        SELECT id, title, summary, body, name, path, web_url
        FROM sharepoint_docs
        ORDER BY synced_at DESC, id DESC
        LIMIT ?
        """,
        (max(1, min(50, int(limit))),),
    ).fetchall()
    return [_hit_from_row(row) for row in rows]


def search_sharepoint_docs(db, q: str, *, limit: int = 5, list_if_empty: bool = False) -> list[dict[str, Any]]:
    """FTS search over synced SharePoint training/onboarding documents."""
    ensure_sharepoint_docs_table(db)
    from mine.catalog_query import fts_query_and, fts_query_or

    raw = (q or "").strip()
    if not raw:
        return list_sharepoint_docs(db, limit=limit) if list_if_empty else []

    out: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _rows_for(match: str | None) -> list:
        if not match:
            return []
        try:
            return db.execute(
                """
                SELECT d.id, d.title, d.summary, d.body, d.name, d.path, d.web_url,
                       bm25(sharepoint_docs_fts) AS rank
                FROM sharepoint_docs_fts
                JOIN sharepoint_docs d ON d.id = sharepoint_docs_fts.rowid
                WHERE sharepoint_docs_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match, limit * 2),
            ).fetchall()
        except Exception:
            logger.exception("SharePoint FTS query failed for %r", match)
            return []

    for match in (fts_query_and(raw), fts_query_or(raw)):
        for row in _rows_for(match):
            rid = int(row["id"])
            if rid in seen:
                continue
            seen.add(rid)
            out.append(_hit_from_row(row))
            if len(out) >= limit:
                return out

    # Fallback: LIKE when FTS empty (short queries / punctuation).
    if not out:
        like = f"%{raw}%"
        rows = db.execute(
            """
            SELECT id, title, summary, body, name, path, web_url
            FROM sharepoint_docs
            WHERE title LIKE ? OR name LIKE ? OR path LIKE ? OR summary LIKE ? OR body LIKE ?
            ORDER BY synced_at DESC
            LIMIT ?
            """,
            (like, like, like, like, like, limit),
        ).fetchall()
        out = [_hit_from_row(row) for row in rows]

    if not out and list_if_empty:
        return list_sharepoint_docs(db, limit=limit)
    return out[:limit]


def docs_count(db=None) -> int:
    db = db or get_db()
    ensure_sharepoint_docs_table(db)
    row = db.execute("SELECT COUNT(*) AS c FROM sharepoint_docs").fetchone()
    return int(row["c"] or 0) if row else 0


@click.command("sync-sharepoint")
@click.option("--force", is_flag=True, help="Ignore sync interval freshness check.")
@with_appcontext
def sync_sharepoint_command(force: bool):
    """Sync the configured SharePoint/Teams training folder into MiNe for Ask MiNe."""
    try:
        result = sync_sharepoint_folder(force=force)
    except Exception as exc:
        click.echo(f"SharePoint sync failed: {exc}", err=True)
        raise SystemExit(1) from exc
    if not result.get("ok"):
        click.echo(result.get("error") or "Sync failed.", err=True)
        raise SystemExit(1)
    if result.get("skipped_fresh"):
        click.echo(
            f"Already fresh ({result.get('age_hours')}h ago) — {result.get('docs')} docs indexed. "
            "Use --force to re-sync."
        )
        return
    click.echo(
        f"Synced folder {result.get('folder')!r}: "
        f"{result.get('synced')} updated, {result.get('skipped')} unchanged, "
        f"{result.get('docs')} total (listed {result.get('listed')})."
    )
    for err in result.get("errors") or []:
        click.echo(f"  ! {err}", err=True)
