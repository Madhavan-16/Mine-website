/**
 * Portal micro-motion: one page-enter, section stagger, table focus.
 * Quiet enterprise motion — no ambient canvas. Respects prefers-reduced-motion.
 */
(function () {
  var reduce =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var body = document.body;
  if (!body || !body.classList.contains("layout-portal")) return;
  if (body.classList.contains("layout-landing")) return;

  function reveal() {
    document.documentElement.classList.remove("portal-motion-prep");
    document.documentElement.classList.add("portal-motion-ready");
  }

  function staggerSections() {
    if (reduce) return;
    var nodes = document.querySelectorAll("[data-portal-stagger]");
    nodes.forEach(function (shell, i) {
      shell.style.setProperty("--portal-stagger-i", String(Math.min(i, 8)));
      shell.classList.add("is-portal-staggered");
    });
  }

  function bindTableFocus() {
    document.querySelectorAll(".mine-table tbody tr").forEach(function (row) {
      if (!row.hasAttribute("tabindex")) row.setAttribute("tabindex", "0");
      row.addEventListener("focusin", function () {
        row.classList.add("is-focus-row");
      });
      row.addEventListener("focusout", function () {
        row.classList.remove("is-focus-row");
      });
    });
  }

  if (!reduce) {
    document.documentElement.classList.add("portal-motion-prep");
  }

  function boot() {
    staggerSections();
    bindTableFocus();
    if (reduce) {
      reveal();
      return;
    }
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(reveal);
    });
    window.setTimeout(reveal, 700);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
