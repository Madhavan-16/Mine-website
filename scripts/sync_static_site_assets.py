"""Mirror static assets into static_site/ for offline HTML preview deploy."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
SITE = ROOT / "static_site"

COPY_DIRS = [
    ("img", "img"),
    ("fonts", "fonts"),
    ("vendor", "vendor"),
]

COPY_CSS = [
    "fonts.css",
    "variables.css",
    "main.css",
    "landing.css",
    "reference.css",
    "wireframe-layout.css",
]

COPY_JS = [
    "landing-hero-showcase.js",
    "landing-motif-modal.js",
    "landing-motion.bundle.js",
    "landing-kpi.js",
]


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def main() -> None:
    for src_rel, dest_rel in COPY_DIRS:
        src = STATIC / src_rel
        dest = SITE / dest_rel
        if not src.is_dir():
            print(f"skip missing dir {src_rel}")
            continue
        copy_tree(src, dest)
        print(f"synced {src_rel}/ -> static_site/{dest_rel}/")

    for name in COPY_CSS:
        src = STATIC / "css" / name
        dest = SITE / "css" / name
        if not src.is_file():
            print(f"skip missing css/{name}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"synced css/{name}")

    for name in COPY_JS:
        src = STATIC / "js" / name
        dest = SITE / "js" / name
        if not src.is_file():
            print(f"skip missing js/{name}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"synced js/{name}")

    print("done")


if __name__ == "__main__":
    main()
