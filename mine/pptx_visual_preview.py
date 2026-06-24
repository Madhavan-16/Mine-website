"""
Visual PPTX preview by parsing slide XML and serving embedded media (SVG/PNG).

Renders icons and images in-browser without LibreOffice or PowerPoint.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from io import BytesIO
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

_MAX_SLIDES = 50
_DEFAULT_CX = 12192000
_DEFAULT_CY = 6858000
_MEDIA_RE = re.compile(r"^ppt/media/[A-Za-z0-9._-]+$")
_MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MEDIA_MIME = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


@dataclass
class _VisualEl:
    kind: str  # "text" | "image"
    left: float
    top: float
    width: float
    height: float
    z: int
    text: str = ""
    media_name: str = ""


@dataclass
class _VisualSlide:
    index: int
    width: int
    height: int
    elements: list[_VisualEl] = field(default_factory=list)


def is_safe_pptx_media_path(path: str) -> bool:
    return bool(_MEDIA_RE.match(path or ""))


def is_safe_pptx_media_filename(name: str) -> bool:
    return bool(_MEDIA_NAME_RE.match(name or ""))


def _blip_embed_rid(blip) -> str | None:
    """Resolve relationship id from a:blip (direct embed or Office SVG extension)."""
    if blip is None:
        return None
    rid = blip.get(f"{{{_NS['r']}}}embed")
    if rid:
        return rid
    for child in blip.iter():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "svgBlip":
            rid = child.get(f"{{{_NS['r']}}}embed")
            if rid:
                return rid
    return None


def read_pptx_media(data: bytes, filename: str) -> tuple[bytes, str] | None:
    """Read one ppt/media asset from a .pptx zip."""
    if not data or not is_safe_pptx_media_filename(filename):
        return None
    zip_path = f"ppt/media/{filename}"
    if not is_safe_pptx_media_path(zip_path):
        return None
    try:
        zf = zipfile.ZipFile(BytesIO(data))
        blob = zf.read(zip_path)
    except (zipfile.BadZipFile, KeyError):
        return None
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = _MEDIA_MIME.get(ext, "application/octet-stream")
    return blob, mime


def _emu_pct(value: int | None, total: int) -> float:
    if not value or not total:
        return 0.0
    return max(0.0, min(100.0, 100.0 * value / total))


def _xfrm_box(node, slide_w: int, slide_h: int) -> tuple[float, float, float, float]:
    xfrm = node.find("a:xfrm", _NS) if node is not None else None
    if xfrm is None:
        return 0.0, 0.0, 20.0, 10.0
    off = xfrm.find("a:off", _NS)
    ext = xfrm.find("a:ext", _NS)
    x = int(off.get("x", 0)) if off is not None else 0
    y = int(off.get("y", 0)) if off is not None else 0
    cx = int(ext.get("cx", 0)) if ext is not None else 0
    cy = int(ext.get("cy", 0)) if ext is not None else 0
    if cx <= 0:
        cx = slide_w // 5
    if cy <= 0:
        cy = slide_h // 10
    return (
        _emu_pct(x, slide_w),
        _emu_pct(y, slide_h),
        _emu_pct(cx, slide_w),
        _emu_pct(cy, slide_h),
    )


def _shape_text(node) -> str:
    chunks: list[str] = []
    for t in node.findall(".//a:t", _NS):
        if t.text:
            chunks.append(t.text)
    return "".join(chunks).strip()


def _rels_map(zf: zipfile.ZipFile, rels_path: str) -> dict[str, str]:
    try:
        root = ET.fromstring(zf.read(rels_path))
    except KeyError:
        return {}
    out: dict[str, str] = {}
    for rel in root:
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            if target.startswith("../"):
                target = "ppt/" + target[3:]
            elif not target.startswith("ppt/"):
                target = "ppt/slides/" + target
            out[rid] = target.replace("\\", "/")
    return out


def _slide_size(zf: zipfile.ZipFile) -> tuple[int, int]:
    try:
        root = ET.fromstring(zf.read("ppt/presentation.xml"))
    except KeyError:
        return _DEFAULT_CX, _DEFAULT_CY
    sld_sz = root.find(".//p:sldSz", _NS)
    if sld_sz is None:
        return _DEFAULT_CX, _DEFAULT_CY
    return int(sld_sz.get("cx", _DEFAULT_CX)), int(sld_sz.get("cy", _DEFAULT_CY))


def _collect_elements(node, rels: dict[str, str], slide_w: int, slide_h: int, z_start: int) -> list[_VisualEl]:
    elements: list[_VisualEl] = []
    z = z_start

    def walk(parent, offset_x=0, offset_y=0):
        nonlocal z
        if parent is None:
            return
        for child in list(parent):
            tag = child.tag.rsplit("}", 1)[-1]

            if tag == "grpSp":
                walk(child, offset_x, offset_y)
                continue

            if tag == "pic":
                blip = child.find(".//a:blip", _NS)
                rid = _blip_embed_rid(blip)
                media = rels.get(rid or "", "")
                if media and is_safe_pptx_media_path(media):
                    left, top, width, height = _xfrm_box(child.find("p:spPr", _NS), slide_w, slide_h)
                    elements.append(
                        _VisualEl("image", left, top, width, height, z, media_name=media.split("/")[-1])
                    )
                    z += 1
                continue

            if tag == "sp":
                text = _shape_text(child)
                if text:
                    left, top, width, height = _xfrm_box(child.find("p:spPr", _NS), slide_w, slide_h)
                    elements.append(_VisualEl("text", left, top, width, height, z, text=text))
                    z += 1
                walk(child, offset_x, offset_y)
                continue

            walk(child, offset_x, offset_y)

    walk(node)
    elements.sort(key=lambda e: e.z)
    return elements


def parse_pptx_visual_slides(data: bytes) -> list[_VisualSlide]:
    if not data:
        return []
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        return []

    slide_w, slide_h = _slide_size(zf)
    slide_paths = sorted(
        [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
        key=lambda p: int(re.search(r"(\d+)", p).group(1)),
    )
    slides: list[_VisualSlide] = []

    for i, slide_path in enumerate(slide_paths[:_MAX_SLIDES], 1):
        rels_path = slide_path.replace("slides/", "slides/_rels/").replace(".xml", ".xml.rels")
        rels = _rels_map(zf, rels_path)
        try:
            root = ET.fromstring(zf.read(slide_path))
        except KeyError:
            continue
        sp_tree = root.find(".//p:spTree", _NS)
        elements = _collect_elements(sp_tree, rels, slide_w, slide_h, 0)
        slides.append(_VisualSlide(i, slide_w, slide_h, elements))

    return slides


def render_pptx_visual_html(
    data: bytes,
    *,
    deck_title: str,
    asset_url_for: Callable[[str], str],
) -> str | None:
    """
    asset_url_for(media_filename) -> URL to serve ppt/media asset for this attachment.
    """
    slides = parse_pptx_visual_slides(data)
    if not slides:
        return None

    title = escape((deck_title or "Presentation").strip() or "Presentation")
    total = len(slides)

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f"<title>{title} · visual preview</title>",
        "<style>",
        ":root{color-scheme:dark;--bg:#0b1220;--panel:#111827;--text:#e5e7eb;--muted:#94a3b8;--border:#1f2937;}",
        "*{box-sizing:border-box;}",
        "body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text);}",
        ".wrap{padding:12px 12px 28px;max-width:1100px;margin:0 auto;}",
        "header{margin-bottom:14px;}",
        "header h1{margin:0 0 6px;font-size:1.05rem;}",
        "header p{margin:0;font-size:11px;color:var(--muted);line-height:1.45;}",
        ".deck{display:grid;gap:18px;}",
        ".slide-card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:12px;}",
        ".slide-hd{margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#38bdf8;}",
        ".stage{position:relative;width:100%;aspect-ratio:16/9;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #cbd5e1;}",
        ".stage-el{position:absolute;overflow:hidden;}",
        ".stage-el img{width:100%;height:100%;object-fit:contain;display:block;}",
        ".stage-el--text{display:flex;align-items:flex-start;padding:2px 4px;font-size:clamp(9px,1.1vw,14px);line-height:1.25;color:#0f172a;white-space:pre-wrap;word-break:break-word;}",
        ".warn{font-size:11px;color:#fcd34d;background:#422006;border:1px solid #854d0e;border-radius:6px;padding:8px 10px;margin-bottom:12px;}",
        "</style></head><body><div class=\"wrap\">",
        "<header>",
        f"<h1>{title}</h1>",
        "<p>Visual preview from embedded slide assets — SVG icons, images, and text. Layout is approximate.</p>",
        "</header>",
    ]

    if total >= _MAX_SLIDES:
        parts.append(f'<p class="warn">Showing first <strong>{_MAX_SLIDES}</strong> slides.</p>')

    parts.append('<div class="deck">')
    for slide in slides:
        parts.append('<section class="slide-card">')
        parts.append(f'<h2 class="slide-hd">Slide {slide.index} / {total}</h2>')
        parts.append('<div class="stage">')
        for el in slide.elements:
            style = (
                f"left:{el.left:.3f}%;top:{el.top:.3f}%;"
                f"width:{max(el.width, 1.5):.3f}%;height:{max(el.height, 1.5):.3f}%;"
                f"z-index:{el.z};"
            )
            if el.kind == "image":
                url = escape(asset_url_for(el.media_name), quote=True)
                parts.append(
                    f'<div class="stage-el" style="{style}">'
                    f'<img src="{url}" alt="" loading="lazy"/>'
                    f"</div>"
                )
            else:
                parts.append(
                    f'<div class="stage-el stage-el--text" style="{style}">{escape(el.text)}</div>'
                )
        parts.append("</div></section>")
    parts.append("</div></div></body></html>")
    return "".join(parts)
