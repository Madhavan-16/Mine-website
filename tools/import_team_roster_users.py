#!/usr/bin/env python3
"""Import MiNe users from the Freeport active resource tracker Excel file."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mine import create_app
from mine.db import get_db
from mine.team_roster import import_roster_users, load_team_roster, roster_xlsx_path


def main() -> int:
    app = create_app()
    with app.app_context():
        path = roster_xlsx_path()
        roster = load_team_roster(path)
        if not roster:
            print(f"No roster rows found. Place or upload workbook at:\n  {path}")
            return 1
        print(f"Roster: {len(roster)} members from {path.name}")
        db = get_db()
        result = import_roster_users(db)
        if result.get("error"):
            print("ERROR:", result["error"])
            return 1
        db.commit()
        print(f"Created: {result['created']}, skipped: {result['skipped']}")
        if result.get("credentials_file"):
            print(f"Credentials: {result['credentials_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
