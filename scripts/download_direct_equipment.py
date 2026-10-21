"""Download DIRECT-map equipment images only (no API)."""
from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_equipment_images import DIRECT, OUT, UA  # noqa: E402


def main() -> None:
    slugs = sys.argv[1:] or list(DIRECT.keys())
    OUT.mkdir(parents=True, exist_ok=True)
    for s in slugs:
        url = DIRECT.get(s)
        if not url:
            print(f"SKIP {s} (no DIRECT url)")
            continue
        dest = OUT / f"{s}.jpg"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            dest.write_bytes(urllib.request.urlopen(req, timeout=120).read())
            print(f"OK   {s} ({dest.stat().st_size} bytes)")
        except OSError as e:
            print(f"FAIL {s}: {e}")
        time.sleep(6)


if __name__ == "__main__":
    main()
