"""Extract business/technical benefits from SoW PDFs."""
import re
from pathlib import Path

from pypdf import PdfReader

PDF_DIR = Path(r"C:\Users\2000137443\Desktop\Project List")

MAPPING = [
    ("2024 Hexaware Continuous Delivery – Core Team", "2024 Hexaware Continious Delivery_Core Team SoW v1.0.docx.pdf"),
    ("PTFI T4V – Data & Reports Rewiring/Repointing for S/4HANA and HR Suite", "JK2400088-001-000-000_Hexaware_Technologies_Inc.pdf"),
    ("NOLA Execution Improvements", "NO2400053_001_000_000 - Hexaware Technologies Inc..pdf"),
    ("2025–2026 SIMS Extension", "Hexaware-SOWSIMS_Extension_2026.pdf"),
    ("PTFI Strategic Planning BI Development", "NO2500108_001_000_000 - Hexaware Technologies Inc..pdf"),
    ("Snowflake OpenFlow Migration", "SnowflakeOpenflowSOWv01.docx.pdf"),
    ("2026 SAP CPI Development & Support", "2026HexawareSAPCPISOWv1.docx.pdf"),
    ("2026 Hexaware Flexi Team", "2026HexawareFlexiSOWV10.pdf"),
    ("2026 GSC / Inventory Optimization", "bmichele_639016124664490227_bmichele_639016124202162599_2026Hexaware_GSC_SOWJantoDec2026.docx.pdf"),
]

BUSINESS_PATTERNS = [
    r"business\s+benefits?",
    r"benefits?\s+to\s+(?:the\s+)?(?:client|customer|freeport|fmi|ptfi)",
    r"expected\s+business\s+benefits?",
    r"business\s+value",
]
TECH_PATTERNS = [
    r"technical\s+benefits?",
    r"tech(?:nical)?\.?\s+benefits?",
    r"technology\s+benefits?",
    r"expected\s+technical\s+benefits?",
]


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def find_section(text: str, patterns: list[str], stop_patterns: list[str]) -> str | None:
    low = text.lower()
    start = -1
    for pat in patterns:
        m = re.search(pat, low, re.I)
        if m:
            start = m.end()
            break
    if start < 0:
        return None
    rest = text[start:]
    end = len(rest)
    for sp in stop_patterns:
        m = re.search(sp, rest, re.I)
        if m and m.start() > 80:
            end = min(end, m.start())
    chunk = rest[:end].strip()
    chunk = re.sub(r"\s+", " ", chunk)
    return chunk[:2500] if chunk else None


def bulletize(text: str) -> str:
    if not text:
        return ""
    # split on bullet-like markers or numbered lists
    parts = re.split(r"(?:\n|•|●|▪|–\s+|\d+[\.\)]\s+)", text)
    lines = []
    for p in parts:
        p = p.strip(" -–—\t")
        if len(p) > 15 and not re.match(r"^(page|confidential|table of)", p, re.I):
            lines.append(p)
    if len(lines) >= 2:
        return "\n".join(lines[:12])
    # sentence split fallback
    sents = re.split(r"(?<=[.!?])\s+", text)
    return "\n".join(s.strip() for s in sents if len(s.strip()) > 20)[:12]


for title, pdf_name in MAPPING:
    path = PDF_DIR / pdf_name
    print("=" * 80)
    print(title)
    print(pdf_name)
    if not path.is_file():
        print("MISSING PDF")
        continue
    text = read_pdf(path)
    stops = [
        r"technical\s+benefit",
        r"business\s+benefit",
        r"scope\s+of\s+(?:work|services)",
        r"deliverables?",
        r"assumptions?",
        r"acceptance",
        r"payment",
        r"invoic",
        r"termination",
        r"appendix",
        r"exhibit",
    ]
    biz = find_section(text, BUSINESS_PATTERNS, stops)
    tech = find_section(text, TECH_PATTERNS, stops)
    print("\n--- BUSINESS ---")
    print(biz or "(not found)")
    print("\n--- TECH ---")
    print(tech or "(not found)")
    # also grep raw mentions
    for kw in ["benefit", "Benefit", "BENEFIT"]:
        if kw in text:
            for line in text.splitlines():
                if "benefit" in line.lower() and len(line.strip()) > 10:
                    print("LINE:", line.strip()[:120])
