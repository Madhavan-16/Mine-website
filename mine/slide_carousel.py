"""HTML carousel viewer for rasterized slide PNG previews."""

from __future__ import annotations

from html import escape


def render_slide_carousel_html(
    *,
    deck_title: str,
    slide_urls: list[str],
) -> str:
    if not slide_urls:
        return ""

    title = escape((deck_title or "Presentation").strip() or "Presentation")
    total = len(slide_urls)
    slides_js = ",\n    ".join(escape(u) for u in slide_urls)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} · slide preview</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1220;
      --panel: #111827;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --border: #1f2937;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr auto;
    }}
    header {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }}
    header h1 {{
      margin: 0;
      font-size: 0.95rem;
      font-weight: 600;
    }}
    header p {{
      margin: 4px 0 0;
      font-size: 11px;
      color: var(--muted);
    }}
    .stage {{
      display: grid;
      place-items: center;
      padding: 12px;
      overflow: auto;
      background:
        radial-gradient(ellipse at top, rgba(56, 189, 248, 0.08), transparent 55%),
        var(--bg);
    }}
    .slide-frame {{
      width: min(100%, 960px);
      background: #000;
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
      overflow: hidden;
    }}
    .slide-frame img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 14px;
      border-top: 1px solid var(--border);
      background: var(--panel);
    }}
    .toolbar button {{
      appearance: none;
      border: 1px solid var(--border);
      background: #1e293b;
      color: var(--text);
      border-radius: 8px;
      padding: 8px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .toolbar button:hover:not(:disabled) {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .toolbar button:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}
    .counter {{
      font-size: 13px;
      font-variant-numeric: tabular-nums;
      color: var(--muted);
    }}
    .dots {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      justify-content: center;
      max-width: 50%;
    }}
    .dot {{
      width: 7px;
      height: 7px;
      border-radius: 999px;
      border: none;
      padding: 0;
      background: #334155;
      cursor: pointer;
    }}
    .dot.is-active {{ background: var(--accent); }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p>Visual slide preview — text, images, and icons as rendered on the slide.</p>
  </header>
  <main class="stage">
    <div class="slide-frame">
      <img id="slide-img" alt="Slide" src="{escape(slide_urls[0])}"/>
    </div>
  </main>
  <footer class="toolbar">
    <button type="button" id="prev-btn" aria-label="Previous slide">← Prev</button>
    <div class="dots" id="dots" aria-hidden="true"></div>
    <span class="counter" id="counter" aria-live="polite">1 / {total}</span>
    <button type="button" id="next-btn" aria-label="Next slide">Next →</button>
  </footer>
  <script>
    const slides = [
    {slides_js}
    ];
    let index = 0;
    const img = document.getElementById("slide-img");
    const counter = document.getElementById("counter");
    const prevBtn = document.getElementById("prev-btn");
    const nextBtn = document.getElementById("next-btn");
    const dots = document.getElementById("dots");

    slides.forEach((_, i) => {{
      const b = document.createElement("button");
      b.type = "button";
      b.className = "dot" + (i === 0 ? " is-active" : "");
      b.title = "Slide " + (i + 1);
      b.addEventListener("click", () => show(i));
      dots.appendChild(b);
    }});

    function show(i) {{
      index = Math.max(0, Math.min(slides.length - 1, i));
      img.src = slides[index];
      counter.textContent = (index + 1) + " / " + slides.length;
      prevBtn.disabled = index === 0;
      nextBtn.disabled = index === slides.length - 1;
      dots.querySelectorAll(".dot").forEach((d, j) => d.classList.toggle("is-active", j === index));
    }}

    prevBtn.addEventListener("click", () => show(index - 1));
    nextBtn.addEventListener("click", () => show(index + 1));
    document.addEventListener("keydown", (e) => {{
      if (e.key === "ArrowLeft") show(index - 1);
      if (e.key === "ArrowRight") show(index + 1);
    }});
    show(0);
  </script>
</body>
</html>"""
