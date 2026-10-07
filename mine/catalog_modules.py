"""Canonical catalog module taxonomy (avoid drift between dashboards, filters, and forms)."""

KNOWLEDGE_SERIES_MODULES = [
    ("kyc", "KYC Series"),
    ("kya", "KYA Series"),
    ("domain_term", "Term of the Week"),
    ("newsletter", "Newsletter"),
    ("case_study", "Case Studies"),
    ("rfp_snippet", "RFP Snippets"),
    ("blog", "Blogs & Whitepapers"),
]

KNOWLEDGE_SERIES_MODULE_KEYS = frozenset(m for m, _ in KNOWLEDGE_SERIES_MODULES)

CASE_STUDY_MODULE = "case_study"

# KYC / KYA / DTOW (term of the week) — only admins & moderators may create these.
RESTRICTED_KNOWLEDGE_CREATE_MODULES = frozenset({"kyc", "kya", "domain_term"})

# Knowledge series that use title + summary only (no separate body field).
KNOWLEDGE_MODULES_WITHOUT_BODY = frozenset({"kyc", "domain_term"})

STANDALONE_REPO_MODULES = frozenset({"onboarding", "innovation", "training", "hall_of_fame"})

# URL segment (path) -> content.module slug
SEGMENT_TO_STANDALONE_MODULE = {
    "training": "training",
    "onboarding": "onboarding",
    "innovation": "innovation",
    "hall-of-fame": "hall_of_fame",
}

STANDALONE_MODULE_TO_SEGMENT = {v: k for k, v in SEGMENT_TO_STANDALONE_MODULE.items()}

STANDALONE_REPO_UI = {
    "training": {
        "list_endpoint": "main.training",
        "list_label": "Training Corner",
        "create_h1": "Add a Training Item",
        "edit_h1": "Edit Training Item",
        "create_flash": "Training item saved.",
        "edit_flash": "Training item updated.",
    },
    "onboarding": {
        "list_endpoint": "main.onboarding",
        "list_label": "Onboarding Kit",
        "create_h1": "Add an Onboarding Note",
        "edit_h1": "Edit Onboarding Note",
        "create_flash": "Onboarding note saved.",
        "edit_flash": "Onboarding note updated.",
    },
    "innovation": {
        "list_endpoint": "main.innovation",
        "list_label": "Innovation Center",
        "create_h1": "Submit an Innovation Story",
        "edit_h1": "Edit Innovation Submission",
        "create_flash": "Innovation story saved.",
        "edit_flash": "Innovation story updated.",
    },
    "hall_of_fame": {
        "list_endpoint": "main.hall_of_fame",
        "list_label": "Hall of Fame",
        "create_h1": "Nominate a Hall of Fame Highlight",
        "edit_h1": "Edit Hall of Fame Nomination",
        "create_flash": "Hall of Fame entry saved.",
        "edit_flash": "Hall of Fame entry updated.",
    },
}

MODULE_LABELS = dict(KNOWLEDGE_SERIES_MODULES)
MODULE_LABELS.update(
    {
        "projects": "Programs & Projects",
        "onboarding": "Onboarding Kit",
        "innovation": "Innovation Center",
        "training": "Training Corner",
        "hall_of_fame": "Hall of Fame",
    }
)

SEARCH_FILTER_MODULES: tuple[tuple[str, str], ...] = (
    ("", "All Catalog"),
    *KNOWLEDGE_SERIES_MODULES,
    ("projects", "Programs & Projects"),
    ("onboarding", "Onboarding Kit"),
    ("innovation", "Innovation Center"),
    ("training", "Training Corner"),
    ("hall_of_fame", "Hall of Fame"),
)

SEARCH_XP_CATEGORIES: tuple[dict[str, str], ...] = tuple(
    {"value": value, "label": label} for value, label in SEARCH_FILTER_MODULES
)

SEARCH_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("relevance", "Relevance"),
    ("recent", "Recently updated"),
    ("alpha", "Title A–Z"),
)


def module_label(slug: str | None) -> str:
    key = (slug or "").strip()
    if not key:
        return "—"
    return MODULE_LABELS.get(key, key.replace("_", " ").title())
