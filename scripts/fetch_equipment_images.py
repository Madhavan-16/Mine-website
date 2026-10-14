"""Fetch distinct mining/copper-process photos for FMI equipment taxonomy."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = ROOT / "templates" / "partials" / "open_pit_copper_domain_content.html"
OUT = ROOT / "static" / "img" / "domain" / "equipment"
UA = "MiNeDomainGuide/1.0 (FMI copper mining reference)"
COMMONS = "https://commons.wikimedia.org/w/api.php"
ENWIKI = "https://en.wikipedia.org/w/api.php"

# Verified Commons photos of actual plant equipment (not generic search noise).
DIRECT: dict[str, str] = {
    "jaw-cone-impact-crusher": "https://upload.wikimedia.org/wikipedia/commons/d/d5/Compound_Cone_Crusher_%28VSC_series%29.jpg",
    "agglomerator": "https://upload.wikimedia.org/wikipedia/commons/d/d9/PELLETIZER.jpg",
}

# Commons search phrases aligned to FMI open-pit copper + PA process areas.
SEARCH: dict[str, list[str]] = {
    "rotary-blast-hole-drill": ["blasthole drill open pit mine", "rotary blast drill mining"],
    "dth-drill": ["down the hole drill mining", "DTH drilling open pit"],
    "pre-split-drill": ["pre split blasting open pit", "wall control blast mining"],
    "explosive-truck": ["ANFO truck mining blast", "explosives truck open pit"],
    "detonator-system": ["electronic detonator mining blast", "mining blast initiation"],
    "stemming-equipment": ["blast hole stemming mining", "open pit blasting"],
    "blast-monitoring": ["blast vibration monitor mining", "seismograph mining blast"],
    "haul-truck": ["ultra class haul truck mining", "copper mine haul truck"],
    "electric-rope-shovel": ["electric rope shovel mining", "P&H mining shovel open pit"],
    "hydraulic-excavator": ["hydraulic excavator open pit mine", "mining excavator copper"],
    "front-end-loader": ["wheel loader mining open pit", "front end loader mine"],
    "water-truck": ["water truck mine dust suppression", "mining water cart"],
    "grader-dozer": ["bulldozer open pit mine", "motor grader mining road"],
    "dispatch-system": ["mine dispatch fleet management", "open pit mine operations center"],
    "acid-truck": ["sulfuric acid tanker mining leach", "acid delivery heap leach"],
    "gyratory-crusher": ["gyratory crusher mine", "primary crusher copper mine"],
    "jaw-cone-impact-crusher": ["impact crusher rock mining plant", "horizontal shaft impact crusher aggregate"],
    "sizer-roll-crusher": ["mineral sizer mining", "roll crusher mine"],
    "rock-breaker": ["rock breaker mining crusher", "hydraulic breaker gyratory"],
    "apron-feeder-vibrating-grizzly": ["apron feeder mining", "vibrating grizzly mine"],
    "conveyor-belt-stacker": ["overland conveyor mining", "stacker mining copper"],
    "agglomerator": ["agglomeration drum mining ore", "rotating drum heap leach copper"],
    "screen-surge-bin": ["vibrating screen mining plant", "surge bin crusher mine"],
    "sag-mill-ag-mill": ["SAG mill copper concentrator", "semi autogenous mill mining"],
    "ball-mill": ["steel balls ball mill grinding", "ball mill cylindrical mining ore"],
    "tower-mill-isamill": ["IsaMill fine grinding mining", "stirred mill concentrator"],
    "pebble-crusher": ["pebble crusher SAG mill", "recirculation crusher mining"],
    "hydrocyclone": ["hydrocyclone copper concentrator", "cyclone classifier mining"],
    "mill-liner-ball-charging": ["ball mill mining grinding", "grinding media copper mine"],
    "variable-speed-drive-vsd-gmd": ["gearless mill drive", "SAG mill drive mining"],
    "rougher-cleaner-scavenger-cells": ["froth flotation copper concentrator", "flotation cells mining"],
    "column-cell": ["column flotation copper", "flotation column concentrator"],
    "regrind-mill": ["regrind mill flotation copper", "fine grinding concentrator"],
    "thickener-filter": ["thickener copper concentrator", "filter press mining concentrate"],
    "reagent-dosing-blower": ["flotation reagent plant mining", "concentrator flotation air"],
    "sampler-tsf": ["tailings storage facility mine", "mine tailings dam copper"],
    "leach-pad-cell-lift": ["Morenci mine heap leach", "copper heap leach pad aerial"],
    "drip-emitter-irrigation": ["heap leach drip irrigation mining", "leach pad irrigation copper"],
    "liner-collection-system": ["heap leach liner HDPE", "leach pad geomembrane"],
    "agglomeration-drum": ["heap leach agglomeration drum", "copper ore agglomerator"],
    "acid-storage-dosing-pump": ["sulfuric acid storage tank industrial", "chemical dosing pump plant"],
    "sx-train": ["solvent extraction copper SX plant", "copper SX-EW plant"],
    "extraction-strip-mixer-settler": ["mixer-settler solvent extraction plant", "SX EW copper mine facility"],
    "pls-raffinate-organic-tanks": ["solvent extraction tank copper plant", "SX plant tanks"],
    "crud-treatment-after-settler": ["solvent extraction copper plant", "SX crud treatment"],
    "ew-cell-cathode-anode": ["copper electrowinning tankhouse", "electrowinning cathode copper"],
    "stripping-machine-crane": ["copper cathode stripping tankhouse", "electrowinning crane"],
    "rectifier-transformer": ["electrowinning rectifier copper", "copper tankhouse power"],
    "electrolyte-circulation-filter-heater": ["copper electrowinning cells", "EW tankhouse electrolyte"],
    "additive-dosing-bleed-treatment": ["copper electrowinning plant", "SX-EW copper refinery"],
    "wash-weigh-strap-station": ["copper cathode production mine", "copper cathode bundle"],
}


def slug(name: str) -> str:
    s = name.replace("&", "and")
    s = re.sub(r"[^a-zA-Z0-9/]+", " ", s)
    s = s.replace("/", "-").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def wiki_api(base: str, params: dict) -> dict:
    req = urllib.request.Request(
        base + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": UA},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(35 * (attempt + 1))
                continue
            return {}
        except OSError:
            return {}
    return {}


def search_thumbs(base: str, query: str, limit: int = 8, namespace: int | None = None) -> list[str]:
    params: dict = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": limit,
        "prop": "pageimages",
        "piprop": "thumbnail",
        "pithumbsize": 960,
    }
    if namespace is not None:
        params["gsrnamespace"] = namespace
    data = wiki_api(base, params)
    urls: list[str] = []
    for page in data.get("query", {}).get("pages", {}).values():
        u = (page.get("thumbnail") or {}).get("source")
        if u:
            urls.append(u)
    return urls


def commons_thumbs(query: str, limit: int = 10) -> list[str]:
    data = wiki_api(
        COMMONS,
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 960,
        }
    )
    urls: list[str] = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        u = info.get("thumburl") or info.get("url")
        if u and re.search(r"\.(jpe?g|png|webp)(/|$)", u, re.I):
            urls.append(u)
    return urls


def pick_url(slug_key: str, name: str, used: set[str]) -> str | None:
    queries = list(SEARCH.get(slug_key, []))
    queries.append(f"{name} open pit copper mine")
    for q in queries:
        for u in commons_thumbs(q, limit=6):
            if u not in used:
                return u
        for u in search_thumbs(ENWIKI, q + " mining", limit=5):
            if u not in used:
                return u
        time.sleep(1.5)
    return None


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def main() -> None:
    import sys

    only = {a for a in sys.argv[1:] if a}
    text = PARTIAL.read_text(encoding="utf-8")
    names = re.findall(r'class="equip-card__name">([^<]+)</h4>', text)
    OUT.mkdir(parents=True, exist_ok=True)
    used_urls: set[str] = set()
    ok = 0
    for name in names:
        s = slug(name)
        if only and s not in only:
            continue
        dest = OUT / f"{s}.jpg"
        if not only and dest.exists() and dest.stat().st_size > 8000:
            ok += 1
            continue
        url = DIRECT.get(s) if s in DIRECT and (only and s in only or not only) else None
        if not url:
            url = pick_url(s, name, used_urls)
        if not url:
            print(f"MISS {s}")
            continue
        try:
            download(url, dest)
            used_urls.add(url)
            ok += 1
            print(f"OK   {s}")
        except OSError as e:
            print(f"FAIL {s}: {e}")
        time.sleep(3.0)
    by_hash: dict[str, list[str]] = {}
    for f in OUT.glob("*.jpg"):
        h = hashlib.md5(f.read_bytes()).hexdigest()
        by_hash.setdefault(h, []).append(f.name)
    dups = [g for g in by_hash.values() if len(g) > 1]
    print(f"Done: {ok}/{len(names)}; duplicate files: {len(dups)}")


if __name__ == "__main__":
    main()
