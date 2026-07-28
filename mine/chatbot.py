"""MiNe knowledge chatbot — FTS retrieval over Knowledge + Domain + Journey + KYC (+ Projects for non-guests)."""

from __future__ import annotations

import re
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from mine.auth_utils import load_current_user, login_required
from mine.catalog_modules import KNOWLEDGE_SERIES_MODULE_KEYS, STANDALONE_REPO_MODULES, module_label
from mine.catalog_query import query_catalog
from mine.db import get_db
from mine.guest import is_guest_user
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

    return result_url_for_content(module or "", cid)


def _page_hit(section_id: str) -> dict[str, Any] | None:
    section = next((s for s in SEARCH_SECTIONS if s.id == section_id), None)
    if not section:
        return None
    return {
        "kind": "page",
        "id": section.id,
        "title": section.label,
        "summary": _PAGE_BLURBS.get(section.id, ""),
        "url": section_open_url(section),
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


def _knowledge_hits(
    db,
    q: str,
    *,
    limit: int = 6,
    module: str | None = None,
    list_module_if_empty: bool = False,
) -> list[dict[str, Any]]:
    modules: tuple[str, ...]
    allowed_modules = KNOWLEDGE_SERIES_MODULE_KEYS | STANDALONE_REPO_MODULES
    if module and module in allowed_modules:
        modules = (module,)
    else:
        modules = tuple(sorted(KNOWLEDGE_SERIES_MODULE_KEYS))
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


def _compose_answer(q: str, pages: list[dict], articles: list[dict], *, note: str | None = None) -> str:
    q_clean = (q or "").strip()
    if not q_clean:
        return _HELP_REPLY

    if note and not pages and not articles:
        return note

    if not pages and not articles:
        return (
            f"I could not find a precise MiNe match for “{q_clean}”. "
            "Try a section name such as “projects”, “journey”, “domain knowledge”, "
            "or “know your customer”, or a more specific topic keyword."
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


def _filter_relevant_articles(q: str, articles: list[dict]) -> list[dict]:
    """Drop weak FTS hits that don't share meaningful tokens with the question."""
    tokens = [t for t in _normalize(q).split() if len(t) >= 4]
    stop = {"what", "when", "where", "which", "that", "this", "with", "from", "about", "have", "does", "will"}
    tokens = [t for t in tokens if t not in stop]
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
        blocks.append(
            f"- Knowledge [{a.get('module_label')}]: {a.get('title')} — {a.get('summary') or ''}"
        )
    return blocks


def _maybe_llm_reply(
    q: str,
    pages: list[dict],
    articles: list[dict],
    *,
    fallback: str,
    force_llm: bool = False,
) -> dict[str, Any]:
    """
    Returns {"reply", "provider", "error"}.
    Uses LLM when configured; otherwise returns fallback.
    force_llm=True for generic / empty-retrieval questions.
    """
    from mine.chatbot_llm import generate_assistant_reply, llm_configured

    if not llm_configured():
        return {"reply": fallback, "provider": None, "error": "not_configured"}

    # Navigation-only answers stay deterministic unless forced.
    if not force_llm and pages and not articles and len(pages) == 1:
        return {"reply": fallback, "provider": None, "error": None}

    result = generate_assistant_reply(q, _context_blocks(pages, articles))
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
        msg = "I couldn't get an AI answer just now — please try again in a few seconds."
    return {"reply": msg, "provider": None, "error": err or "llm_failed"}


def _out(
    reply: str,
    *,
    sources: list | None = None,
    query: str = "",
    provider: str | None = None,
    llm_error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reply": reply, "sources": sources or [], "query": query}
    if provider:
        payload["provider"] = provider
    if llm_error and llm_error not in ("not_configured",):
        # Safe debug hint for Azure Network tab (no secrets).
        payload["llm_error"] = llm_error[:180]
    return payload


def answer_question(q: str, *, guest: bool = False) -> dict[str, Any]:
    q = (q or "").strip()
    if len(q) > 500:
        q = q[:500]

    allowed = _allowed_section_ids(guest=guest)
    qn = _normalize(q)

    # Greetings / small talk — conversational, no source dump.
    if _is_greeting(q):
        fallback = _HELP_REPLY if qn in {"help", "?", "what can you do", "who are you"} else _GREETING_REPLIES[0]
        if qn in {"thanks", "thank you", "ty"}:
            fallback = "You're welcome — anything else I can help with?"
        llm = _maybe_llm_reply(
            q or "Say a short friendly hello and ask how you can help. Do not list portal pages.",
            [],
            [],
            fallback=fallback,
            force_llm=True,
        )
        reply, provider, err = llm["reply"], llm["provider"], llm["error"]
        # Never show AI failure noise on a simple hello — fall back to a warm greeting.
        if provider is None:
            reply = fallback
        return _out(reply, query=q, provider=provider, llm_error=err if provider else None)

    # Guests asking for staff-only sections get a clear message (not a wrong case study).
    _guest_blocked = {
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
    }
    if guest and qn in _guest_blocked:
        return {
            "reply": (
                "That section is available to full MiNe accounts (not Guest). "
                "Sign in with your username to open Onboarding kit, Training corner, "
                "Innovation, Hall of Fame, or Programs & projects. "
                "As Guest you can browse Knowledge, Domain Knowledge, Journey, and Know your Customer."
            ),
            "sources": [h for h in (_page_hit("knowledge"),) if h],
            "query": q,
        }

    # Definition / explain questions → plain AI answer (no FTS source cards).
    if _is_general_knowledge_question(qn):
        from mine.chatbot_llm import llm_configured

        llm = _maybe_llm_reply(q, [], [], fallback=_HELP_REPLY, force_llm=True)
        reply, provider, err = llm["reply"], llm["provider"], llm["error"]
        if provider is None and not llm_configured():
            reply = (
                f"I can answer “{q}” when GROQ_API_KEY is set in Azure App Settings "
                "(Environment variables), then restart the app. "
                "Or ask for a MiNe page like “domain knowledge” or “projects”."
            )
            err = "not_configured"
        return _out(reply, query=q, provider=provider, llm_error=err)

    db = get_db()

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
            reply = _compose_answer(q, pages, articles, note=note)
        else:
            reply = _compose_answer(q, pages, [])
        return {"reply": reply, "sources": pages + articles, "query": q}

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
        )
        llm = _maybe_llm_reply(q, pages, articles, fallback=fallback, force_llm=False)
        return _out(
            llm["reply"],
            sources=pages + articles,
            query=q,
            provider=llm["provider"],
            llm_error=llm["error"],
        )

    # General questions → answer like a normal AI assistant (no weak FTS source cards).
    if not _looks_like_portal_query(q, allowed):
        from mine.chatbot_llm import llm_configured

        fallback = (
            f"I don't have a special MiNe page for that — here's a quick take on “{q}” "
            "when the AI assistant is available."
        )
        llm = _maybe_llm_reply(q, [], [], fallback=fallback, force_llm=True)
        reply, provider, err = llm["reply"], llm["provider"], llm["error"]
        if provider is None and not llm_configured():
            reply = (
                f"I could not find a MiNe match for “{q}”, and no free LLM API key is configured. "
                "Add GROQ_API_KEY in Azure App Settings (or .env) for general AI answers, "
                "or ask about Knowledge, Domain, Journey, KYC, or Projects."
            )
            err = "not_configured"
        return _out(reply, query=q, provider=provider, llm_error=err)

    pages = _static_page_hits(q, allowed)
    articles: list[dict[str, Any]] = []
    if not pages:
        articles = _knowledge_hits(db, q, limit=6)
    elif len(qn.split()) >= 2:
        articles = _knowledge_hits(db, q, limit=4)
    articles = _filter_relevant_articles(q, articles)

    has_mine = bool(pages or articles)
    if has_mine:
        fallback = _compose_answer(q, pages, articles)
        force = bool(articles) or len(qn.split()) >= 2
        llm = _maybe_llm_reply(
            q, pages, articles, fallback=fallback, force_llm=force
        )
        return _out(
            llm["reply"],
            sources=pages + articles,
            query=q,
            provider=llm["provider"],
            llm_error=llm["error"],
        )

    from mine.chatbot_llm import llm_configured

    fallback = f"I didn't find a matching MiNe page for “{q}”. Answering generally when available."
    llm = _maybe_llm_reply(q, [], [], fallback=fallback, force_llm=True)
    reply, provider, err = llm["reply"], llm["provider"], llm["error"]
    if provider is None and not llm_configured():
        reply = (
            f"I could not find a MiNe match for “{q}”, and no free LLM API key is configured. "
            "Add GROQ_API_KEY in Azure App Settings (or .env) to enable general AI answers, "
            "or ask about Knowledge, Domain, Journey, KYC, or Projects."
        )
        err = "not_configured"
    return _out(reply, query=q, provider=provider, llm_error=err)


@bp.route("/status", methods=["GET"])
@login_required
def chat_status():
    """Quick LLM config + connectivity check (for Azure debugging)."""
    from mine.chatbot_llm import _resolve_provider, _setting, generate_assistant_reply, llm_configured

    provider = _resolve_provider()
    configured = llm_configured()
    key_set = bool(_setting("GROQ_API_KEY") or _setting("GEMINI_API_KEY"))
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
            "provider_setting": _setting("CHATBOT_LLM_PROVIDER", "auto"),
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

    user = load_current_user()
    result = answer_question(message, guest=is_guest_user(user))
    payload_out = {
        "ok": True,
        "reply": result["reply"],
        "sources": result["sources"],
        "query": result["query"],
    }
    if result.get("provider"):
        payload_out["provider"] = result["provider"]
    if result.get("llm_error"):
        payload_out["llm_error"] = result["llm_error"]
    return jsonify(payload_out)
