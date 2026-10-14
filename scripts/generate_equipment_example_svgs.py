"""Generate yellow open-pit equipment example SVGs for Domain Knowledge taxonomy."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = ROOT / "templates" / "partials" / "open_pit_copper_domain_content.html"
OUT = ROOT / "static" / "img" / "domain" / "equipment"

Y = "#F5A623"
Y_D = "#D4891A"
Y_L = "#FFC857"
STROKE = "#7A5510"
BG = "#FFFFFF"


def slug(name: str) -> str:
    s = name.replace("&", "and").replace("–", "-")
    s = re.sub(r"[^a-zA-Z0-9/]+", " ", s)
    s = s.replace("/", "-").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def pick_variant(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("truck", "haul", "grader", "dozer", "cart")):
        return "truck"
    if "drill" in n:
        return "drill"
    if any(k in n for k in ("shovel", "excavator", "loader", "breaker")):
        return "excavator"
    if any(k in n for k in ("crusher", "mill", "sag", "ball", "sizer", "cyclone", "pebble")):
        return "crusher"
    if any(k in n for k in ("cell", "tank", "train", "pad", "thickener", "filter", "ew ", "sx", "leach", "liner", "emitter", "conveyor", "stacker", "feeder", "screen", "bin", "agglomer", "rectifier", "pump", "dosing", "strip", "wash", "sampler")):
        return "plant"
    if any(k in n for k in ("monitor", "dispatch", "detonator", "system")):
        return "cabinet"
    return "machine"


def art(variant: str) -> str:
    g = f'<rect width="960" height="540" fill="{BG}"/>'
    g += '<path d="M80 420 H880" stroke="#C5D4DE" stroke-width="4"/>'
    if variant == "truck":
        g += f'<path d="M220 380 h420 l60-80 h100 l40 80 h80 v40 H220z" fill="{Y}" stroke="{STROKE}" stroke-width="3"/>'
        g += f'<path d="M280 300 h180 l40 60 H280z" fill="{Y_L}" stroke="{STROKE}" stroke-width="2"/>'
        g += f'<circle cx="300" cy="420" r="36" fill="#333"/><circle cx="620" cy="420" r="36" fill="#333"/>'
    elif variant == "drill":
        g += f'<rect x="360" y="120" width="240" height="300" rx="12" fill="{Y}" stroke="{STROKE}" stroke-width="3"/>'
        g += f'<rect x="468" y="40" width="24" height="200" fill="{Y_D}"/>'
        g += f'<path d="M480 240 v120" stroke="{STROKE}" stroke-width="8"/>'
        g += f'<circle cx="480" cy="380" r="28" fill="{Y_L}" stroke="{STROKE}" stroke-width="2"/>'
    elif variant == "excavator":
        g += f'<path d="M260 380 h200 v-60 h120 l80-100 40 30-90 110H460v70H260z" fill="{Y}" stroke="{STROKE}" stroke-width="3"/>'
        g += f'<circle cx="320" cy="400" r="40" fill="#333"/><circle cx="400" cy="400" r="40" fill="#333"/>'
    elif variant == "crusher":
        g += f'<path d="M380 140 L520 380 H340z" fill="{Y_L}" stroke="{STROKE}" stroke-width="3"/>'
        g += f'<ellipse cx="430" cy="380" rx="120" ry="40" fill="{Y}" stroke="{STROKE}" stroke-width="3"/>'
    elif variant == "plant":
        g += f'<rect x="300" y="160" width="80" height="220" fill="{Y}" stroke="{STROKE}" stroke-width="2"/>'
        g += f'<rect x="420" y="120" width="80" height="260" fill="{Y_L}" stroke="{STROKE}" stroke-width="2"/>'
        g += f'<rect x="540" y="200" width="80" height="180" fill="{Y}" stroke="{STROKE}" stroke-width="2"/>'
    elif variant == "cabinet":
        g += f'<rect x="340" y="140" width="280" height="240" rx="8" fill="{Y}" stroke="{STROKE}" stroke-width="3"/>'
        g += f'<rect x="380" y="180" width="200" height="120" fill="{Y_L}" stroke="{STROKE}" stroke-width="2"/>'
    else:
        g += f'<rect x="300" y="180" width="360" height="200" rx="16" fill="{Y}" stroke="{STROKE}" stroke-width="3"/>'
        g += f'<rect x="340" y="220" width="120" height="80" fill="{Y_L}" stroke="{STROKE}" stroke-width="2"/>'
    return g


def svg(name: str) -> str:
    title = name.replace("&", "&amp;").replace("<", "&lt;")
    variant = pick_variant(name)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" '
        f'aria-label="Example illustration: {title}">\n'
        f"{art(variant)}\n"
        f'<text x="480" y="500" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" '
        f'font-size="22" font-weight="700" fill="{STROKE}">{title}</text>\n'
        f"</svg>\n"
    )


def main() -> None:
    text = PARTIAL.read_text(encoding="utf-8")
    names = re.findall(r'class="equip-card__name">([^<]+)</h4>', text)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        (OUT / f"{slug(name)}.svg").write_text(svg(name), encoding="utf-8")
    print(f"Wrote {len(names)} SVGs to {OUT}")


if __name__ == "__main__":
    main()
