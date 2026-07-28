"""Free-tier LLM clients for MiNe chatbot (Groq and Google Gemini)."""

from __future__ import annotations

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

# Prefer a current Groq free-tier chat model; allow override via CHATBOT_LLM_MODEL.
_DEFAULT_GROQ_MODELS = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
)


def _clean_secret(value: Any) -> str:
    if value is None:
        return ""
    # App config may hold non-strings (e.g. CHATBOT_LLM_TIMEOUT as float).
    v = str(value).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        v = v[1:-1].strip()
    # Azure portal paste sometimes adds zero-width / BOM characters.
    v = v.replace("\ufeff", "").replace("\u200b", "").replace("\r", "").replace("\n", "")
    return v.strip()


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


def _verify_path() -> bool | str:
    try:
        import certifi

        return certifi.where()
    except Exception:
        return True


def _session() -> requests.Session:
    """
    Dedicated session for LLM calls.
    trust_env=False avoids broken HTTP(S)_PROXY vars that Azure App Service
    sometimes injects and that break outbound calls to Groq.
    """
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
    """Prefer IPv4 — some Azure App Service hosts fail on IPv6 routes to public APIs."""
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
    """POST with short retries for transient Azure/Groq failures."""
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
                logger.info(
                    "LLM HTTP %s — retry %s/3 after %.1fs",
                    resp.status_code,
                    attempt + 2,
                    delay,
                )
                time.sleep(delay)
                continue
            return resp
        except requests.RequestException as exc:
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


def _groq_models() -> list[str]:
    configured = _setting("CHATBOT_LLM_MODEL")
    models: list[str] = []
    if configured:
        models.append(configured)
    for m in _DEFAULT_GROQ_MODELS:
        if m not in models:
            models.append(m)
    return models


def _call_groq(system: str, user: str) -> str:
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
    for model in _groq_models():
        resp = _post_json(
            url,
            headers=headers,
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
        if resp.status_code in (400, 404) and "model" in (resp.text or "").lower():
            last_error = _http_error_message(resp)
            logger.warning("Groq model %s rejected — trying next: %s", model, last_error)
            continue
        if not resp.ok:
            raise RuntimeError(_http_error_message(resp))
        data = resp.json()
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if text.strip():
            return text
        last_error = f"Empty LLM response from model {model}"
    raise RuntimeError(last_error or "Empty LLM response")


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
