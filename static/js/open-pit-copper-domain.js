(function () {
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

  function prepInfographicBars(scope) {
    var host = scope || root;
    host.querySelectorAll(".signal-fill[data-w]").forEach(function (bar) {
      var w = bar.getAttribute("data-w");
      if (w) bar.style.setProperty("--bar-w", w + "%");
    });
  }

  function activateReveal(node) {
    if (!node || node.classList.contains("in")) return;
    node.classList.add("in");
    node.querySelectorAll(".signal-fill[data-w]").forEach(function (bar) {
      bar.classList.add("is-live");
    });
  }

  prepInfographicBars(root);

  var revealNodes = root.querySelectorAll(".reveal");
  if (revealNodes.length) {
    var reducedMotion = false;
    try {
      reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {}

    if (reducedMotion || !("IntersectionObserver" in window)) {
      revealNodes.forEach(function (n) { activateReveal(n); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          activateReveal(e.target);
          io.unobserve(e.target);
        });
      }, { threshold: 0.12, rootMargin: "0px 0px 0px 0px" });

      revealNodes.forEach(function (n) {
        var rect = n.getBoundingClientRect();
        if (rect.top < window.innerHeight * 0.92 && rect.bottom > 0) {
          activateReveal(n);
        } else {
          io.observe(n);
        }
      });
    }
  }

  var modal = document.getElementById("img-zoom-modal");
  var stage = document.getElementById("img-zoom-stage");
  var target = document.getElementById("img-zoom-target");
  var closeBtn = document.getElementById("img-zoom-close");
  var triggers = root.querySelectorAll(".zoomable-image");
  if (!modal || !stage || !target || !closeBtn) return;
  if (!triggers.length) return;

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
