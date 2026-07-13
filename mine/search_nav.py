"""Universal search navigation — section intent detection and destination URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from flask import url_for

from mine.catalog_modules import KNOWLEDGE_SERIES_MODULE_KEYS, STANDALONE_REPO_MODULES

_MIN_PREFIX_LEN = 3
_MIN_REDIRECT_SCORE = 480


@dataclass(frozen=True)
class SearchSection:
    id: str
    label: str
    aliases: tuple[str, ...]
    kind: str  # knowledge | route
    module: str | None = None
    endpoint: str | None = None


SEARCH_SECTIONS: tuple[SearchSection, ...] = (
    SearchSection(
        id="knowledge",
        label="Knowledge repository",
        aliases=(
            "knowledge repository",
            "knowledge repo",
            "knowledge catalogue",
            "knowledge catalog",
            "knowledge",
            "repository",
            "catalogue",
            "catalog",
        ),
        kind="route",
        endpoint="main.knowledge",
    ),
    SearchSection(
        id="case_study",
        label="Case studies",
        aliases=("case study", "case studies", "case-study", "case-studies", "cases", "case"),
        kind="knowledge",
        module="case_study",
    ),
    SearchSection(
        id="kyc_series",
        label="KYC series",
        aliases=("kyc series", "kyc episode", "kyc episodes", "kyc entry", "kyc entries", "kyc"),
        kind="knowledge",
        module="kyc",
    ),
    SearchSection(
        id="kya",
        label="KYA series",
        aliases=("kya series", "kya episode", "kya episodes", "kya", "know your account"),
        kind="knowledge",
        module="kya",
    ),
    SearchSection(
        id="domain_term",
        label="Term of the week",
        aliases=("term of the week", "domain term", "domain terms", "terms", "term"),
        kind="knowledge",
        module="domain_term",
    ),
    SearchSection(
        id="newsletter",
        label="Newsletter",
        aliases=("newsletter", "newsletters", "newsletter archive"),
        kind="knowledge",
        module="newsletter",
    ),
    SearchSection(
        id="rfp_snippet",
        label="RFP snippets",
        aliases=("rfp snippets", "rfp snippet", "rfp"),
        kind="knowledge",
        module="rfp_snippet",
    ),
    SearchSection(
        id="blog",
        label="Blogs & whitepapers",
        aliases=(
            "blogs and whitepapers",
            "blogs & whitepapers",
            "blog",
            "blogs",
            "whitepaper",
            "whitepapers",
        ),
        kind="knowledge",
        module="blog",
    ),
    SearchSection(
        id="projects",
        label="Programs & projects",
        aliases=(
            "programs and projects",
            "program and projects",
            "programmes and projects",
            "programme and projects",
            "programs & projects",
            "programmes & projects",
            "programs projects",
            "programmes projects",
            "programs & project",
            "projects portal",
            "delivery portfolio",
            "programs",
            "programmes",
            "program",
            "programme",
            "projects",
            "project",
        ),
        kind="route",
        endpoint="projects.project_list",
    ),
    SearchSection(
        id="onboarding",
        label="Onboarding kit",
        aliases=("onboarding kit", "onboarding", "onboard", "on-boarding"),
        kind="route",
        endpoint="main.onboarding",
    ),
    SearchSection(
        id="innovation",
        label="Innovation center",
        aliases=("innovation center", "innovation centre", "innovation", "innovate"),
        kind="route",
        endpoint="main.innovation",
    ),
    SearchSection(
        id="training",
        label="Training corner",
        aliases=("training corner", "training", "train", "learn"),
        kind="route",
        endpoint="main.training",
    ),
    SearchSection(
        id="hall_of_fame",
        label="Hall of Fame",
        aliases=("hall of fame", "hall-of-fame", "halloffame", "hof", "fame"),
        kind="route",
        endpoint="main.hall_of_fame",
    ),
    SearchSection(
        id="journey",
        label="Hexaware Journey",
        aliases=(
            "hexaware journey",
            "freeport journey",
            "partnership journey",
            "journey timeline",
            "journey",
        ),
        kind="route",
        endpoint="main.journey",
    ),
    SearchSection(
        id="domain_knowledge",
        label="Domain Knowledge",
        aliases=(
            "domain knowledge",
            "open pit copper",
            "open-pit copper",
            "copper domain",
            "mining domain",
            "mining domain knowledge",
            "copper mining",
            "copper",
        ),
        kind="route",
        endpoint="main.open_pit_copper_domain",
    ),
    SearchSection(
        id="fmi_kyc",
        label="Know your Customer — Freeport",
        aliases=(
            "know your customer freeport",
            "know your customer",
            "know your client",
            "freeport customer",
            "freeport kyc",
            "program map",
            "programme map",
            "fmi kyc",
            "customer freeport",
        ),
        kind="route",
        endpoint="reference.fmi_kyc",
    ),
    SearchSection(
        id="dashboard",
        label="Dashboard",
        aliases=("dashboard", "command center", "command centre", "home"),
        kind="route",
        endpoint="main.dashboard",
    ),
)

_ALIAS_INDEX: tuple[tuple[str, SearchSection], ...] = tuple(
    sorted(
        ((alias, section) for section in SEARCH_SECTIONS for alias in section.aliases),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)


def _normalize_query(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = re.sub(r"[^\w\s&/-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _phrase_in_query(query: str, phrase: str) -> bool:
    if not phrase:
        return False
    padded = f" {query} "
    return f" {phrase} " in padded


def _score_alias(query: str, alias_norm: str) -> tuple[int, str]:
    """Score how strongly a query matches a section alias. Higher is better."""
    if not alias_norm:
        return (0, "")

    if query == alias_norm:
        return (1000 + len(alias_norm), "")

    if query.startswith(alias_norm + " "):
        return (900 + len(alias_norm), query[len(alias_norm) :].strip())

    if _phrase_in_query(query, alias_norm):
        remainder = re.sub(rf"\b{re.escape(alias_norm)}\b", " ", query, count=1)
        remainder = re.sub(r"\s+", " ", remainder).strip()
        return (800 + len(alias_norm), remainder)

    tokens = query.split()
    if len(tokens) == 1:
        token = tokens[0]
        if len(token) < _MIN_PREFIX_LEN:
            return (0, "")

        if alias_norm == token:
            return (950 + len(alias_norm), "")

        if alias_norm.startswith(token):
            return (520 + len(token), "")

        for word in alias_norm.split():
            if word == token:
                return (540 + len(word), "")
            if len(token) >= 4 and word.startswith(token):
                return (500 + len(token), "")

    return (0, "")


def _best_section_match(query: str) -> tuple[SearchSection | None, int, str]:
    best_section: SearchSection | None = None
    best_score = 0
    best_remainder = ""

    for section in SEARCH_SECTIONS:
        for alias in section.aliases:
            alias_norm = _normalize_query(alias)
            score, remainder = _score_alias(query, alias_norm)
            if score > best_score:
                best_section = section
                best_score = score
                best_remainder = remainder

    return best_section, best_score, best_remainder


def _section_destination_url(section: SearchSection, remainder: str | None = None) -> str:
    q = (remainder or "").strip() or None
    if section.kind == "knowledge" and section.module:
        return url_for("main.knowledge", module=section.module, q=q)
    if section.endpoint and not q:
        return url_for(section.endpoint)
    if section.endpoint and q:
        module_slug = {
            "main.onboarding": "onboarding",
            "main.innovation": "innovation",
            "main.training": "training",
            "main.hall_of_fame": "hall_of_fame",
            "projects.project_list": "projects",
        }.get(section.endpoint)
        if module_slug:
            return url_for("search.search", q=q, module=module_slug, stay=1)
        return url_for(section.endpoint, q=q)
    return url_for("search.search", q=remainder or "")


def section_open_url(section: SearchSection, remainder: str | None = None) -> str:
    """Direct open URL for a matched section (search result shortcuts)."""
    return _section_destination_url(section, remainder)


def resolve_section_navigation(q: str, module: str | None = None) -> str | None:
    """Return a redirect URL when the query is primarily section navigation."""
    del module  # Section intent wins over catalogue filters unless stay=1 on search page.
    normalized = _normalize_query(q)
    if not normalized:
        return None

    best_section, best_score, remainder = _best_section_match(normalized)
    if not best_section or best_score < _MIN_REDIRECT_SCORE:
        return None
    return _section_destination_url(best_section, remainder or None)


def section_search_hits(q: str, limit: int = 8) -> list[dict]:
    """Section matches formatted for the search results page (no auto-redirect)."""
    normalized = _normalize_query(q)
    if not normalized:
        return []

    scored: list[tuple[int, SearchSection]] = []
    seen: set[str] = set()
    for section in SEARCH_SECTIONS:
        best = 0
        for alias in section.aliases:
            alias_norm = _normalize_query(alias)
            score, _ = _score_alias(normalized, alias_norm)
            best = max(best, score)
        if best >= 420 and section.id not in seen:
            scored.append((best, section))
            seen.add(section.id)

    scored.sort(key=lambda pair: pair[0], reverse=True)
    hits: list[dict] = []
    for score, section in scored[:limit]:
        hits.append(
            {
                "section": section,
                "url": section_open_url(section),
                "kind_label": "Knowledge series" if section.kind == "knowledge" else "MiNe section",
                "score": score,
            }
        )
    return hits


def matching_sections(q: str, limit: int = 8) -> list[SearchSection]:
    """Sections that loosely match the query (for result-page shortcuts)."""
    normalized = _normalize_query(q)
    if not normalized:
        return []

    scored: list[tuple[int, SearchSection]] = []
    seen: set[str] = set()
    for section in SEARCH_SECTIONS:
        best = 0
        for alias in section.aliases:
            alias_norm = _normalize_query(alias)
            score, _ = _score_alias(normalized, alias_norm)
            best = max(best, score)
        if best >= 420 and section.id not in seen:
            scored.append((best, section))
            seen.add(section.id)

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [section for _, section in scored[:limit]]


def result_url_for_content(module: str, content_id: int) -> str:
    """Module-aware link for a catalogue search hit."""
    mod = (module or "").strip()
    if mod == "projects":
        return url_for("projects.project_list", open=content_id)
    if mod in STANDALONE_REPO_MODULES:
        endpoint = {
            "onboarding": "main.onboarding",
            "innovation": "main.innovation",
            "training": "main.training",
            "hall_of_fame": "main.hall_of_fame",
        }.get(mod)
        if endpoint:
            return url_for(endpoint)
    if mod in KNOWLEDGE_SERIES_MODULE_KEYS:
        return url_for("content.content_view", cid=content_id)
    return url_for("content.content_view", cid=content_id)
