/**
 * Click-to-zoom for .zoomable-image (2× display, scroll to inspect).
 * Works on any page that includes #img-zoom-modal markup.
 */
(function () {
  "use strict";

  var modal = document.getElementById("img-zoom-modal");
  var stage = document.getElementById("img-zoom-stage");
  var target = document.getElementById("img-zoom-target");
  var closeBtn = document.getElementById("img-zoom-close");
  if (!modal || !stage || !target || !closeBtn) return;

  var triggers = document.querySelectorAll(".zoomable-image");
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
      var natural = target.naturalWidth || 0;
      // Domain Knowledge style: 2× of natural for readable body text when scrolling.
      var boosted = natural ? Math.max(natural * 2, natural) : 0;
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
    if (!img.hasAttribute("tabindex")) img.setAttribute("tabindex", "0");
    if (!img.getAttribute("role")) img.setAttribute("role", "button");
    img.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openZoom(img.currentSrc || img.src, img.alt);
      }
    });
  });

  closeBtn.addEventListener("click", closeZoom);
  modal.addEventListener("click", function (e) {
    if (e.target === modal) closeZoom();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal.classList.contains("is-open")) closeZoom();
  });
})();
