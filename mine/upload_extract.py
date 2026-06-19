"""Best-effort text extraction from uploaded knowledge files for autofill."""

from __future__ import annotations

import io
import re
from pathlib import Path

# Cap extracted plain text to keep memory and response time bounded (~upload limit order).
_MAX_EXTRACT_CHARS = 350_000


def title_from_filename(filename: str) -> str:
    stem = Path(filename or "document").stem
    stem = re.sub(r"[_\s]+", " ", stem).strip()
    return stem or "Untitled"


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\x00", "")).strip()


def _clip(s: str, max_len: int) -> str:
    s = _norm_ws(s)
    if len(s) <= max_len:
        return s
    cut = s[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def _gist_summary(blob_raw: str, blob_norm: str, max_sentences: int = 5, max_chars: int = 900) -> str:
    """Short intro: a few sentences/lines, not the full document."""
    text = blob_norm or _norm_ws(blob_raw)
    if not text:
        return ""
    if len(text) <= 280:
        return text[:2000]

    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences: list[str] = []
    for s in raw_sentences:
        s = s.strip()
        if len(s) < 14:
            continue
        sentences.append(s)
        if len(sentences) >= max_sentences:
            break

    if len(sentences) >= 2:
        joined = "\n".join(sentences[:max_sentences])
        if len(joined) > max_chars:
            joined = _clip(joined, max_chars)
        return joined[:2000]

    lines: list[str] = []
    for ln in blob_raw.splitlines():
        t = _norm_ws(ln)
        t = re.sub(r"^#+\s*", "", t).strip()
        if len(t) < 18:
            continue
        lines.append(t)
        if len(lines) >= max_sentences:
            break
    if len(lines) >= 2:
        joined = "\n".join(_clip(l, 260) for l in lines[:max_sentences])
        return joined[:max_chars][:2000]

    return _clip(text, min(max_chars, 700))


def _clean_autofill_title(title: str) -> str:
    t = (title or "").strip()
    t = re.sub(r"^#+\s*", "", t).strip()
    return t[:500]


def _strip_series_header_for_summary(blob_raw: str, blob_norm: str, title: str) -> tuple[str, str]:
    """Remove leading episode / series / title boilerplate so the summary is substantive content only."""
    title_plain = _clean_autofill_title(title or "")
    t_key = title_plain.lower()

    lines = blob_raw.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        plain = re.sub(r"^#+\s*", "", stripped).strip()
        low = plain.lower()
        long_line = len(plain) > 420

        if not long_line and re.match(r"^#+\s", stripped):
            i += 1
            continue
        if not long_line and re.search(r"\bdomain term of the week\b", low) and len(plain) < 220:
            i += 1
            continue
        if not long_line and re.match(r"^episode\s*[\d.]+\s*[:.\-–]", low, re.I) and len(plain) < 180:
            i += 1
            continue
        if t_key and len(t_key) > 8 and not long_line:
            if low == t_key or (low.startswith(t_key) and len(plain) <= len(t_key) + 45):
                i += 1
                continue
        break

    raw2 = "\n".join(lines[i:]).strip()
    if not raw2:
        raw2 = blob_raw
    norm2 = _norm_ws(raw2)

    # One-line PDF/PPT dumps: drop prefix through "Domain Term of the Week" (and light punctuation).
    norm2 = re.sub(
        r"(?is)^.{0,320}?\bdomain term of the week\b\s*[.\-–:;•]?\s*",
        "",
        norm2,
        count=1,
    ).strip()

    # Remaining leading episode slug on one line
    norm2 = re.sub(
        r"(?is)^#?\s*episode\s*[\d.]+\s*[:.\-–]\s*.{0,160}?(?=\s+[A-Z]|\s+[a-z]{4,}\s)",
        "",
        norm2,
        count=1,
    ).strip()

    if t_key and len(t_key) > 8:
        lo = norm2.lower()
        if lo.startswith(t_key):
            tail = norm2[len(title_plain) :].lstrip()
            tail = re.sub(r"^[\-–—:.;,•·]+", "", tail)
            if len(tail) > 45:
                norm2 = tail

    if len(norm2) < 42:
        return blob_raw, blob_norm
    return raw2, norm2


def _first_line_title(blob: str, fallback: str, max_len: int = 200) -> str:
    for raw in blob.splitlines():
        line = _norm_ws(raw)
        if len(line) >= 6:
            return (line[:max_len] + "…") if len(line) > max_len else line
    return fallback


def _truncate_blob(blob: str) -> str:
    if len(blob) <= _MAX_EXTRACT_CHARS:
        return blob
    return blob[:_MAX_EXTRACT_CHARS] + "\n…[extraction truncated at size limit]"


def extract_pdf(data: bytes, filename: str) -> tuple[str, str, str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    meta_title = ""
    md = reader.metadata
    if md:
        raw = getattr(md, "title", None)
        if raw:
            meta_title = _norm_ws(str(raw))
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        if total >= _MAX_EXTRACT_CHARS:
            break
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)
            total += len(t)
    blob = "\n".join(parts)
    blob = _truncate_blob(blob)
    blob_norm = _norm_ws(blob)
    title = meta_title or _first_line_title(blob, title_from_filename(filename))
    title = _clean_autofill_title(title)
    raw_s, norm_s = _strip_series_header_for_summary(blob, blob_norm, title)
    summary = _gist_summary(raw_s, norm_s) if norm_s else ""
    return title, summary, ""


def extract_docx(data: bytes, filename: str) -> tuple[str, str, str]:
    from docx import Document

    doc = Document(io.BytesIO(data))
    title = title_from_filename(filename)
    chunks: list[str] = []

    for p in doc.paragraphs:
        txt = _norm_ws(p.text)
        if not txt:
            continue
        style_name = getattr(getattr(p, "style", None), "name", None) or ""
        if style_name.startswith("Title") and len(txt) <= 500:
            title = txt[:500]
        elif style_name.startswith("Heading 1") and len(txt) <= 500 and title == title_from_filename(filename):
            title = txt[:500]
        chunks.append(txt)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                tx = _norm_ws(cell.text)
                if tx:
                    chunks.append(tx)

    blob = "\n".join(chunks)
    blob = _truncate_blob(blob)
    blob_norm = _norm_ws(blob)

    if title == title_from_filename(filename) and chunks:
        first = chunks[0]
        if 6 <= len(first) <= 300:
            title = first[:500]
    title = _clean_autofill_title(title)

    raw_s, norm_s = _strip_series_header_for_summary(blob, blob_norm, title)
    summary = _gist_summary(raw_s, norm_s) if norm_s else ""
    return title, summary, ""


def _pptx_iter_shapes(shapes):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _pptx_iter_shapes(shape.shapes)
        else:
            yield shape


def extract_pptx(data: bytes, filename: str) -> tuple[str, str, str]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    chunks: list[str] = []
    total = 0

    for slide in prs.slides:
        if total >= _MAX_EXTRACT_CHARS:
            break
        for shape in _pptx_iter_shapes(slide.shapes):
            if hasattr(shape, "text"):
                t = _norm_ws(getattr(shape, "text", "") or "")
                if t:
                    chunks.append(t)
                    total += len(t)
        if slide.has_notes_slide:
            try:
                nf = slide.notes_slide.notes_text_frame
                if nf and nf.text:
                    t = _norm_ws(nf.text)
                    if t:
                        chunks.append(t)
                        total += len(t)
            except Exception:
                pass

    blob = "\n".join(chunks)
    blob = _truncate_blob(blob)
    blob_norm = _norm_ws(blob)

    title = title_from_filename(filename)
    for t in chunks:
        if 6 <= len(t) <= 220:
            title = t[:500]
            break
    title = _clean_autofill_title(title)

    raw_s, norm_s = _strip_series_header_for_summary(blob, blob_norm, title)
    summary = _gist_summary(raw_s, norm_s) if norm_s else ""
    return title, summary, ""


def extract_xlsx(data: bytes, filename: str) -> tuple[str, str, str]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        rows: list[str] = []
        total = 0
        max_rows_per_sheet = 8000
        for sheetname in wb.sheetnames:
            if total >= _MAX_EXTRACT_CHARS:
                break
            ws = wb[sheetname]
            rows.append(f"[{sheetname}]")
            for row in ws.iter_rows(max_row=max_rows_per_sheet, values_only=True):
                if total >= _MAX_EXTRACT_CHARS:
                    break
                cells = [_norm_ws(str(c)) for c in row if c is not None and _norm_ws(str(c))]
                if cells:
                    line = " ".join(cells)
                    rows.append(line)
                    total += len(line)
        blob = "\n".join(rows)
        blob = _truncate_blob(blob)
        blob_norm = _norm_ws(blob)

        non_hdr = [r for r in rows if r and not r.startswith("[")]
        title = title_from_filename(filename)
        if non_hdr:
            cand = non_hdr[0]
            if len(cand) <= 200:
                title = cand[:500]
            elif len(non_hdr) > 1:
                cand2 = non_hdr[1]
                if len(cand2) <= 200:
                    title = cand2[:500]

        title = _clean_autofill_title(title[:500])
        raw_s, norm_s = _strip_series_header_for_summary(blob, blob_norm, title)
        summary = _gist_summary(raw_s, norm_s) if norm_s else ""
        return title, summary, ""
    finally:
        wb.close()


def suggest_from_upload(filename: str, data: bytes) -> dict[str, str]:
    """Return title and a short summary gist; body is left empty for the client."""
    name = filename or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    title = title_from_filename(name)
    summary = ""

    try:
        if ext == "pdf":
            title, summary, _ = extract_pdf(data, name)
        elif ext == "docx":
            title, summary, _ = extract_docx(data, name)
        elif ext == "pptx":
            title, summary, _ = extract_pptx(data, name)
        elif ext == "xlsx":
            title, summary, _ = extract_xlsx(data, name)
        elif ext == "ppt":
            title = title_from_filename(name)
            summary = "Legacy .ppt files cannot be read for auto-fill; use .pptx or type a summary."
        elif ext in ("png", "jpg", "jpeg"):
            title = title_from_filename(name)
            summary = "Image attachment — add a short description if needed."
        else:
            title = title_from_filename(name)
    except Exception:
        title = title_from_filename(name)
        summary = ""

    return {
        "title": _clean_autofill_title((title or title_from_filename(name))[:500]),
        "summary": (summary or "")[:2000],
        "body": "",
    }
