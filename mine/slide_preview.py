"""
Rasterize PowerPoint slides to PNG for high-fidelity in-browser preview.

Priority:
  1. Microsoft PowerPoint (COM) on Windows — best icon/font fidelity
  2. LibreOffice direct PNG export
  3. LibreOffice PDF + pypdfium2 page rasterization
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mine.preview_convert import convert_office_file_to_pdf, find_libreoffice_executable

logger = logging.getLogger(__name__)

_SLIDE_EXT = frozenset({"ppt", "pptx"})


def is_slide_deck_path(path: str | Path) -> bool:
    ext = Path(path).suffix.lower().lstrip(".")
    return ext in _SLIDE_EXT


def slide_preview_root(upload_folder: str | Path, attachment_id: int) -> Path:
    return Path(upload_folder).resolve() / ".slide_previews" / str(int(attachment_id))


def list_slide_pngs(preview_dir: str | Path | None) -> list[str]:
    if not preview_dir:
        return []
    root = Path(preview_dir)
    if not root.is_dir():
        return []
    files = sorted(root.glob("*.png"), key=_slide_sort_key)
    return [str(p.resolve()) for p in files if p.is_file()]


def _slide_sort_key(path: Path) -> tuple:
    m = re.search(r"(\d+)", path.stem)
    return (int(m.group(1)) if m else 0, path.name.lower())


def _normalize_png_sequence(out_dir: Path) -> list[str]:
    """Rename discovered PNGs to 001.png, 002.png, … for stable URLs."""
    found: list[Path] = []
    for p in sorted(out_dir.glob("*.png"), key=_slide_sort_key):
        if p.is_file():
            found.append(p)
    if not found:
        return []

    # If already 001.png style, keep order
    if all(re.fullmatch(r"\d{3}", p.stem) for p in found):
        return [str(p.resolve()) for p in found]

    paths: list[str] = []
    for i, src in enumerate(found, 1):
        dest = out_dir / f"{i:03d}.png"
        if src.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            src.rename(dest)
        paths.append(str(dest.resolve()))
    return paths


def _pdf_to_pngs(pdf_path: Path, out_dir: Path, *, scale: float = 2.0) -> list[str]:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 not installed; cannot rasterize PDF slides")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(len(pdf)):
            dest = out_dir / f"{i + 1:03d}.png"
            page = pdf[i]
            bitmap = page.render(scale=scale)
            pil = bitmap.to_pil()
            pil.save(dest, "PNG", optimize=True)
            paths.append(str(dest.resolve()))
    finally:
        pdf.close()
    return paths


def _libreoffice_direct_png(src: Path, out_dir: Path) -> list[str]:
    soffice = find_libreoffice_executable()
    if not soffice:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--norestore",
                "--convert-to",
                "png",
                "--outdir",
                str(out_dir),
                str(src),
            ],
            check=True,
            timeout=300,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("LibreOffice PNG export failed for %s: %s", src.name, e)
        return []
    return _normalize_png_sequence(out_dir)


def _libreoffice_pdf_png(src: Path, out_dir: Path, upload_folder: str, *, scale: float) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="mine-pdf-") as tmp:
        pdf = convert_office_file_to_pdf(str(src), upload_folder, out_dir=tmp)
        if not pdf or not os.path.isfile(pdf):
            return []
        return _pdf_to_pngs(Path(pdf), out_dir, scale=scale)


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powerpoint_available() -> bool:
    if os.name != "nt":
        return False
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        "try {\n"
        "  $pp = New-Object -ComObject PowerPoint.Application\n"
        "  $pp.Quit()\n"
        "  'ok'\n"
        "} catch { 'no' }\n"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=False,
            timeout=20,
            capture_output=True,
            text=True,
        )
        return "ok" in (result.stdout or "")
    except (subprocess.TimeoutExpired, OSError):
        return False


def slide_export_available() -> bool:
    """True when raster slide export can run (LibreOffice and/or PowerPoint)."""
    if find_libreoffice_executable():
        return True
    return _powerpoint_available()


def _powerpoint_export_png(src: Path, out_dir: Path) -> list[str]:
    """Export slides via PowerPoint COM (Windows + Office installed)."""
    if os.name != "nt":
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        f"$src = {_powershell_quote(str(src.resolve()))}\n"
        f"$out = {_powershell_quote(str(out_dir.resolve()))}\n"
        "$pp = New-Object -ComObject PowerPoint.Application\n"
        "$pp.Visible = 0\n"
        "try {\n"
        "  $pres = $pp.Presentations.Open($src, $true, $true, $false)\n"
        "  try { $pres.Export($out, 'PNG') } finally { $pres.Close() }\n"
        "} finally { $pp.Quit() }\n"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=True,
            timeout=300,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        logger.info("PowerPoint slide export unavailable for %s: %s", src.name, e)
        return []

    # PowerPoint names exports Slide1.PNG, Slide2.PNG, …
    found = sorted(out_dir.glob("Slide*.png"), key=_slide_sort_key)
    if not found:
        found = sorted(out_dir.glob("*.png"), key=_slide_sort_key)
    if not found:
        return []

    paths: list[str] = []
    for i, src_png in enumerate(found, 1):
        dest = out_dir / f"{i:03d}.png"
        if src_png.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            src_png.rename(dest)
        paths.append(str(dest.resolve()))
    return paths


def generate_slide_png_previews(
    source_path: str | Path,
    upload_folder: str | Path,
    attachment_id: int,
    *,
    scale: float = 2.0,
) -> list[str]:
    """
    Build PNGs for each slide under upload_folder/.slide_previews/<id>/.
    Returns ordered absolute paths to PNG files.
    """
    src = Path(source_path).resolve()
    if not src.is_file() or not is_slide_deck_path(src):
        return []

    out_dir = slide_preview_root(upload_folder, attachment_id)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    strategies = (
        lambda: _powerpoint_export_png(src, out_dir),
        lambda: _libreoffice_direct_png(src, out_dir),
        lambda: _libreoffice_pdf_png(src, out_dir, str(upload_folder), scale=scale),
    )
    for build in strategies:
        paths = build()
        if paths:
            meta = out_dir / "meta.json"
            meta.write_text(json.dumps({"count": len(paths), "source": src.name}), encoding="utf-8")
            logger.info("Slide preview: %s slides for attachment %s", len(paths), attachment_id)
            return paths

    shutil.rmtree(out_dir, ignore_errors=True)
    return []


def remove_slide_preview_dir(preview_dir: str | Path | None) -> None:
    if not preview_dir:
        return
    try:
        shutil.rmtree(Path(preview_dir), ignore_errors=True)
    except OSError:
        pass
