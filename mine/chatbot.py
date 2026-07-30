"""MiNe knowledge chatbot — FTS retrieval over Knowledge + Domain + Journey + KYC (+ Projects for non-guests)."""

from __future__ import annotations

import os
import re
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from mine.auth_utils import load_current_user, login_required
from mine.catalog_modules import KNOWLEDGE_SERIES_MODULE_KEYS, STANDALONE_REPO_MODULES, module_label
from mine.catalog_query import query_catalog
from mine.db import get_db
from mine.guest import is_guest_user
from mine.project_catalog import load_project_section_catalog
from mine.search_nav import SEARCH_SECTIONS, section_open_url, section_search_hits

bp = Blueprint("chatbot", __name__, url_prefix="/api/chat")

# Base pages always in chatbot scope (guest-safe).
_BASE_SECTION_IDS = frozenset({"knowledge", "journey", "domain_knowledge", "fmi_kyc"})
# Extra sections for full (non-guest) signed-in users.
_STAFF_SECTION_IDS = frozenset(
    {"projects", "onboarding", "training", "innovation", "hall_of_fame"}
)

_PAGE_BLURBS: dict[str, str] = {
    "knowledge": (
        "The Knowledge repository holds approved Freeport–Hexaware knowledge articles "
        "(KYC/KYA series, term of the week, newsletters, case studies, RFP snippets, blogs)."
    ),
    "journey": (
        "Freeport–Hexaware Journey covers the partnership story and digital/mining transformation themes, "
        "including the autonomous mining revolution narrative."
    ),
    "domain_knowledge": (
        "Domain Knowledge explains open-pit copper mining concepts — lifecycle, value chain, "
        "digital enablement, and related operations topics."
    ),
    "fmi_kyc": (
        "Know your Customer — Freeport introduces Freeport-McMoRan as the account customer: "
        "business context, evolution timeline, and engagement background."
    ),
    "projects": (
        "Programs & projects is the portfolio of Freeport engagement programmes and delivery projects "
        "(status, managers, and published project records)."
    ),
    "onboarding": (
        "Onboarding kit helps new joiners ramp up with Freeport–Hexaware orientation notes and resources."
    ),
    "training": (
        "Training corner collects learning materials and training items for the Freeport engagement."
    ),
    "innovation": (
        "Innovation center highlights innovation stories and ideas from the Freeport–Hexaware team."
    ),
    "hall_of_fame": (
        "Hall of Fame celebrates wins and standout contributions from the engagement."
    ),
}


# Knowledge-series intents: exact-ish queries should filter to one module, not random FTS.
_MODULE_INTENT: tuple[tuple[tuple[str, ...], str], ...] = (
    (("case study", "case studies", "casestudy"), "case_study"),
    (("kyc series", "kyc episode", "kyc"), "kyc"),
    (("kya series", "kya"), "kya"),
    (("term of the week", "domain term", "terms"), "domain_term"),
    (("newsletter", "newsletters"), "newsletter"),
    (("rfp", "rfp snippet", "rfp snippets"), "rfp_snippet"),
    (("blog", "blogs", "whitepaper", "whitepapers"), "blog"),
)

_HELP_REPLY = (
    "Hey — I'm Ask MiNe. How can I assist you today? "
    "Ask me anything, or try onboarding, training, journey, copper, projects, or Knowledge."
)

_HELP_REPLY_GUEST = (
    "Hey — I'm Ask MiNe. As Guest you can explore Knowledge, Domain Knowledge, "
    "Freeport–Hexaware Journey, and Know your Customer. "
    "Sign in with a full account for Programs & projects and other staff sections."
)

_GUEST_STAFF_REPLY = (
    "That area is available to full MiNe accounts (not Guest).\n\n"
    "Sign in with your username to open **Programs & projects**, SOW details, "
    "**Onboarding**, **Training**, **Innovation**, or **Hall of Fame**.\n\n"
    "As Guest you can browse **Knowledge**, **Domain Knowledge**, **Journey**, "
    "and **Know your Customer**."
)

_GUEST_STAFF_EXACT = frozenset(
    {
        "project",
        "projects",
        "program",
        "programs",
        "programme",
        "programmes",
        "onboarding",
        "onboard",
        "onboarding kit",
        "training",
        "train",
        "training corner",
        "innovation",
        "innovation center",
        "innovation centre",
        "hall of fame",
        "hof",
        "sow",
        "sows",
        "sow documents",
        "sow document",
        "portfolio",
        "sims",
        "openflow",
        "open flow",
        "related projects",
        "compare projects",
        "show architecture",
        "open document",
    }
)

_GUEST_STAFF_PHRASES = (
    "statement of work",
    "programs and projects",
    "programmes and projects",
    "project portfolio",
    "onboarding kit",
    "training corner",
    "innovation center",
    "innovation centre",
    "hall of fame",
    "sims extension",
    "sims project",
    "project sims",
    "snowflake openflow",
    "openflow migration",
    "related projects",
    "compare projects",
    "sow document",
)

_GREETING_REPLIES = (
    "Hey! How can I assist you today?",
    "Hi there — what can I help you with?",
    "Hello! Ask me anything, or dig into Freeport knowledge whenever you're ready.",
)

_GREETING_WORDS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hiya",
        "yo",
        "sup",
        "howdy",
        "hola",
        "good morning",
        "good afternoon",
        "good evening",
        "gm",
        "help",
        "?",
    }
)



def _chatbot_enabled() -> bool:
    return bool(current_app.config.get("CHATBOT_ENABLED", True))


def _normalize(q: str) -> str:
    q = (q or "").strip().lower()
    q = q.replace("&", " and ")
    q = re.sub(r"[^\w\s/-]+", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _allowed_section_ids(*, guest: bool) -> frozenset[str]:
    if guest:
        return _BASE_SECTION_IDS
    return _BASE_SECTION_IDS | _STAFF_SECTION_IDS


def _snippet(text: str | None, limit: int = 220) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    return raw[: limit - 1].rstrip() + "…"


def _result_url_for_content(module: str | None, cid: int) -> str:
    from mine.search_nav import result_url_for_content

    try:
        return result_url_for_content(module or "", cid)
    except Exception:
        return f"/content/{cid}" if cid else "/projects"


def _page_hit(section_id: str) -> dict[str, Any] | None:
    section = next((s for s in SEARCH_SECTIONS if s.id == section_id), None)
    if not section:
        return None
    try:
        url = section_open_url(section)
    except Exception:
        url = f"/{section_id.replace('_', '-')}"
    return {
        "kind": "page",
        "id": section.id,
        "title": section.label,
        "summary": _PAGE_BLURBS.get(section.id, ""),
        "url": url,
        "module_label": "Portal page",
    }


def _exact_section_intent(q: str, allowed: frozenset[str]) -> str | None:
    """If the query is primarily a portal section name, return that section id."""
    qn = _normalize(q)
    if not qn:
        return None
    # "What is copper" is a definition — not a request to open Domain Knowledge.
    if _is_general_knowledge_question(qn):
        return None

    # Prefer exact alias equality (e.g. "project" / "copper" → section).
    best: tuple[int, str] | None = None
    nav_prefixes = ("go to ", "open ", "show ", "show me ", "take me to ")
    for section in SEARCH_SECTIONS:
        if section.id not in allowed:
            continue
        for alias in section.aliases:
            an = _normalize(alias)
            if not an:
                continue
            candidate = qn
            for prefix in nav_prefixes:
                if qn.startswith(prefix):
                    candidate = qn[len(prefix) :].strip()
                    break
            if candidate == an:
                score = 1000 + len(an)
                if not best or score > best[0]:
                    best = (score, section.id)
    return best[1] if best else None


def _module_intent(q: str) -> str | None:
    qn = _normalize(q)
    if _is_general_knowledge_question(qn):
        return None
    for aliases, module in _MODULE_INTENT:
        for alias in aliases:
            if qn == alias or qn == _normalize(alias):
                return module
    return None


def _is_greeting(q: str) -> bool:
    qn = _normalize(q)
    if not qn:
        return True
    if qn in _GREETING_WORDS:
        return True
    # Light small-talk
    starters = (
        "how are you",
        "how's it going",
        "hows it going",
        "what can you do",
        "who are you",
        "thanks",
        "thank you",
        "ty",
    )
    return any(qn == s or qn.startswith(s + " ") for s in starters)


def _is_general_knowledge_question(qn: str) -> bool:
    """True for definition / explain-style questions that need a plain AI answer."""
    qn = (qn or "").strip()
    if not qn:
        return False
    # Explicit portal ask still uses MiNe retrieval + links.
    portal_force = (
        "freeport",
        "hexaware",
        "mine portal",
        "in mine",
        "on mine",
        "knowledge repository",
        "domain knowledge",
        "know your customer",
        "case stud",
        "term of the week",
        "newsletter",
        "rfp",
        "journey page",
        "our portal",
    )
    if any(m in qn for m in portal_force):
        return False
    patterns = (
        "what is ",
        "what are ",
        "whats ",
        "what's ",
        "who is ",
        "who are ",
        "define ",
        "definition of ",
        "meaning of ",
        "explain ",
        "tell me about ",
        "tell me what ",
        "how does ",
        "how do ",
        "how is ",
        "how are ",
        "why is ",
        "why are ",
        "why do ",
        "why does ",
        "describe ",
    )
    return any(qn.startswith(p) for p in patterns)


def _is_question_form(qn: str) -> bool:
    if "?" in qn:
        return True
    if _is_general_knowledge_question(qn):
        return True
    starters = (
        "what ",
        "whats ",
        "what's ",
        "why ",
        "how ",
        "when ",
        "who ",
        "which ",
        "explain ",
        "tell me ",
        "can you ",
        "could you ",
        "is ",
        "are ",
        "do ",
        "does ",
        "define ",
        "describe ",
    )
    return any(qn.startswith(s) for s in starters)


def _looks_like_portal_query(q: str, allowed: frozenset[str]) -> bool:
    """True when the user is navigating MiNe / asking about portal content."""
    qn = _normalize(q)
    # Plain knowledge questions → AI answer only (no source cards).
    if _is_general_knowledge_question(qn):
        return False
    if _exact_section_intent(q, allowed) or _module_intent(q):
        return True
    markers = (
        "freeport",
        "hexaware",
        "mine portal",
        "in mine",
        "on mine",
        "ask mine",
        "knowledge repository",
        "knowledge article",
        "domain knowledge",
        "open pit",
        "open-pit",
        "know your customer",
        "fmi kyc",
        "case stud",
        "term of the week",
        "newsletter",
        "rfp snippet",
        "where can i find",
        "where is",
        "take me to",
        "open the",
        "show me the",
        "go to",
        "link to",
    )
    if any(m in qn for m in markers):
        return True
    # Short nav phrases (e.g. "copper", "journey", "projects") — not full questions.
    if not _is_question_form(qn) and len(qn.split()) <= 4:
        if _static_page_hits(q, allowed):
            return True
    return False


def _static_page_hits(q: str, allowed: frozenset[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    exact = _exact_section_intent(q, allowed)
    if exact:
        hit = _page_hit(exact)
        if hit:
            return [hit]

    for item in section_search_hits(q, limit=12):
        section = item.get("section")
        if not section or section.id not in allowed:
            continue
        if section.id in seen:
            continue
        # Require a reasonably strong section score to avoid weak false positives.
        if int(item.get("score") or 0) < 480:
            continue
        seen.add(section.id)
        hit = _page_hit(section.id)
        if hit:
            hits.append(hit)

    # Keyword fallback for common phrases
    qn = _normalize(q)
    keyword_map = (
        (("journey", "hexaware journey", "partnership journey"), "journey"),
        (("domain knowledge", "open pit", "open-pit", "copper domain"), "domain_knowledge"),
        (("know your customer", "freeport kyc", "fmi kyc"), "fmi_kyc"),
        (("knowledge repository", "knowledge hub", "knowledge catalogue"), "knowledge"),
        (("programs and projects", "programmes and projects", "programs projects"), "projects"),
    )
    for aliases, sid in keyword_map:
        if sid not in allowed or sid in seen:
            continue
        if any(_normalize(a) in qn or qn == _normalize(a) for a in aliases):
            hit = _page_hit(sid)
            if hit:
                seen.add(sid)
                hits.append(hit)
    return hits


def _query_tokens(q: str) -> list[str]:
    stop = {
        "what", "when", "where", "which", "that", "this", "with", "from", "about",
        "have", "does", "will", "tell", "me", "the", "and", "for", "are", "is",
        "a", "an", "of", "to", "in", "on", "please", "explain", "describe", "define",
        "related", "technologies", "technology", "document", "compare", "architecture",
        "business", "process", "processes", "project", "projects",
    }
    return [t for t in _normalize(q).split() if len(t) >= 3 and t not in stop]


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalize(s))


def _normalize_history(history: list | None, *, limit: int = 8) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        out.append({"role": role, "content": content[:1200]})
    return out[-limit:]


def _last_topic_from_history(history: list[dict[str, str]]) -> str:
    """Best-effort entity from recent user turns (e.g. SIMS, OpenFlow)."""
    skip = {
        "related projects",
        "related technologies",
        "open document",
        "compare projects",
        "show architecture",
        "explain business process",
        "projects",
        "knowledge",
        "onboarding",
        "training",
    }
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        raw = (item.get("content") or "").strip()
        qn = _normalize(raw)
        if not qn or qn in skip or _is_greeting(raw):
            continue
        # Prefer quoted / known short project-like phrases.
        m = re.search(r"[\"']([^\"']{2,60})[\"']", raw)
        if m:
            return m.group(1).strip()
        tokens = _query_tokens(raw)
        if tokens:
            # Keep a compact phrase from meaningful tokens.
            return " ".join(tokens[:4])
        if len(qn) <= 48:
            return raw.strip()
    return ""


_FOLLOWUP_RE = re.compile(
    r"\b(it|its|they|them|their|this|that|these|those)\b|"
    r"^(related |what technologies|who (developed|built|created)|"
    r"compare |show architecture|explain (this|business)|open document)",
    re.I,
)


def _is_followup_question(q: str) -> bool:
    qn = _normalize(q)
    if not qn:
        return False
    if _FOLLOWUP_RE.search(qn):
        return True
    # Short vague asks after a prior topic.
    return len(qn.split()) <= 5 and qn in {
        "related projects",
        "related technologies",
        "open document",
        "compare projects",
        "show architecture",
        "explain business process",
        "technologies",
        "architecture",
        "sow",
        "scope",
        "overview",
    }


def _expand_query_with_context(
    q: str,
    *,
    history: list[dict[str, str]],
    page_path: str = "",
    page_title: str = "",
) -> tuple[str, str]:
    """
    Returns (display_question, search_query).
    Expands pronouns / follow-ups using history and current page.
    """
    topic = _last_topic_from_history(history)
    path_n = _normalize(page_path or "")
    title_n = (page_title or "").strip()
    # Strip site suffix from document.title.
    for sep in (" | ", " — ", " - "):
        if sep in title_n:
            title_n = title_n.split(sep)[0].strip()
            break

    qn = _normalize(q)
    # "Explain this" on a project page → use page title.
    if qn in {"explain this", "explain", "what is this", "tell me about this"} and title_n:
        if any(x in path_n for x in ("project", "sow", "knowledge", "domain", "journey")):
            return q, f"{title_n} {q}"

    if topic and _is_followup_question(q):
        # Avoid duplicating if topic already in the question.
        if _normalize(topic) not in qn:
            return q, f"{topic} {q}"
    return q, q


def _page_context_label(*, page_path: str = "", page_title: str = "", page_endpoint: str = "") -> str:
    bits = []
    title = (page_title or "").strip()
    for sep in (" | ", " — ", " - "):
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    path = (page_path or "").strip()
    endpoint = (page_endpoint or "").strip()
    if title:
        bits.append(title)
    if path:
        bits.append(f"path {path}")
    if endpoint:
        bits.append(f"endpoint {endpoint}")
    return " · ".join(bits) if bits else ""


def _guest_requests_staff_content(q: str) -> bool:
    """True when a Guest question targets staff-only portal areas (projects/SOW/etc.)."""
    qn = _normalize(q)
    if not qn:
        return False
    if qn in _GUEST_STAFF_EXACT:
        return True
    padded = f" {qn} "
    for phrase in _GUEST_STAFF_PHRASES:
        pn = _normalize(phrase)
        if not pn:
            continue
        if padded.find(f" {pn} ") >= 0 or qn.startswith(pn + " ") or qn.endswith(" " + pn):
            return True
    # Strong catalog title hits (e.g. “tell me about SIMS”) stay staff-only for guests.
    try:
        hits = _project_catalog_hits(q, limit=1)
        if hits:
            title_n = _normalize(str(hits[0].get("title") or ""))
            tokens = _query_tokens(q)
            if title_n and any(t in title_n for t in tokens):
                return True
    except Exception:
        pass
    return False


def _guest_safe_sources(sources: list | None) -> list[dict[str, Any]]:
    """Drop project / staff-only links that Guests cannot open."""
    from mine.guest import guest_may_visit_path

    staff_modules = STANDALONE_REPO_MODULES | {"projects"}
    out: list[dict[str, Any]] = []
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        mod = (item.get("module") or "").strip().lower()
        kind = (item.get("kind") or "").strip().lower()
        if mod in staff_modules or kind == "project":
            continue
        sid = str(item.get("id") or "")
        if sid in _STAFF_SECTION_IDS:
            continue
        url = (item.get("url") or "").strip()
        if url and not guest_may_visit_path(url):
            continue
        out.append(item)
    return out


def _follow_up_suggestions(topic: str = "", *, guest: bool = False) -> list[dict[str, str]]:
    t = (topic or "").strip()
    if guest:
        return [
            {"label": "Knowledge Base", "query": "knowledge"},
            {"label": "Domain Knowledge", "query": "domain knowledge"},
            {"label": "Journey", "query": "journey"},
            {"label": "Know your Customer", "query": "know your customer"},
            {
                "label": "Mining Process",
                "query": "what are the major mining operations",
            },
        ]
    prefix = f"{t} - " if t else ""
    base = [
        ("Related Projects", f"{prefix}related projects" if t else "related projects"),
        (
            "Related Technologies",
            f"What technologies does {t} use?" if t else "related technologies",
        ),
        ("Open Document", f"Open document for {t}" if t else "open document"),
        ("Compare Projects", f"Compare {t} with related projects" if t else "compare projects"),
        ("Show Architecture", f"Show architecture for {t}" if t else "show architecture"),
        (
            "Explain Business Process",
            f"Explain business process for {t}" if t else "explain business process",
        ),
    ]
    return [{"label": label, "query": query} for label, query in base]


# Lightweight TTL cache for identical questions (no conversation history).
_ANSWER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ANSWER_CACHE_TTL = 90.0
_ANSWER_CACHE_MAX = 64


def _cache_get(key: str) -> dict[str, Any] | None:
    import time

    item = _ANSWER_CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if time.time() - ts > _ANSWER_CACHE_TTL:
        _ANSWER_CACHE.pop(key, None)
        return None
    return dict(payload)


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    import time

    if len(_ANSWER_CACHE) >= _ANSWER_CACHE_MAX:
        # Drop oldest.
        oldest = min(_ANSWER_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _ANSWER_CACHE.pop(oldest, None)
    _ANSWER_CACHE[key] = (time.time(), dict(payload))


def _knowledge_hits(
    db,
    q: str,
    *,
    limit: int = 6,
    module: str | None = None,
    list_module_if_empty: bool = False,
    include_projects: bool = False,
) -> list[dict[str, Any]]:
    modules: tuple[str, ...]
    allowed_modules = KNOWLEDGE_SERIES_MODULE_KEYS | STANDALONE_REPO_MODULES | {"projects"}
    if module and module in allowed_modules:
        modules = (module,)
    else:
        mods = set(KNOWLEDGE_SERIES_MODULE_KEYS)
        if include_projects:
            mods.add("projects")
        modules = tuple(sorted(mods))
    rows = []
    try:
        catalog = query_catalog(
            db,
            q=q,
            modules=modules,
            approved_only=True,
            sort="relevance",
            page=1,
            per_page=limit,
        )
        rows = catalog.get("rows") or []
    except Exception:
        current_app.logger.exception("Chatbot catalogue search failed for %r", q)
        rows = []

    # Series-name queries (e.g. "case studies" / "onboarding") often don't FTS-match article titles —
    # fall back to the latest approved items in that module.
    if list_module_if_empty and module and not rows:
        try:
            catalog = query_catalog(
                db,
                q=None,
                module=module,
                approved_only=True,
                sort="recent",
                page=1,
                per_page=limit,
            )
            rows = catalog.get("rows") or []
        except Exception:
            current_app.logger.exception("Chatbot module list failed for %r", module)
            rows = []

    out: list[dict[str, Any]] = []
    for row in rows:
        cid = int(row["id"])
        mod = (row["module"] or "").strip()
        summary = _snippet(row["summary"] or row["body"])
        out.append(
            {
                "kind": "knowledge",
                "id": cid,
                "title": row["title"] or f"Item #{cid}",
                "summary": summary,
                "url": _result_url_for_content(mod, cid),
                "module_label": module_label(mod),
                "module": mod,
            }
        )
    return out


def _project_catalog_hits(q: str, *, limit: int = 4) -> list[dict[str, Any]]:
    """Search Programs & Projects portfolio config (SOW-backed catalog)."""
    tokens = _query_tokens(q)
    if not tokens:
        return []
    try:
        catalog = load_project_section_catalog()
    except Exception:
        current_app.logger.exception("Chatbot project catalog load failed")
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in catalog.get("entries") or []:
        # Include inactive portfolio rows — chatbot still answers from SOW notes.
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        sections = entry.get("sections") or {}
        engagement = entry.get("engagement_details") or {}
        blob_parts = [
            title,
            sections.get("overview") or "",
            sections.get("scope_of_work") or "",
            sections.get("technologies") or "",
            sections.get("supported_applications") or "",
            engagement.get("sow_title") or "",
            engagement.get("supported_systems") or "",
            " ".join(engagement.get("activities") or []),
        ]
        blob = _normalize(" ".join(str(p) for p in blob_parts if p))
        title_n = _normalize(title)
        blob_c = _compact(blob)
        title_c = _compact(title)
        score = 0
        for t in tokens:
            tc = _compact(t)
            if not tc:
                continue
            if t in title_n or (len(tc) >= 4 and tc in title_c):
                score += 120
            elif t in blob or (len(tc) >= 4 and tc in blob_c):
                score += 40
        # Prefer multi-token hits (e.g. snowflake + openflow).
        if score and len(tokens) >= 2:
            hits = sum(
                1
                for t in tokens
                if t in blob or (len(_compact(t)) >= 4 and _compact(t) in blob_c)
            )
            if hits >= 2:
                score += 50
        # Strong single-token title match (SIMS, OpenFlow).
        if score < 80 and len(tokens) == 1:
            t0 = tokens[0]
            if t0 in title_n or _compact(t0) in title_c:
                score = 100
        if not entry.get("is_active", True) and score:
            score = max(80, score - 15)
        if score < 80:
            continue
        overview = (sections.get("overview") or "").strip()
        scope = (sections.get("scope_of_work") or "").strip()
        summary = _snippet(overview or scope, limit=320)
        cid = entry.get("content_id")
        url = "/projects"
        if cid is not None:
            try:
                url = _result_url_for_content("projects", int(cid))
            except Exception:
                url = "/projects"
        scored.append(
            (
                score,
                {
                    "kind": "project",
                    "id": cid or entry.get("catalog_key") or title,
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "module_label": "Programs & projects",
                    "module": "projects",
                    "detail": {
                        "overview": overview,
                        "scope": scope,
                        "technologies": (sections.get("technologies") or "").strip(),
                        "client": (engagement.get("client") or "").strip(),
                        "sow_title": (engagement.get("sow_title") or "").strip(),
                    },
                },
            )
        )

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]


def _filter_relevant_articles(q: str, articles: list[dict]) -> list[dict]:
    """Drop weak FTS hits that don't share meaningful tokens with the question."""
    tokens = _query_tokens(q)
    if not tokens or not articles:
        return articles
    kept: list[dict] = []
    for a in articles:
        blob = _normalize(f"{a.get('title') or ''} {a.get('summary') or ''}")
        if any(t in blob for t in tokens):
            kept.append(a)
    return kept


def _context_blocks(pages: list[dict], articles: list[dict]) -> list[str]:
    blocks: list[str] = []
    for p in pages[:4]:
        blocks.append(
            f"- Portal page: {p.get('title')} — {p.get('summary') or ''} (path: {p.get('url')})"
        )
    for a in articles[:6]:
        detail = a.get("detail") or {}
        extra = ""
        if detail:
            bits = []
            if detail.get("sow_title"):
                bits.append(f"SOW: {detail['sow_title']}")
            if detail.get("client"):
                bits.append(f"Client: {detail['client']}")
            if detail.get("overview"):
                bits.append(f"Overview: {_snippet(detail['overview'], 420)}")
            if detail.get("scope"):
                bits.append(f"Scope: {_snippet(detail['scope'], 320)}")
            if detail.get("technologies"):
                bits.append(f"Technologies: {_snippet(detail['technologies'], 220)}")
            extra = " | ".join(bits)
        blocks.append(
            f"- MiNe [{a.get('module_label')}]: {a.get('title')} — "
            f"{extra or (a.get('summary') or '')}"
        )
    return blocks


def _retrieve_mine_content(q: str, *, guest: bool) -> tuple[list[dict], list[dict]]:
    """Prefer website content: projects catalog + knowledge (+ projects DB when allowed)."""
    allowed = _allowed_section_ids(guest=guest)
    db = get_db()
    pages = _static_page_hits(q, allowed)
    articles: list[dict[str, Any]] = []

    if not guest and "projects" in allowed:
        articles.extend(_project_catalog_hits(q, limit=4))

    # Knowledge + approved project content rows.
    fts = _knowledge_hits(
        db,
        q,
        limit=6,
        include_projects=(not guest and "projects" in allowed),
    )
    fts = _filter_relevant_articles(q, fts)

    # Deduplicate by title/id while keeping project-catalog hits first.
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in articles + fts:
        key = _normalize(str(item.get("title") or "")) or str(item.get("id"))
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)

    # If we found project/knowledge hits, also attach the Programs & projects hub.
    if merged and not guest and "projects" in allowed:
        if any((a.get("module") == "projects") for a in merged):
            hub = _page_hit("projects")
            if hub and not any(p.get("id") == "projects" for p in pages):
                pages = [hub] + pages

    return pages, merged[:8]


def _compose_answer(q: str, pages: list[dict], articles: list[dict], *, note: str | None = None, guest: bool = False) -> str:
    q_clean = (q or "").strip()
    if not q_clean:
        return _HELP_REPLY_GUEST if guest else _HELP_REPLY

    if note and not pages and not articles:
        return note

    if not pages and not articles:
        if guest:
            return (
                "I couldn't find that information in the Guest-accessible MiNe pages.\n\n"
                "Try **knowledge**, **domain knowledge**, **journey**, or **know your customer**.\n\n"
                "Programs & projects and SOW details need a full MiNe account."
            )
        return (
            "I couldn't find that information in the MiNe knowledge repository.\n\n"
            "Would you like a general explanation instead?\n\n"
            "You can also try **projects**, **journey**, **domain knowledge**, "
            "or **know your customer**."
        )

    parts: list[str] = []
    if note:
        parts.append(note)

    if pages and not articles:
        parts.append(f"Best match for “{q_clean}”:")
    elif articles and not pages:
        parts.append(f"Approved Knowledge items for “{q_clean}”:")
    else:
        parts.append(f"Here’s what matches “{q_clean}”:")

    for p in pages[:3]:
        blurb = p.get("summary") or ""
        line = f"• {p['title']}"
        if blurb:
            line += f" — {blurb}"
        parts.append(line)

    for a in articles[:5]:
        label = a.get("module_label") or "Knowledge"
        line = f"• [{label}] {a['title']}"
        if a.get("summary"):
            line += f" — {a['summary']}"
        parts.append(line)

    parts.append("Open a source link below to continue.")
    return "\n".join(parts)


def _maybe_llm_reply(
    q: str,
    pages: list[dict],
    articles: list[dict],
    *,
    fallback: str,
    force_llm: bool = False,
    history: list[dict] | None = None,
    page_context: str | None = None,
    empty_context_ok: bool = False,
    guest: bool = False,
) -> dict[str, Any]:
    """
    Returns {"reply", "provider", "error"}.
    Uses LLM when configured; otherwise returns fallback.
    force_llm=True for generic / empty-retrieval questions.
    empty_context_ok=True for greetings (do not claim MiNe miss).
    """
    from mine.chatbot_llm import generate_assistant_reply, llm_configured

    if not llm_configured():
        return {"reply": fallback, "provider": None, "error": "not_configured"}

    # Navigation-only answers stay deterministic unless forced.
    if not force_llm and pages and not articles and len(pages) == 1:
        return {"reply": fallback, "provider": None, "error": None}

    mine_found = bool(pages or articles) or empty_context_ok
    result = generate_assistant_reply(
        q,
        _context_blocks(pages, articles),
        history=history,
        page_context=page_context,
        mine_found=mine_found,
        guest=guest,
    )
    if result.get("ok") and result.get("text"):
        return {
            "reply": str(result["text"]).strip(),
            "provider": result.get("provider"),
            "error": None,
        }
    # LLM failed — keep portal fallback if we have sources, else explain cleanly.
    err = (result.get("error") or "").strip()
    if pages or articles:
        return {"reply": fallback, "provider": None, "error": err or "llm_failed"}
    err_l = err.lower()
    if "401" in err or "403" in err or "invalid" in err_l or "unauthorized" in err_l:
        msg = "The Groq API key looks invalid — check GROQ_API_KEY in Azure App Settings."
    elif "429" in err or "rate" in err_l:
        msg = "Groq rate limit hit — wait about a minute, then ask again."
    elif "timed out" in err_l or "timeout" in err_l or "connection" in err_l:
        msg = "Could not reach Groq from the server just now — try again in a few seconds."
    elif "http 5" in err_l or "502" in err or "503" in err or "504" in err:
        msg = "Groq had a temporary outage — try your question again."
    elif "certificate" in err_l or "ssl" in err_l:
        msg = "Secure connection to Groq failed on the server — try again shortly."
    else:
        msg = (
            "I couldn't find that information in the MiNe knowledge repository.\n\n"
            "Would you like a general explanation instead?"
        )
    # Include a short safe diagnostic so Azure failures are visible without Log Stream.
    if err:
        safe = re.sub(r"gsk_[A-Za-z0-9]+", "gsk_***", err)
        safe = re.sub(r"AIza[A-Za-z0-9_\-]+", "AIza***", safe)
        safe = " ".join(safe.split())
        if len(safe) > 140:
            safe = safe[:139] + "…"
        msg = f"{msg} ({safe})"
    return {"reply": msg, "provider": None, "error": err or "llm_failed"}


def _prepare_sources(sources: list | None) -> list[dict[str, Any]]:
    """Deduplicate and rank sources so the top item is the best deep-link CTA."""
    if not sources:
        return []

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        kind = (item.get("kind") or "").lower()
        module = (item.get("module") or "").lower()
        title = _normalize(str(item.get("title") or ""))
        # Concrete project / article first; hub pages last.
        if kind == "project" or module == "projects":
            score = 300
        elif kind == "page":
            score = 40
        else:
            score = 180
        # Prefer named project pages over the portfolio hub label.
        if title in {"programs and projects", "programs & projects", "projects"}:
            score -= 80
        return (score, len(str(item.get("summary") or "")))

    best_by_url: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    for item in sources:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        key = url.lower()
        score = rank(item)
        prev = best_by_url.get(key)
        if not prev or score > prev[0]:
            best_by_url[key] = (score, item)

    cleaned = [pair[1] for pair in best_by_url.values()]
    cleaned.sort(key=rank, reverse=True)
    return cleaned[:8]


def _out(
    reply: str,
    *,
    sources: list | None = None,
    query: str = "",
    provider: str | None = None,
    llm_error: str | None = None,
    follow_ups: list | None = None,
    topic: str = "",
    guest: bool = False,
) -> dict[str, Any]:
    prepared = _prepare_sources(sources)
    if guest:
        prepared = _guest_safe_sources(prepared)
    payload: dict[str, Any] = {
        "reply": (reply or "").strip(),
        "sources": prepared,
        "query": query,
        "follow_ups": (
            follow_ups
            if follow_ups is not None
            else _follow_up_suggestions(topic, guest=guest)
        ),
        "topic": topic or "",
    }
    if provider:
        payload["provider"] = provider
    if llm_error and llm_error not in ("not_configured",):
        # Safe debug hint for Azure Network tab (no secrets).
        payload["llm_error"] = llm_error[:180]
    return payload


def answer_question(
    q: str,
    *,
    guest: bool = False,
    history: list | None = None,
    page_path: str = "",
    page_title: str = "",
    page_endpoint: str = "",
) -> dict[str, Any]:
    q = (q or "").strip()
    if len(q) > 500:
        q = q[:500]

    hist = _normalize_history(history)
    display_q, search_q = _expand_query_with_context(
        q, history=hist, page_path=page_path, page_title=page_title
    )
    page_ctx = _page_context_label(
        page_path=page_path, page_title=page_title, page_endpoint=page_endpoint
    )
    topic = _last_topic_from_history(hist + [{"role": "user", "content": search_q}])

    # Cache only standalone questions (no prior turns).
    cache_key = ""
    if not hist and not _is_followup_question(q):
        cache_key = f"{int(guest)}|{_normalize(search_q)}|{_normalize(page_path)}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

    allowed = _allowed_section_ids(guest=guest)
    qn = _normalize(q)
    # Prefer expanded query for retrieval when follow-up.
    retrieve_q = search_q if search_q != q else q
    retrieve_qn = _normalize(retrieve_q)

    # Greetings / small talk — conversational, no source dump.
    if _is_greeting(q):
        if guest:
            fallback = (
                _HELP_REPLY_GUEST
                if qn in {"help", "?", "what can you do", "who are you"}
                else _GREETING_REPLIES[0]
            )
        else:
            fallback = (
                _HELP_REPLY
                if qn in {"help", "?", "what can you do", "who are you"}
                else _GREETING_REPLIES[0]
            )
        if qn in {"thanks", "thank you", "ty"}:
            fallback = "You're welcome — anything else I can help with?"
        greet_prompt = (
            "Say a short friendly hello. Mention Guest can use Knowledge, Domain Knowledge, "
            "Journey, and Know your Customer. Do not mention projects, SOW, onboarding, or training."
            if guest
            else "Say a short friendly hello and ask how you can help. Do not list portal pages."
        )
        llm = _maybe_llm_reply(
            q or greet_prompt,
            [],
            [],
            fallback=fallback,
            force_llm=True,
            history=hist,
            page_context=page_ctx,
            empty_context_ok=True,
            guest=guest,
        )
        reply, provider, err = llm["reply"], llm["provider"], llm["error"]
        # Never show AI failure noise on a simple hello — fall back to a warm greeting.
        if provider is None:
            reply = fallback
        return _out(
            reply,
            query=q,
            provider=provider,
            llm_error=err if provider else None,
            topic="",
            follow_ups=[],
            guest=guest,
        )

    # Guests must not receive staff-only project / SOW / kit content.
    if guest and _guest_requests_staff_content(retrieve_q):
        return _out(
            _GUEST_STAFF_REPLY,
            sources=[h for h in (_page_hit("knowledge"),) if h],
            query=q,
            topic="",
            follow_ups=_follow_up_suggestions(guest=True),
            guest=True,
        )

    db = get_db()

    def _finish(payload: dict[str, Any]) -> dict[str, Any]:
        if cache_key and payload.get("reply"):
            _cache_set(cache_key, payload)
        return payload

    # Strong section intent → open that portal page (+ list items for kit/training/etc.).
    exact = _exact_section_intent(q, allowed)
    if exact:
        page = _page_hit(exact)
        pages = [page] if page else []
        articles: list[dict[str, Any]] = []
        if exact in STANDALONE_REPO_MODULES:
            articles = _knowledge_hits(
                db, q, limit=8, module=exact, list_module_if_empty=True
            )
            note = f"Here’s the {module_label(exact)} page and available items."
            reply = _compose_answer(q, pages, articles, note=note, guest=guest)
        elif exact == "projects" and not guest:
            articles = _project_catalog_hits("project", limit=6) or _knowledge_hits(
                db, q, limit=6, module="projects", list_module_if_empty=True, include_projects=True
            )
            # For bare "projects", list portfolio hub without forcing a weak FTS query.
            if qn in {"project", "projects", "program", "programs", "programme", "programmes"}:
                try:
                    from mine.project_catalog import load_project_section_catalog

                    entries = [
                        e
                        for e in (load_project_section_catalog().get("entries") or [])
                        if e.get("is_active", True)
                    ][:8]
                    articles = []
                    for e in entries:
                        articles.append(
                            {
                                "kind": "project",
                                "id": e.get("content_id") or e.get("catalog_key"),
                                "title": e.get("title"),
                                "summary": _snippet((e.get("sections") or {}).get("overview") or "", 220),
                                "url": "/projects",
                                "module_label": "Programs & projects",
                                "module": "projects",
                            }
                        )
                except Exception:
                    pass
            reply = _compose_answer(
                q, pages, articles, note="Programs & projects in the MiNe portfolio.", guest=guest
            )
        else:
            reply = _compose_answer(q, pages, [], guest=guest)
        return _finish(_out(reply, sources=pages + articles, query=q, topic=topic, guest=guest))

    # Knowledge-series intent (e.g. "case studies") → filter that module.
    mod = _module_intent(q)
    if mod:
        articles = _knowledge_hits(db, q, limit=6, module=mod, list_module_if_empty=True)
        pages = []
        hub = _page_hit("knowledge")
        if hub:
            pages.append(hub)
        fallback = _compose_answer(
            q,
            pages,
            articles,
            note=f"Showing the {module_label(mod)} series in Knowledge.",
            guest=guest,
        )
        llm = _maybe_llm_reply(
            display_q,
            pages,
            articles,
            fallback=fallback,
            force_llm=False,
            history=hist,
            page_context=page_ctx,
            guest=guest,
        )
        return _finish(
            _out(
                llm["reply"],
                sources=pages + articles,
                query=q,
                provider=llm["provider"],
                llm_error=llm["error"],
                topic=topic,
                guest=guest,
            )
        )

    # Always try MiNe website content first (projects catalog + knowledge).
    # Use expanded retrieve_q so follow-ups like "technologies?" resolve against SIMS etc.
    pages, articles = _retrieve_mine_content(retrieve_q, guest=guest)
    if guest:
        pages = _guest_safe_sources(pages)
        articles = _guest_safe_sources(articles)

    # Page-aware boost: browsing Programs & Projects with a vague ask → portfolio hub.
    if not pages and not articles and "project" in _normalize(page_path):
        hub = _page_hit("projects")
        if hub and not guest:
            pages = [hub]
            if retrieve_qn in {"explain this", "explain", "what is this", "tell me about this"} and page_title:
                p2, a2 = _retrieve_mine_content(page_title, guest=guest)
                if p2 or a2:
                    pages, articles = p2, a2

    from mine.chatbot_llm import llm_configured

    if pages or articles:
        # Prefer a project title as the follow-up topic when retrieval found one.
        if not guest:
            for a in articles:
                if a.get("module") == "projects" and a.get("title"):
                    topic = str(a["title"])
                    break
        fallback = _compose_answer(display_q, pages, articles, guest=guest)
        llm = _maybe_llm_reply(
            display_q,
            pages,
            articles,
            fallback=fallback,
            force_llm=True,
            history=hist,
            page_context=page_ctx,
            guest=guest,
        )
        return _finish(
            _out(
                llm["reply"],
                sources=pages + articles,
                query=q,
                provider=llm["provider"],
                llm_error=llm["error"],
                topic=topic if not guest else "",
                guest=guest,
            )
        )

    # No MiNe match → general AI assistant (friendly wording).
    fallback = (
        (
            "I couldn't find that in Guest-accessible MiNe pages.\n\n"
            "Try Knowledge, Domain Knowledge, Journey, or Know your Customer — "
            "or sign in with a full account for Programs & projects."
        )
        if guest
        else (
            "I couldn't find that information in the MiNe knowledge repository.\n\n"
            "Would you like a general explanation instead?"
        )
    )
    llm = _maybe_llm_reply(
        display_q,
        [],
        [],
        fallback=fallback,
        force_llm=True,
        history=hist,
        page_context=page_ctx,
        guest=guest,
    )
    reply, provider, err = llm["reply"], llm["provider"], llm["error"]
    if provider is None and not llm_configured():
        reply = (
            (
                "I couldn't find that in Guest-accessible MiNe pages, and no free LLM API key is configured.\n\n"
                "Try Knowledge, Domain Knowledge, Journey, or Know your Customer."
            )
            if guest
            else (
                "I couldn't find that information in the MiNe knowledge repository.\n\n"
                "No free LLM API key is configured for a general explanation. "
                "Add GROQ_API_KEY in Azure App Settings (or .env), "
                "or ask about Knowledge, Domain, Journey, KYC, or Projects."
            )
        )
        err = "not_configured"
    return _finish(
        _out(reply, query=q, provider=provider, llm_error=err, topic="" if guest else topic, guest=guest)
    )


@bp.route("/status", methods=["GET"])
@login_required
def chat_status():
    """Quick LLM config + connectivity check (for Azure debugging)."""
    from mine.chatbot_llm import _resolve_provider, _setting, generate_assistant_reply, llm_configured

    provider = _resolve_provider()
    configured = llm_configured()
    key_set = bool(_setting("GROQ_API_KEY") or _setting("GEMINI_API_KEY"))
    key_prefix = ""
    groq = _setting("GROQ_API_KEY")
    if groq:
        key_prefix = groq[:7] + "…" + groq[-4:]
    probe: dict[str, Any] = {"ok": False}
    if configured and provider:
        result = generate_assistant_reply("Reply with exactly: OK", [])
        probe = {
            "ok": bool(result.get("ok")),
            "provider": result.get("provider"),
            "error": (result.get("error") or "")[:180] or None,
            "sample": ((result.get("text") or "")[:40] or None),
        }
    return jsonify(
        {
            "ok": True,
            "chatbot_enabled": _chatbot_enabled(),
            "llm_configured": configured,
            "provider": provider,
            "key_set": key_set,
            "key_prefix": key_prefix or None,
            "provider_setting": _setting("CHATBOT_LLM_PROVIDER", "auto"),
            "website_site_name": (os.environ.get("WEBSITE_SITE_NAME") or "").strip() or None,
            "probe": probe,
        }
    )


@bp.route("", methods=["POST"])
@bp.route("/", methods=["POST"])
@login_required
def chat():
    if not _chatbot_enabled():
        return jsonify({"error": "Chatbot is disabled."}), 503

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or payload.get("q") or "").strip()
    if not message:
        return jsonify({"error": "Please enter a question."}), 400

    history = payload.get("history") or []
    if not isinstance(history, list):
        history = []
    page = payload.get("page") or {}
    if not isinstance(page, dict):
        page = {}
    page_path = (page.get("path") or payload.get("page_path") or "").strip()[:200]
    page_title = (page.get("title") or payload.get("page_title") or "").strip()[:200]
    page_endpoint = (page.get("endpoint") or payload.get("page_endpoint") or "").strip()[:120]

    user = load_current_user()
    result = answer_question(
        message,
        guest=is_guest_user(user),
        history=history,
        page_path=page_path,
        page_title=page_title,
        page_endpoint=page_endpoint,
    )
    payload_out = {
        "ok": True,
        "reply": result["reply"],
        "sources": result["sources"],
        "query": result["query"],
        "follow_ups": result.get("follow_ups") or [],
        "topic": result.get("topic") or "",
    }
    if result.get("provider"):
        payload_out["provider"] = result["provider"]
    if result.get("llm_error"):
        payload_out["llm_error"] = result["llm_error"]
    return jsonify(payload_out)
