"""Programs & Projects — structured section content (config/program_project_sections.json)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from flask import current_app

PROJECT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("overview", "Project Overview"),
    ("supported_applications", "Supported Applications"),
    ("scope_of_work", "Scope of Work"),
    ("business_functions", "Business Functions Supported"),
    ("mining_value_chain", "Mining Value Chain Supported"),
    ("technologies", "Technologies"),
    ("business_benefits", "Business Benefits"),
    ("tech_benefits", "Tech. Benefits"),
)

PROJECT_SECTION_ICONS: dict[str, str] = {
    "overview": "overview",
    "supported_applications": "apps",
    "scope_of_work": "scope",
    "business_functions": "functions",
    "mining_value_chain": "value-chain",
    "technologies": "tech-stack",
    "business_benefits": "business-benefits",
    "tech_benefits": "tech-benefits",
}

_CHIP_SECTIONS = frozenset({"supported_applications", "technologies", "mining_value_chain"})

_APP_BRAND_RULES: tuple[tuple[str, str], ...] = (
    ("snowflake openflow", "snowflake"),
    ("snowflake data cloud", "snowflake"),
    ("snowflake", "snowflake"),
    ("microsoft power bi", "microsoft-power-bi"),
    ("power bi", "microsoft-power-bi"),
    ("microsoft teams", "microsoft-teams"),
    ("sharepoint", "microsoft-sharepoint"),
    ("excel", "microsoft-excel"),
    ("azure data factory", "microsoft-azure"),
    ("cosmos db", "microsoft-azure"),
    ("sql server", "microsoft-sql-server"),
    ("sql", "microsoft-sql-server"),
    ("odata", "odata"),
    ("rest api", "rest-api"),
    ("soap", "rest-api"),
    ("json", "rest-api"),
    ("xml", "rest-api"),
    ("sap cloud platform integration", "sap-cpi"),
    ("sap cpi", "sap-cpi"),
    ("sap integration", "sap-cpi"),
    ("sap ariba", "sap-ariba"),
    ("ariba", "sap-ariba"),
    ("successfactors", "sap-successfactors"),
    ("businessobjects", "sap-businessobjects"),
    ("sap bo", "sap-businessobjects"),
    ("s/4hana", "sap-s4hana"),
    ("s4hana", "sap-s4hana"),
    ("onestream", "onestream"),
    ("sims", "sims"),
    ("nola", "nola"),
    ("enterprise data warehouse", "fcx-edw"),
    (" edw", "fcx-edw"),
    ("customapps", "customapps"),
    ("enterprise integration platform", "enterprise-integration"),
    ("enterprise integration", "enterprise-integration"),
    ("enterprise applications", "enterprise-applications"),
    ("data engineering", "data-integration"),
    ("data pipeline", "data-integration"),
    ("data integration", "data-integration"),
    ("etl", "data-integration"),
    ("elt", "data-integration"),
    ("devops", "devops"),
    ("project management", "project-management"),
    ("inventory optimization", "inventory-optimization"),
    ("supply chain", "supply-chain"),
    ("operational analytics", "operational-analytics"),
    ("enterprise analytics", "operational-analytics"),
    ("analytics platform", "operational-analytics"),
    ("data analytics", "operational-analytics"),
    ("enterprise reporting", "enterprise-reporting"),
    ("business intelligence", "business-intelligence"),
    ("sap", "sap"),
)


def _app_brand_slug(label: str) -> str | None:
    """Map application / technology label to a brand icon asset slug."""
    t = (label or "").lower()
    for needle, slug in _APP_BRAND_RULES:
        if needle in t:
            return slug
    return None


def _build_chip(label: str, section_key: str) -> dict:
    chip = {"text": label, "icon": _chip_icon(label, section_key)}
    if section_key in ("supported_applications", "technologies"):
        brand = _app_brand_slug(label)
        if brand:
            chip["brand"] = brand
    return chip


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


_VALUE_CHAIN_STAGES: tuple[dict[str, str], ...] = (
    {"id": "plan", "label": "Plan", "icon": "plan"},
    {"id": "extract", "label": "Extract", "icon": "production"},
    {"id": "haul", "label": "Haul", "icon": "logistics"},
    {"id": "process", "label": "Process", "icon": "process"},
    {"id": "maintain", "label": "Maintain", "icon": "maintenance"},
    {"id": "supply", "label": "Supply", "icon": "inventory"},
    {"id": "report", "label": "Report", "icon": "dashboard"},
)

_BUSINESS_FUNCTION_GROUPS: tuple[dict[str, str | tuple[str, ...]], ...] = (
    {
        "id": "operations",
        "title": "Mine Operations",
        "icon": "production",
        "keywords": (
            "mine operation",
            "production operation",
            "production monitor",
            "maintenance",
            "equipment",
            "asset &",
            "asset and",
            "engineering",
            "operational excellence",
            "continuous improvement",
            "ore ",
            "haul",
            "drill",
            "blast",
            "processing",
            "mining",
        ),
    },
    {
        "id": "planning",
        "title": "Planning & Finance",
        "icon": "plan",
        "keywords": (
            "strategic plan",
            "financial plan",
            "operational plan",
            "finance",
            "financial",
            "budget",
            "cost optim",
            "cost management",
            "corporate report",
            "decision support",
            "capital",
            "human resource",
            "workforce",
        ),
    },
    {
        "id": "analytics",
        "title": "Analytics & BI",
        "icon": "analytics",
        "keywords": (
            "business intelligence",
            "analytics",
            "data engineering",
            "digital transformation",
            "insight",
        ),
    },
    {
        "id": "reporting",
        "title": "Reporting & Performance",
        "icon": "report",
        "keywords": (
            "reporting",
            "executive",
            "performance monitor",
            "performance management",
            "operational report",
            "production report",
            "esg",
            "sustainability",
            "master data",
            "data management",
            "monitoring",
        ),
    },
    {
        "id": "supply_chain",
        "title": "Supply Chain & Materials",
        "icon": "logistics",
        "keywords": (
            "supply chain",
            "procurement",
            "inventory",
            "warehouse",
            "material",
            "vendor",
            "supplier",
            "logistics",
            "sourcing",
            "replenish",
            "global supply",
        ),
    },
    {
        "id": "technology",
        "title": "Technology & Integration",
        "icon": "pipeline",
        "keywords": (
            "integration",
            "it operation",
            "automation",
            "enterprise application",
            "enterprise data",
            "data exchange",
            "project management",
            "data platform",
            "consolidat",
            "process automation",
        ),
    },
)


def _classify_business_function(label: str) -> str:
    """Assign a business-function label to one of five domain cards."""
    t = (label or "").lower()
    for group in _BUSINESS_FUNCTION_GROUPS:
        if any(keyword in t for keyword in group["keywords"]):
            return str(group["id"])
    return "analytics"


def _extract_business_function_lines(text: str) -> list[str]:
    """Normalize prose or line-list copy into function labels for card grouping."""
    text = (text or "").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1:
        return lines

    extracted: list[str] = []
    domain_match = re.search(
        r"\bfrom\s+((?:[a-z/&\-\s]+?(?:,\s*|\s+and\s+))+[a-z/&\-\s]+)\s+(?:systems?|sources?|platforms?)",
        text,
        re.I,
    )
    if domain_match:
        for part in re.split(r",\s*|\s+and\s+", domain_match.group(1)):
            part = part.strip()
            if len(part) > 2:
                extracted.append(part.title() if part.islower() else part)

    t = text.lower()
    theme_labels = (
        (("production", "equipment performance", "operational efficiency"), "Production & Equipment Performance"),
        (("strategic decision", "executive", "decision-making"), "Strategic Decision-Making"),
        (("insight", "analytics", "reporting"), "Enterprise Analytics & Reporting"),
        (("data integration", "consolidat", "data platform"), "Enterprise Data Consolidation"),
    )
    for keywords, label in theme_labels:
        if any(keyword in t for keyword in keywords) and label not in extracted:
            extracted.append(label)

    if extracted:
        return extracted

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]
    if sentences:
        return sentences[:5]
    return [text]


def _split_function_card(card: dict) -> list[dict]:
    """Split an oversized function card using concise labels from each half."""
    items = card["capabilities"]
    if len(items) < 2:
        return [card]
    mid = (len(items) + 1) // 2
    left, right = items[:mid], items[mid:]
    return [
        {
            **card,
            "id": f"{card['id']}-a",
            "title": left[0]["text"] if len(left) == 1 else f"{card['title']} · Focus",
            "capabilities": left,
        },
        {
            **card,
            "id": f"{card['id']}-b",
            "title": right[0]["text"] if len(right) == 1 else f"{card['title']} · Extended",
            "capabilities": right,
        },
    ]


def _ensure_function_card_count(cards: list[dict], *, minimum: int = 4, maximum: int = 5) -> list[dict]:
    """Expand or trim cards so the section reads as four or five domain groupings."""
    cards = list(cards)
    total_items = sum(len(card["capabilities"]) for card in cards)
    if total_items < minimum:
        return cards

    while len(cards) < minimum:
        largest = max(cards, key=lambda card: len(card["capabilities"]))
        if len(largest["capabilities"]) < 2:
            break
        idx = cards.index(largest)
        cards = cards[:idx] + _split_function_card(largest) + cards[idx + 1 :]
        if len(cards) >= maximum:
            break

    while len(cards) > maximum:
        smallest = min(cards, key=lambda card: len(card["capabilities"]))
        if len(smallest["capabilities"]) == 0:
            cards.remove(smallest)
            continue
        merge_target = min(
            (card for card in cards if card is not smallest),
            key=lambda card: len(card["capabilities"]),
        )
        merge_target["capabilities"] = merge_target["capabilities"] + smallest["capabilities"]
        cards.remove(smallest)

    return cards


def _build_business_function_cards(lines: list[str]) -> dict:
    """Group business-function labels into four or five thematic cards."""
    buckets: dict[str, list[dict]] = {str(group["id"]): [] for group in _BUSINESS_FUNCTION_GROUPS}
    for line in lines:
        group_id = _classify_business_function(line)
        buckets[group_id].append(_build_chip(line, "business_functions"))

    cards: list[dict] = []
    for group in _BUSINESS_FUNCTION_GROUPS:
        items = buckets[str(group["id"])]
        if items:
            cards.append(
                {
                    "id": group["id"],
                    "title": group["title"],
                    "icon": group["icon"],
                    "capabilities": items,
                }
            )

    cards = _ensure_function_card_count(cards)
    return {"layout": "function_cards", "cards": cards}


def _value_chain_stage_id(label: str) -> str:
    """Map catalog value-chain label to a canonical pit-to-port stage."""
    t = (label or "").lower()
    if any(
        k in t
        for k in (
            "mine plan",
            "strategic mine",
            "strategic plan",
            "resource plan",
            "engineering execution",
            "production schedul",
            "material plan",
            "cost & budget",
            "cost and budget",
            "capital & operational",
            "production forecast",
        )
    ):
        return "plan"
    if "haul" in t or "haulage" in t:
        return "haul"
    if any(
        k in t
        for k in (
            "supply chain",
            "logistic",
            "procurement",
            "inventory",
            "warehouse",
            "sourcing",
            "replenish",
            "material procurement",
        )
    ):
        return "supply"
    if any(
        k in t
        for k in (
            "maintenance",
            "equipment",
            "asset &",
            "asset and",
            "spare part",
            "utilization",
        )
    ):
        return "maintain"
    if any(
        k in t
        for k in (
            "reporting",
            " monitoring",
            "analytics",
            "performance monitoring",
            "performance analysis",
            "financial",
            "executive",
            "business performance",
            "workforce",
            "data integration",
            "data management",
            "decision support",
            "continuous process",
            "operational reporting",
        )
    ) or t.endswith(" reporting"):
        return "report"
    if any(
        k in t
        for k in (
            "drill",
            "blast",
            "ore extraction",
            "production operation",
            "production data collection",
            "production support",
        )
    ):
        return "extract"
    if any(k in t for k in ("ore process", "crushing")):
        return "process"
    return "report"


def _build_value_chain_flow(chips: list[dict]) -> dict:
    """Horizontal pit-to-port stages with catalog labels grouped under each."""
    buckets: dict[str, list[dict]] = {stage["id"]: [] for stage in _VALUE_CHAIN_STAGES}
    for chip in chips:
        stage_id = _value_chain_stage_id(chip["text"])
        buckets[stage_id].append(chip)

    stages: list[dict] = []
    for stage in _VALUE_CHAIN_STAGES:
        items = buckets[stage["id"]]
        stages.append(
            {
                "id": stage["id"],
                "label": stage["label"],
                "icon": stage["icon"],
                "active": bool(items),
                "details": [item["text"] for item in items],
            }
        )

    return {
        "layout": "value_chain_flow",
        "stages": stages,
        "activeCount": sum(1 for stage in stages if stage["active"]),
        "chips": chips,
    }


def parse_section_display(section_key: str, text: str) -> dict:
    """Shape section text for interactive portal layouts (chips, duration badge, prose)."""
    text = (text or "").strip()
    if not text:
        return {"empty": True}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if section_key in _CHIP_SECTIONS:
        chips = [_build_chip(line, section_key) for line in lines]
        if section_key == "mining_value_chain":
            return _build_value_chain_flow(chips)
        return {"layout": "chips", "chips": chips}
    if section_key in ("business_benefits", "tech_benefits") and len(lines) > 1:
        return {
            "layout": "chips",
            "chips": [_build_chip(line, section_key) for line in lines],
        }
    if section_key == "business_functions":
        function_lines = _extract_business_function_lines(text)
        if function_lines:
            return _build_business_function_cards(function_lines)
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


def build_section_views(
    sections: dict[str, str], engagement_details: dict | None = None
) -> dict[str, dict]:
    views = {key: parse_section_display(key, sections.get(key, "")) for key in _SECTION_KEYS}
    overview = views.get("overview")
    if overview and not overview.get("empty") and engagement_details:
        overview["sowDetails"] = engagement_details
    return views


def _config_path() -> Path:
    raw = (current_app.config.get("PROGRAM_PROJECT_SECTIONS_JSON") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = (Path(current_app.config["BASE_DIR"]) / p).resolve()
        return p
    return _CONFIG_PATH


def _normalize_active(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "active")
    return bool(value)


def project_is_active(row: dict) -> bool:
    return _normalize_active(row.get("is_active", True))


def filter_projects_by_active(rows: list[dict], active: str = "1") -> list[dict]:
    mode = (active or "1").strip().lower()
    if mode == "all":
        return rows
    want_active = mode != "0"
    return [row for row in rows if project_is_active(row) is want_active]


def _config_path_unsafe() -> Path:
    """Config path without Flask request context (for catalog writes)."""
    return _CONFIG_PATH


def set_catalog_project_active(*, catalog_key: str | None = None, title: str | None = None, is_active: bool = True) -> bool:
    """Persist active flag for a catalog-only portfolio entry in program_project_sections.json."""
    path = _config_path()
    if not path.is_file():
        path = _config_path_unsafe()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False

    updated = False
    for idx, entry in enumerate(data.get("projects") or []):
        if not isinstance(entry, dict):
            continue
        key = f"cfg-{idx}"
        entry_title = (entry.get("title") or "").strip()
        if catalog_key and key == catalog_key:
            entry["is_active"] = bool(is_active)
            updated = True
            break
        if title and entry_title == title.strip():
            entry["is_active"] = bool(is_active)
            updated = True
            break

    if not updated:
        return False
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def set_db_project_active(db, content_id: int, is_active: bool) -> bool:
    cur = db.execute(
        "UPDATE projects SET is_active = ? WHERE content_id = ?",
        (1 if is_active else 0, content_id),
    )
    return cur.rowcount > 0


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
        engagement_details = entry.get("engagement_details")
        if not isinstance(engagement_details, dict):
            engagement_details = None

        if cid is not None:
            by_id[str(cid)] = sections
        if title:
            by_title[title.lower()] = sections
            catalog_entry = {
                "catalog_key": f"cfg-{idx}",
                "title": title,
                "content_id": cid,
                "sections": sections,
                "is_active": _normalize_active(entry.get("is_active", True)),
            }
            if engagement_details:
                catalog_entry["engagement_details"] = engagement_details
            entries.append(catalog_entry)

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
        if "is_active" not in item or item.get("is_active") is None:
            item["is_active"] = 1
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
            item = db_by_id[str(cid)]
            if "is_active" not in entry:
                item["is_active"] = entry.get("is_active", item.get("is_active", 1))
            out.append(item)
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
        engagement_details = entry.get("engagement_details")
        if not isinstance(engagement_details, dict):
            engagement_details = None
        out.append(
            {
                "id": entry.get("catalog_key") or title,
                "catalog_key": entry.get("catalog_key"),
                "title": title,
                "program_name": None,
                "project_manager": None,
                "delivery_status": None,
                "region": None,
                "is_active": entry.get("is_active", True),
                "sections": sections,
                "section_views": build_section_views(sections, engagement_details),
                "catalog_only": True,
            }
        )
        used_titles.add(key)

    for row in rows:
        if str(row["id"]) in used_ids:
            continue
        out.append(db_by_id[str(row["id"])])

    return out


def _parse_date_part(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            if fmt in ("%B %Y", "%b %Y"):
                return date(parsed.year, parsed.month, 1)
            return parsed
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}", text):
        return date(int(text), 1, 1)
    return None


def parse_duration_range(duration: str | None) -> dict:
    """Parse overview duration text into ISO start/end dates."""
    label = (duration or "").strip() or None
    if not label:
        return {"start": None, "end": None, "label": None}
    parts = [p.strip() for p in re.split(r"\s*[–—-]\s*", label) if p.strip()]
    if not parts:
        return {"start": None, "end": None, "label": label}
    start = _parse_date_part(parts[0])
    end = _parse_date_part(parts[1]) if len(parts) > 1 else None
    if start and not end:
        end = date(start.year, 12, 31)
    if end and not start:
        start = date(end.year, 1, 1)
    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "label": label,
    }


def build_portfolio_viz(rows: list[dict]) -> dict:
    """Gantt + summary insights for the portfolio timeline view."""
    projects: list[dict] = []

    for idx, row in enumerate(rows):
        pid = str(row.get("id") or f"project-{idx}")
        title = (row.get("title") or "").strip() or "Untitled project"
        overview = (row.get("section_views") or {}).get("overview") or {}
        duration = parse_duration_range(overview.get("duration"))

        projects.append(
            {
                "id": pid,
                "title": title,
                "order": idx,
                "tone": idx % 3,
                "duration": duration.get("label"),
                "start": duration.get("start"),
                "end": duration.get("end"),
                "shortRange": (
                    f"{_format_insight_date(duration.get('start'))} – {_format_insight_date(duration.get('end'))}"
                    if duration.get("start") and duration.get("end")
                    else None
                ),
            }
        )

    gantt_rows = [p for p in projects if p.get("start") and p.get("end")]
    gantt_rows.sort(key=lambda p: p.get("order", 0))

    starts = [p["start"] for p in gantt_rows]
    ends = [p["end"] for p in gantt_rows]
    range_start = min(starts) if starts else None
    range_end = max(ends) if ends else None

    today_iso = date.today().isoformat()
    active_today = [
        p
        for p in projects
        if p.get("start")
        and p.get("end")
        and p["start"] <= today_iso <= p["end"]
    ]

    return {
        "gantt": {
            "rangeStart": range_start,
            "rangeEnd": range_end,
            "rows": gantt_rows,
        },
        "insights": {
            "projectCount": len(projects),
            "activeTodayCount": len(active_today),
            "rangeLabel": (
                f"{_format_insight_date(range_start)} – {_format_insight_date(range_end)}"
                if range_start and range_end
                else None
            ),
        },
    }


def _format_insight_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        parsed = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return iso
    return parsed.strftime("%b %Y")


def fetch_approved_project_rows(db):
    """Approved project content rows; tolerates DBs before projects.is_active migration."""
    sql_with_active = """
        SELECT c.*, u.display_name AS author_name,
               p.program_name, p.project_manager, p.delivery_status,
               p.is_active,
               (SELECT meta_value FROM content_meta m
                WHERE m.content_id = c.id AND m.meta_key = 'region' LIMIT 1) AS region
        FROM content c
        JOIN users u ON u.id = c.author_id
        JOIN projects p ON p.content_id = c.id
        WHERE c.module = 'projects' AND c.status = 'approved'
    """
    sql_legacy = """
        SELECT c.*, u.display_name AS author_name,
               p.program_name, p.project_manager, p.delivery_status,
               1 AS is_active,
               (SELECT meta_value FROM content_meta m
                WHERE m.content_id = c.id AND m.meta_key = 'region' LIMIT 1) AS region
        FROM content c
        JOIN users u ON u.id = c.author_id
        JOIN projects p ON p.content_id = c.id
        WHERE c.module = 'projects' AND c.status = 'approved'
    """
    try:
        return db.execute(sql_with_active).fetchall()
    except Exception:
        return db.execute(sql_legacy).fetchall()


def count_portfolio_projects(db=None, rows=None, catalog: dict | None = None, *, active_only: bool = False) -> int:
    """Projects visible on /projects — catalog entries plus approved DB rows, deduplicated."""
    if rows is None:
        if db is None:
            catalog = catalog if catalog is not None else load_project_section_catalog()
            entries = catalog.get("entries") or []
            if active_only:
                return sum(1 for entry in entries if project_is_active(entry))
            return len(entries)
        rows = fetch_approved_project_rows(db)
    enriched = enrich_project_rows(rows, catalog)
    if active_only:
        enriched = filter_projects_by_active(enriched, "1")
    return len(enriched)
