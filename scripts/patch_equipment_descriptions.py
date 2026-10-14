"""Apply two-line FMI process descriptions to equipment taxonomy cards."""
from __future__ import annotations

import re
from pathlib import Path

PARTIAL = Path(__file__).resolve().parents[1] / "templates/partials/open_pit_copper_domain_content.html"

# slug -> (line 1, line 2)
DESCS: dict[str, tuple[str, str]] = {
    "rotary-blast-hole-drill": (
        "Production drill rig for vertical blast patterns on open-pit benches.",
        "Feeds drilling and blasting PA metrics: meters drilled, availability, and pattern quality.",
    ),
    "dth-drill": (
        "Down-the-hole hammer drill for hard-rock penetration at the bench face.",
        "Used where D&B requires deeper energy per meter in competent ore and waste.",
    ),
    "pre-split-drill": (
        "Smaller drill for perimeter control holes that protect final pit walls.",
        "Supports wall-control blasting and stable highwall geometry in the mine plan.",
    ),
    "explosive-truck": (
        "Mobile unit that loads ANFO or emulsion into charged blast holes.",
        "Links to blast preparation KPIs: charge mass, truck utilization, and safety compliance.",
    ),
    "detonator-system": (
        "Electronic or non-electric initiation system for timed blast sequences.",
        "Enables controlled energy release and vibration limits for nearby infrastructure.",
    ),
    "stemming-equipment": (
        "Places inert material above explosives to confine blast energy in the hole.",
        "Improves fragmentation control and reduces flyrock risk on production blasts.",
    ),
    "blast-monitoring": (
        "Seismographs and velocity-of-detonation tools that record blast performance.",
        "Validates vibration, airblast, and fragmentation against mine permit limits.",
    ),
    "haul-truck": (
        "Ultra-class rear-dump truck moving ore and waste from shovel to crusher or dump.",
        "Core load-and-haul PA: payload, cycle time, utilization, and queue time at load/dump.",
    ),
    "electric-rope-shovel": (
        "Primary electric loading unit with rope-suspended dipper in the open pit.",
        "Drives loading rate, pass match with haul fleet, and shovel availability KPIs.",
    ),
    "hydraulic-excavator": (
        "Hydraulic shovel or backhoe configuration for selective mining and loading.",
        "Used for ore/waste control, bench cleanup, and supporting shovel redundancy.",
    ),
    "front-end-loader": (
        "Rubber-tired loader for stockpiles, leach pad support, and auxiliary loading.",
        "Supports rehandle, road maintenance material, and short-haul ore movement.",
    ),
    "water-truck": (
        "High-capacity tanker that wets haul roads for dust suppression.",
        "Protects visibility and road integrity; tied to HSE and road maintenance plans.",
    ),
    "grader-dozer": (
        "Motor grader or dozer for road shape, drainage, and stockpile management.",
        "Keeps haul routes safe and supports dump and pad construction standards.",
    ),
    "dispatch-system": (
        "Fleet management system assigning trucks to shovels and optimized routes.",
        "Integrates GPS, production targets, and real-time shift reporting for the pit.",
    ),
    "acid-truck": (
        "Dedicated tanker delivering sulfuric acid to leach pads or acid storage.",
        "Supports hydromet acid balance, pad irrigation rates, and hazardous-material controls.",
    ),
    "gyratory-crusher": (
        "Primary crusher using a gyrating mantle against a concave bowl.",
        "First size-reduction step for mill feed; governs crusher throughput and availability.",
    ),
    "jaw-cone-impact-crusher": (
        "Secondary and tertiary crushers including cone and impact configurations.",
        "Produces controlled product size for grinding, leach, or agglomeration feed.",
    ),
    "sizer-roll-crusher": (
        "Low-speed roll or mineral sizer for softer ore and fines control.",
        "Alternative sizing path where impact crushing is less efficient or desirable.",
    ),
    "rock-breaker": (
        "Pedestal-mounted hydraulic hammer breaking oversize at the crusher pocket.",
        "Prevents crusher trips and protects downstream milling and conveyor capacity.",
    ),
    "apron-feeder-vibrating-grizzly": (
        "Apron or grizzly feeder that scalps fines and meters ore into the crusher.",
        "Stabilizes crusher feed rate and removes undersize before primary crushing.",
    ),
    "conveyor-belt-stacker": (
        "Belt conveyors and stackers moving crushed ore to stockpiles or leach pads.",
        "Links crushing to downstream processing with tonnage and availability tracking.",
    ),
    "agglomerator": (
        "Rotating drum that binds fine ore with acid for strong heap leach permeability.",
        "Critical for copper heap leach where fines would otherwise channel or pond.",
    ),
    "screen-surge-bin": (
        "Vibrating screens and surge bins for size classification and feed buffering.",
        "Decouples upstream mining rate from crusher and mill feed stability.",
    ),
    "sag-mill-ag-mill": (
        "Semi-autogenous or autogenous mill using ore and limited steel media.",
        "Primary grinding stage for concentrator throughput and specific energy KPIs.",
    ),
    "ball-mill": (
        "Rotating mill with steel balls for fine grinding after SAG or secondary crushing.",
        "Sets P80 for flotation feed; drives milling kWh per tonne and liner life metrics.",
    ),
    "tower-mill-isamill": (
        "Stirred vertical mill for fine regrind or ultrafine liberation work.",
        "Used when flotation needs finer particle size than conventional ball milling.",
    ),
    "pebble-crusher": (
        "Crusher recirculating pebbles rejected from SAG mill discharge.",
        "Increases SAG throughput by preventing critical-size buildup in the mill.",
    ),
    "hydrocyclone": (
        "Centrifugal classifier splitting slurry into overflow fines and underflow coarse.",
        "Controls grind circuit particle size distribution feeding flotation or leach.",
    ),
    "mill-liner-ball-charging": (
        "Mill liner systems and ball-charging equipment maintaining grinding media levels.",
        "Affects mill availability, power draw, and consistent grinding performance.",
    ),
    "variable-speed-drive-vsd-gmd": (
        "Variable-speed or gearless drive controlling mill rotational speed.",
        "Optimizes grind efficiency and soft-start for large concentrator motors.",
    ),
    "rougher-cleaner-scavenger-cells": (
        "Flotation banks recovering copper sulfide from mill feed slurry.",
        "Rougher, cleaner, and scavenger stages set recovery and concentrate grade KPIs.",
    ),
    "column-cell": (
        "Tall column flotation cell for high-grade cleaning of copper concentrate.",
        "Improves final concentrate grade with lower residence time than mechanical cells.",
    ),
    "regrind-mill": (
        "Fine mill between rougher and cleaner flotation stages.",
        "Liberates locked copper minerals to improve cleaner recovery and grade.",
    ),
    "thickener-filter": (
        "Thickeners and filters dewatering flotation concentrate for shipment.",
        "Produces filter-cake moisture specs and clear overflow for water recycle.",
    ),
    "reagent-dosing-blower": (
        "Reagent skids and blowers supplying collectors, frothers, and flotation air.",
        "Directly influences recovery, froth stability, and concentrator operating cost.",
    ),
    "sampler-tsf": (
        "Cross-stream samplers and tailings storage facility components.",
        "Supports metallurgical accounting samples and environmental tailings management.",
    ),
    "leach-pad-cell-lift": (
        "Engineered heap leach pad, cells, and lifts stacking acid-leached ore.",
        "Primary hydromet asset for PLS generation and copper extraction to SX.",
    ),
    "drip-emitter-irrigation": (
        "Drip or sprinkler network applying acid solution across the leach pad surface.",
        "Controls application rate, ponding prevention, and uniform copper dissolution.",
    ),
    "liner-collection-system": (
        "HDPE liner and drainage piping collecting pregnant leach solution (PLS).",
        "Prevents environmental release and routes PLS to SX feed ponds.",
    ),
    "agglomeration-drum": (
        "Rotary drum conditioning ore with acid before placement on the heap.",
        "Same agglomeration role as the agglomerator in crush-leach flow paths.",
    ),
    "acid-storage-dosing-pump": (
        "Acid storage tanks and metering pumps supplying leach and SX circuits.",
        "Maintains site acid inventory, dose accuracy, and safe transfer to pads.",
    ),
    "sx-train": (
        "Solvent extraction train with mixer-settlers transferring copper to organic phase.",
        "Central hydromet step linking PLS to electrowinning feed electrolyte.",
    ),
    "extraction-strip-mixer-settler": (
        "Mixer-settler units for extraction and stripping stages in the SX circuit.",
        "Where copper transfers between aqueous PLS/ electrolyte and organic solvent.",
    ),
    "pls-raffinate-organic-tanks": (
        "Tank farms holding pregnant leach solution, raffinate, and organic inventory.",
        "Provides surge capacity and flow balance across leach, SX, and EW.",
    ),
    "crud-treatment-after-settler": (
        "Crud treatment and after-settlers polishing organic phase before SX reuse.",
        "Protects SX efficiency by removing entrained solids and third-phase emulsions.",
    ),
    "ew-cell-cathode-anode": (
        "Electrowinning cells plating copper onto cathodes from rich electrolyte.",
        "Produces LME-grade cathode copper tracked in metal accounting and FINWIP.",
    ),
    "stripping-machine-crane": (
        "Cathode stripping machines and cranes harvesting plates from EW cells.",
        "Links tankhouse output to cathode washing, weighing, and bundling.",
    ),
    "rectifier-transformer": (
        "Rectifiers and transformers supplying controlled DC power to EW cells.",
        "Drives current efficiency, energy per pound copper, and tankhouse uptime.",
    ),
    "electrolyte-circulation-filter-heater": (
        "Electrolyte circulation loops with filtration and temperature control.",
        "Maintains purity and temperature for stable cathode quality in EW.",
    ),
    "additive-dosing-bleed-treatment": (
        "Additive dosing and bleed treatment controlling EW impurity levels.",
        "Manages cobalt, iron, and organic carryover within tankhouse specifications.",
    ),
    "wash-weigh-strap-station": (
        "Cathode wash, weigh, and strapping line preparing finished copper packages.",
        "Final production accounting step before shipment to smelters or customers.",
    ),
}


def slug(name: str) -> str:
    s = name.replace("&", "and")
    s = re.sub(r"[^a-zA-Z0-9/]+", " ", s)
    s = s.replace("/", "-").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def desc_html(l1: str, l2: str) -> str:
    return (
        f'<p class="equip-card__desc">'
        f'<span class="equip-card__desc-line">{l1}</span>'
        f'<span class="equip-card__desc-line">{l2}</span>'
        f"</p>"
    )


def main() -> None:
    text = PARTIAL.read_text(encoding="utf-8")
    names = re.findall(r'class="equip-card__name">([^<]+)</h4>', text)
    for name in names:
        s = slug(name)
        l1, l2 = DESCS[s]
        pattern = (
            rf'(<h4 class="equip-card__name">{re.escape(name)}</h4>.*?)'
            r'<p class="equip-card__desc">.*?</p>'
        )
        text, n = re.subn(pattern, r"\1" + desc_html(l1, l2), text, count=1, flags=re.S)
        if not n:
            raise SystemExit(f"Could not patch description for {name}")
    PARTIAL.write_text(text, encoding="utf-8")
    print(f"Patched {len(names)} equipment descriptions.")


if __name__ == "__main__":
    main()
