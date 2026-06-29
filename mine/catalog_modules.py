"""Canonical catalogue module taxonomy (avoid drift between dashboards, filters, and forms)."""

KNOWLEDGE_SERIES_MODULES = [
    ("kyc", "KYC series"),
    ("kya", "KYA series"),
    ("domain_term", "Term of the week"),
    ("newsletter", "Newsletter"),
    ("case_study", "Case studies"),
    ("rfp_snippet", "RFP snippets"),
    ("blog", "Blogs & whitepapers"),
]

KNOWLEDGE_SERIES_MODULE_KEYS = frozenset(m for m, _ in KNOWLEDGE_SERIES_MODULES)

CASE_STUDY_MODULE = "case_study"

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
        "list_label": "Training corner",
        "create_h1": "Add a training item",
        "edit_h1": "Edit training item",
        "create_flash": "Training item saved.",
        "edit_flash": "Training item updated.",
    },
    "onboarding": {
        "list_endpoint": "main.onboarding",
        "list_label": "Onboarding kit",
        "create_h1": "Add an onboarding note",
        "edit_h1": "Edit onboarding note",
        "create_flash": "Onboarding note saved.",
        "edit_flash": "Onboarding note updated.",
    },
    "innovation": {
        "list_endpoint": "main.innovation",
        "list_label": "Innovation center",
        "create_h1": "Submit an innovation story",
        "edit_h1": "Edit innovation submission",
        "create_flash": "Innovation story saved.",
        "edit_flash": "Innovation story updated.",
    },
    "hall_of_fame": {
        "list_endpoint": "main.hall_of_fame",
        "list_label": "Hall of Fame",
        "create_h1": "Nominate a Hall of Fame highlight",
        "edit_h1": "Edit Hall of Fame nomination",
        "create_flash": "Hall of Fame entry saved.",
        "edit_flash": "Hall of Fame entry updated.",
    },
}
