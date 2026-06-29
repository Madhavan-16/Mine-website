"""Verify all static assets referenced by MiNe exist locally for offline deploy."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
TEMPLATES = ROOT / "templates"
STATIC_SITE = ROOT / "static_site"

STATIC_REF_RE = re.compile(
    r"""url_for\s*\(\s*['"]static['"]\s*,\s*filename\s*=\s*['"]([^'"]+)['"]"""
)
IMG_SRC_RE = re.compile(r"""src\s*=\s*['"](?:\.\./)?(?:img|media|css|js|fonts)/([^'"]+)['"]""")
CSS_URL_RE = re.compile(r"""url\s*\(\s*['"]?\.\./([^'")]+)['"]?\s*\)""")

REQUIRED_STATIC_FILES = [
    "img/hexaware-freeport-lockup.png",
    "img/freeport-story-timeline.png",
    "img/journey/two-decades-excellence-transformation-journey.png",
    "img/journey/freeport-hexaware-partnership-milestones-original.png",
    "img/freeport-autonomous-mining-revolution.png",
    "img/strategic-context-delivery-teams.png",
    "img/freeport-strategic-corporate-snapshot.png",
    "img/freeport-leadership-key-roles-may-2026.png",
    "img/freeport-path-to-autonomous-mining.png",
    "img/freeport-global-mining-network.png",
    "img/knowledge-problem-table.png",
    "img/domain/digital-mining-value-chain-mapping.png",
    "img/domain/end-to-end-mining-value-chain.png",
    "img/domain/mapping-services-to-client.png",
    "img/domain/measurement-hierarchy.png",
    "img/domain/mining-and-refining-process.png",
    "img/domain/mining-lifecycle-value.png",
    "img/hero-motifs/hero-motifs-open-pit.png",
    "img/hero-motifs/hero-motifs-copper.png",
    "img/hero-motifs/hero-motifs-haul-truck.png",
    "img/hero-motifs/hero-motifs-processing.png",
    "img/hero-motifs/hero-motifs-safety.png",
    "fonts/inter/Inter-Regular.woff2",
    "fonts/inter/Inter-Medium.woff2",
    "fonts/inter/Inter-SemiBold.woff2",
    "fonts/inter/Inter-Bold.woff2",
    "fonts/inter/Inter-ExtraBold.woff2",
    "css/fonts.css",
    "css/main.css",
    "css/landing.css",
    "css/open-pit-copper-domain.css",
    "js/landing-hero-showcase.js",
    "js/landing-motif-modal.js",
    "js/landing-motion.bundle.js",
    "js/landing-kpi.js",
    "js/open-pit-copper-domain.js",
    "js/journey-motion.bundle.js",
    "js/site-motion.bundle.js",
    "vendor/aos/aos.css",
    "vendor/aos/aos.js",
    "vendor/gsap/gsap.min.js",
    "vendor/gsap/ScrollTrigger.min.js",
]

LEADERSHIP_DIR = STATIC / "img" / "leadership"


def collect_template_refs() -> set[str]:
    refs: set[str] = set()
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        refs.update(STATIC_REF_RE.findall(text))
    return refs


def collect_static_site_refs() -> set[str]:
    refs: set[str] = set()
    for path in STATIC_SITE.rglob("*"):
        if path.suffix.lower() not in {".html", ".css"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in IMG_SRC_RE.findall(text):
            if match.startswith("css/") or match.startswith("js/"):
                refs.add(match)
            elif match.startswith("fonts/"):
                refs.add(match)
            elif match.startswith("media/"):
                refs.add(match)
            else:
                refs.add(f"img/{match}")
        if path.suffix.lower() == ".css":
            for rel in CSS_URL_RE.findall(text):
                refs.add(rel.replace("\\", "/"))
    return refs


def main() -> int:
    missing: list[str] = []
    all_required = set(REQUIRED_STATIC_FILES)

    for ref in collect_template_refs():
        if ref.startswith("img/") or ref.startswith("media/") or ref.startswith("fonts/"):
            all_required.add(ref)

    for ref in collect_static_site_refs():
        all_required.add(ref)

    for rel in sorted(all_required):
        path = STATIC / rel.replace("/", "\\") if "\\" in str(STATIC) else STATIC / rel
        if not path.is_file():
            missing.append(rel)

    if LEADERSHIP_DIR.is_dir():
        leaders = list(LEADERSHIP_DIR.glob("*.png"))
        if len(leaders) < 12:
            missing.append(f"img/leadership/*.png (found {len(leaders)}, expected 12)")
    else:
        missing.append("img/leadership/ (directory)")

    if missing:
        print("MISSING ASSETS:")
        for m in missing:
            print(f"  - {m}")
        return 1

    print(f"OK — {len(all_required)} static files verified (templates + static_site + manifest).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
