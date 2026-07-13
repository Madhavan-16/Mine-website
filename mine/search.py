from flask import Blueprint, current_app, render_template, request

from mine.auth_utils import login_required
from mine.catalog_modules import SEARCH_FILTER_MODULES, SEARCH_SORT_OPTIONS, module_label
from mine.catalog_query import CATALOG_SORT_OPTIONS, query_catalog
from mine.db import get_db
from mine.search_nav import result_url_for_content, section_search_hits

bp = Blueprint("search", __name__)

_VALID_SORT = {key for key, _ in CATALOG_SORT_OPTIONS}


def _author_options(db) -> list[str]:
    rows = db.execute(
        """
        SELECT DISTINCT u.display_name AS n
        FROM users u
        JOIN content c ON c.author_id = u.id
        WHERE c.status = 'approved'
        ORDER BY n COLLATE NOCASE
        LIMIT 100
        """
    ).fetchall()
    return [r["n"] for r in rows if r["n"]]


@bp.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    module = (request.args.get("module") or "").strip() or None
    author = (request.args.get("author") or "").strip() or None
    sort = (request.args.get("sort") or "relevance").strip()
    if sort not in _VALID_SORT:
        sort = "relevance"

    rows = []
    db = get_db()
    if q:
        try:
            catalog = query_catalog(
                db,
                q=q,
                module=module,
                author=author,
                approved_only=True,
                sort=sort,
                page=1,
                per_page=50,
            )
            rows = catalog["rows"]
        except Exception as exc:
            current_app.logger.warning("Catalogue search failed for %r: %s", q, exc)
            rows = []

    section_shortcuts = section_search_hits(q) if q else []
    author_options = _author_options(db)

    enriched_rows = []
    for row in rows:
        item = dict(row)
        item["module_label"] = module_label(item.get("module"))
        item["result_url"] = result_url_for_content(item.get("module", ""), item["id"])
        enriched_rows.append(item)

    return render_template(
        "search.html",
        q=q,
        module=module,
        author=author,
        sort=sort,
        rows=enriched_rows,
        section_shortcuts=section_shortcuts,
        filter_modules=SEARCH_FILTER_MODULES,
        sort_options=SEARCH_SORT_OPTIONS,
        author_options=author_options,
    )
