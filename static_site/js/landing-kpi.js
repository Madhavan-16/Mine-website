/**
 * Portal stats KPI strip: count-up on scroll (+ stagger).
 * Reduced motion → final numbers immediately (no scroll wait).
 */
(function () {
  var root = document.getElementById("landing-kpi-scope");
  if (!root) return;

  var reduce =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function parseTarget(el) {
    var raw = Number.parseInt(el.getAttribute("data-kpi-target"), 10);
    return Number.isNaN(raw) ? 0 : raw;
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function formatInt(n) {
    return typeof n.toLocaleString === "function"
      ? n.toLocaleString("en-US", { maximumFractionDigits: 0 })
      : String(n);
  }

  function runCount(el, target, durationMs, startDelayMs) {
    el.textContent = "0";

    window.setTimeout(function () {
      var startTs = null;
      function frame(ts) {
        if (startTs === null) startTs = ts;
        var p = Math.min(1, (ts - startTs) / durationMs);
        var cur = Math.round(easeOutCubic(p) * target);
        el.textContent = formatInt(cur);
        if (p < 1) window.requestAnimationFrame(frame);
      }
      window.requestAnimationFrame(frame);
    }, startDelayMs || 0);
  }

  function reveal() {
    var nodes = Array.prototype.slice.call(root.querySelectorAll(".landing-kpi-value[data-kpi-target]"));

    if (reduce) {
      nodes.forEach(function (el) {
        el.textContent = formatInt(parseTarget(el));
      });
      root.classList.add("landing-kpi-scope--revealed");
      return;
    }

    nodes.forEach(function (el, i) {
      runCount(el, parseTarget(el), 980 + Math.min(i, 6) * 70, i * 85);
    });
    root.classList.add("landing-kpi-scope--revealed");
  }

  if (reduce) {
    reveal();
    return;
  }

  if ("IntersectionObserver" in window) {
    var obs = new IntersectionObserver(
      function (entries, o) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            o.disconnect();
            reveal();
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 }
    );
    obs.observe(root);
  } else {
    reveal();
  }
})();
