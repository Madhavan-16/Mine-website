"""Free-tier LLM clients for MiNe chatbot (Groq and Google Gemini)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are Ask MiNe — a friendly, sharp AI assistant embedded in the Hexaware–Freeport MiNe portal. "
    "Talk like a modern chatbot (natural, warm, clear) — not like a search engine or RAG demo.\n"
    "Rules:\n"
    "1) Answer the user's question directly. Lead with the answer; never open with meta lines "
    "like “Based on the provided context”, “According to MINE CONTEXT”, or “As an AI”.\n"
    "2) For greetings or small talk, reply briefly and invite how you can help "
    "(e.g. “Hey — how can I assist you today?”).\n"
    "3) For general questions (science, definitions, how things work, etc.), answer from general knowledge. "
    "Do not force Freeport/MiNe into the answer unless the user asked about them.\n"
    "4) When optional portal notes are provided and the user is clearly asking about MiNe/Freeport content, "
    "you may weave those facts in naturally — still without mentioning “context” or “sources”.\n"
    "5) If unsure, say so briefly. Do not invent MiNe URLs.\n"
    "6) Keep answers under ~180 words unless the user asks for more detail. Plain text only "
    "(light numbered lists are fine; no markdown tables)."
)

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _clean_secret(value: str | None) -> str:
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        v = v[1:-1].strip()
    return v


def _setting(name: str, default: str = "") -> str:
    """Prefer live process env (Azure App Settings), then Flask config."""
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
    # auto / anything else with a key
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


def _build_user_prompt(question: str, context_blocks: list[str]) -> str:
    parts = [f"User:\n{question.strip()}"]
    if context_blocks:
        parts.append(
            "Optional portal notes (use only if relevant to this question; never mention these notes):\n"
            + "\n".join(context_blocks)
        )
    parts.append("Assistant:")
    return "\n\n".join(parts)


def _http_error_message(resp: requests.Response) -> str:
    body = (resp.text or "").strip().replace("\n", " ")
    if len(body) > 240:
        body = body[:239] + "…"
    return f"HTTP {resp.status_code}: {body or resp.reason}"


def _post_json(url: str, *, headers: dict, payload: dict, timeout: float) -> requests.Response:
    """POST with short retries for transient Azure/Groq failures."""
    verify: bool | str = True
    try:
        import certifi

        verify = certifi.where()
    except Exception:
        verify = True

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                url, headers=headers, json=payload, timeout=timeout, verify=verify
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt < 2:
                retry_after = resp.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else 0.9 * (attempt + 1)
                except ValueError:
                    delay = 0.9 * (attempt + 1)
                delay = min(max(delay, 0.5), 8.0)
                logger.info(
                    "LLM HTTP %s — retry %s/3 after %.1fs",
                    resp.status_code,
                    attempt + 2,
                    delay,
                )
                time.sleep(delay)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < 2:
                delay = 0.9 * (attempt + 1)
                logger.info("LLM network error (%s) — retry %s/3 after %.1fs", exc, attempt + 2, delay)
                time.sleep(delay)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("LLM request failed after retries")


def _call_groq(system: str, user: str) -> str:
    api_key = _setting("GROQ_API_KEY")
    model = _setting("CHATBOT_LLM_MODEL") or "llama-3.1-8b-instant"
    url = "https://api.groq.com/openai/v1/chat/completions"
    timeout = float(_setting("CHATBOT_LLM_TIMEOUT") or "60")
    resp = _post_json(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": model,
            "temperature": 0.65,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=timeout,
    )
    if not resp.ok:
        raise RuntimeError(_http_error_message(resp))
    data = resp.json()
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _call_gemini(system: str, user: str) -> str:
    api_key = _setting("GEMINI_API_KEY")
    model = _setting("CHATBOT_LLM_MODEL") or "gemini-2.0-flash"
    timeout = float(_setting("CHATBOT_LLM_TIMEOUT") or "60")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    resp = _post_json(
        url,
        headers={"Content-Type": "application/json"},
        payload={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.65,
                "maxOutputTokens": 700,
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


def generate_assistant_reply(question: str, context_blocks: list[str]) -> dict[str, Any]:
    """
    Call configured free-tier LLM.
    Returns {"ok": True, "text": "...", "provider": "groq"|"gemini"} or {"ok": False, "error": "..."}.
    """
    provider = _resolve_provider()
    if not provider:
        return {"ok": False, "error": "No LLM provider configured"}

    user_prompt = _build_user_prompt(question, context_blocks)
    try:
        if provider == "groq":
            text = _call_groq(_SYSTEM_PROMPT, user_prompt)
        else:
            text = _call_gemini(_SYSTEM_PROMPT, user_prompt)
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "Empty LLM response", "provider": provider}
        return {"ok": True, "text": text, "provider": provider}
    except Exception as exc:
        logger.warning("Chatbot LLM (%s) failed: %s", provider, exc)
        return {"ok": False, "error": str(exc), "provider": provider}
