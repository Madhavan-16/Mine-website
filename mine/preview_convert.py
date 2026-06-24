"""
Generate PDF previews for Office documents using LibreOffice headless (optional).

If LibreOffice is not installed or conversion fails, preview_path stays unset and the UI
can use Office Online embed (PPT, Excel, etc. where configured) or the built-in .xlsx HTML table preview.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from mine.config import Config

logger = logging.getLogger(__name__)

# Extensions we attempt to convert when LibreOffice is available (matches typical uploads).
_CONVERT_EXTENSIONS = frozenset({"ppt", "pptx", "doc", "docx", "xls", "xlsx"})


def _libreoffice_search_paths() -> list[Path]:
    """Candidate soffice.exe locations (system install + project tools/)."""
    candidates: list[Path] = []
    if os.name == "nt":
        for root in (
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        ):
            candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    else:
        candidates.extend(Path(p) for p in ("/usr/bin/soffice", "/usr/bin/libreoffice"))

    tools = Config.BASE_DIR / "tools"
    if tools.is_dir():
        for name in (
            "LibreOffice/program/soffice.exe",
            "LibreOfficePortable/App/libreoffice/program/soffice.exe",
            "LibreOfficePortable/App/LibreOffice/program/soffice.exe",
        ):
            candidates.append(tools / name)
        try:
            for found in tools.rglob("soffice.exe"):
                candidates.append(found)
        except OSError:
            pass
    return candidates


def find_libreoffice_executable() -> str | None:
    env = (os.environ.get("LIBREOFFICE_PATH") or os.environ.get("SOFFICE_PATH") or "").strip()
    if env and Path(env).is_file():
        return env
    for cand in _libreoffice_search_paths():
        if cand.is_file():
            return str(cand)
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_office_file_to_pdf(
    source_path: str,
    upload_folder: str,
    *,
    out_dir: str | Path | None = None,
) -> str | None:
    """
    Convert an Office document to PDF.
    Source must live under upload_folder; PDF is written to out_dir (defaults to upload_folder).
    Returns absolute path to the PDF or None.
    """
    src = Path(source_path).resolve()
    if not src.is_file():
        return None
    ext = src.suffix.lower().lstrip(".")
    if ext not in _CONVERT_EXTENSIONS:
        return None
    upload_root = Path(upload_folder).resolve()
    dest_dir = Path(out_dir).resolve() if out_dir else upload_root

    def _is_under(p: Path, root: Path) -> bool:
        try:
            p.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    if not _is_under(src, upload_root):
        logger.warning("Attachment path outside upload folder; refusing conversion for %s", source_path)
        return None

    soffice = find_libreoffice_executable()
    if not soffice:
        logger.debug("LibreOffice/soffice not found; no PDF preview for %s", src.name)
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(dest_dir),
                str(src),
            ],
            check=True,
            timeout=180,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, FileNotFoundError) as e:
        logger.warning("PDF conversion failed for %s: %s", src.name, e)
        return None

    pdf_path = dest_dir / f"{src.stem}.pdf"
    if not pdf_path.is_file():
        logger.warning("Expected PDF missing after conversion: %s", pdf_path)
        return None
    return str(pdf_path.resolve())
