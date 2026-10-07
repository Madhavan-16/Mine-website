"""Repair PDF/slide paste artifacts in content text fields.

Fixes:
  - Spaced glyphs: "B U I L D I N G" / "2 0 1 9"
  - Outline noise: "1.No … 2.Loss …" → clean prose without 1./2./3.

Usage (from repo root):

  python tools/repair_spaced_glyphs.py
  python tools/repair_spaced_glyphs.py --db path/to/mine.db
  python tools/repair_spaced_glyphs.py --dry-run
"""

from __future__ import annotations

import argparse
import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_cleanup():
    path = ROOT / "mine" / "text_cleanup.py"
    spec = importlib.util.spec_from_file_location("mine_text_cleanup", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def repair(db_path: Path, cleanup, *, dry_run: bool = False) -> int:
    readable = cleanup.readable_summary
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, title, summary, body FROM content").fetchall()
    changed = 0
    for row in rows:
        updates = {}
        for field in ("title", "summary", "body"):
            raw = row[field]
            if not raw:
                continue
            # Titles: only collapse spaced glyphs (keep intentional numbering rare)
            if field == "title":
                fixed = cleanup.collapse_spaced_glyphs(raw)
            else:
                fixed = readable(raw)
            if fixed != raw:
                updates[field] = fixed
        if not updates:
            continue
        changed += 1
        print(f"id={row['id']} fields={list(updates)} title={row['title'][:80]!r}")
        if dry_run:
            for f, v in updates.items():
                print(f"  {f}: {v[:240]!r}")
            continue
        sets = ", ".join(f"{k} = ?" for k in updates)
        con.execute(
            f"UPDATE content SET {sets}, updated_at = datetime('now') WHERE id = ?",
            [*updates.values(), row["id"]],
        )
    if not dry_run and changed:
        con.commit()
    con.close()
    return changed


def _self_test(cleanup) -> None:
    samples = [
        (
            "2 0 0 6 — 2 0 1 9 · B U I L D I N G T H E D A T A F O U N D A T I O N",
            "2006 — 2019 · BUILDING THE DATA FOUNDATION",
        ),
        (
            "1.No consistent mechanism. 2.Loss of confidence. 3. No single point.",
            "No consistent mechanism. Loss of confidence. No single point.",
        ),
        (
            "1. No visibility.\r\n2. Resulting costs.\r\n3. Manual cleanup is risky.",
            "No visibility. Resulting costs. Manual cleanup is risky.",
        ),
        ("Normal readable summary stays put.", "Normal readable summary stays put."),
    ]
    for raw, expect in samples:
        got = cleanup.readable_summary(raw)
        if got != expect:
            raise SystemExit(f"self-test failed:\n  want {expect!r}\n  got  {got!r}")
    print("self-test ok")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "mine.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    cleanup = _load_cleanup()
    if args.self_test:
        _self_test(cleanup)
        return
    n = repair(args.db, cleanup, dry_run=args.dry_run)
    print(f"{'would update' if args.dry_run else 'updated'} {n} row(s) in {args.db}")


if __name__ == "__main__":
    main()
