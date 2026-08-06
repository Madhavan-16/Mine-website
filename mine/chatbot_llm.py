"""Free-tier LLM clients for MiNe chatbot (Groq and Google Gemini)."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any

import requests
from flask import current_app, has_app_context
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are MiNe AI — a professional, friendly, enterprise assistant for the Hexaware–Freeport MiNe portal.\n"
    "Personality: helpful, concise, conversational, context-aware. Never robotic. Avoid repetitive greetings.\n"
    "Knowledge priority (strict):\n"
    "1) MiNe portal notes / projects / SOW / knowledge articles provided in this turn — "
    "use them only when they directly answer the user’s question\n"
    "2) Conversation history (resolve pronouns like it/this/they to the last discussed project or topic)\n"
    "3) General AI knowledge when notes do not cover the question\n"
    "Never invent Freeport/Hexaware project facts, dates, budgets, or SOW details.\n"
    "If MiNe notes are missing for a portal/project question, say clearly that you could not find it "
    "in the MiNe knowledge repository, then offer a careful general explanation if appropriate.\n"
    "When MiNe notes exist for a named project (e.g. SIMS, Snowflake OpenFlow), answer from those notes — "
    "do not substitute unrelated public definitions.\n"
    "Critical: Answer the user’s actual question. Do not dump unrelated projects, case studies, or SOWs "
    "just because a keyword appears in the notes.\n"
    "For mining value-chain / FMI process / flowchart / lifecycle questions: explain the mining stages only. "
    "Do not mention SIMS, OpenFlow, SOWs, or portfolio projects unless the user asked for them.\n"
    "Response style:\n"
    "- Be precise and concise — prefer short answers unless the user asks for depth\n"
    "- Start with a short summary sentence that answers the question\n"
    "- Use Markdown: ## headings only when needed, bullet lists, **bold** for key terms\n"
    "- Use tables when comparing items\n"
    "- For architecture/flows/value chains: use ONE continuous numbered list (1. 2. 3. …) "
    "with short `-` detail bullets under each stage, then one **Flow:** A → B → C line. "
    "Do NOT restart numbering at 1 for each stage. Do NOT use ASCII box diagrams. "
    "When asked for a flowchart/diagram and no portal image is provided in the notes, "
    "add ONE fenced ```mermaid flowchart TD block with 4–8 short stage nodes "
    "(A[\"Label\"] --> B[\"Label\"]). When a Domain Knowledge image is noted in the "
    "portal notes, do NOT invent a mermaid block — acknowledge the diagram below.\n"
    "- Fenced code blocks only for real code/config or the mermaid flowchart above\n"
    "- Keep greetings to 1–2 short sentences — no long menus unless asked\n"
    "- Plain Markdown only (no HTML). Light emoji only if it improves scannability.\n"
    "Do not mention “context”, “RAG”, or “as an AI”."
)

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

_DEFAULT_GROQ_MODELS = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
)


def _clean_secret(value: Any) -> str:
    if value is None:
        return ""
    v = str(value).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        v = v[1:-1].strip()
    v = v.replace("\ufeff", "").replace("\u200b", "").replace("\r", "").replace("\n", "")
    return v.strip()


def _setting(name: str, default: str = "") -> str:
    env_val = _clean_secret(os.environ.get(name))
    if env_val:
        return env_val
    if has_app_context():
        return _clean_secret(current_app.config.get(name) or default)
    return _clean_secret(default)


def llm_configured() -> bool:
    provider = _setting("CHATBOT_LLM_PROVIDER", "auto").lower() or "auto"
    if provider in ("none", "off", "0"):
        return False
    groq = _setting("GROQ_API_KEY")
    gemini = _setting("GEMINI_API_KEY")
    if provider == "groq":
        return bool(groq)
    if provider in ("gemini", "google"):
        return bool(gemini)
    return bool(groq or gemini)


def _resolve_provider() -> str | None:
    provider = _setting("CHATBOT_LLM_PROVIDER", "auto").lower() or "auto"
    groq = _setting("GROQ_API_KEY")
    gemini = _setting("GEMINI_API_KEY")
    if provider in ("none", "off", "0"):
        return None
    if provider == "groq" and groq:
        return "groq"
    if provider in ("gemini", "google") and gemini:
        return "gemini"
    if groq:
        return "groq"
    if gemini:
        return "gemini"
    return None


def _normalize_history(history: list[dict] | None, *, limit: int = 8) -> list[dict[str, str]]:
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


def _build_user_prompt(
    question: str,
    context_blocks: list[str],
    *,
    page_context: str | None = None,
    mine_found: bool = False,
    guest: bool = False,
    concise: bool = False,
    need_ai_diagram: bool = False,
    has_portal_diagram: bool = False,
) -> str:
    parts = [f"Current user question:\n{question.strip()}"]
    if guest:
        parts.append(
            "GUEST MODE: This user is Guest. Only discuss Knowledge repository, Domain Knowledge "
            "(copper mining), Freeport–Hexaware Journey, and Know your Customer. "
            "Do not provide Programs & projects, SOW, Onboarding, Training, Innovation, or Hall of Fame details. "
            "If asked about those, say they need a full MiNe account and suggest Guest-allowed topics."
        )
    if concise:
        parts.append(
            "CONCISE / DOMAIN MODE:\n"
            "- Answer only what the user asked.\n"
            "- Keep it short: 1 summary sentence + a clear structure (bullets or numbered stages).\n"
            "- Do not list projects, case studies, SOWs, programmes, SIMS, OpenFlow, or engagement details "
            "unless the user explicitly asked for them.\n"
            "- If portal notes are off-topic, ignore them and answer from clear domain knowledge.\n"
            "- For value chain / FMI process / flowchart / lifecycle asks:\n"
            "  • Use ONE ordered list numbered 1. 2. 3. 4. … (never restart at 1 for each stage)\n"
            "  • Under each stage, 1–2 short `-` detail bullets\n"
            "  • End with **Flow:** StageA → StageB → StageC\n"
            "  • About 4–6 stages is enough unless the user asks for more depth"
        )
    if has_portal_diagram:
        parts.append(
            "PORTAL DIAGRAM AVAILABLE: A Domain Knowledge infographic will be shown under your reply. "
            "Briefly mention it. Do NOT add a mermaid/code flowchart."
        )
    if need_ai_diagram:
        parts.append(
            "AI FLOWCHART REQUIRED (do not reuse a portal screenshot):\n"
            "- Create a NEW flowchart for the topic in conversation (resolve “this/it” from history).\n"
            "- After the numbered stages, include exactly ONE mermaid fence.\n"
            "- Prefer `flowchart LR` (left-to-right) for value chains; use `flowchart TD` only if clearer.\n"
            "- Process steps: S1[\"Label\"]  Decision points: D1{\"Question?\"}\n"
            "- Branch with edge labels: D1 -->|Yes| S2[\"...\"] and D1 -->|No| S3[\"...\"]\n"
            "- Example:\n"
            "```mermaid\n"
            "flowchart LR\n"
            "  S1[\"Explore\"] --> D1{\"Viable?\"}\n"
            "  D1 -->|Yes| S2[\"Mine\"]\n"
            "  D1 -->|No| S3[\"Stop\"]\n"
            "  S2 --> S4[\"Process\"]\n"
            "```\n"
            "- Use 4–8 nodes; keep labels short (2–4 words).\n"
            "- Do not claim you cannot draw diagrams.\n"
            "- Do not produce raster/photo images; the chat UI will render this flowchart.\n"
            "- Do not mention SIMS, OpenFlow, or unrelated projects."
        )
    if page_context and not concise:
        parts.append(f"User is currently viewing: {page_context}")
    if context_blocks:
        parts.append(
            "MiNe portal notes (use only if they directly help answer the question):\n"
            + "\n".join(context_blocks)
        )
        if not concise:
            parts.append(
                "Answer using the MiNe portal notes above when they match the question. "
                "Stay specific to Freeport/Hexaware content when relevant."
            )
    elif mine_found is False and not concise:
        parts.append(
            "No matching MiNe portal notes were found for this question. "
            "Start with: I couldn't find this information in the MiNe knowledge repository. "
            "Then offer a careful general explanation if helpful, and ask if they want that."
        )
    parts.append("Write the assistant reply now in polished Markdown.")
    return "\n\n".join(parts)


def _http_error_message(resp: requests.Response) -> str:
    body = (resp.text or "").strip().replace("\n", " ")
    if len(body) > 240:
        body = body[:239] + "…"
    return f"HTTP {resp.status_code}: {body or resp.reason}"


def _verify_path() -> bool | str:
    try:
        import certifi

        return certifi.where()
    except Exception:
        return True


def _session() -> requests.Session:
    sess = requests.Session()
    sess.trust_env = False
    adapter = HTTPAdapter(
        max_retries=Retry(total=0, redirect=False),
        pool_connections=4,
        pool_maxsize=4,
    )
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess


def _force_ipv4_once() -> None:
    if getattr(_force_ipv4_once, "_done", False):
        return
    try:
        _orig = socket.getaddrinfo

        def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
            infos = _orig(host, port, family, type, proto, flags)
            v4 = [i for i in infos if i[0] == socket.AF_INET]
            return v4 + [i for i in infos if i[0] != socket.AF_INET] if v4 else infos

        socket.getaddrinfo = _ipv4_first  # type: ignore[assignment]
        _force_ipv4_once._done = True  # type: ignore[attr-defined]
    except Exception:
        pass


def _post_json(url: str, *, headers: dict, payload: dict, timeout: float) -> requests.Response:
    _force_ipv4_once()
    verify = _verify_path()
    last_exc: Exception | None = None
    sess = _session()
    for attempt in range(3):
        try:
            resp = sess.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
                verify=verify,
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt < 2:
                retry_after = resp.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else 0.9 * (attempt + 1)
                except ValueError:
                    delay = 0.9 * (attempt + 1)
                delay = min(max(delay, 0.5), 8.0)
                time.sleep(delay)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(0.9 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("LLM request failed after retries")


def _groq_models() -> list[str]:
    configured = _setting("CHATBOT_LLM_MODEL")
    models: list[str] = []
    if configured:
        models.append(configured)
    for m in _DEFAULT_GROQ_MODELS:
        if m not in models:
            models.append(m)
    return models


def _call_groq(system: str, messages: list[dict[str, str]], *, max_tokens: int = 1100) -> str:
    api_key = _setting("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is empty on the server")
    url = "https://api.groq.com/openai/v1/chat/completions"
    timeout = float(_setting("CHATBOT_LLM_TIMEOUT") or "60")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "MiNe-AskMiNe/1.0",
    }
    last_error = ""
    chat_messages = [{"role": "system", "content": system}, *messages]
    for model in _groq_models():
        resp = _post_json(
            url,
            headers=headers,
            payload={
                "model": model,
                "temperature": 0.4 if max_tokens <= 600 else 0.55,
                "max_tokens": max_tokens,
                "messages": chat_messages,
            },
            timeout=timeout,
        )
        if resp.status_code in (400, 404) and "model" in (resp.text or "").lower():
            last_error = _http_error_message(resp)
            continue
        if not resp.ok:
            raise RuntimeError(_http_error_message(resp))
        data = resp.json()
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if text.strip():
            return text
        last_error = f"Empty LLM response from model {model}"
    raise RuntimeError(last_error or "Empty LLM response")


def _iter_groq_stream(
    system: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 1100,
):
    """Yield text deltas from Groq chat completions (stream=True)."""
    api_key = _setting("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is empty on the server")
    url = "https://api.groq.com/openai/v1/chat/completions"
    timeout = float(_setting("CHATBOT_LLM_TIMEOUT") or "90")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "MiNe-AskMiNe/1.0",
    }
    chat_messages = [{"role": "system", "content": system}, *messages]
    last_error = ""
    sess = _session()
    verify = _verify_path()
    for model in _groq_models():
        try:
            resp = sess.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "temperature": 0.4 if max_tokens <= 600 else 0.55,
                    "max_tokens": max_tokens,
                    "messages": chat_messages,
                    "stream": True,
                },
                timeout=timeout,
                verify=verify,
                stream=True,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
        if resp.status_code in (400, 404) and "model" in (resp.text or "").lower():
            last_error = _http_error_message(resp)
            resp.close()
            continue
        if not resp.ok:
            last_error = _http_error_message(resp)
            resp.close()
            continue
        got_any = False
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip() if isinstance(raw, str) else raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = ((payload.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                if delta:
                    got_any = True
                    yield delta
        finally:
            resp.close()
        if got_any:
            return
        last_error = f"Empty stream from model {model}"
    raise RuntimeError(last_error or "Empty LLM stream")


def stream_assistant_reply(
    question: str,
    context_blocks: list[str],
    *,
    history: list[dict] | None = None,
    page_context: str | None = None,
    mine_found: bool = False,
    guest: bool = False,
    concise: bool = False,
    need_ai_diagram: bool = False,
    has_portal_diagram: bool = False,
):
    """
    Yield text tokens. Uses Groq streaming when available; otherwise one-shot Gemini/Groq.
    """
    provider = _resolve_provider()
    if not provider:
        raise RuntimeError("No LLM provider configured")

    prior = _normalize_history(history)
    user_prompt = _build_user_prompt(
        question,
        context_blocks,
        page_context=page_context,
        mine_found=mine_found,
        guest=guest,
        concise=concise,
        need_ai_diagram=need_ai_diagram,
        has_portal_diagram=has_portal_diagram,
    )
    messages = [*prior, {"role": "user", "content": user_prompt}]
    max_tokens = 900 if need_ai_diagram else (550 if concise else 1100)

    if provider == "groq":
        yield from _iter_groq_stream(_SYSTEM_PROMPT, messages, max_tokens=max_tokens)
        return

    # Gemini (and fallback): one-shot then yield as coarse chunks for progressive UI.
    text = _call_gemini(_SYSTEM_PROMPT, messages, max_tokens=max_tokens)
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Empty LLM response")
    step = 28
    for i in range(0, len(text), step):
        yield text[i : i + step]


def _call_gemini(system: str, messages: list[dict[str, str]], *, max_tokens: int = 1100) -> str:
    api_key = _setting("GEMINI_API_KEY")
    model = _setting("CHATBOT_LLM_MODEL") or "gemini-2.0-flash"
    timeout = float(_setting("CHATBOT_LLM_TIMEOUT") or "60")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    contents = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m.get("content") or ""}]})
    resp = _post_json(
        url,
        headers={"Content-Type": "application/json"},
        payload={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4 if max_tokens <= 600 else 0.55,
                "maxOutputTokens": max_tokens,
            },
        },
        timeout=timeout,
    )
    if not resp.ok:
        raise RuntimeError(_http_error_message(resp))
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [p.get("text") or "" for p in parts if isinstance(p, dict)]
    return "\n".join(t for t in texts if t).strip()


def generate_assistant_reply(
    question: str,
    context_blocks: list[str],
    *,
    history: list[dict] | None = None,
    page_context: str | None = None,
    mine_found: bool = False,
    guest: bool = False,
    concise: bool = False,
    need_ai_diagram: bool = False,
    has_portal_diagram: bool = False,
) -> dict[str, Any]:
    provider = _resolve_provider()
    if not provider:
        return {"ok": False, "error": "No LLM provider configured"}

    prior = _normalize_history(history)
    user_prompt = _build_user_prompt(
        question,
        context_blocks,
        page_context=page_context,
        mine_found=mine_found,
        guest=guest,
        concise=concise,
        need_ai_diagram=need_ai_diagram,
        has_portal_diagram=has_portal_diagram,
    )
    messages = [*prior, {"role": "user", "content": user_prompt}]
    max_tokens = 900 if need_ai_diagram else (550 if concise else 1100)
    try:
        if provider == "groq":
            text = _call_groq(_SYSTEM_PROMPT, messages, max_tokens=max_tokens)
        else:
            text = _call_gemini(_SYSTEM_PROMPT, messages, max_tokens=max_tokens)
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "Empty LLM response", "provider": provider}
        return {"ok": True, "text": text, "provider": provider}
    except Exception as exc:
        logger.warning("Chatbot LLM (%s) failed: %s", provider, exc)
        return {"ok": False, "error": str(exc), "provider": provider}
