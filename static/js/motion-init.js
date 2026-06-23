/**
 * Scroll / enter animations via AOS (global). Dashboard adds GSAP + ScrollTrigger for timeline depth.
 * Homepage uses the Motion package (Framer Motion’s JS engine) via `landing-motion.bundle.js`.
 */
(function () {
  function boot() {
    if (typeof AOS === "undefined") return;

    AOS.init({
      once: true,
      duration: 520,
      easing: "ease-out-cubic",
      offset: 32,
      delay: 0,
      anchorPlacement: "top-bottom",
      disable: function () {
        var body = document.body;
        if (body && body.classList.contains("layout-landing")) return true;
        return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      },
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.addEventListener(
    "resize",
    function () {
      if (typeof AOS !== "undefined" && AOS.refresh) {
        AOS.refresh();
      }
    },
    { passive: true }
  );
})();
