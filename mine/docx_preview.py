"""Build a minimal HTML preview for .docx uploads (paragraph text extraction)."""

from __future__ import annotations

import logging
from html import escape
from io import BytesIO

logger = logging.getLogger(__name__)

_MAX_PARAS = 200


def render_docx_preview_html(
    data: bytes,
    *,
    doc_title: str = "",
    max_paras: int = _MAX_PARAS,
) -> str | None:
    """Return a full HTML document with document paragraphs, or None if unreadable."""
    try:
        from docx import Document
    except ImportError:
        logger.warning("python-docx not available; skipping docx HTML preview")
        return None

    if not data:
        return None

    try:
        doc = Document(BytesIO(data))
    except Exception as e:
        logger.info("docx preview could not open document: %s", e)
        return None

    paras = [(p.text or "").strip() for p in doc.paragraphs if (p.text or "").strip()]
    if not paras:
        return None

    total = len(paras)
    shown = paras[:max_paras]
    truncated = total > max_paras
    title = escape((doc_title or "Document").strip() or "Document")

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f"<title>{title} · preview</title>",
        "<style>",
        "body{margin:0;font-family:Georgia,serif;font-size:14px;background:#fff;color:#1e293b;line-height:1.55;}",
        ".wrap{box-sizing:border-box;padding:20px 24px 32px;max-width:720px;margin:0 auto;}",
        "h1{font-family:system-ui,sans-serif;font-size:1.15rem;margin:0 0 12px;}",
        ".note{font-family:system-ui,sans-serif;font-size:11px;color:#64748b;margin:0 0 16px;}",
        ".warn{font-size:11px;color:#92400e;background:#fffbeb;border:1px solid #fcd34d;border-radius:6px;padding:8px 10px;margin-bottom:12px;}",
        "p{margin:0 0 12px;}",
        "</style></head><body><div class=\"wrap\">",
        f"<h1>{title}</h1>",
        "<p class=\"note\">Text preview — formatting and images are not shown. Download the original for the full document.</p>",
    ]

    if truncated:
        parts.append(
            f'<p class="warn">Showing the first <strong>{max_paras}</strong> of <strong>{total}</strong> paragraphs.</p>'
        )

    for para in shown:
        parts.append(f"<p>{escape(para)}</p>")

    parts.append("</div></body></html>")
    return "".join(parts)
