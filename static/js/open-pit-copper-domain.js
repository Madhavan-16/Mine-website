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
  if (!modal || !stage || !target || !closeBtn) return;
  var triggers = root.querySelectorAll(".zoomable-image");

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

  function equipSlug(name) {
    return name
      .replace(/&/g, "and")
      .replace(/\//g, "-")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  var equipSection = root.querySelector(".equip-section");
  var equipBase = equipSection && equipSection.getAttribute("data-equip-image-base");
  var equipModal = document.getElementById("equip-detail-modal");
  var equipTitle = document.getElementById("equip-detail-title");
  var equipImg = document.getElementById("equip-detail-img");
  var equipDesc = document.getElementById("equip-detail-desc");
  var equipClose = document.getElementById("equip-detail-close");

  function closeEquipDetail() {
    if (!equipModal) return;
    equipModal.classList.remove("is-open");
    equipModal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function openEquipDetail(title, desc, src, alt) {
    if (!equipModal || !equipTitle || !equipImg || !equipDesc) return;
    equipTitle.textContent = title;
    if (desc && desc.indexOf("<") >= 0) {
      equipDesc.innerHTML = desc;
    } else {
      equipDesc.textContent = desc || "";
    }
    equipImg.onerror = function () {
      equipImg.onerror = null;
      equipImg.removeAttribute("src");
      equipImg.alt = "Photo unavailable";
    };
    equipImg.src = src;
    equipImg.alt = alt || title;
    equipModal.classList.add("is-open");
    equipModal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  if (equipBase && equipModal && equipClose) {
    equipClose.addEventListener("click", closeEquipDetail);
    equipModal.addEventListener("click", function (e) {
      if (e.target === equipModal) closeEquipDetail();
    });
    root.querySelectorAll(".equip-card__name").forEach(function (titleEl) {
      var card = titleEl.closest(".equip-card");
      if (!card) return;
      var title = titleEl.textContent.trim();
      var descEl = card.querySelector(".equip-card__desc");
      var desc = descEl ? descEl.innerHTML.trim() : "";
      titleEl.setAttribute("tabindex", "0");
      titleEl.setAttribute("role", "button");
      titleEl.setAttribute("aria-label", "Open reference photo for " + title);
      function openEquip() {
        openEquipDetail(
          title,
          desc,
          equipBase + "/" + equipSlug(title) + ".jpg",
          "Reference photo: " + title
        );
      }
      titleEl.addEventListener("click", function (e) {
        e.preventDefault();
        openEquip();
      });
      titleEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openEquip();
        }
      });
    });
  }

  closeBtn.addEventListener("click", closeZoom);
  modal.addEventListener("click", function (e) { if (e.target === modal) closeZoom(); });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (equipModal && equipModal.classList.contains("is-open")) closeEquipDetail();
    else if (modal.classList.contains("is-open")) closeZoom();
  });
})();
