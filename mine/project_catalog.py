"""Programs & Projects — structured section content (config/program_project_sections.json)."""

from __future__ import annotations

import json
from pathlib import Path

from flask import current_app

PROJECT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("overview", "Project Overview"),
    ("supported_applications", "Supported Applications"),
    ("scope_of_work", "Scope of Work"),
    ("business_functions", "Business Functions Supported"),
    ("mining_value_chain", "Mining Value Chain Supported"),
    ("technologies", "Technologies"),
)

PROJECT_SECTION_ICONS: dict[str, str] = {
    "overview": "overview",
    "supported_applications": "apps",
    "scope_of_work": "scope",
    "business_functions": "functions",
    "mining_value_chain": "value-chain",
    "technologies": "tech-stack",
}

_CHIP_SECTIONS = frozenset({"supported_applications", "technologies", "mining_value_chain"})


def _chip_icon(label: str, section_key: str) -> str:
    """Infer a contextual icon slug from chip label text."""
    t = (label or "").lower()
    if "nola" in t:
        return "app"
    if "successfactors" in t or "human resource" in t or "workforce" in t:
        return "enterprise"
    if "elt" in t or "etl" in t:
        return "pipeline"
    if "snowflake" in t or "openflow" in t:
        return "warehouse"
    if "cosmos" in t:
        return "database"
    if "sharepoint" in t:
        return "app"
    if "odata" in t:
        return "pipeline"
    if "data factory" in t:
        return "pipeline"
    if "s/4hana" in t or "s4hana" in t:
        return "enterprise"
    if "rest" in t or "soap" in t or "api" in t or "xml" in t or "json" in t:
        return "pipeline"
    if "sims" in t:
        return "app"
    if "ariba" in t:
        return "enterprise"
    if "inventory" in t or "warehouse" in t or "replenish" in t:
        return "inventory"
    if "procurement" in t or "sourcing" in t or "vendor" in t or "supplier" in t:
        return "logistics"
    if "power bi" in t:
        return "chart"
    if "businessobjects" in t or "sap bo" in t:
        return "enterprise"
    if "sap" in t:
        return "enterprise"
    if "sql" in t:
        return "database"
    if "etl" in t or "data integration" in t:
        return "pipeline"
    if "warehouse" in t or "edw" in t:
        return "warehouse"
    if "analytics" in t or t == "bi" or "business intelligence" in t:
        return "analytics"
    if "report" in t:
        return "report"
    if section_key == "mining_value_chain":
        if "drill" in t or "blast" in t:
            return "plan"
        if "haul" in t:
            return "logistics"
        if "crush" in t:
            return "process"
        if "extract" in t:
            return "production"
        if "procurement" in t:
            return "logistics"
        if "plan" in t:
            return "plan"
        if "production" in t:
            return "production"
        if "ore" in t or "process" in t:
            return "process"
        if "asset" in t or "equipment" in t or "maintenance" in t:
            return "maintenance"
        if "supply" in t or "logistic" in t:
            return "logistics"
        if "inventory" in t:
            return "inventory"
        if "executive" in t or "monitor" in t:
            return "dashboard"
        return "chain-link"
    if section_key == "supported_applications" or section_key == "business_functions":
        if "transformation" in t or "operations" in t:
            return "analytics"
        return "app"
    return "chip"

_SECTION_KEYS = frozenset(k for k, _ in PROJECT_SECTIONS)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "program_project_sections.json"


def _empty_sections() -> dict[str, str]:
    return {key: "" for key in _SECTION_KEYS}


def parse_section_display(section_key: str, text: str) -> dict:
    """Shape section text for interactive portal layouts (chips, duration badge, prose)."""
    text = (text or "").strip()
    if not text:
        return {"empty": True}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if section_key in _CHIP_SECTIONS:
        chips = [{"text": line, "icon": _chip_icon(line, section_key)} for line in lines]
        layout = "timeline" if section_key == "mining_value_chain" else "chips"
        return {"layout": layout, "chips": chips}
    if section_key == "business_functions" and len(lines) > 1:
        return {
            "layout": "chips",
            "chips": [{"text": line, "icon": _chip_icon(line, section_key)} for line in lines],
        }
    if section_key == "overview":
        duration = None
        body_lines = lines
        if lines and lines[0].lower().startswith("duration"):
            duration = lines[0].split(":", 1)[-1].strip() if ":" in lines[0] else lines[0]
            body_lines = lines[1:]
        return {
            "layout": "overview",
            "duration": duration,
            "body": "\n\n".join(body_lines) if body_lines else "",
        }
    return {"layout": "prose", "body": text}


def build_section_views(sections: dict[str, str]) -> dict[str, dict]:
    return {key: parse_section_display(key, sections.get(key, "")) for key in _SECTION_KEYS}


def _config_path() -> Path:
    raw = (current_app.config.get("PROGRAM_PROJECT_SECTIONS_JSON") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = (Path(current_app.config["BASE_DIR"]) / p).resolve()
        return p
    return _CONFIG_PATH


def load_project_section_catalog() -> dict:
    path = _config_path()
    if not path.is_file():
        return {"by_content_id": {}, "by_title": {}, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"by_content_id": {}, "by_title": {}, "entries": []}

    by_id: dict[str, dict[str, str]] = {}
    by_title: dict[str, dict[str, str]] = {}
    entries: list[dict] = []

    for idx, entry in enumerate(data.get("projects") or []):
        if not isinstance(entry, dict):
            continue
        sections = _empty_sections()
        raw_sections = entry.get("sections") or {}
        if isinstance(raw_sections, dict):
            for key in _SECTION_KEYS:
                val = raw_sections.get(key)
                if val is not None:
                    sections[key] = str(val).strip()

        title = (entry.get("title") or "").strip()
        cid = entry.get("content_id")

        if cid is not None:
            by_id[str(cid)] = sections
        if title:
            by_title[title.lower()] = sections
            entries.append(
                {
                    "catalog_key": f"cfg-{idx}",
                    "title": title,
                    "content_id": cid,
                    "sections": sections,
                }
            )

    return {"by_content_id": by_id, "by_title": by_title, "entries": entries}


def sections_for_project(*, content_id: int, title: str, catalog: dict | None = None) -> dict[str, str]:
    catalog = catalog if catalog is not None else load_project_section_catalog()
    by_id = catalog.get("by_content_id") or {}
    by_title = catalog.get("by_title") or {}
    if str(content_id) in by_id:
        merged = _empty_sections()
        merged.update(by_id[str(content_id)])
        return merged
    hit = by_title.get((title or "").strip().lower())
    if hit:
        merged = _empty_sections()
        merged.update(hit)
        return merged
    return _empty_sections()


def enrich_project_rows(rows, catalog: dict | None = None) -> list[dict]:
    catalog = catalog if catalog is not None else load_project_section_catalog()
    db_by_title: dict[str, dict] = {}
    db_by_id: dict[str, dict] = {}

    for row in rows:
        item = dict(row)
        item["sections"] = sections_for_project(
            content_id=int(row["id"]),
            title=row["title"] or "",
            catalog=catalog,
        )
        item["section_views"] = build_section_views(item["sections"])
        db_by_title[(row["title"] or "").strip().lower()] = item
        db_by_id[str(row["id"])] = item

    out: list[dict] = []
    used_titles: set[str] = set()
    used_ids: set[str] = set()

    for entry in catalog.get("entries") or []:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        key = title.lower()
        cid = entry.get("content_id")
        if cid is not None and str(cid) in db_by_id:
            out.append(db_by_id[str(cid)])
            used_ids.add(str(cid))
            used_titles.add(key)
            continue
        if key in db_by_title:
            item = db_by_title[key]
            out.append(item)
            used_ids.add(str(item["id"]))
            used_titles.add(key)
            continue
        sections = dict(entry.get("sections") or _empty_sections())
        out.append(
            {
                "id": entry.get("catalog_key") or title,
                "title": title,
                "program_name": None,
                "project_manager": None,
                "delivery_status": None,
                "region": None,
                "sections": sections,
                "section_views": build_section_views(sections),
                "catalog_only": True,
            }
        )
        used_titles.add(key)

    for row in rows:
        if str(row["id"]) in used_ids:
            continue
        out.append(db_by_id[str(row["id"])])

    return out


def count_portfolio_projects(db=None, rows=None, catalog: dict | None = None) -> int:
    """Projects visible on /projects — catalog entries plus approved DB rows, deduplicated."""
    if rows is None:
        if db is None:
            catalog = catalog if catalog is not None else load_project_section_catalog()
            return len(catalog.get("entries") or [])
        rows = db.execute(
            """
            SELECT c.*, u.display_name AS author_name,
                   p.program_name, p.project_manager, p.delivery_status,
                   NULL AS region
            FROM content c
            JOIN users u ON u.id = c.author_id
            JOIN projects p ON p.content_id = c.id
            WHERE c.module = 'projects' AND c.status = 'approved'
            """
        ).fetchall()
    return len(enrich_project_rows(rows, catalog))
