"""Download self-hosted Inter fonts into static/ for offline deployment."""
from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = ROOT / "static" / "fonts" / "inter"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

INTER_FONTS = {
    "Inter-Regular.woff2": (
        "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Regular.woff2"
    ),
    "Inter-Medium.woff2": (
        "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Medium.woff2"
    ),
    "Inter-SemiBold.woff2": (
        "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-SemiBold.woff2"
    ),
    "Inter-Bold.woff2": (
        "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Bold.woff2"
    ),
    "Inter-ExtraBold.woff2": (
        "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-ExtraBold.woff2"
    ),
}


def fetch(url: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 1024:
        print(f"skip {dest.name} ({dest.stat().st_size} bytes)")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "MiNe-asset-bundle/1.0"})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=300) as resp:
            data = resp.read()
        dest.write_bytes(data)
        print(f"ok   {dest.name} ({len(data)} bytes)")
        return True
    except Exception as exc:
        print(f"fail {dest.name}: {exc}")
        return False


def main() -> None:
    print("=== Inter fonts ===")
    for name, url in INTER_FONTS.items():
        fetch(url, FONTS_DIR / name)


if __name__ == "__main__":
    main()
