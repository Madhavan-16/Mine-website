#!/usr/bin/env python3
"""Backfill PDF and visual slide previews for Office attachments."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mine import create_app
from mine.preview_backfill import backfill_missing_pdf_previews, backfill_missing_slide_previews
from mine.preview_convert import find_libreoffice_executable


def main() -> int:
    app = create_app()
    with app.app_context():
        from mine.db import get_db

        lo = find_libreoffice_executable()
        if lo:
            print(f"LibreOffice: {lo}")
        else:
            print("LibreOffice not found (PowerPoint export may still work on Windows).")

        db = get_db()
        pdf_result = backfill_missing_pdf_previews(db, app.config["UPLOAD_FOLDER"])
        print("PDF backfill:", pdf_result)
        if app.config.get("ENABLE_SLIDE_PREVIEW", True):
            slide_result = backfill_missing_slide_previews(
                db,
                app.config["UPLOAD_FOLDER"],
                scale=float(app.config.get("SLIDE_PREVIEW_SCALE", 2.0)),
            )
            print("Slide backfill:", slide_result)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
