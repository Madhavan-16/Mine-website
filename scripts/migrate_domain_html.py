"""One-off migration: embed open-pit copper domain HTML into MiNe templates."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path.home() / "Downloads" / "open_pit_copper_mining_domain_2026-04-24 (2) (1).html"


def scope_css(raw: str) -> str:
    lines = raw.split("\n")
    out: list[str] = []
    in_media = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("@media"):
            in_media = True
            out.append(line)
            continue
        if in_media and stripped == "}":
            out.append(line)
            in_media = False
            continue
        if stripped.startswith("@import") or stripped.startswith("@keyframes"):
            out.append(line)
            continue
        if stripped.startswith(":root"):
            out.append(".domain-knowledge-page {")
            inner = line.replace(":root", "").strip()
            if inner != "{":
                out.append(inner)
            continue
        if (
            stripped
            and not stripped.startswith("@")
            and not stripped.startswith("/*")
            and "{" in stripped
            and not stripped.startswith(".domain-knowledge-page")
        ):
            sel, rest = stripped.split("{", 1)
            sel = sel.strip()
            if sel == "*":
                sel = ".domain-knowledge-page, .domain-knowledge-page *"
            elif sel in ("html", "body"):
                sel = ".domain-knowledge-page"
            else:
                parts = [p.strip() for p in sel.split(",")]
                scoped = []
                for part in parts:
                    if part.startswith(".domain-knowledge-page"):
                        scoped.append(part)
                    else:
                        scoped.append(f".domain-knowledge-page {part}")
                sel = ", ".join(scoped)
            out.append(f"{sel} {{{rest}")
        else:
            out.append(line)
    return "\n".join(out)


PORTAL_OVERRIDES = """
/* Portal shell — full bleed; original FCX blue theme preserved */
.main:has(.domain-knowledge-page) {
  padding: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.domain-knowledge-page .sticky-nav {
  top: var(--portal-header-offset);
  z-index: 90;
}

.domain-knowledge-page thead th {
  top: calc(var(--portal-header-offset) + 48px);
}

.domain-knowledge-page .img-zoom-modal {
  z-index: 300;
}

.domain-knowledge-page .section {
  max-width: none;
  width: 100%;
  padding-left: clamp(20px, 3vw, 48px);
  padding-right: clamp(20px, 3vw, 48px);
}

.domain-knowledge-page .section-divider {
  width: 100%;
  padding-left: clamp(20px, 3vw, 48px);
  padding-right: clamp(20px, 3vw, 48px);
}

.domain-knowledge-page .hero-content {
  max-width: none;
  width: 100%;
  padding-left: clamp(20px, 3vw, 48px);
  padding-right: clamp(20px, 3vw, 48px);
}

.domain-knowledge-page .domain-cards {
  max-width: none;
  width: 100%;
}

.domain-knowledge-page .hero-footer {
  left: clamp(20px, 3vw, 48px);
  right: clamp(20px, 3vw, 48px);
}

.domain-knowledge-page .lifecycle-image-wrap,
.domain-knowledge-page .valuechain-image-wrap,
.domain-knowledge-page .digital-enable-image-wrap,
.domain-knowledge-page .service-map-image-wrap,
.domain-knowledge-page .pa-hierarchy-image-wrap {
  width: 100%;
  overflow-x: visible;
}

.domain-knowledge-page .lifecycle-image-wrap img,
.domain-knowledge-page .valuechain-image-wrap img,
.domain-knowledge-page .digital-enable-image-wrap img,
.domain-knowledge-page .service-map-image-wrap img,
.domain-knowledge-page .pa-hierarchy-image-wrap img {
  width: 100%;
  max-width: 100%;
  height: auto;
}
"""


JS = """(function () {
  "use strict";

  var root = document.querySelector(".domain-knowledge-page");
  if (!root) return;

  var links = root.querySelectorAll(".sticky-nav a");
  var sections = [];
  links.forEach(function (a) {
    var id = a.getAttribute("href");
    if (id && id.startsWith("#")) sections.push({ el: root.querySelector(id), link: a });
  });
  function onScroll() {
    var offset = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--portal-header-offset"), 10) || 80;
    var y = window.scrollY + offset + 48;
    var active = null;
    sections.forEach(function (s) { if (s.el && s.el.offsetTop <= y) active = s; });
    links.forEach(function (a) { a.classList.remove("active"); });
    if (active) active.link.classList.add("active");
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  var revealNodes = root.querySelectorAll(".reveal");
  if (revealNodes.length) {
    if (!("IntersectionObserver" in window)) {
      revealNodes.forEach(function (n) { n.classList.add("in"); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          e.target.classList.add("in");
          io.unobserve(e.target);
        });
      }, { threshold: 0.22, rootMargin: "0px 0px -8% 0px" });
      revealNodes.forEach(function (n) { io.observe(n); });
    }
  }

  var modal = document.getElementById("img-zoom-modal");
  var stage = document.getElementById("img-zoom-stage");
  var target = document.getElementById("img-zoom-target");
  var closeBtn = document.getElementById("img-zoom-close");
  var triggers = root.querySelectorAll(".zoomable-image");
  if (!modal || !stage || !target || !closeBtn || !triggers.length) return;

  function openZoom(src, alt) {
    target.classList.remove("is-boosted");
    target.style.width = "auto";
    target.src = src;
    target.alt = alt || "Full resolution infographic";
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    stage.scrollTop = 0;
    stage.scrollLeft = 0;
    target.onload = function () {
      var boosted = Math.max((target.naturalWidth || 0) * 2, target.naturalWidth || 0);
      if (boosted) {
        target.style.width = boosted + "px";
        target.classList.add("is-boosted");
      }
    };
  }

  function closeZoom() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  triggers.forEach(function (img) {
    img.addEventListener("click", function () {
      openZoom(img.currentSrc || img.src, img.alt);
    });
  });
  closeBtn.addEventListener("click", closeZoom);
  modal.addEventListener("click", function (e) { if (e.target === modal) closeZoom(); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal.classList.contains("is-open")) closeZoom();
  });
})();
"""


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    style_m = re.search(r"<style>(.*?)</style>", text, re.DOTALL)
    css = style_m.group(1) if style_m else ""
    body_m = re.search(r"<body>(.*?)</body>", text, re.DOTALL)
    body = body_m.group(1) if body_m else ""
    body = re.sub(r"<script>.*?</script>", "", body, flags=re.DOTALL).strip()

    replacements = {
        'src="/open-pit-copper-domain/lifecycle-image"': 'src="{{ url_for(\'main.open_pit_copper_domain_lifecycle_image\') }}"',
        'src="/open-pit-copper-domain/value-chain-image?v=6"': 'src="{{ url_for(\'main.open_pit_copper_domain_value_chain_image\') }}?v=6"',
        'src="/open-pit-copper-domain/digital-enablement-image?v=5"': 'src="{{ url_for(\'main.open_pit_copper_domain_digital_enablement_image\') }}?v=5"',
        'src="/open-pit-copper-domain/service-map-image?v=1"': 'src="{{ url_for(\'main.open_pit_copper_domain_service_map_image\') }}?v=1"',
        'src="/open-pit-copper-domain/measurement-hierarchy-image?v=3"': 'src="{{ url_for(\'main.open_pit_copper_domain_measurement_hierarchy_image\') }}?v=3"',
    }
    for old, new in replacements.items():
        body = body.replace(old, new)

    css_path = ROOT / "static/css/open-pit-copper-domain.css"
    css_path.write_text(scope_css(css) + PORTAL_OVERRIDES, encoding="utf-8")

    partial_path = ROOT / "templates/partials/open_pit_copper_domain_content.html"
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.write_text(body, encoding="utf-8")

    js_path = ROOT / "static/js/open-pit-copper-domain.js"
    js_path.write_text(JS, encoding="utf-8")

    print(f"Wrote {css_path} ({css_path.stat().st_size} bytes)")
    print(f"Wrote {partial_path} ({partial_path.stat().st_size} bytes)")
    print(f"Wrote {js_path}")


if __name__ == "__main__":
    main()
