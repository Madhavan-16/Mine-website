"""Teams / SharePoint Training_Documents catalog for Training corner (Open in Teams links)."""

from __future__ import annotations

import re
from urllib.parse import quote

from flask import current_app

# FMI Offshore → General → Training_Documents (Teams / SharePoint)
SITE_HOST = "https://hexawareonline.sharepoint.com"
SITE_PATH = "/sites/FMIOFFSHORE/Shared Documents/General/Training_Documents"

# Exact folder names as in Teams, grouped for a calmer Training corner layout
TRAINING_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "kt",
        "Knowledge transfer",
        (
            "AD KT",
            "ArcGIS KT",
            "Functional KT",
            "KT DOCS",
            "T4V-S4HANA Handover KT Sessions",
        ),
    ),
    (
        "analytics",
        "Power BI & analytics",
        (
            "PBI Upskilling Sessions",
            "Power BI Training",
        ),
    ),
    (
        "sessions",
        "Sessions & recordings",
        (
            "Midweek Mind Share Sessions",
            "Old Knowledge Sharing Session",
            "Session Recordings - T4V Project",
        ),
    ),
    (
        "tools",
        "Tools & demos",
        (
            "AI Documents",
            "HVR Demo",
            "T2S Conversion Tool",
        ),
    ),
    (
        "account",
        "Account & archive",
        (
            "Account Training",
            "Archive Old Folders",
        ),
    ),
)

TRAINING_FOLDERS: tuple[str, ...] = tuple(
    name for _key, _label, names in TRAINING_GROUPS for name in names
)


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "folder"


FOLDER_BY_SLUG: dict[str, str] = {_slugify(n): n for n in TRAINING_FOLDERS}


def root_folder_url(app=None) -> str:
    app = app or current_app
    configured = (app.config.get("TEAMS_TRAINING_FOLDER_URL") or "").strip()
    if configured:
        return configured
    return f"{SITE_HOST}{quote(SITE_PATH, safe='/:')}"


def folder_web_url(*path_parts: str, app=None) -> str:
    """Browser URL for Training_Documents or a subfolder (opens in SharePoint / Teams)."""
    parts = [p.strip().strip("/") for p in path_parts if (p or "").strip()]
    if not parts:
        return root_folder_url(app)
    encoded = "/".join(quote(p, safe="") for p in parts)
    base = f"{SITE_HOST}/sites/FMIOFFSHORE/Shared%20Documents/General/Training_Documents"
    return f"{base}/{encoded}"


def catalog_groups(app=None) -> list[dict]:
    """Grouped folders for Training corner UI."""
    out: list[dict] = []
    for key, label, names in TRAINING_GROUPS:
        out.append(
            {
                "key": key,
                "label": label,
                "folders": [
                    {
                        "name": name,
                        "slug": _slugify(name),
                        "teams_url": folder_web_url(name, app=app),
                        "initial": (name[:1] or "?").upper(),
                    }
                    for name in names
                ],
            }
        )
    return out


def catalog_cards(app=None) -> list[dict[str, str]]:
    """Flat folder list (name + Open in Teams URL)."""
    return [
        {
            "name": f["name"],
            "slug": f["slug"],
            "teams_url": f["teams_url"],
        }
        for group in catalog_groups(app)
        for f in group["folders"]
    ]
