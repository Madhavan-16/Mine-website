"""Repair paste/OCR artifacts common in PDF and slide extracts."""

from __future__ import annotations

import re

# Single glyphs (and lone hyphens) separated by spaces — typical slide/PDF letter-spacing.
_SPACED_GLYPH_RUN = re.compile(
    r"(?<![A-Za-z0-9])("
    r"[A-Za-z0-9]"
    r"(?:\s+(?:[A-Za-z0-9]|[—–\-])){3,}"
    r")(?![A-Za-z0-9])"
)

# Longest-first lexicon to reinsert word breaks after collapsing spaced caps.
_WORD_LEXICON = tuple(
    sorted(
        {
            "FOUNDATION",
            "MIGRATION",
            "INTELLIGENCE",
            "OPERATIONS",
            "FOUNDATIONAL",
            "PARTNERSHIP",
            "INFLECTION",
            "ADOPTION",
            "ADVANCED",
            "BUILDING",
            "CROSSING",
            "THROUGH",
            "SNOWFLAKE",
            "REPORTING",
            "AUTOMATION",
            "ANALYTICS",
            "PRIMARY",
            "CLOUD",
            "FIRST",
            "DATA",
            "WITH",
            "FROM",
            "INTO",
            "OVER",
            "UNDER",
            "THAT",
            "THIS",
            "AND",
            "FOR",
            "THE",
            "OF",
            "TO",
            "IN",
            "ON",
            "AT",
            "BY",
            "OR",
            "AN",
            "AS",
            "AI",
            "BI",
            "IT",
            "IOT",
            "KPI",
            "ETL",
            "RFP",
            "KYC",
            "KYA",
            "A",
        },
        key=len,
        reverse=True,
    )
)


def _greedy_word_split(collapsed: str) -> str:
    """Split an ALLCAPS blob into lexicon words when the whole string can be consumed."""
    s = collapsed or ""
    if len(s) < 4:
        return s
    # Keep hyphenated compounds as units (AI-FIRST).
    chunks = re.split(r"([—–\-])", s)
    out: list[str] = []
    for chunk in chunks:
        if chunk in "—–-" or not chunk:
            out.append(chunk)
            continue
        upper = chunk.upper()
        parts: list[str] = []
        i = 0
        n = len(upper)
        ok = True
        while i < n:
            hit = None
            for word in _WORD_LEXICON:
                if upper.startswith(word, i):
                    hit = word
                    break
            if not hit:
                ok = False
                break
            parts.append(chunk[i : i + len(hit)])
            i += len(hit)
        out.append(" ".join(parts) if ok and parts else chunk)
    # Rejoin hyphens without extra spaces: "AI - FIRST" → "AI-FIRST"
    joined = "".join(out)
    joined = re.sub(r"\s*([—–\-])\s*", r"\1", joined)
    joined = re.sub(r"\s{2,}", " ", joined).strip()
    return joined


def _collapse_run(run: str) -> str:
    tokens = [t for t in re.split(r"\s+", run.strip()) if t]
    if not tokens:
        return run
    # Digit eras joined with a dash: "2 0 0 6 — 2 0 1 9" → "2006 — 2019"
    if all(t.isdigit() or t in "—–-" for t in tokens) and any(t.isdigit() for t in tokens):
        parts: list[str] = []
        buf: list[str] = []
        for t in tokens:
            if t.isdigit():
                buf.append(t)
            else:
                if buf:
                    parts.append("".join(buf))
                    buf = []
                parts.append(f" {t} ")
        if buf:
            parts.append("".join(buf))
        return re.sub(r"\s{2,}", " ", "".join(parts)).strip()
    joined = "".join(tokens)
    # Letter / hyphen title runs
    if re.fullmatch(r"[A-Za-z—–\-]+", joined):
        return _greedy_word_split(joined)
    return joined


def has_spaced_glyphs(text: str | None) -> bool:
    """True when text contains PDF/slide letter-spacing artifacts."""
    if not text:
        return False
    return bool(_SPACED_GLYPH_RUN.search(text))


def collapse_spaced_glyphs(text: str | None) -> str:
    """Turn 'B U I L D I N G' / '2 0 1 9' paste artifacts into readable text."""
    if not text:
        return ""
    if not has_spaced_glyphs(text):
        return text
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fixed: list[str] = []
    for line in lines:
        out = line
        prev = None
        while prev != out:
            prev = out
            out = _SPACED_GLYPH_RUN.sub(lambda m: _collapse_run(m.group(1)), out)
        out = re.sub(r"[ \t]{2,}", " ", out)
        fixed.append(out)
    return "\n".join(fixed)


# Outline markers: "1. ", "1.", "2)", "(3) " — including missing space after the dot.
_OUTLINE_SPLIT = re.compile(
    r"(?:^|[\r\n]+|\s+)(?=\(?\d{1,2}(?:[.)]|\))\s*(?:[A-Za-z“\"'(]|$))"
)
_OUTLINE_PREFIX = re.compile(r"^\(?\d{1,2}(?:[.)]|\))\s*")


def _looks_like_numbered_outline(text: str) -> bool:
    """True when the blob is mostly a 1./2./3. challenge list (common in case-study paste)."""
    markers = re.findall(r"(?:^|[\r\n]|\s)\(?\d{1,2}[.)]", text)
    return len(markers) >= 2


def strip_outline_numbers(text: str | None) -> str:
    """Drop pasted 1./2./3. markers and return readable prose (or line-wise items)."""
    if not text:
        return ""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""

    if _looks_like_numbered_outline(raw):
        chunks = _OUTLINE_SPLIT.split(raw)
        items: list[str] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            chunk = _OUTLINE_PREFIX.sub("", chunk).strip()
            # Fix "1.No" style left on a chunk that didn't split cleanly
            chunk = re.sub(r"^(\d{1,2})\.(?=[A-Za-z])", "", chunk).strip()
            if chunk:
                items.append(chunk)
        if len(items) >= 2:
            prose: list[str] = []
            for item in items:
                item = re.sub(r"\s+", " ", item).strip()
                item = item.rstrip(".;:")
                if item:
                    prose.append(item)
            if not prose:
                return raw
            joined = ". ".join(prose)
            if not joined.endswith((".", "!", "?")):
                joined += "."
            return joined

    # Single leading marker or missing space after "1."
    fixed = re.sub(r"^(\d{1,2})\.(?=[A-Za-z])", r"\1. ", raw)
    fixed = re.sub(r"^(\d{1,2})\.\s+", "", fixed, count=1)
    return fixed.strip()


def readable_summary(text: str | None) -> str:
    """Card/excerpt cleanup: fix spaced glyphs and drop inconsistent outline numbers."""
    return strip_outline_numbers(collapse_spaced_glyphs(text))
