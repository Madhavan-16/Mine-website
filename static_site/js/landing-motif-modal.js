/**
 * Landing hero value-chain cards — in-page insight modals (no navigation).
 */
(function () {
  var modal = document.getElementById("landing-motif-modal");
  if (!modal) return;

  var dialog = modal.querySelector(".landing-motif-modal__dialog");
  var panels = Array.from(modal.querySelectorAll("[data-motif-panel]"));
  var openers = document.querySelectorAll("[data-motif-open]");
  var closers = modal.querySelectorAll("[data-motif-close]");
  var lastFocus = null;

  function panelFor(slug) {
    return modal.querySelector('[data-motif-panel="' + slug + '"]');
  }

  function setTitleId(slug) {
    var title = panelFor(slug) && panelFor(slug).querySelector(".landing-motif-modal__title");
    if (title && dialog) {
      dialog.setAttribute("aria-labelledby", title.id || "landing-motif-modal-title");
    }
  }

  function openMotif(slug) {
    var panel = panelFor(slug);
    if (!panel) return;

    lastFocus = document.activeElement;

    panels.forEach(function (p) {
      p.hidden = p.getAttribute("data-motif-panel") !== slug;
    });

    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("is-open");
    document.body.classList.add("landing-motif-modal-open");
    setTitleId(slug);

    window.requestAnimationFrame(function () {
      if (dialog) dialog.focus();
    });
  }

  function closeMotif() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("landing-motif-modal-open");
    panels.forEach(function (p) {
      p.hidden = true;
    });

    window.setTimeout(function () {
      modal.hidden = true;
      activeSlug = null;
      if (lastFocus && typeof lastFocus.focus === "function") {
        lastFocus.focus();
      }
    }, 220);
  }

  openers.forEach(function (btn) {
    btn.addEventListener("click", function () {
      openMotif(btn.getAttribute("data-motif-open"));
    });
  });

  closers.forEach(function (el) {
    el.addEventListener("click", closeMotif);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal.classList.contains("is-open")) {
      e.preventDefault();
      closeMotif();
    }
  });
})();
