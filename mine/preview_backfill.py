"""Backfill rasterized slide previews and PDF previews for Office attachments."""

from __future__ import annotations

import logging

from mine.preview_convert import convert_office_file_to_pdf, find_libreoffice_executable
from mine.slide_preview import generate_slide_png_previews, is_slide_deck_path, list_slide_pngs
from mine.upload_paths import resolve_stored_upload_path

logger = logging.getLogger(__name__)

_OFFICE_PDF_EXT = frozenset({"ppt", "pptx", "doc", "docx", "xls"})


def backfill_missing_pdf_previews(db, upload_folder: str) -> dict:
    """Convert Office uploads that lack preview_path to PDF via LibreOffice."""
    if not find_libreoffice_executable():
        logger.info("LibreOffice not found; skipping PDF preview backfill")
        return {"converted": 0, "failed": 0, "skipped": "no_libreoffice"}

    rows = db.execute(
        """
        SELECT * FROM attachments
        WHERE preview_path IS NULL OR preview_path = ''
        """
    ).fetchall()

    converted = 0
    failed = 0
    for att in rows:
        fname = (att["file_name"] or "").strip().lower()
        ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
        if ext not in _OFFICE_PDF_EXT:
            continue
        source = resolve_stored_upload_path(att["file_path"])
        if not source:
            failed += 1
            continue
        pdf = convert_office_file_to_pdf(source, upload_folder)
        if pdf:
            db.execute(
                "UPDATE attachments SET preview_path = ? WHERE id = ?",
                (pdf, att["id"]),
            )
            converted += 1
            logger.info("PDF preview backfill: attachment %s -> %s", att["id"], pdf)
        else:
            failed += 1

    if converted:
        db.commit()
    return {"converted": converted, "failed": failed}


def backfill_missing_slide_previews(db, upload_folder: str, *, scale: float = 2.0) -> dict:
    """Rasterize slide decks that lack slide_preview_dir."""
    from mine.slide_preview import generate_slide_png_previews, is_slide_deck_path, list_slide_pngs, slide_export_available

    if not slide_export_available():
        logger.info("No slide export tool (LibreOffice/PowerPoint); skipping slide backfill")
        return {"converted": 0, "failed": 0, "skipped": "no_export_tool"}

    rows = db.execute(
        """
        SELECT * FROM attachments
        WHERE slide_preview_dir IS NULL OR slide_preview_dir = ''
        """
    ).fetchall()

    converted = 0
    failed = 0
    skipped = 0
    for att in rows:
        fname = att["file_name"] or ""
        if not is_slide_deck_path(fname):
            continue
        if list_slide_pngs(att["slide_preview_dir"]):
            skipped += 1
            continue
        source = resolve_stored_upload_path(att["file_path"])
        if not source:
            failed += 1
            continue
        paths = generate_slide_png_previews(source, upload_folder, att["id"], scale=scale)
        if paths:
            from pathlib import Path

            db.execute(
                "UPDATE attachments SET slide_preview_dir = ? WHERE id = ?",
                (str(Path(paths[0]).parent), att["id"]),
            )
            converted += 1
            logger.info("Slide preview backfill: attachment %s (%s slides)", att["id"], len(paths))
        else:
            failed += 1

    if converted:
        db.commit()
    return {"converted": converted, "failed": failed, "skipped": skipped}
