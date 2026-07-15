"""Paginated, sortable, FTS-indexed catalogue queries."""

from __future__ import annotations

import math
import re
from typing import Any

CATALOG_PAGE_SIZE_DEFAULT = 20
CATALOG_PAGE_SIZE_MAX = 100

CATALOG_SORT_SQL = {
    "recent": "c.updated_at DESC",
    "oldest": "c.updated_at ASC",
    "alpha": "c.title COLLATE NOCASE ASC",
    "alpha_desc": "c.title COLLATE NOCASE DESC",
    "module": "c.module COLLATE NOCASE ASC, c.title COLLATE NOCASE ASC",
    "status": "c.status COLLATE NOCASE ASC, c.updated_at DESC",
}

CATALOG_SORT_OPTIONS = (
    ("recent", "Recently updated"),
    ("oldest", "Oldest first"),
    ("alpha", "Title A–Z"),
    ("alpha_desc", "Title Z–A"),
    ("relevance", "Relevance"),
)

CATALOG_SORT_OPTIONS_ADMIN = CATALOG_SORT_OPTIONS + (
    ("module", "Module"),
    ("status", "Status"),
)

CATALOG_STATUS_OPTIONS = (
    ("", "All statuses"),
    ("approved", "Approved"),
    ("pending", "Pending review"),
    ("draft", "Draft"),
    ("rejected", "Rejected"),
)


def _fts_token(token: str) -> str:
    """Build one FTS5 token; use prefix match for normal words so names hit easily."""
    if re.fullmatch(r"[A-Za-z0-9_/-]+", token):
        if len(token) >= 3:
            return f"{token}*"
        return token
    safe = token.replace('"', "")
    return f'"{safe}"' if safe else token


def fts_query_and(raw: str) -> str | None:
    parts = [p for p in re.split(r"\s+", (raw or "").strip()) if p]
    if not parts:
        return None
    cleaned = []
    for part in parts:
        part = part.replace('"', "").replace("'", "")
        if part:
            cleaned.append(part)
    if not cleaned:
        return None
    return " AND ".join(_fts_token(token) for token in cleaned)


def fts_query_or(raw: str) -> str | None:
    parts = [p for p in re.split(r"\s+", (raw or "").strip()) if p]
    if not parts:
        return None
    cleaned = []
    for part in parts:
        part = part.replace('"', "").replace("'", "")
        if part:
            cleaned.append(part)
    if not cleaned:
        return None
    tokens = [_fts_token(token) for token in cleaned]
    if len(tokens) == 1:
        return tokens[0]
    return " OR ".join(tokens)


def _resolve_sort(sort: str, *, has_query: bool) -> str:
    key = (sort or "recent").strip()
    if key == "relevance":
        return "relevance" if has_query else "recent"
    if key not in CATALOG_SORT_SQL:
        return "recent"
    return key


def _build_filters(
    *,
    module: str | None,
    modules: tuple[str, ...] | list[str] | None,
    author: str | None,
    status: str | None,
    approved_only: bool,
) -> tuple[str, list]:
    clauses: list[str] = []
    args: list = []

    if approved_only:
        clauses.append("c.status = 'approved'")
    elif status:
        clauses.append("c.status = ?")
        args.append(status)

    if module:
        clauses.append("c.module = ?")
        args.append(module)
    elif modules:
        module_list = list(modules)
        placeholders = ",".join("?" * len(module_list))
        clauses.append(f"c.module IN ({placeholders})")
        args.extend(module_list)

    if author:
        clauses.append("u.display_name = ?")
        args.append(author)

    return (" AND ".join(clauses) if clauses else "1=1"), args


def _count_rows(db, *, from_clause: str, where_sql: str, args: list) -> int:
    row = db.execute(
        f"SELECT COUNT(*) AS c {from_clause} WHERE {where_sql}",
        args,
    ).fetchone()
    return int(row["c"] or 0)


def _order_sql(sort_key: str, *, fts: bool) -> str:
    if sort_key == "relevance" and fts:
        return "rank ASC"
    return CATALOG_SORT_SQL[sort_key]


def query_catalog(
    db,
    *,
    q: str | None = None,
    module: str | None = None,
    modules: tuple[str, ...] | list[str] | None = None,
    author: str | None = None,
    status: str | None = None,
    approved_only: bool = False,
    sort: str = "recent",
    page: int = 1,
    per_page: int = CATALOG_PAGE_SIZE_DEFAULT,
) -> dict[str, Any]:
    """Return paginated catalogue rows with total count and paging metadata."""
    qtext = (q or "").strip()
    page = max(1, int(page or 1))
    per_page = min(CATALOG_PAGE_SIZE_MAX, max(1, int(per_page or CATALOG_PAGE_SIZE_DEFAULT)))
    sort_key = _resolve_sort(sort, has_query=bool(qtext))
    offset = (page - 1) * per_page

    filter_sql, filter_args = _build_filters(
        module=module,
        modules=modules,
        author=author,
        status=status,
        approved_only=approved_only,
    )

    rows: list = []
    total = 0
    used_fts = False

    if qtext:
        for fts in (fts_query_and(qtext), fts_query_or(qtext)):
            if not fts:
                continue
            try:
                rank_select = "bm25(content_fts) AS rank" if sort_key == "relevance" else "0 AS rank"
                from_clause = """
                    FROM content_fts
                    JOIN content c ON c.id = content_fts.rowid
                    JOIN users u ON u.id = c.author_id
                """
                where_sql = f"content_fts MATCH ? AND {filter_sql}"
                args = [fts, *filter_args]
                total = _count_rows(db, from_clause=from_clause, where_sql=where_sql, args=args)
                if total == 0:
                    # Empty FTS hit — try next query shape, then LIKE fallback below.
                    continue
                order_by = _order_sql(sort_key, fts=True)
                rows = db.execute(
                    f"""
                    SELECT c.*, u.display_name AS author_name, {rank_select}
                    {from_clause}
                    WHERE {where_sql}
                    ORDER BY {order_by}
                    LIMIT ? OFFSET ?
                    """,
                    [*args, per_page, offset],
                ).fetchall()
                used_fts = True
                break
            except Exception:
                rows = []
                total = 0
                continue

    if not used_fts and qtext:
        like = f"%{qtext}%"
        # Token-wise LIKE so multi-word queries still hit titles/summaries/tags.
        tokens = [t for t in re.split(r"\s+", qtext) if len(t) >= 2]
        from_clause = """
            FROM content c
            JOIN users u ON u.id = c.author_id
        """
        like_parts = [
            "(c.title LIKE ? OR COALESCE(c.summary, '') LIKE ? OR COALESCE(c.body, '') LIKE ?"
            " OR EXISTS (SELECT 1 FROM content_meta m WHERE m.content_id = c.id"
            " AND m.meta_key = 'tag' AND m.meta_value LIKE ?))"
        ]
        like_args: list = [like, like, like, like]
        if len(tokens) > 1:
            for tok in tokens:
                tok_like = f"%{tok}%"
                like_parts.append(
                    "(c.title LIKE ? OR COALESCE(c.summary, '') LIKE ? OR COALESCE(c.body, '') LIKE ?"
                    " OR EXISTS (SELECT 1 FROM content_meta m WHERE m.content_id = c.id"
                    " AND m.meta_key = 'tag' AND m.meta_value LIKE ?))"
                )
                like_args.extend([tok_like, tok_like, tok_like, tok_like])
        where_sql = f"{filter_sql} AND ({' OR '.join(like_parts)})"
        args = [*filter_args, *like_args]
        total = _count_rows(db, from_clause=from_clause, where_sql=where_sql, args=args)
        order_by = _order_sql(sort_key, fts=False)
        rows = db.execute(
            f"""
            SELECT c.*, u.display_name AS author_name
            {from_clause}
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*args, per_page, offset],
        ).fetchall()

    if not qtext:
        from_clause = """
            FROM content c
            JOIN users u ON u.id = c.author_id
        """
        where_sql = filter_sql
        args = list(filter_args)
        total = _count_rows(db, from_clause=from_clause, where_sql=where_sql, args=args)
        order_by = _order_sql(sort_key, fts=False)
        rows = db.execute(
            f"""
            SELECT c.*, u.display_name AS author_name
            {from_clause}
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*args, per_page, offset],
        ).fetchall()

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages and total > 0:
        page = total_pages

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "sort": sort_key,
        "q": qtext,
        "used_fts": used_fts,
        "showing_from": offset + 1 if total else 0,
        "showing_to": min(offset + len(rows), total),
    }


def pagination_pages(page: int, total_pages: int, *, radius: int = 2) -> list[int | None]:
    """Build a compact page number list (None = ellipsis)."""
    if total_pages <= 1:
        return [1]
    pages: list[int | None] = []
    start = max(1, page - radius)
    end = min(total_pages, page + radius)
    if start > 1:
        pages.append(1)
        if start > 2:
            pages.append(None)
    pages.extend(range(start, end + 1))
    if end < total_pages:
        if end < total_pages - 1:
            pages.append(None)
        pages.append(total_pages)
    return pages


def catalog_query_params(
    *,
    q: str | None = None,
    module: str | None = None,
    author: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    per_page: int | None = None,
) -> dict[str, str | int]:
    """URL query params for catalogue filter links (omit empties)."""
    raw = {
        "q": (q or "").strip(),
        "module": (module or "").strip(),
        "author": (author or "").strip(),
        "status": (status or "").strip(),
        "sort": (sort or "").strip(),
        "per_page": per_page,
    }
    return {key: value for key, value in raw.items() if value not in (None, "", 0)}


def enrich_catalog_for_template(catalog: dict[str, Any], **query_filters) -> dict[str, Any]:
    """Attach pagination links and preserved filter params for templates."""
    enriched = dict(catalog)
    enriched["page_numbers"] = pagination_pages(enriched["page"], enriched["total_pages"])
    enriched["query_params"] = catalog_query_params(
        q=enriched.get("q"),
        module=query_filters.get("module"),
        author=query_filters.get("author"),
        status=query_filters.get("status"),
        sort=enriched.get("sort"),
        per_page=enriched.get("per_page"),
    )
    return enriched
